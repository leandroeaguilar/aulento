"""Las dos claves de Gemini (Free y Paid), el nivel activo y el modelo de una cuenta.

Las llamadas al modelo las hace la pasarela de IA de la cuenta (`core/ia/pasarela.py`) con el adaptador de
Gemini (`core/ia/gemini.py`); acá queda qué claves y qué modelos se prueban, y en qué orden.
"""

from typing import Any, Optional

from aulento.core.almacenes import ServicioDeCuenta
from aulento.core.ia.gemini import MODELO_POR_DEFECTO, modelos_candidatos
from aulento.core.ia.tarifas import TARIFAS_POR_MILLON, costo_estimado
from aulento.core.ia.tipos import GEMINI, MENSAJE_FALTA_CLAVE, FaltaClaveDeIA, IANoDisponibleError
from aulento.core.secretos import (
    AJUSTE_GEMINI_MODELO,
    AJUSTE_GEMINI_NIVEL_ACTIVO,
    SECRETO_GEMINI_CLAVE_GRATUITA,
    MENSAJE_CLAVE_MAESTRA_INVALIDA,
    SECRETO_GEMINI_CLAVE_PAGA,
    ClaveMaestraInvalida,
    SecretoIlegible,
)
from aulento.models.roadmap import DualKeyStatus

# Los errores de IA viven en `core/ia/tipos.py`; se siguen pudiendo importar de acá
__all__ = [
    "DEFAULT_GEMINI_MODEL",
    "MENSAJE_CLAVE_ILEGIBLE",
    "MENSAJE_FALTA_CLAVE",
    "SECRETOS_DE_CLAVES",
    "FaltaClaveDeIA",
    "GeminiGateway",
    "IANoDisponibleError",
    "descripcion_de_clave",
]

DEFAULT_GEMINI_MODEL = MODELO_POR_DEFECTO
NIVELES = ("free", "paid", "auto")
SECRETOS_DE_CLAVES = (SECRETO_GEMINI_CLAVE_GRATUITA, SECRETO_GEMINI_CLAVE_PAGA)
MENSAJE_CLAVE_ILEGIBLE = "No se pudo leer la clave guardada; volvé a cargarla."

# Tarifas de Google AI Studio por 1M de tokens (USD): viven con las de los demás proveedores
MODEL_PRICING_PER_1M = TARIFAS_POR_MILLON[GEMINI]


def descripcion_de_clave(pista: str | None) -> str | None:
    """Lo único que se muestra de una clave cargada: puntos suspensivos y, a lo sumo, sus últimos cuatro caracteres."""
    return None if pista is None else f"...{pista}"


class GeminiGateway(ServicioDeCuenta):
    """Las claves de Google AI Studio, el nivel activo y el modelo de una cuenta: qué se prueba y en qué orden.

    Se arma con `GeminiGateway(conn, user_id)`, o con `de_repositorio` / `con_conexion_propia` si no hay una
    conexión a mano. Las claves salen solo del almacén cifrado de la cuenta: ni archivos del directorio de
    datos ni variables de entorno del servidor.
    """

    def resolve_free_key(self) -> Optional[str]:
        """Clave gratuita de la cuenta, o None si no la cargó. Levanta `SecretoIlegible` si no se puede descifrar."""
        with self._almacenes() as (secretos, _):
            return secretos.leer(SECRETO_GEMINI_CLAVE_GRATUITA)

    def resolve_paid_key(self) -> Optional[str]:
        """Clave paga de la cuenta, o None si no la cargó. Levanta `SecretoIlegible` si no se puede descifrar."""
        with self._almacenes() as (secretos, _):
            return secretos.leer(SECRETO_GEMINI_CLAVE_PAGA)

    def _configuracion(self) -> tuple[Optional[str], Optional[str], str]:
        """Clave gratuita, clave paga y nivel activo de la cuenta, leídos de una vez."""
        with self._almacenes() as (secretos, ajustes):
            gratuita = secretos.leer(SECRETO_GEMINI_CLAVE_GRATUITA)
            paga = secretos.leer(SECRETO_GEMINI_CLAVE_PAGA)
            nivel = ajustes.leer(AJUSTE_GEMINI_NIVEL_ACTIVO)
        return gratuita, paga, self._nivel_efectivo(nivel, bool(gratuita), bool(paga))

    @staticmethod
    def _nivel_efectivo(guardado: Any, hay_gratuita: bool, hay_paga: bool) -> str:
        """El nivel elegido por la cuenta o, si no eligió, el que corresponde a las claves que tiene."""
        if guardado in NIVELES:
            return guardado
        if hay_paga and hay_gratuita:
            return "auto"
        if hay_paga:
            return "paid"
        return "free"

    def resolve_active_tier(self) -> str:
        """Determina el modo activo de la cuenta: 'free', 'paid' o 'auto'."""
        return self._configuracion()[2]

    def get_active_api_key(self) -> Optional[str]:
        """Clave de la cuenta que corresponde a su nivel activo; None si no tiene ninguna."""
        gratuita, paga, nivel = self._configuracion()
        if nivel == "paid":
            return paga or gratuita
        return gratuita or paga

    def exigir_clave(self, mensaje: str | None = None) -> str:
        """Devuelve la clave activa de la cuenta; si no tiene ninguna levanta `FaltaClaveDeIA`."""
        clave = self.get_active_api_key()
        if not clave:
            raise FaltaClaveDeIA(mensaje)
        return clave

    def resolve_model(self, explicit_model: Optional[str] = None) -> str:
        """Modelo preferido: el indicado, si no el que eligió la cuenta, si no el predeterminado."""
        if explicit_model and explicit_model.strip():
            return explicit_model.strip()
        with self._almacenes() as (_, ajustes):
            guardado = ajustes.leer(AJUSTE_GEMINI_MODELO)
        if isinstance(guardado, str) and guardado.strip():
            return guardado.strip()
        return DEFAULT_GEMINI_MODEL

    def save_model(self, model_name: str) -> None:
        """Guarda el modelo preferido de la cuenta."""
        if not model_name or not model_name.strip():
            raise ValueError("El modelo no puede estar vacío.")
        with self._almacenes() as (_, ajustes):
            ajustes.guardar(AJUSTE_GEMINI_MODELO, model_name.strip())

    def save_keys_config(
        self,
        free_key: Optional[str] = None,
        paid_key: Optional[str] = None,
        tier: Optional[str] = None,
    ) -> None:
        """Guarda cifradas las claves que se reciban y el nivel activo de la cuenta. Una clave vacía no cambia nada."""
        with self._almacenes() as (secretos, ajustes):
            if free_key is not None and free_key.strip():
                secretos.guardar(SECRETO_GEMINI_CLAVE_GRATUITA, free_key.strip())
            if paid_key is not None and paid_key.strip():
                secretos.guardar(SECRETO_GEMINI_CLAVE_PAGA, paid_key.strip())
            if tier is not None and tier.strip().lower() in NIVELES:
                ajustes.guardar(AJUSTE_GEMINI_NIVEL_ACTIVO, tier.strip().lower())

    def get_status(self) -> DualKeyStatus:
        """Estado de las claves y el modelo de la cuenta. De cada clave informa si está y sus últimos cuatro caracteres.

        Una clave guardada que no se puede descifrar figura como cargada, sin pista y con el aviso de volver a cargarla
        o, si lo que está mal es la clave maestra del servidor, con el aviso de eso.
        """
        pistas: dict[str, Optional[str]] = {}
        errores: dict[str, Optional[str]] = {}
        with self._almacenes() as (secretos, ajustes):
            cargadas = {nombre: secretos.tiene(nombre) for nombre in SECRETOS_DE_CLAVES}
            for nombre in SECRETOS_DE_CLAVES:
                pistas[nombre] = errores[nombre] = None
                if not cargadas[nombre]:
                    continue
                try:
                    pistas[nombre] = descripcion_de_clave(secretos.pista(nombre))
                except SecretoIlegible:
                    errores[nombre] = MENSAJE_CLAVE_ILEGIBLE
                except ClaveMaestraInvalida:
                    errores[nombre] = MENSAJE_CLAVE_MAESTRA_INVALIDA
            nivel = ajustes.leer(AJUSTE_GEMINI_NIVEL_ACTIVO)
            modelo = ajustes.leer(AJUSTE_GEMINI_MODELO)

        return DualKeyStatus(
            has_free_key=cargadas[SECRETO_GEMINI_CLAVE_GRATUITA],
            has_paid_key=cargadas[SECRETO_GEMINI_CLAVE_PAGA],
            active_tier=self._nivel_efectivo(
                nivel, cargadas[SECRETO_GEMINI_CLAVE_GRATUITA], cargadas[SECRETO_GEMINI_CLAVE_PAGA]
            ),
            free_key_masked=pistas[SECRETO_GEMINI_CLAVE_GRATUITA],
            paid_key_masked=pistas[SECRETO_GEMINI_CLAVE_PAGA],
            free_key_error=errores[SECRETO_GEMINI_CLAVE_GRATUITA],
            paid_key_error=errores[SECRETO_GEMINI_CLAVE_PAGA],
            active_model=modelo.strip() if isinstance(modelo, str) and modelo.strip() else DEFAULT_GEMINI_MODEL,
        )

    get_keys_status = get_status

    @staticmethod
    def calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Costo estimado en USD según las tarifas conocidas; 0.0 si el modelo no tiene tarifa."""
        return costo_estimado(GEMINI, model, prompt_tokens, completion_tokens) or 0.0

    def claves_en_orden(self) -> list[tuple[str, str]]:
        """Las claves de la cuenta con las que sale un pedido, como `(nivel, clave)` y en el orden en que se prueban.

        En modo `auto` va primero la gratuita y detrás la paga; en `free` o `paid`, solo esa. Si el nivel elegido
        no tiene clave cargada, la que haya.
        """
        gratuita, paga, nivel = self._configuracion()
        if nivel == "paid" and paga:
            return [("paid", paga)]
        if nivel == "free" and gratuita:
            return [("free", gratuita)]
        if nivel == "auto":
            return [par for par in (("free", gratuita), ("paid", paga)) if par[1]]
        if gratuita:
            return [("free", gratuita)]
        return [("paid", paga)] if paga else []

    def modelos_candidatos(self) -> list[str]:
        """El modelo preferido de la cuenta y, detrás, los de rotación."""
        return modelos_candidatos(self.resolve_model())
