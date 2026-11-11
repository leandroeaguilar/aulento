"""Doble de la red de Gemini para las baterías de la 034. Las dos cuentas con sesión real están en `nube_cuentas`."""

from dataclasses import dataclass, field
from unittest.mock import MagicMock

import httpx

from aulento.core.embedding_service import EMBEDDING_DIMENSIONS


@dataclass
class Pedido:
    url: str
    clave: str | None
    cuerpo: dict

    @property
    def modelo(self) -> str:
        return self.url.rsplit("/models/", 1)[1].split(":")[0]

    @property
    def instruccion_de_sistema(self) -> str | None:
        partes = (self.cuerpo.get("systemInstruction") or self.cuerpo.get("system_instruction") or {}).get("parts")
        return partes[0]["text"] if partes else None


@dataclass
class RedDeGemini:
    """Doble de `httpx.Client.post`: anota cada pedido a Google y responde lo que se le configure.

    `texto` es lo que «genera» el modelo; `estado_por_clave` permite que una clave reciba otro estado HTTP
    (por ejemplo 429 para la gratuita).
    """

    texto: str = "{}"
    estado_por_clave: dict[str, int] = field(default_factory=dict)
    pedidos: list[Pedido] = field(default_factory=list)

    def claves(self) -> list[str | None]:
        return [pedido.clave for pedido in self.pedidos]

    def vaciar(self) -> None:
        self.pedidos.clear()

    def recibir(self, url, json=None, headers=None, **_):
        clave = (headers or {}).get("x-goog-api-key")
        self.pedidos.append(Pedido(url=str(url), clave=clave, cuerpo=json or {}))
        respuesta = MagicMock()
        respuesta.status_code = self.estado_por_clave.get(clave, 200)
        respuesta.text = "respuesta del doble de Gemini"
        if "embedContent" in str(url):
            respuesta.json.return_value = {"embedding": {"values": [1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1)}}
        else:
            respuesta.json.return_value = {
                "candidates": [{"content": {"parts": [{"text": self.texto}]}}],
                "usageMetadata": {"promptTokenCount": 7, "candidatesTokenCount": 5, "totalTokenCount": 12},
            }
        return respuesta


def instalar_red_de_gemini(monkeypatch) -> RedDeGemini:
    """Sustituye la salida a Google de todo el proceso: ningún pedido llega a la red."""
    red = RedDeGemini()
    monkeypatch.setattr(httpx.Client, "post", red.recibir)
    return red
