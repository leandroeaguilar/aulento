"""Contrato de un proveedor de IA y la única salida HTTP de la capa.

Todo pedido a un proveedor pasa por `ProveedorHTTP._post` o `_get`: ahí se mide la latencia y se traducen los
códigos HTTP y las fallas de red a los errores de `tipos.py`. La clave viaja solo en las cabeceras; ni ella ni
el cuerpo de la respuesta del proveedor llegan a un mensaje o al registro.
"""

import base64
import copy
import logging
import math
import re
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from aulento.core.ia.tipos import (
    ACCION_DE_LA_CAPACIDAD,
    DIMENSIONES_DE_EMBEDDING,
    EMBEDDINGS,
    NOMBRE_VISIBLE,
    CapacidadNoSoportada,
    ClaveRechazada,
    CuotaAgotada,
    FaltaClaveDeIA,
    IANoDisponibleError,
    ModeloInexistente,
    Pedido,
    PedidoInvalido,
    Respuesta,
    mensaje_falta_clave,
)

logger = logging.getLogger(__name__)

SEGUNDOS_POR_DEFECTO = 45.0
SEGUNDOS_PARA_LISTAR = 15.0
INSTRUCCION_JSON = "Respondé únicamente con un objeto JSON válido, sin texto antes ni después y sin bloques de código."
TEXTO_DE_PRUEBA = "Respondé solamente: ok"
TOKENS_DE_PRUEBA = 64

# Lo único que se toma de un cuerpo de error: un identificador corto, sin espacios ni texto libre
_CODIGO_SANO = re.compile(r"[A-Za-z0-9_.\-]{1,48}")


class Proveedor(Protocol):
    """Lo que la pasarela le pide a cada proveedor."""

    nombre: str
    capacidades: frozenset[str]
    modelo_por_defecto: str | None
    modelos_sugeridos: tuple[str, ...]
    modelo_de_embeddings: str | None

    def generar(self, pedido: Pedido, clave: str, modelo: str | None) -> Respuesta: ...

    def embeber(self, texto: str, clave: str, tarea: str = "documento") -> tuple[list[float], str]: ...

    def modelos(self, clave: str) -> list[str]: ...

    def probar(self, clave: str, modelo: str | None) -> Respuesta: ...


@dataclass(frozen=True)
class RespuestaHTTP:
    datos: dict[str, Any]
    latencia_ms: float


def codigo_sano(valor: Any, clave: str = "") -> str | None:
    """El código de error del proveedor si es un identificador corto; cualquier otra cosa se descarta."""
    if isinstance(valor, bool) or not isinstance(valor, str | int):
        return None
    texto = str(valor)
    if _CODIGO_SANO.fullmatch(texto) is None or (clave and clave in texto):
        return None
    return texto


def entero(valor: Any) -> int:
    """Una cuenta de tokens tal como vino, o cero si el proveedor no la informó como entero."""
    return valor if isinstance(valor, int) and not isinstance(valor, bool) else 0


def en_base64(datos: bytes) -> str:
    """Base64 estándar en una sola línea, como lo esperan los tres proveedores."""
    return base64.b64encode(datos).decode("ascii")


def con_instruccion_json(sistema: str | None) -> str:
    """La instrucción de sistema del llamador con el pedido de responder solo JSON al final."""
    return f"{sistema.strip()}\n\n{INSTRUCCION_JSON}" if sistema and sistema.strip() else INSTRUCCION_JSON


def esquema_estricto(esquema: dict[str, Any]) -> dict[str, Any]:
    """Copia del esquema en la que cada objeto declara `additionalProperties: false` y todas sus propiedades en `required`.

    Es lo que exigen las salidas estructuradas de Anthropic y de OpenAI; lo que el esquema ya declara no se toca.
    """

    def completar(nodo: Any) -> Any:
        if isinstance(nodo, list):
            return [completar(elemento) for elemento in nodo]
        if not isinstance(nodo, dict):
            return nodo
        completo = {clave: completar(valor) for clave, valor in nodo.items()}
        if completo.get("type") == "object" and isinstance(completo.get("properties"), dict):
            completo.setdefault("additionalProperties", False)
            completo.setdefault("required", list(completo["properties"]))
        return completo

    return completar(copy.deepcopy(esquema))


def vector_unitario(valores: Any, proveedor: str, modelo: str) -> list[float]:
    """El vector normalizado; levanta `IANoDisponibleError` si no tiene las dimensiones esperadas."""
    if not isinstance(valores, list) or len(valores) != DIMENSIONES_DE_EMBEDDING:
        raise IANoDisponibleError(
            f"{NOMBRE_VISIBLE[proveedor]} devolvió un embedding que no tiene {DIMENSIONES_DE_EMBEDDING} dimensiones.",
            proveedor=proveedor,
            modelo=modelo,
            estado=200,
        )
    norma = math.sqrt(sum(float(x) * float(x) for x in valores)) or 1.0
    return [float(x) / norma for x in valores]


class ProveedorHTTP:
    """Base de los adaptadores: la salida HTTP, la traducción de errores y la prueba de conexión."""

    nombre: str
    capacidades: frozenset[str]
    modelo_por_defecto: str | None = None
    modelos_sugeridos: tuple[str, ...] = ()
    # El modelo con que calcula embeddings; `None` si no los ofrece
    modelo_de_embeddings: str | None = None
    segundos_por_defecto: float = SEGUNDOS_POR_DEFECTO

    @property
    def nombre_visible(self) -> str:
        return NOMBRE_VISIBLE[self.nombre]

    def _cabeceras(self, clave: str) -> dict[str, str]:
        raise NotImplementedError

    def _codigo_de_error(self, datos: dict[str, Any]) -> Any:
        """El tipo o código de error que el proveedor pone en el cuerpo de una respuesta fallida."""
        raise NotImplementedError

    def generar(self, pedido: Pedido, clave: str, modelo: str | None) -> Respuesta:
        raise NotImplementedError

    def modelos(self, clave: str) -> list[str]:
        raise NotImplementedError

    def embeber(self, texto: str, clave: str, tarea: str = "documento") -> tuple[list[float], str]:
        raise CapacidadNoSoportada(
            f"{self.nombre_visible} no puede {ACCION_DE_LA_CAPACIDAD[EMBEDDINGS]}.",
            capacidad=EMBEDDINGS,
            proveedor=self.nombre,
        )

    def _exigir_capacidad(self, pedido: Pedido) -> None:
        if pedido.capacidad not in self.capacidades:
            raise CapacidadNoSoportada(
                f"{self.nombre_visible} no puede {ACCION_DE_LA_CAPACIDAD[pedido.capacidad]}.",
                capacidad=pedido.capacidad,
                proveedor=self.nombre,
            )

    def probar(self, clave: str, modelo: str | None) -> Respuesta:
        """Un pedido mínimo al modelo: si vuelve una `Respuesta`, la clave y el modelo sirven."""
        return self.generar(Pedido(usuario=TEXTO_DE_PRUEBA, max_tokens=TOKENS_DE_PRUEBA), clave, modelo)

    def _post(
        self,
        url: str,
        cuerpo: dict[str, Any],
        clave: str,
        *,
        modelo: str | None = None,
        timeout: float | None = None,
        cabeceras: dict[str, str] | None = None,
    ) -> RespuestaHTTP:
        return self._pedir(url, cuerpo, clave, modelo, timeout or self.segundos_por_defecto, cabeceras)

    def _get(self, url: str, clave: str, *, timeout: float = SEGUNDOS_PARA_LISTAR) -> RespuestaHTTP:
        return self._pedir(url, None, clave, None, timeout, None)

    def _pedir(
        self,
        url: str,
        cuerpo: dict[str, Any] | None,
        clave: str,
        modelo: str | None,
        timeout: float,
        cabeceras_propias: dict[str, str] | None,
    ) -> RespuestaHTTP:
        if not clave:
            raise FaltaClaveDeIA(mensaje_falta_clave(self.nombre), proveedor=self.nombre, modelo=modelo)
        cabeceras = {**self._cabeceras(clave), **(cabeceras_propias or {})}
        inicio = time.perf_counter()
        try:
            with httpx.Client(timeout=timeout) as cliente:
                if cuerpo is None:
                    respuesta = cliente.get(url, headers=cabeceras)
                else:
                    respuesta = cliente.post(url, json=cuerpo, headers=cabeceras)
        except httpx.TimeoutException:
            logger.warning("%s no respondió en %.0f s (modelo %s).", self.nombre_visible, timeout, modelo)
            raise IANoDisponibleError(
                f"{self.nombre_visible} tardó más de {timeout:.0f} segundos en responder. Probá de nuevo.",
                proveedor=self.nombre,
                modelo=modelo,
                latencia_ms=_milisegundos_desde(inicio),
            ) from None
        except Exception as error:  # noqa: BLE001
            # Del error solo se registra el tipo: su texto puede traer la dirección o datos del pedido
            logger.warning("No se pudo conectar con %s (%s).", self.nombre_visible, type(error).__name__)
            raise IANoDisponibleError(
                f"No se pudo conectar con {self.nombre_visible}. Revisá la conexión y probá de nuevo.",
                proveedor=self.nombre,
                modelo=modelo,
                latencia_ms=_milisegundos_desde(inicio),
            ) from None

        latencia_ms = _milisegundos_desde(inicio)
        estado = respuesta.status_code
        datos = _cuerpo_json(respuesta)
        if 200 <= estado < 300:
            if datos is None:
                raise IANoDisponibleError(
                    f"{self.nombre_visible} devolvió una respuesta que no se pudo leer.",
                    proveedor=self.nombre,
                    modelo=modelo,
                    estado=estado,
                    latencia_ms=latencia_ms,
                )
            return RespuestaHTTP(datos=datos, latencia_ms=latencia_ms)

        codigo = codigo_sano(self._codigo_de_error(datos or {}), clave)
        logger.warning(
            "%s respondió HTTP %s (%s) al pedido del modelo %s.",
            self.nombre_visible,
            estado,
            codigo or "sin código",
            modelo,
        )
        raise self._error_http(estado, codigo, modelo, latencia_ms)

    def _error_http(self, estado: int, codigo: str | None, modelo: str | None, latencia_ms: float) -> IANoDisponibleError:
        """El error tipado de un código HTTP, con un mensaje propio de cada caso."""
        quien = self.nombre_visible
        detalle = f" ({codigo})" if codigo else ""
        datos = {"proveedor": self.nombre, "modelo": modelo, "estado": estado, "codigo": codigo, "latencia_ms": latencia_ms}
        if estado == 401:
            return ClaveRechazada(f"{quien} rechazó la clave de tu cuenta. Revisala o volvé a cargarla en Configuración.", **datos)
        if estado == 403:
            return ClaveRechazada(
                f"La clave de {quien} de tu cuenta no tiene permiso para este pedido o para el modelo elegido.", **datos
            )
        if estado == 404:
            cual = f"el modelo «{modelo}»" if modelo else "lo que se le pidió"
            return ModeloInexistente(f"{quien} no reconoce {cual}. Elegí otro modelo en Configuración.", **datos)
        if estado == 429:
            if codigo == "insufficient_quota":
                return CuotaAgotada(
                    f"La clave de {quien} de tu cuenta no tiene cuota disponible. Revisá el saldo o el plan de tu cuenta de {quien}.",
                    **datos,
                )
            return CuotaAgotada(
                f"La clave de {quien} de tu cuenta agotó su cuota o superó el límite de pedidos. Probá de nuevo en unos minutos.",
                **datos,
            )
        if estado == 400:
            return PedidoInvalido(f"{quien} rechazó el pedido porque no es válido{detalle}.", **datos)
        if estado >= 500:
            return IANoDisponibleError(
                f"{quien} no está disponible en este momento (HTTP {estado}). Probá de nuevo en unos minutos.", **datos
            )
        return IANoDisponibleError(f"{quien} respondió con un error (HTTP {estado}){detalle}.", **datos)


def _milisegundos_desde(inicio: float) -> float:
    return (time.perf_counter() - inicio) * 1000.0


def _cuerpo_json(respuesta: Any) -> dict[str, Any] | None:
    """El cuerpo de la respuesta si es un objeto JSON; `None` si no lo es."""
    try:
        datos = respuesta.json()
    except ValueError:
        return None
    return datos if isinstance(datos, dict) else None
