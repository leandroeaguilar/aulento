"""Lo que comparten los proveedores de IA: el pedido neutral, la respuesta, las capacidades y los errores."""

from dataclasses import dataclass
from typing import Any

GEMINI = "gemini"
ANTHROPIC = "anthropic"
OPENAI = "openai"
PROVEEDORES = (GEMINI, ANTHROPIC, OPENAI)
NOMBRE_VISIBLE = {GEMINI: "Gemini", ANTHROPIC: "Anthropic", OPENAI: "OpenAI"}

TEXTO = "texto"
PDF = "pdf"
AUDIO = "audio"
EMBEDDINGS = "embeddings"
CAPACIDADES = (TEXTO, PDF, AUDIO, EMBEDDINGS)
# Cómo se nombra cada capacidad en un mensaje: «Anthropic no puede evaluar audio.»
ACCION_DE_LA_CAPACIDAD = {
    TEXTO: "generar texto",
    PDF: "leer un PDF",
    AUDIO: "evaluar audio",
    EMBEDDINGS: "calcular embeddings",
}

MIME_PDF = "application/pdf"
DIMENSIONES_DE_EMBEDDING = 768
# Lo que se manda a embeber de un fragmento, como mucho
CARACTERES_A_EMBEBER = 2048

MENSAJE_FALTA_CLAVE = "No hay una clave de Gemini configurada para tu cuenta. Cargala en Configuración para usar la IA."


def mensaje_falta_clave(proveedor: str) -> str:
    """Lo que se le dice a una cuenta que no cargó la clave del proveedor con el que se iba a hacer el pedido."""
    if proveedor == GEMINI:
        return MENSAJE_FALTA_CLAVE
    return (
        f"No hay una clave de {NOMBRE_VISIBLE[proveedor]} configurada para tu cuenta. "
        "Cargala en Configuración para usar la IA."
    )


@dataclass(frozen=True)
class Adjunto:
    """Un archivo que acompaña al pedido: un PDF o un audio, en bytes."""

    mime: str
    datos: bytes


@dataclass(frozen=True)
class Pedido:
    """Lo que un llamador le pide a un modelo, sin el formato de ningún proveedor.

    `json` pide que la respuesta sea un objeto JSON; `esquema`, además, que cumpla ese JSON Schema (implica `json`).
    `max_tokens` y `timeout` en `None` dejan los valores por defecto del proveedor. `temperatura` es una
    preferencia: la envía solo el proveedor que la admite (Gemini); los modelos de Anthropic y varios de OpenAI
    rechazan el pedido si la trae.
    """

    usuario: str
    sistema: str | None = None
    adjuntos: tuple[Adjunto, ...] = ()
    json: bool = False
    esquema: dict[str, Any] | None = None
    max_tokens: int | None = None
    timeout: float | None = None
    temperatura: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "adjuntos", tuple(self.adjuntos))
        for adjunto in self.adjuntos:
            if adjunto.mime != MIME_PDF and not adjunto.mime.startswith("audio/"):
                raise ValueError(f"Adjunto de tipo no soportado ({adjunto.mime!r}): se admiten PDF y audio.")

    @property
    def pide_json(self) -> bool:
        return self.json or self.esquema is not None

    @property
    def capacidad(self) -> str:
        """La capacidad que tiene que tener el proveedor que atienda este pedido."""
        if any(adjunto.mime.startswith("audio/") for adjunto in self.adjuntos):
            return AUDIO
        if self.adjuntos:
            return PDF
        return TEXTO


@dataclass(frozen=True)
class Respuesta:
    """Lo que respondió un modelo y lo que costó.

    `nivel` es la clave de Gemini con la que salió (`free` o `paid`) y `None` en los demás proveedores.
    `costo_usd` es `None` cuando no se conoce la tarifa del modelo. `por_capacidad` indica que no respondió el
    proveedor activo de la cuenta sino otro, porque el activo no tiene la capacidad pedida. `truncada`, que el
    modelo cortó la respuesta al llegar al tope de tokens.
    """

    texto: str
    proveedor: str
    modelo: str
    tokens_entrada: int = 0
    tokens_salida: int = 0
    costo_usd: float | None = None
    latencia_ms: float = 0.0
    nivel: str | None = None
    por_capacidad: bool = False
    truncada: bool = False


@dataclass(frozen=True)
class Embedding:
    """Un vector unitario de `DIMENSIONES_DE_EMBEDDING` dimensiones, con el modelo y el proveedor que lo calcularon."""

    vector: list[float]
    modelo: str
    proveedor: str
    por_capacidad: bool = False


class IANoDisponibleError(RuntimeError):
    """La operación necesita IA y no hay clave, cuota o respuesta utilizable.

    Cuando el error viene de un pedido que llegó a un proveedor lleva `proveedor`, `modelo`, `estado` (el código
    HTTP), `codigo` (el tipo de error que informó el proveedor, saneado) y `latencia_ms`. El mensaje es para
    mostrar a la persona: nunca lleva la clave ni el texto de la respuesta del proveedor.
    """

    def __init__(
        self,
        mensaje: str,
        *,
        proveedor: str | None = None,
        modelo: str | None = None,
        estado: int | None = None,
        codigo: str | None = None,
        latencia_ms: float = 0.0,
        tokens_entrada: int = 0,
        tokens_salida: int = 0,
    ) -> None:
        super().__init__(mensaje)
        self.proveedor = proveedor
        self.modelo = modelo
        self.estado = estado
        self.codigo = codigo
        self.latencia_ms = latencia_ms
        self.tokens_entrada = tokens_entrada
        self.tokens_salida = tokens_salida


class FaltaClaveDeIA(IANoDisponibleError):
    """La cuenta que pide la operación no tiene cargada la clave del proveedor que la iba a atender."""

    def __init__(self, mensaje: str | None = None, **datos: Any) -> None:
        super().__init__(mensaje or MENSAJE_FALTA_CLAVE, **datos)


class FaltaElegirModelo(IANoDisponibleError):
    """El proveedor no tiene modelo por defecto y la cuenta todavía no eligió uno."""


class ClaveRechazada(IANoDisponibleError):
    """El proveedor no aceptó la clave de la cuenta, o la clave no tiene permiso para lo pedido."""


class CuotaAgotada(IANoDisponibleError):
    """La clave se quedó sin cuota o superó el límite de pedidos del proveedor."""


class ModeloInexistente(IANoDisponibleError):
    """El proveedor no conoce el modelo elegido."""


class PedidoInvalido(IANoDisponibleError):
    """El proveedor rechazó el pedido por su forma (HTTP 400)."""


class RespuestaRechazada(IANoDisponibleError):
    """El modelo se negó a responder o el proveedor filtró la respuesta."""


class CapacidadNoSoportada(IANoDisponibleError):
    """El pedido necesita una capacidad que ningún proveedor con clave de la cuenta tiene."""

    def __init__(self, mensaje: str, *, capacidad: str, quienes_la_ofrecen: tuple[str, ...] = (), **datos: Any) -> None:
        super().__init__(mensaje, **datos)
        self.capacidad = capacidad
        self.quienes_la_ofrecen = quienes_la_ofrecen


# Lo que solo se arregla cambiando la configuración de la cuenta: repetir el pedido no sirve
ERRORES_DE_LA_CUENTA_CON_LA_IA = (
    FaltaClaveDeIA,
    FaltaElegirModelo,
    ClaveRechazada,
    ModeloInexistente,
    CapacidadNoSoportada,
)


def motivo_sin_ia(error: IANoDisponibleError) -> str | None:
    """Por qué un resultado se obtuvo sin IA, para decirlo junto al resultado; `None` si solo falta cargar la clave.

    Sin clave, el indicador de «sin IA» que cada operación ya tenía alcanza. Una clave rechazada, la cuota agotada,
    un modelo inexistente, una negativa del modelo o una capacidad que nadie ofrece llevan el mensaje del error.
    """
    return None if isinstance(error, FaltaClaveDeIA) else str(error)
