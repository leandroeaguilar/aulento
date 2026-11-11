"""Cliente mínimo de Streamable HTTP para probar el servidor MCP de punta a punta, con el token de una cuenta."""

import json
from dataclasses import dataclass, field
from typing import Any

from starlette.testclient import TestClient

from aulento.mcp.server import BearerAuthMiddleware, create_study_mcp_server

HOST = "127.0.0.1:8000"
VERSION_DEL_PROTOCOLO = "2025-06-18"


def aplicacion_mcp(read_only: bool = False):
    """La misma aplicación ASGI que arma `run_sse_server` para el transporte http, sin levantar uvicorn."""
    app = create_study_mcp_server(read_only=read_only).streamable_http_app(host="127.0.0.1")
    app.add_middleware(BearerAuthMiddleware)
    return app


def mensaje_de(respuesta) -> dict:
    """Mensaje JSON-RPC de una respuesta de Streamable HTTP (JSON directo o el último evento SSE)."""
    if respuesta.headers.get("content-type", "").startswith("application/json"):
        return respuesta.json()
    datos = [linea[5:].strip() for linea in respuesta.text.splitlines() if linea.startswith("data:")]
    return json.loads(datos[-1])


def cabeceras_de(token: str | None) -> dict[str, str]:
    cabeceras = {"Accept": "application/json, text/event-stream", "Host": HOST}
    if token is not None:
        cabeceras["Authorization"] = f"Bearer {token}"
    return cabeceras


@dataclass
class SesionMcp:
    """Sesión MCP abierta por HTTP con el token de una cuenta."""

    cliente: TestClient
    token: str
    sesion_id: str = ""
    _siguiente: int = field(default=1, repr=False)

    @classmethod
    def abrir(cls, cliente: TestClient, token: str) -> "SesionMcp":
        sesion = cls(cliente, token)
        inicio = sesion.pedir_crudo(
            "initialize",
            {"protocolVersion": VERSION_DEL_PROTOCOLO, "capabilities": {}, "clientInfo": {"name": "pruebas", "version": "0"}},
            de_sesion=False,
        )
        assert inicio.status_code == 200, inicio.text
        sesion.sesion_id = inicio.headers["mcp-session-id"]
        aviso = cliente.post(
            "/mcp", headers=sesion.cabeceras(), json={"jsonrpc": "2.0", "method": "notifications/initialized"}
        )
        assert aviso.status_code == 202, aviso.text
        return sesion

    def cabeceras(self, token: str | None = None) -> dict[str, str]:
        return {
            **cabeceras_de(token or self.token),
            "mcp-session-id": self.sesion_id,
            "mcp-protocol-version": VERSION_DEL_PROTOCOLO,
        }

    def pedir_crudo(self, metodo: str, params: dict | None = None, de_sesion: bool = True, token: str | None = None):
        cuerpo: dict[str, Any] = {"jsonrpc": "2.0", "id": self._siguiente, "method": metodo}
        self._siguiente += 1
        if params is not None:
            cuerpo["params"] = params
        cabeceras = self.cabeceras(token) if de_sesion else cabeceras_de(token or self.token)
        return self.cliente.post("/mcp", headers=cabeceras, json=cuerpo)

    def pedir(self, metodo: str, params: dict | None = None) -> dict:
        respuesta = self.pedir_crudo(metodo, params)
        assert respuesta.status_code == 200, respuesta.text
        mensaje = mensaje_de(respuesta)
        assert "result" in mensaje, mensaje
        return mensaje["result"]

    def llamar(self, herramienta: str, argumentos: dict | None = None) -> str:
        """Texto que devuelve una herramienta."""
        return self.pedir("tools/call", {"name": herramienta, "arguments": argumentos or {}})["content"][0]["text"]

    def leer(self, uri: str) -> str:
        """Contenido de un recurso."""
        return self.pedir("resources/read", {"uri": uri})["contents"][0]["text"]

    def prompt(self, nombre: str, argumentos: dict | None = None) -> str:
        """Texto de un prompt."""
        return self.pedir("prompts/get", {"name": nombre, "arguments": argumentos or {}})["messages"][0]["content"]["text"]
