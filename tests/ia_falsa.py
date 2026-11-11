"""Doble de la red de los tres proveedores de IA (035): anota cada pedido y responde como la API de cada uno.

Sustituye `httpx.Client.post` y `httpx.Client.get` de todo el proceso: ningún pedido llega a la red, y uno a una
dirección que no es de Gemini, Anthropic u OpenAI hace fallar el test.
"""

import json as json_estandar
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, patch

import httpx

from aulento.core.ia.pasarela import PasarelaDeIA
from aulento.core.ia.tipos import FaltaClaveDeIA, IANoDisponibleError, Respuesta

GEMINI, ANTHROPIC, OPENAI = "gemini", "anthropic", "openai"
SERVIDOR = {
    "https://generativelanguage.googleapis.com/": GEMINI,
    "https://api.anthropic.com/": ANTHROPIC,
    "https://api.openai.com/": OPENAI,
}
# Lo que el doble pone en el cuerpo de cada error, junto con la clave recibida: nada de esto puede salir de la capa
TEXTO_CRUDO = "TEXTO-CRUDO-DEL-PROVEEDOR"
DIMENSIONES = 768
# El código de error que cada proveedor pone en el cuerpo, por estado HTTP
CODIGO_DE_ERROR = {
    GEMINI: {400: "INVALID_ARGUMENT", 401: "UNAUTHENTICATED", 403: "PERMISSION_DENIED", 404: "NOT_FOUND", 429: "RESOURCE_EXHAUSTED"},
    ANTHROPIC: {
        400: "invalid_request_error",
        401: "authentication_error",
        403: "permission_error",
        404: "not_found_error",
        429: "rate_limit_error",
        529: "overloaded_error",
    },
    OPENAI: {400: "invalid_request_error", 401: "invalid_api_key", 404: "model_not_found", 429: "rate_limit_exceeded"},
}
USO_DE_GEMINI = {"promptTokenCount": 7, "candidatesTokenCount": 5, "totalTokenCount": 12}
USO_DE_ANTHROPIC = {"input_tokens": 11, "output_tokens": 9}
USO_DE_OPENAI = {"prompt_tokens": 13, "completion_tokens": 4, "total_tokens": 17}
MODELOS_DE_GEMINI = [
    {"name": "models/gemini-flash-lite-latest", "supportedGenerationMethods": ["generateContent", "countTokens"]},
    {"name": "models/gemini-embedding-001", "supportedGenerationMethods": ["embedContent"]},
    {"name": "models/gemini-3.8-flash", "supportedGenerationMethods": ["generateContent"]},
]
MODELOS_DE_ANTHROPIC = [
    {"id": "claude-opus-5-5", "display_name": "Claude Opus 5.5", "type": "model"},
    {"id": "claude-sonnet-5-5", "display_name": "Claude Sonnet 5.5", "type": "model"},
    {"id": "claude-haiku-5-5", "display_name": "Claude Haiku 5.5", "type": "model"},
]
MODELOS_DE_OPENAI = [
    {"id": "modelo-de-chat-b"},
    {"id": "text-embedding-3-small"},
    {"id": "whisper-1"},
    {"id": "tts-1"},
    {"id": "dall-e-3"},
    {"id": "omni-moderation-latest"},
    {"id": "gpt-image-1"},
    {"id": "modelo-de-audio-preview"},
    {"id": "modelo-de-chat-a"},
]


@dataclass
class PedidoAnotado:
    metodo: str
    url: str
    cabeceras: dict[str, str]
    cuerpo: dict[str, Any] | None

    @property
    def proveedor(self) -> str:
        return next(proveedor for servidor, proveedor in SERVIDOR.items() if self.url.startswith(servidor))

    @property
    def clave(self) -> str | None:
        if self.proveedor == GEMINI:
            return self.cabeceras.get("x-goog-api-key")
        if self.proveedor == ANTHROPIC:
            return self.cabeceras.get("x-api-key")
        return (self.cabeceras.get("Authorization") or "").removeprefix("Bearer ") or None

    @property
    def modelo(self) -> str | None:
        """El modelo al que va el pedido: en Gemini está en la dirección; en los otros dos, en el cuerpo."""
        if self.proveedor == GEMINI:
            return self.url.rsplit("/models/", 1)[1].split(":")[0] if "/models/" in self.url else None
        return (self.cuerpo or {}).get("model")


class RespuestaFalsa:
    def __init__(self, estado: int, cuerpo: Any) -> None:
        self.status_code = estado
        self._cuerpo = cuerpo
        self.text = str(cuerpo)

    def json(self) -> Any:
        """Un cuerpo que es texto (una página de error, por ejemplo) falla al leerse como JSON, igual que en `httpx`."""
        return json_estandar.loads(self._cuerpo) if isinstance(self._cuerpo, str) else self._cuerpo


@dataclass
class RedDeIA:
    """Lo que responde cada proveedor y lo que recibió.

    `texto` es lo que «genera» el modelo. `estado_por_clave` y `estado_por_modelo` hacen fallar con ese estado HTTP
    los pedidos de una clave o a un modelo. `cuerpos` reemplaza el cuerpo de la respuesta correcta de un proveedor
    y `codigos` el código de error que pone en el cuerpo. `falla`, si se fija, es la excepción con la que «se cae»
    la red antes de responder.
    """

    texto: str = "{}"
    estado_por_clave: dict[str, int] = field(default_factory=dict)
    estado_por_modelo: dict[str, int] = field(default_factory=dict)
    cuerpos: dict[str, Any] = field(default_factory=dict)
    codigos: dict[str, str] = field(default_factory=dict)
    falla: Exception | None = None
    pedidos: list[PedidoAnotado] = field(default_factory=list)

    def de(self, proveedor: str) -> list[PedidoAnotado]:
        return [pedido for pedido in self.pedidos if pedido.proveedor == proveedor]

    def claves(self) -> list[str | None]:
        return [pedido.clave for pedido in self.pedidos]

    def modelos(self) -> list[str | None]:
        return [pedido.modelo for pedido in self.pedidos]

    def vaciar(self) -> None:
        self.pedidos.clear()

    def post(self, url, json=None, headers=None, **otros):
        assert not otros, f"argumentos que el doble no conoce: {sorted(otros)}"
        return self._recibir("POST", str(url), dict(headers or {}), json)

    def get(self, url, headers=None, **otros):
        assert not otros, f"argumentos que el doble no conoce: {sorted(otros)}"
        return self._recibir("GET", str(url), dict(headers or {}), None)

    def _recibir(self, metodo: str, url: str, cabeceras: dict[str, str], cuerpo: dict | None) -> RespuestaFalsa:
        pedido = PedidoAnotado(metodo=metodo, url=url, cabeceras=cabeceras, cuerpo=cuerpo)
        assert any(url.startswith(servidor) for servidor in SERVIDOR), f"pedido a una dirección no prevista: {url}"
        self.pedidos.append(pedido)
        if self.falla is not None:
            raise self.falla
        estado = self.estado_por_clave.get(pedido.clave or "") or self.estado_por_modelo.get(pedido.modelo or "") or 200
        if estado != 200:
            return RespuestaFalsa(estado, self._cuerpo_de_error(pedido, estado))
        return RespuestaFalsa(200, self._cuerpo_correcto(pedido))

    def _cuerpo_de_error(self, pedido: PedidoAnotado, estado: int) -> dict[str, Any]:
        proveedor = pedido.proveedor
        codigo = self.codigos.get(proveedor) or CODIGO_DE_ERROR[proveedor].get(estado, "error_del_servidor")
        mensaje = f"{TEXTO_CRUDO} con la clave {pedido.clave}"
        if proveedor == GEMINI:
            return {"error": {"code": estado, "message": mensaje, "status": codigo}}
        if proveedor == ANTHROPIC:
            return {"type": "error", "error": {"type": codigo, "message": mensaje}}
        return {"error": {"message": mensaje, "type": "error_de_openai", "code": codigo}}

    def _cuerpo_correcto(self, pedido: PedidoAnotado) -> Any:
        proveedor, url = pedido.proveedor, pedido.url
        if pedido.metodo == "GET":
            assert url.endswith("/models"), f"lectura no prevista: {url}"
            if proveedor == GEMINI:
                return {"models": MODELOS_DE_GEMINI}
            return {"data": MODELOS_DE_ANTHROPIC if proveedor == ANTHROPIC else MODELOS_DE_OPENAI}
        if url.endswith(":embedContent"):
            return {"embedding": {"values": [3.0, 4.0] + [0.0] * (DIMENSIONES - 2)}}
        if url.endswith("/v1/embeddings"):
            return {"data": [{"index": 0, "embedding": [0.0, 6.0, 8.0] + [0.0] * (DIMENSIONES - 3)}]}
        if proveedor in self.cuerpos:
            return self.cuerpos[proveedor]
        if proveedor == GEMINI:
            assert url.endswith(":generateContent"), f"pedido no previsto: {url}"
            return {"candidates": [{"content": {"parts": [{"text": self.texto}]}}], "usageMetadata": USO_DE_GEMINI}
        if proveedor == ANTHROPIC:
            assert url.endswith("/v1/messages"), f"pedido no previsto: {url}"
            return {
                "id": "msg_de_prueba",
                "type": "message",
                "role": "assistant",
                "model": pedido.modelo,
                "content": [{"type": "thinking", "thinking": ""}, {"type": "text", "text": self.texto}],
                "stop_reason": "end_turn",
                "usage": USO_DE_ANTHROPIC,
            }
        assert url.endswith("/v1/chat/completions"), f"pedido no previsto: {url}"
        return {
            "id": "chatcmpl-de-prueba",
            "model": pedido.modelo,
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": self.texto, "refusal": None}, "finish_reason": "stop"}
            ],
            "usage": USO_DE_OPENAI,
        }


def instalar_red_de_ia(monkeypatch) -> RedDeIA:
    """Sustituye la salida a los tres proveedores de todo el proceso: ningún pedido llega a la red."""
    red = RedDeIA()
    monkeypatch.setattr(httpx.Client, "post", red.post)
    monkeypatch.setattr(httpx.Client, "get", red.get)
    return red


# --- Doble de la pasarela, para los tests de un solo llamador: no pasa por los adaptadores ni por la red ---

_SIN_FIJAR = object()


def respuesta_de(cuerpo: Any, proveedor: str = GEMINI, modelo: str = "gemini-flash-latest", **campos) -> Respuesta:
    """La `Respuesta` de la pasarela con ese texto, o con ese valor escrito como JSON."""
    texto = cuerpo if isinstance(cuerpo, str) else json_estandar.dumps(cuerpo)
    campos.setdefault("nivel", "free" if proveedor == GEMINI else None)
    return Respuesta(texto=texto, proveedor=proveedor, modelo=modelo, **campos)


@contextmanager
def ia_sustituida(*en_orden: Any, siempre: Any = _SIN_FIJAR, sin_clave: bool = False):
    """Sustituye `PasarelaDeIA.generar` y entrega el doble del modelo, que anota `(pedido, endpoint_tipo, repo)`.

    `siempre` es lo que responde a todo pedido; `en_orden`, lo que responde a cada uno. Una `Respuesta` se devuelve,
    una excepción se levanta y `None` es un proveedor que no respondió (`IANoDisponibleError`). Con `sin_clave`
    la cuenta no tiene clave: `generar` levanta `FaltaClaveDeIA` y al modelo no le llega ningún pedido.
    """
    pendientes = list(en_orden)

    def responder(pedido, endpoint_tipo, repo):
        efecto = pendientes.pop(0) if siempre is _SIN_FIJAR else siempre
        if efecto is None:
            raise IANoDisponibleError("Gemini no está disponible en este momento (HTTP 503).", proveedor=GEMINI, estado=503)
        if isinstance(efecto, Exception):
            raise efecto
        return efecto

    modelo = MagicMock(side_effect=responder)

    def generar(self, pedido, endpoint_tipo="generic", repo=None):
        if sin_clave:
            raise FaltaClaveDeIA(proveedor=GEMINI)
        return modelo(pedido, endpoint_tipo, repo)

    with patch.object(PasarelaDeIA, "generar", generar):
        yield modelo
