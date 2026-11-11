"""Cliente mínimo del transporte SSE (`/sse` + `/messages/`) para probar el servidor MCP sin levantar uvicorn.

El cliente de pruebas de Starlette espera a que la aplicación termine de responder antes de devolver la respuesta,
y un `GET /sse` no termina mientras dure la sesión. Por eso este cliente habla ASGI directo: deja el `GET` abierto
en una tarea, lee los eventos a medida que la aplicación los emite y manda cada `POST` como otro pedido ASGI.
No abre sockets ni espera por tiempo: cada lectura se desbloquea con el evento que llega.
"""

import json
import math
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import anyio

from aulento.mcp.server import BearerAuthMiddleware, create_study_mcp_server

HOST = "127.0.0.1:8000"
VERSION_DEL_PROTOCOLO = "2025-06-18"
ESPERA_MAXIMA_SEGUNDOS = 20


def aplicacion_mcp_sse(read_only: bool = False):
    """La misma aplicación ASGI que arma `run_sse_server` para el transporte sse."""
    app = create_study_mcp_server(read_only=read_only).sse_app(host="127.0.0.1")
    app.add_middleware(BearerAuthMiddleware)
    return app


def _scope(metodo: str, ruta: str, consulta: str, token: str | None, cliente: tuple[str, int]) -> dict[str, Any]:
    cabeceras = [(b"host", HOST.encode()), (b"accept", b"application/json, text/event-stream")]
    if metodo == "POST":
        cabeceras.append((b"content-type", b"application/json"))
    if token is not None:
        cabeceras.append((b"authorization", f"Bearer {token}".encode()))
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": metodo,
        "scheme": "http",
        "path": ruta,
        "raw_path": ruta.encode(),
        "query_string": consulta.encode(),
        "root_path": "",
        "headers": cabeceras,
        "client": cliente,
        "server": ("127.0.0.1", 8000),
    }


@dataclass
class SesionSse:
    """Sesión SSE abierta con el token de una cuenta; `eventos` entrega cada evento del servidor en orden."""

    app: Any
    token: str
    cliente: tuple[str, int]
    eventos: Any
    ruta_de_mensajes: str = ""
    _siguiente: int = field(default=1, repr=False)

    async def evento(self) -> tuple[str, str]:
        """El próximo evento del servidor (`tipo`, `datos`); falla si no llega ninguno."""
        with anyio.fail_after(ESPERA_MAXIMA_SEGUNDOS):
            return await self.eventos.receive()

    async def mensaje(self) -> dict:
        """El próximo mensaje JSON-RPC que el servidor manda por el flujo."""
        tipo, datos = await self.evento()
        assert tipo == "message", (tipo, datos)
        return json.loads(datos)

    async def publicar(self, cuerpo: dict, token: str | None = None, sin_token: bool = False) -> tuple[int, str]:
        """Manda un mensaje al `/messages/` de esta sesión, con el token propio o con otro; devuelve estado y cuerpo."""
        ruta, _, consulta = self.ruta_de_mensajes.partition("?")
        return await pedir(
            self.app, "POST", ruta, consulta, None if sin_token else (token or self.token), self.cliente, cuerpo
        )

    async def pedir(self, metodo: str, params: dict | None = None, token: str | None = None) -> tuple[int, int]:
        """Publica un pedido JSON-RPC y devuelve (estado HTTP, id del pedido); la respuesta llega por el flujo."""
        identificador = self._siguiente
        self._siguiente += 1
        cuerpo: dict[str, Any] = {"jsonrpc": "2.0", "id": identificador, "method": metodo}
        if params is not None:
            cuerpo["params"] = params
        estado, _ = await self.publicar(cuerpo, token=token)
        return estado, identificador

    async def iniciar(self) -> None:
        estado, identificador = await self.pedir(
            "initialize",
            {"protocolVersion": VERSION_DEL_PROTOCOLO, "capabilities": {}, "clientInfo": {"name": "pruebas", "version": "0"}},
        )
        assert estado == 202, estado
        inicio = await self.mensaje()
        assert inicio["id"] == identificador and "result" in inicio, inicio
        estado, _ = await self.publicar({"jsonrpc": "2.0", "method": "notifications/initialized"})
        assert estado == 202, estado

    async def llamar(self, herramienta: str, argumentos: dict | None = None) -> str:
        """Texto que devuelve una herramienta llamada con el token de la sesión."""
        estado, identificador = await self.pedir("tools/call", {"name": herramienta, "arguments": argumentos or {}})
        assert estado == 202, estado
        respuesta = await self.mensaje()
        assert respuesta["id"] == identificador and "result" in respuesta, respuesta
        return respuesta["result"]["content"][0]["text"]


async def pedir(
    app: Any, metodo: str, ruta: str, consulta: str, token: str | None, cliente: tuple[str, int], cuerpo: dict | None = None
) -> tuple[int, str]:
    """Un pedido ASGI completo (no de flujo): devuelve el estado y el cuerpo de la respuesta."""
    pendiente = [{"type": "http.request", "body": json.dumps(cuerpo).encode() if cuerpo is not None else b"", "more_body": False}]
    respuesta: dict[str, Any] = {"estado": 0, "cuerpo": b""}

    async def recibir() -> dict:
        return pendiente.pop() if pendiente else {"type": "http.disconnect"}

    async def enviar(mensaje: dict) -> None:
        if mensaje["type"] == "http.response.start":
            respuesta["estado"] = mensaje["status"]
        elif mensaje["type"] == "http.response.body":
            respuesta["cuerpo"] += mensaje.get("body", b"")

    with anyio.fail_after(ESPERA_MAXIMA_SEGUNDOS):
        await app(_scope(metodo, ruta, consulta, token, cliente), recibir, enviar)
    return respuesta["estado"], respuesta["cuerpo"].decode("utf-8", errors="replace")


@asynccontextmanager
async def sesion_sse(app: Any, token: str, cliente: tuple[str, int] = ("203.0.113.9", 40000)):
    """Abre `GET /sse` con el token, espera el evento `endpoint` y entrega la sesión; al salir corta la conexión."""
    escritor, lector = anyio.create_memory_object_stream[tuple[str, str]](math.inf)
    cortar = anyio.Event()
    estado: dict[str, Any] = {"http": 0, "resto": ""}

    async def recibir() -> dict:
        await cortar.wait()
        return {"type": "http.disconnect"}

    async def enviar(mensaje: dict) -> None:
        if mensaje["type"] == "http.response.start":
            estado["http"] = estado["http"] or mensaje["status"]
            return
        if mensaje["type"] != "http.response.body" or cortar.is_set():
            return
        texto = estado["resto"] + mensaje.get("body", b"").decode("utf-8").replace("\r\n", "\n")
        *completos, estado["resto"] = texto.split("\n\n")
        for bloque in completos:
            campos = dict(linea.split(": ", 1) for linea in bloque.split("\n") if ": " in linea and not linea.startswith(":"))
            if "event" in campos:
                escritor.send_nowait((campos["event"], campos.get("data", "")))

    async def conexion() -> None:
        try:
            await app(_scope("GET", "/sse", "", token, cliente), recibir, enviar)
        except Exception:
            # Cortada la conexión, lo que el servidor haga al cerrar su lado no es parte de la prueba
            if not cortar.is_set():
                raise

    async with escritor, lector, anyio.create_task_group() as tareas:
        tareas.start_soon(conexion)
        sesion = SesionSse(app=app, token=token, cliente=cliente, eventos=lector)
        try:
            tipo, datos = await sesion.evento()
            assert (estado["http"], tipo) == (200, "endpoint"), (estado["http"], tipo, datos)
            sesion.ruta_de_mensajes = datos
            yield sesion
        finally:
            # El cliente se desconecta y el servidor cierra su lado; si no lo hiciera, la tarea se cancela
            cortar.set()
            tareas.cancel_scope.deadline = anyio.current_time() + ESPERA_MAXIMA_SEGUNDOS
