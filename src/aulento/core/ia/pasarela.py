"""La pasarela de IA de una cuenta: resuelve su proveedor, su clave y su modelo, y registra el consumo."""

import dataclasses
import logging
import time
from typing import Any

from aulento.core.almacenes import ServicioDeCuenta
from aulento.core.eventos import IA_ANTES, IA_CONSUMO, bus
from aulento.core.gemini_gateway import (
    MENSAJE_CLAVE_ILEGIBLE,
    SECRETOS_DE_CLAVES,
    GeminiGateway,
    descripcion_de_clave,
)
from aulento.core.ia.anthropic import ProveedorAnthropic
from aulento.core.ia.base import Proveedor
from aulento.core.ia.gemini import (
    NIVEL_GRATUITO,
    NIVEL_PAGO,
    Intento,
    ProveedorGemini,
)
from aulento.core.ia.openai import ProveedorOpenAI
from aulento.core.ia.tarifas import costo_de_un_error
from aulento.core.ia.tipos import (
    ACCION_DE_LA_CAPACIDAD,
    ANTHROPIC,
    CAPACIDADES,
    EMBEDDINGS,
    GEMINI,
    NOMBRE_VISIBLE,
    OPENAI,
    PROVEEDORES,
    CapacidadNoSoportada,
    Embedding,
    FaltaClaveDeIA,
    IANoDisponibleError,
    Pedido,
    Respuesta,
    mensaje_falta_clave,
)
from aulento.core.secretos import (
    AJUSTE_ANTHROPIC_MODELO,
    AJUSTE_IA_PROVEEDOR_ACTIVO,
    AJUSTE_OPENAI_MODELO,
    MENSAJE_CLAVE_MAESTRA_INVALIDA,
    SECRETO_ANTHROPIC_CLAVE,
    SECRETO_GEMINI_CLAVE_GRATUITA,
    SECRETO_GEMINI_CLAVE_PAGA,
    SECRETO_OPENAI_CLAVE,
    ClaveMaestraInvalida,
    SecretoIlegible,
)
from aulento.db.cuenta import exigir_repositorio_de_cuenta
from aulento.db.roadmap_repository import registrar_consumo_de_ia

logger = logging.getLogger(__name__)

# Cuando el proveedor activo no tiene la capacidad que pide una operación, se prueba con los demás en este orden
# y atiende el primero que la tiene y tiene clave cargada. Gemini va primero porque ofrece las cuatro.
ORDEN_DE_REEMPLAZO = (GEMINI, OPENAI, ANTHROPIC)

SECRETO_DE_LA_CLAVE = {ANTHROPIC: SECRETO_ANTHROPIC_CLAVE, OPENAI: SECRETO_OPENAI_CLAVE}
AJUSTE_DEL_MODELO = {ANTHROPIC: AJUSTE_ANTHROPIC_MODELO, OPENAI: AJUSTE_OPENAI_MODELO}
SECRETO_DEL_NIVEL = {NIVEL_GRATUITO: SECRETO_GEMINI_CLAVE_GRATUITA, NIVEL_PAGO: SECRETO_GEMINI_CLAVE_PAGA}

# Con qué nivel se anota el consumo de un proveedor que no distingue clave gratuita de paga
NIVEL_SIN_DISTINCION = "paid"
ENDPOINT_DE_EMBEDDINGS = "embeddings"
ENDPOINT_DE_PRUEBA = "prueba_de_conexion"

ADAPTADORES: dict[str, Proveedor] = {GEMINI: ProveedorGemini(), ANTHROPIC: ProveedorAnthropic(), OPENAI: ProveedorOpenAI()}


def exigir_proveedor(proveedor: str) -> str:
    """Devuelve el nombre del proveedor si es uno de los tres; si no, levanta `ValueError`."""
    if proveedor not in PROVEEDORES:
        raise ValueError(f"Proveedor de IA desconocido ({proveedor!r}): los disponibles son {', '.join(PROVEEDORES)}.")
    return proveedor


class PasarelaDeIA(ServicioDeCuenta):
    """Toda llamada a un modelo de IA de una cuenta: con su proveedor activo, su clave y su modelo.

    Se arma con `PasarelaDeIA(conn, user_id)`, o con `de_repositorio` / `con_conexion_propia` si no hay una
    conexión a mano. Las claves, el nivel y el modelo de Gemini son los de `GeminiGateway`; los de Anthropic y
    OpenAI viven en el almacén cifrado y los ajustes de la cuenta.
    """

    # --- Configuración de la cuenta ---

    def _gemini(self) -> GeminiGateway:
        if self._conn is not None:
            return GeminiGateway(self._conn, self.user_id)
        return GeminiGateway.con_conexion_propia(self.user_id, self._db_path)

    def proveedor_activo(self) -> str:
        """El proveedor que eligió la cuenta; si no eligió ninguno, Gemini."""
        with self._almacenes() as (_, ajustes):
            guardado = ajustes.leer(AJUSTE_IA_PROVEEDOR_ACTIVO)
        return guardado if guardado in PROVEEDORES else GEMINI

    def fijar_proveedor(self, proveedor: str) -> None:
        """Elige el proveedor activo de la cuenta."""
        with self._almacenes() as (_, ajustes):
            ajustes.guardar(AJUSTE_IA_PROVEEDOR_ACTIVO, exigir_proveedor(proveedor))

    def guardar_clave(self, proveedor: str, clave: str, nivel: str = NIVEL_GRATUITO) -> None:
        """Guarda cifrada la clave de la cuenta para ese proveedor. `nivel` (`free` o `paid`) solo cuenta en Gemini."""
        exigir_proveedor(proveedor)
        if not isinstance(clave, str) or not clave.strip():
            raise ValueError("La clave no puede estar vacía.")
        if proveedor == GEMINI:
            if nivel not in SECRETO_DEL_NIVEL:
                raise ValueError(f"Nivel de clave de Gemini desconocido ({nivel!r}): es `free` o `paid`.")
            self._gemini().save_keys_config(**{"free_key" if nivel == NIVEL_GRATUITO else "paid_key": clave})
            return
        with self._almacenes() as (secretos, _):
            secretos.guardar(SECRETO_DE_LA_CLAVE[proveedor], clave.strip())

    def quitar_clave(self, proveedor: str, nivel: str | None = None) -> bool:
        """Borra la clave de ese proveedor; devuelve si había alguna. En Gemini, sin `nivel`, borra las dos."""
        exigir_proveedor(proveedor)
        if proveedor == GEMINI:
            if nivel is not None and nivel not in SECRETO_DEL_NIVEL:
                raise ValueError(f"Nivel de clave de Gemini desconocido ({nivel!r}): es `free` o `paid`.")
            nombres = SECRETOS_DE_CLAVES if nivel is None else (SECRETO_DEL_NIVEL[nivel],)
        else:
            nombres = (SECRETO_DE_LA_CLAVE[proveedor],)
        with self._almacenes() as (secretos, _):
            borradas = [secretos.borrar(nombre) for nombre in nombres]
        return any(borradas)

    def fijar_modelo(self, proveedor: str, modelo: str) -> None:
        """Guarda el modelo que la cuenta usa con ese proveedor: uno de la lista o uno escrito a mano."""
        exigir_proveedor(proveedor)
        if not isinstance(modelo, str) or not modelo.strip():
            raise ValueError("El modelo no puede estar vacío.")
        if proveedor == GEMINI:
            self._gemini().save_model(modelo)
            return
        with self._almacenes() as (_, ajustes):
            ajustes.guardar(AJUSTE_DEL_MODELO[proveedor], modelo.strip())

    def modelo_de(self, proveedor: str) -> str | None:
        """El modelo de la cuenta para ese proveedor: el que eligió o el predeterminado; `None` si no hay ninguno."""
        exigir_proveedor(proveedor)
        if proveedor == GEMINI:
            return self._gemini().resolve_model()
        with self._almacenes() as (_, ajustes):
            guardado = ajustes.leer(AJUSTE_DEL_MODELO[proveedor])
        if isinstance(guardado, str) and guardado.strip():
            return guardado.strip()
        return ADAPTADORES[proveedor].modelo_por_defecto

    def _clave_de(self, proveedor: str) -> str | None:
        """La clave con la que sale un pedido suelto a ese proveedor; en Gemini, la del nivel activo."""
        if proveedor == GEMINI:
            return self._gemini().get_active_api_key()
        with self._almacenes() as (secretos, _):
            return secretos.leer(SECRETO_DE_LA_CLAVE[proveedor])

    def _tiene_clave(self, proveedor: str) -> bool:
        nombres = SECRETOS_DE_CLAVES if proveedor == GEMINI else (SECRETO_DE_LA_CLAVE[proveedor],)
        with self._almacenes() as (secretos, _):
            return any(secretos.tiene(nombre) for nombre in nombres)

    def _exigir_clave(self, proveedor: str) -> str:
        clave = self._clave_de(proveedor)
        if not clave:
            raise FaltaClaveDeIA(mensaje_falta_clave(proveedor), proveedor=proveedor)
        return clave

    def capacidades(self) -> list[str]:
        """Lo que sabe hacer el proveedor activo de la cuenta."""
        return self._capacidades_de(self.proveedor_activo())

    def _capacidades_de(self, proveedor: str) -> list[str]:
        return [capacidad for capacidad in CAPACIDADES if capacidad in ADAPTADORES[proveedor].capacidades]

    def estado(self) -> dict[str, Any]:
        """El proveedor activo y, de cada proveedor, si tiene clave, su pista, su modelo y lo que sabe hacer.

        De una clave se informa, a lo sumo, sus últimos cuatro caracteres. Una clave guardada que no se puede
        descifrar figura como cargada, sin pista y con el aviso que corresponde.
        """
        activo = self.proveedor_activo()
        de_gemini = self._gemini().get_status()
        proveedores: dict[str, dict[str, Any]] = {}
        for proveedor in PROVEEDORES:
            adaptador = ADAPTADORES[proveedor]
            if proveedor == GEMINI:
                la_paga = de_gemini.has_paid_key and (de_gemini.active_tier == NIVEL_PAGO or not de_gemini.has_free_key)
                datos: dict[str, Any] = {
                    "tiene_clave": de_gemini.has_free_key or de_gemini.has_paid_key,
                    "clave": de_gemini.paid_key_masked if la_paga else de_gemini.free_key_masked,
                    "error_de_clave": de_gemini.paid_key_error if la_paga else de_gemini.free_key_error,
                    "modelo": de_gemini.active_model,
                    "nivel_activo": de_gemini.active_tier,
                    "clave_gratuita": de_gemini.free_key_masked,
                    "clave_paga": de_gemini.paid_key_masked,
                }
            else:
                tiene, pista, error = self._pista_de(SECRETO_DE_LA_CLAVE[proveedor])
                datos = {"tiene_clave": tiene, "clave": pista, "error_de_clave": error, "modelo": self.modelo_de(proveedor)}
            proveedores[proveedor] = {
                "nombre": NOMBRE_VISIBLE[proveedor],
                "activo": proveedor == activo,
                **datos,
                "capacidades": self._capacidades_de(proveedor),
                "modelos_sugeridos": list(adaptador.modelos_sugeridos),
            }
        return {"proveedor_activo": activo, "capacidades": self._capacidades_de(activo), "proveedores": proveedores}

    def _pista_de(self, secreto: str) -> tuple[bool, str | None, str | None]:
        """(está cargada, pista, aviso si no se puede leer) de una clave guardada."""
        with self._almacenes() as (secretos, _):
            if not secretos.tiene(secreto):
                return False, None, None
            try:
                return True, descripcion_de_clave(secretos.pista(secreto)), None
            except SecretoIlegible:
                return True, None, MENSAJE_CLAVE_ILEGIBLE
            except ClaveMaestraInvalida:
                return True, None, MENSAJE_CLAVE_MAESTRA_INVALIDA

    # --- Llamadas ---

    def _quien_atiende(self, capacidad: str) -> tuple[str, bool]:
        """(proveedor, por_capacidad): quién atiende una operación que necesita esa capacidad.

        El activo, si la tiene. Si no, el primero de `ORDEN_DE_REEMPLAZO` que la tiene y tiene clave cargada;
        si no hay ninguno levanta `CapacidadNoSoportada` diciendo qué falta y quién la ofrece.
        """
        activo = self.proveedor_activo()
        if capacidad in ADAPTADORES[activo].capacidades:
            return activo, False
        la_ofrecen = tuple(p for p in ORDEN_DE_REEMPLAZO if capacidad in ADAPTADORES[p].capacidades)
        for proveedor in la_ofrecen:
            if self._tiene_clave(proveedor):
                return proveedor, True
        quienes = " o ".join(NOMBRE_VISIBLE[p] for p in la_ofrecen)
        raise CapacidadNoSoportada(
            f"{NOMBRE_VISIBLE[activo]}, tu proveedor de IA activo, no puede {ACCION_DE_LA_CAPACIDAD[capacidad]}. "
            f"Esa capacidad la ofrece {quienes}: cargá su clave en Configuración para usarla.",
            capacidad=capacidad,
            quienes_la_ofrecen=la_ofrecen,
            proveedor=activo,
        )

    def generar(self, pedido: Pedido, endpoint_tipo: str = "generic", repo: Any | None = None) -> Respuesta:
        """Atiende el pedido con el proveedor, la clave y el modelo de la cuenta, y anota el consumo a su nombre.

        `repo`, si se pasa, es el repositorio de rutas de la misma cuenta. Levanta `FaltaClaveDeIA` si el proveedor
        que atiende no tiene clave, `CapacidadNoSoportada` si ninguno con clave puede con el pedido, y el error
        propio de cada falla del proveedor (`ClaveRechazada`, `CuotaAgotada`, `ModeloInexistente`,
        `RespuestaRechazada`...), todos `IANoDisponibleError`.
        """
        self._exigir_repositorio_propio(repo)
        proveedor, por_capacidad = self._quien_atiende(pedido.capacidad)
        # Una extensión puede frenar la llamada antes de que llegue al proveedor (por ejemplo, sin saldo)
        bus.verificar(IA_ANTES, user_id=self.user_id, proveedor=proveedor, endpoint_tipo=endpoint_tipo)
        if proveedor == GEMINI:
            respuesta = self._generar_con_gemini(pedido, endpoint_tipo, repo)
        else:
            respuesta = self._generar_con(proveedor, pedido, endpoint_tipo, repo)
        return dataclasses.replace(respuesta, por_capacidad=por_capacidad)

    def _generar_con_gemini(self, pedido: Pedido, endpoint_tipo: str, repo: Any | None) -> Respuesta:
        """Gemini conserva la conmutación gratuita → paga ante un límite de cuota y la rotación de modelos."""
        gemini = self._gemini()
        claves = gemini.claves_en_orden()
        if not claves:
            raise FaltaClaveDeIA(mensaje_falta_clave(GEMINI), proveedor=GEMINI)

        def anotar(intento: Intento) -> None:
            if intento.estado is None:
                return  # el pedido no llegó al proveedor
            self._anotar(
                repo,
                proveedor=GEMINI,
                modelo=intento.modelo,
                endpoint_tipo=endpoint_tipo,
                nivel=intento.nivel,
                tokens_entrada=intento.tokens_entrada,
                tokens_salida=intento.tokens_salida,
                tokens_totales=intento.tokens_totales,
                costo_usd=intento.costo_usd,
                estado=intento.estado,
                latencia_ms=intento.latencia_ms,
            )

        respuesta, _ = ADAPTADORES[GEMINI].generar_con_conmutacion(
            ProveedorGemini.cuerpo(pedido), claves, gemini.modelos_candidatos(), pedido.timeout, anotar
        )
        return respuesta

    def _generar_con(self, proveedor: str, pedido: Pedido, endpoint_tipo: str, repo: Any | None) -> Respuesta:
        clave = self._exigir_clave(proveedor)
        modelo = self.modelo_de(proveedor)
        try:
            respuesta = ADAPTADORES[proveedor].generar(pedido, clave, modelo)
        except IANoDisponibleError as error:
            self._anotar_error(repo, error, proveedor, modelo, endpoint_tipo)
            raise
        self._anotar_respuesta(repo, respuesta, endpoint_tipo)
        return respuesta

    def embeber(self, texto: str, tarea: str = "documento") -> Embedding:
        """El embedding del texto con el proveedor de la cuenta que sabe calcularlos; anota la llamada."""
        proveedor, por_capacidad = self._quien_atiende(EMBEDDINGS)
        # Como en `generar`: una extensión puede frenar la llamada antes de que llegue al proveedor (051, R10)
        bus.verificar(IA_ANTES, user_id=self.user_id, proveedor=proveedor, endpoint_tipo=ENDPOINT_DE_EMBEDDINGS)
        if proveedor == GEMINI:
            gemini = self._gemini()
            paga = gemini.resolve_paid_key()
            clave, nivel = (paga, NIVEL_PAGO) if paga else (gemini.resolve_free_key(), NIVEL_GRATUITO)
        else:
            clave, nivel = self._clave_de(proveedor), NIVEL_SIN_DISTINCION
        if not clave:
            raise FaltaClaveDeIA(mensaje_falta_clave(proveedor), proveedor=proveedor)

        inicio = time.perf_counter()
        try:
            vector, modelo = ADAPTADORES[proveedor].embeber(texto, clave, tarea=tarea)
        except IANoDisponibleError as error:
            self._anotar_error(None, error, proveedor, error.modelo, ENDPOINT_DE_EMBEDDINGS, nivel)
            raise
        self._anotar(
            None,
            proveedor=proveedor,
            modelo=modelo,
            endpoint_tipo=ENDPOINT_DE_EMBEDDINGS,
            nivel=nivel,
            tokens_entrada=0,
            tokens_salida=0,
            tokens_totales=0,
            costo_usd=None,
            estado=200,
            latencia_ms=(time.perf_counter() - inicio) * 1000.0,
        )
        return Embedding(vector=vector, modelo=modelo, proveedor=proveedor, por_capacidad=por_capacidad)

    def embeddings_de_la_cuenta(self) -> tuple[str, str] | None:
        """(proveedor, modelo) con los que hoy se calcularía un embedding de la cuenta, sin llamar a nadie.

        `None` si ningún proveedor de la cuenta que los ofrezca tiene clave cargada.
        """
        try:
            proveedor, _ = self._quien_atiende(EMBEDDINGS)
        except CapacidadNoSoportada:
            return None
        modelo = ADAPTADORES[proveedor].modelo_de_embeddings
        return (proveedor, modelo) if modelo and self._tiene_clave(proveedor) else None

    def modelos(self, proveedor: str) -> list[str]:
        """Los modelos que el proveedor ofrece a la clave de la cuenta, pedidos al proveedor en el momento."""
        exigir_proveedor(proveedor)
        return ADAPTADORES[proveedor].modelos(self._exigir_clave(proveedor))

    def probar(self, proveedor: str) -> dict[str, Any]:
        """Prueba la clave y el modelo de la cuenta con un pedido mínimo; no levanta por una falla del proveedor.

        Devuelve `{"ok", "proveedor", "modelo", "mensaje", "latencia_ms"}`. La prueba queda anotada en el consumo.
        """
        exigir_proveedor(proveedor)
        modelo = self.modelo_de(proveedor)
        nivel = NIVEL_SIN_DISTINCION
        try:
            if proveedor == GEMINI:
                claves = self._gemini().claves_en_orden()
                if not claves:
                    raise FaltaClaveDeIA(mensaje_falta_clave(GEMINI), proveedor=GEMINI)
                nivel, clave = claves[0]
            else:
                clave = self._exigir_clave(proveedor)
            respuesta = ADAPTADORES[proveedor].probar(clave, modelo)
        except IANoDisponibleError as error:
            self._anotar_error(None, error, proveedor, modelo, ENDPOINT_DE_PRUEBA, nivel)
            return {"ok": False, "proveedor": proveedor, "modelo": modelo, "mensaje": str(error), "latencia_ms": None}
        self._anotar_respuesta(None, respuesta, ENDPOINT_DE_PRUEBA, nivel)
        return {
            "ok": True,
            "proveedor": proveedor,
            "modelo": respuesta.modelo,
            "mensaje": f"{NOMBRE_VISIBLE[proveedor]} respondió con el modelo {respuesta.modelo}.",
            "latencia_ms": round(respuesta.latencia_ms, 1),
        }

    # --- Consumo ---

    def _exigir_repositorio_propio(self, repo: Any | None) -> None:
        if repo is not None and exigir_repositorio_de_cuenta(repo) != self.user_id:
            raise ValueError("El consumo de IA se anota en la cuenta que hace la llamada, no en otra.")

    def _anotar_respuesta(
        self, repo: Any | None, respuesta: Respuesta, endpoint_tipo: str, nivel: str = NIVEL_SIN_DISTINCION
    ) -> None:
        self._anotar(
            repo,
            proveedor=respuesta.proveedor,
            modelo=respuesta.modelo,
            endpoint_tipo=endpoint_tipo,
            nivel=respuesta.nivel or nivel,
            tokens_entrada=respuesta.tokens_entrada,
            tokens_salida=respuesta.tokens_salida,
            tokens_totales=respuesta.tokens_entrada + respuesta.tokens_salida,
            costo_usd=respuesta.costo_usd,
            estado=200,
            latencia_ms=respuesta.latencia_ms,
        )

    def _anotar_error(
        self,
        repo: Any | None,
        error: IANoDisponibleError,
        proveedor: str,
        modelo: str | None,
        endpoint_tipo: str,
        nivel: str = NIVEL_SIN_DISTINCION,
    ) -> None:
        """Anota un pedido que llegó al proveedor y falló; el que no llegó (sin estado HTTP) no se anota."""
        if error.estado is None:
            return
        self._anotar(
            repo,
            proveedor=proveedor,
            modelo=error.modelo or modelo or "",
            endpoint_tipo=endpoint_tipo,
            nivel=nivel,
            tokens_entrada=error.tokens_entrada,
            tokens_salida=error.tokens_salida,
            tokens_totales=error.tokens_entrada + error.tokens_salida,
            costo_usd=costo_de_un_error(error),
            estado=error.estado,
            latencia_ms=error.latencia_ms,
        )

    def _anotar(
        self,
        repo: Any | None,
        *,
        proveedor: str,
        modelo: str,
        endpoint_tipo: str,
        nivel: str,
        tokens_entrada: int,
        tokens_salida: int,
        tokens_totales: int,
        costo_usd: float | None,
        estado: int,
        latencia_ms: float,
    ) -> None:
        """Registra la llamada a nombre de la cuenta: en su repositorio de rutas si se pasó, o en su propia conexión.

        Una falla al registrar no tapa la respuesta del modelo: se avisa en el registro y se sigue.
        """
        fila = {
            "provider": proveedor,
            "model": modelo,
            "endpoint_tipo": endpoint_tipo,
            "api_tier": nivel,
            "prompt_tokens": tokens_entrada,
            "completion_tokens": tokens_salida,
            "total_tokens": tokens_totales,
            "estimated_cost_usd": costo_usd,
            "status_code": estado,
            "latency_ms": latencia_ms,
        }
        try:
            if repo is not None:
                repo.log_api_usage(**fila)
            else:
                with self._conexion() as conn:
                    registrar_consumo_de_ia(conn, self.user_id, **fila)
        except Exception as error:  # noqa: BLE001
            logger.warning("No se pudo anotar el consumo de IA de la cuenta %s (%s).", self.user_id, type(error).__name__)
        # Se avisa aunque anotar haya fallado: quien escucha (por ejemplo, una extensión que cobra) no depende
        # del registro local. El bus atrapa los errores de cada suscriptor.
        bus.emitir(
            IA_CONSUMO,
            user_id=self.user_id,
            proveedor=proveedor,
            modelo=modelo,
            endpoint_tipo=endpoint_tipo,
            tokens_entrada=tokens_entrada,
            tokens_salida=tokens_salida,
            tokens_totales=tokens_totales,
            estado=estado,
        )
