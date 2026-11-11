"""Servidor MCP integrado para Aulento (materiales subidos, Rutas, Clases, Libros y FSRS)."""

import asyncio
import logging
from pathlib import Path
from typing import Any

import uvicorn
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from aulento.core.exposicion import proxies_de_confianza
from aulento.core.extensiones import validar_cuenta
from aulento.core.materiales import AlmacenDeMateriales, MaterialNoEncontrado
from aulento.db.connection import get_connection
from aulento.db.schema import create_schema
from aulento.mcp.copilot import register_copilot_tool
from aulento.mcp.prompts import register_mcp_prompts
from aulento.mcp.resources import register_mcp_resources
from aulento.mcp.security import (
    FrenoDeRechazos,
    cuenta_mcp_actual,
    fijar_cuenta_mcp,
    herramienta_auditada,
    log_mcp_tool_execution,
    registrar_rechazo_mcp,
    resolver_token_mcp,
    restablecer_cuenta_mcp,
    set_audit_client_ip,
    set_audit_transport,
)
from aulento.mcp.tools_books import register_book_tools
from aulento.mcp.tools_courses import register_course_tools
from aulento.mcp.tools_fsrs import register_fsrs_tools
from aulento.mcp.tools_lessons import register_lesson_tools
from aulento.mcp.tools_planner import register_planner_tools
from aulento.mcp.tools_schedule import register_schedule_tools
from aulento.mcp.tools_vectors import register_vector_tools

logger = logging.getLogger(__name__)

# Lo más que devuelve `materials_read` de un material, con consulta o sin ella
MAX_CARACTERES_POR_LECTURA = 40_000
MAX_MATERIALES_POR_BUSQUEDA = 10


def create_study_mcp_server(read_only: bool = False, db_path: Path | str | None = None) -> MCPServer:
    """Crea y configura la instancia del servidor MCP con todas las herramientas académicas de Aulento.
    
    Args:
        read_only: Si es True, desactiva todas las herramientas que modifican estado (create/update/delete).
        db_path: Ruta personalizada a la base de datos SQLite (útil en pruebas).
    """
    instructions = (
        "Servidor MCP oficial de Aulento (Sistema Maestro de Estudio Local-First).\n"
        "Permite buscar y leer los materiales de estudio que subió la cuenta, consultar rutas de aprendizaje,\n"
        "obtener el master prompt pedagógico de cada tema, generar y guardar clases magistrales completas\n"
        "con extracción de flashcards FSRS y sincronización canónica al Obsidian Vault, actualizar el progreso\n"
        "de cursos externos mediante enlaces y gestionar el avance de libros por páginas y capítulos."
    )
    if read_only:
        instructions += "\n[MODO ACTIVO: SOLO LECTURA (READ-ONLY)]"

    server = MCPServer(
        name="aulento",
        instructions=instructions,
    )
    try:
        conn = get_connection(db_path)
        try:
            create_schema(conn)
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        logger.error("No se pudo preparar el esquema de la base para el servidor MCP: %s", e)

    def materiales_de_la_cuenta() -> AlmacenDeMateriales:
        """Materiales subidos por la cuenta del pedido en curso."""
        return AlmacenDeMateriales.con_conexion_propia(cuenta_mcp_actual(), db_path)

    def auditar(tool_name: str, params: dict[str, Any], status: str = "success", error_message: str | None = None) -> None:
        log_mcp_tool_execution(tool_name, params, status=status, error_message=error_message, db_path=db_path)

    tool = herramienta_auditada(server, db_path)

    # --- Materiales subidos por la cuenta ---
    @tool()
    def materials_search(query: str) -> str:
        """Busca entre los materiales de estudio que la cuenta subió (PDF, Markdown y texto) por palabras clave.

        Args:
            query: Tema o palabras a buscar (ej. 'BigQuery', 'árboles de decisión').
        """
        encontrados = materiales_de_la_cuenta().buscar(query, limite=MAX_MATERIALES_POR_BUSQUEDA)
        auditar("materials_search", {"query": query, "results": len(encontrados)})
        if not encontrados:
            return f"No se encontraron materiales para la consulta: '{query}'."
        lines = [f"Encontrados {len(encontrados)} material(es):"]
        for material in encontrados:
            lines.append(
                f"- [{material['id']}] {material['nombre']} ({material['caracteres']} caracteres, "
                f"{material['puntaje']} coincidencias)"
            )
        lines.append("\nLeé uno con `materials_read(material_id, query)` para ver los pasajes que tratan el tema.")
        return "\n".join(lines)

    @tool()
    def materials_read(material_id: int, query: str | None = None) -> str:
        """Lee un material de la cuenta por su ID: con `query`, los pasajes que tratan ese tema; sin ella, el principio.

        Args:
            material_id: ID del material tal como lo devuelve `materials_search`.
            query: Tema opcional; si se da, se devuelven los pasajes relevantes de todo el texto.
        """
        params = {"material_id": material_id, "query": query}
        materiales = materiales_de_la_cuenta()
        try:
            material = materiales.obtener(material_id, con_texto=False)
            texto = materiales.fragmentos_relevantes(material_id, query or "", MAX_CARACTERES_POR_LECTURA)
        except MaterialNoEncontrado:
            auditar("materials_read", params, status="error", error_message="no encontrado")
            return f"Error: Material {material_id} no encontrado."
        auditar("materials_read", {**params, "name": material["nombre"]})
        if query:
            alcance = f"Pasajes sobre '{query}'"
        elif material["caracteres"] > len(texto):
            alcance = (
                f"Primeros {len(texto)} de {material['caracteres']} caracteres; "
                "pasá `query` para leer los pasajes de un tema"
            )
        else:
            alcance = "Texto completo"
        return "\n".join([f"# {material['nombre']}", f"**{alcance}:**\n", texto])

    # --- Registro Modular de Dominios Académicos ---
    register_lesson_tools(server, read_only=read_only, db_path=db_path)
    register_course_tools(server, read_only=read_only, db_path=db_path)
    register_book_tools(server, read_only=read_only, db_path=db_path)
    register_fsrs_tools(server, read_only=read_only, db_path=db_path)
    register_schedule_tools(server, read_only=read_only, db_path=db_path)
    register_planner_tools(server, read_only=read_only, db_path=db_path)
    register_copilot_tool(server, read_only=read_only, db_path=db_path)
    register_vector_tools(server, db_path=db_path)
    register_mcp_prompts(server)
    register_mcp_resources(server, db_path=db_path)

    return server


def run_stdio_server(user_id: int, read_only: bool = False, db_path: Path | str | None = None) -> None:
    """Ejecuta el servidor MCP conectado a stdio (modo seguro sin puertos de red), operando como `user_id`.

    La cuenta se fija una vez, antes de arrancar: todo el proceso sirve a esa cuenta.
    """
    set_audit_transport("stdio")
    marca = fijar_cuenta_mcp(user_id)
    try:
        server = create_study_mcp_server(read_only=read_only, db_path=db_path)
        asyncio.run(server.run_stdio_async())
    finally:
        restablecer_cuenta_mcp(marca)


class BearerAuthMiddleware:
    """Autenticación obligatoria por Bearer Token de una cuenta para los transportes de red.

    Resuelve el token contra los tokens MCP de las cuentas y fija la cuenta dueña durante el pedido:
    el SDK entrega a cada herramienta el contexto del pedido HTTP que trajo su mensaje, así que
    `cuenta_mcp_actual()` devuelve siempre la cuenta del token de ese mensaje. Además declara la
    cuenta como dueña de la sesión del transporte, que el SDK niega (404) a cualquier otra cuenta.

    Es un middleware ASGI puro: `BaseHTTPMiddleware` envuelve la respuesta y rompe la sesión SSE
    del SDK en cuanto un cliente real empieza a enviar mensajes.
    """

    def __init__(self, app: Any, db_path: Path | str | None = None, freno: FrenoDeRechazos | None = None) -> None:
        self.app = app
        self.db_path = db_path
        self.freno = freno or FrenoDeRechazos()

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        if request.method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        # Las herramientas del pedido auditan con esta IP
        client_ip = request.client.host if request.client else None
        set_audit_client_ip(client_ip)

        token = request.headers.get("Authorization")
        usuario = resolver_token_mcp(token, db_path=self.db_path)
        if usuario is None:
            motivo = "token inválido, revocado o de una cuenta desactivada" if token else "token ausente"
            # El 401 se responde siempre; lo que tiene tope es cuántos rechazos de una IP quedan escritos
            if self.freno.permite(client_ip):
                registrar_rechazo_mcp(motivo, client_ip=client_ip, db_path=self.db_path)
            response = JSONResponse(
                {
                    "error": "Unauthorized",
                    "detail": "Acceso denegado al servidor MCP de Aulento. Se requiere el Bearer Token vigente de una cuenta activa en el encabezado Authorization (se crea con `aulento mcp token create <usuario>`).",
                },
                status_code=401,
            )
            await response(scope, receive, send)
            return

        conn = get_connection(self.db_path)
        try:
            validar_cuenta(usuario, conn)
        except HTTPException as error:
            response = JSONResponse(
                {
                    "error": "Forbidden",
                    "detail": error.detail,
                },
                status_code=error.status_code,
            )
            await response(scope, receive, send)
            return
        finally:
            conn.close()

        scope["user"] = AuthenticatedUser(AccessToken(token="", client_id=f"cuenta:{usuario.id}", scopes=[]))
        marca = fijar_cuenta_mcp(usuario.id)
        try:
            await self.app(scope, receive, send)
        finally:
            restablecer_cuenta_mcp(marca)


HOSTS_LOCALES = ("127.0.0.1", "localhost", "[::1]")


def normalizar_host_permitido(valor: str) -> str:
    """Host tal como llega en la cabecera `Host`: minúsculas e IPv6 entre corchetes.

    Lanza `ValueError` si el valor trae esquema, ruta o espacios (se espera `mi-pc.local` o `10.0.0.5:8000`).
    """
    h = valor.strip().lower()
    if not h or "/" in h or " " in h or "@" in h:
        raise ValueError(f"Host permitido no válido: '{valor}'. Indicá solo el nombre o la IP, con puerto opcional.")
    if not h.startswith("[") and h.count(":") > 1:
        h = f"[{h}]"
    return h


def transport_security_for(allowed_hosts: list[str] | None) -> TransportSecuritySettings | None:
    """Protección de `Host`/`Origin` para una lista de hosts permitidos; None deja la del SDK.

    Los hosts locales se permiten siempre: lo que protege el acceso es el token, no el nombre del host.
    """
    hosts = [normalizar_host_permitido(h) for h in (allowed_hosts or []) if h and h.strip()]
    if not hosts:
        return None
    permitidos: list[str] = []
    origenes: list[str] = []
    for h in [*hosts, *HOSTS_LOCALES]:
        con_puerto = "]:" in h if h.startswith("[") else ":" in h
        for v in [h] if con_puerto else [h, f"{h}:*"]:
            if v not in permitidos:
                permitidos.append(v)
                origenes.extend([f"http://{v}", f"https://{v}"])
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=permitidos,
        allowed_origins=origenes,
    )


def create_mcp_asgi_app(
    read_only: bool = False,
    db_path: Path | str | None = None,
    allowed_hosts: list[str] | None = None,
) -> tuple[MCPServer, Any]:
    """Crea el servidor MCP y su aplicación ASGI Streamable HTTP lista para montar en /mcp."""
    server = create_study_mcp_server(read_only=read_only, db_path=db_path)
    seguridad = transport_security_for(allowed_hosts)
    app = server.streamable_http_app(streamable_http_path="/", transport_security=seguridad)
    app.add_middleware(BearerAuthMiddleware, db_path=db_path)
    proxies = proxies_de_confianza()
    if proxies:
        app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=proxies)
    return server, app


def run_sse_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    read_only: bool = False,
    db_path: Path | str | None = None,
    ssl_certfile: str | None = None,
    ssl_keyfile: str | None = None,
    allowed_hosts: list[str] | None = None,
    transport: str = "sse",
) -> None:
    """Ejecuta el servidor MCP por red con autenticación obligatoria por el Bearer Token de una cuenta.

    `transport` es "sse" (ruta `/sse`) o "http" (Streamable HTTP, ruta `/mcp`). Con `ssl_certfile`
    y `ssl_keyfile` sirve por HTTPS. Con `allowed_hosts` rechaza las peticiones cuyo `Host` no esté
    en la lista o cuyo `Origin` no corresponda a esos hosts.
    """
    if transport not in ("sse", "http"):
        raise ValueError(f"Transporte de red no reconocido: {transport}")
    set_audit_transport(transport)
    server = create_study_mcp_server(read_only=read_only, db_path=db_path)
    esquema = "https" if ssl_certfile else "http"
    ruta = "/sse" if transport == "sse" else "/mcp"
    print(f"🔒 Aulento MCP Server escuchando en {esquema}://{host}:{port}{ruta}")
    print("🔑 Cada cliente entra con el token de su cuenta: se crea con `aulento mcp token create <usuario>`.")

    seguridad = transport_security_for(allowed_hosts)
    if transport == "sse":
        app = server.sse_app(host=host, transport_security=seguridad)
    else:
        app = server.streamable_http_app(host=host, transport_security=seguridad)
    app.add_middleware(BearerAuthMiddleware, db_path=db_path)
    # El más externo: el token, el freno de rechazos y la auditoría ven la dirección real del cliente
    proxies = proxies_de_confianza()
    if proxies:
        app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=proxies)
    # Sin log de accesos: el token puede venir en la URL (?token=) y quedaría escrito.
    # Las cabeceras de proxy las resuelve la aplicación con AULENTO_TRUSTED_PROXIES, no Uvicorn.
    opciones: dict[str, Any] = {"host": host, "port": port, "access_log": False, "proxy_headers": False}
    if ssl_certfile and ssl_keyfile:
        opciones.update(ssl_certfile=ssl_certfile, ssl_keyfile=ssl_keyfile)
    uvicorn.run(app, **opciones)
