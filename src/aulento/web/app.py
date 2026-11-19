"""Aplicación central FastAPI para la interfaz web local de Aulento."""

import ipaddress
import logging
import os
import re
import sqlite3
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from aulento.auth.dependencias import usuario_actual
from aulento.config import is_local_mode, is_saas_mode
from aulento.core.exposicion import (
    exigir_modo_compatible_con_la_exposicion,
    proxies_de_confianza,
)
from aulento.core.extensiones import (
    Extension,
    aplicar_migraciones_de_extension,
    insertar_etiquetas,
    registrar_extensiones,
    validar_extensiones,
)
from aulento.core.gemini_gateway import MENSAJE_CLAVE_ILEGIBLE, SECRETOS_DE_CLAVES
from aulento.core.ia.tipos import (
    CapacidadNoSoportada,
    ClaveRechazada,
    CuotaAgotada,
    FaltaClaveDeIA,
    FaltaElegirModelo,
    IANoDisponibleError,
    ModeloInexistente,
    PedidoInvalido,
)
from aulento.core.identity import (
    LocalIdentityProvider,
    SinProveedorDeIdentidad,
    obtener_proveedor_de_identidad,
)
from aulento.core.permisos import AccionNoPermitida
from aulento.core.registro import abrir_registro_local, cerrar_registro_local
from aulento.core.secretos import (
    MENSAJE_CLAVE_MAESTRA_INVALIDA,
    MENSAJE_SECRETO_ILEGIBLE,
    ClaveMaestraInvalida,
    SecretoIlegible,
)
from aulento.vault.rutas import (
    MENSAJE_NOTA_NO_ENCONTRADA,
    RutaFueraDelVaultError,
    VaultNoDisponibleError,
)
from aulento.web.dependencies import get_db_connection
from aulento.web.routes.activity import router as activity_router
from aulento.web.routes.analytics import router as analytics_router
from aulento.web.routes.books import router as books_router
from aulento.web.routes.capacidades import router as capacidades_router
from aulento.web.routes.cuenta import router as cuenta_router
from aulento.web.routes.diagnostics import router as diagnostics_router
from aulento.web.routes.duolingo import router as duolingo_router
from aulento.web.routes.exams import router as exams_router
from aulento.web.routes.focus import router as focus_router
from aulento.web.routes.fsrs import router as fsrs_router
from aulento.web.routes.hub import router as hub_router
from aulento.web.routes.hub import router_webhook as hub_webhook_router
from aulento.web.routes.ia import router as ia_router
from aulento.web.routes.macro_fsrs import router as macro_fsrs_router
from aulento.web.routes.materiales import router as materiales_router
from aulento.web.routes.mcp import router as mcp_router
from aulento.web.routes.onboarding import router as onboarding_router
from aulento.web.routes.planner import router as planner_router
from aulento.web.routes.roadmap import router as roadmap_router
from aulento.web.routes.schedule import feed_publico as schedule_feed_publico
from aulento.web.routes.schedule import router as schedule_router
from aulento.web.routes.vault import router as vault_router
from aulento.web.routes.vectors import router as vectors_router

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

# Los documentos de la pestaña de documentación: clave → (título, archivo). Se escriben en `docs/`;
# instalada como paquete (wheel o imagen de la nube), la app no tiene `docs/` y el build los copia a
# `aulento/documentos/` (ver `setup.py`, que repite los nombres de archivo).
DOCUMENTOS_DE_LA_APP: dict[str, tuple[str, str]] = {
    "manual": ("Manual de Usuario: Interfaz Web de Aulento", "MANUAL_DE_USUARIO.md"),
    "api": ("Referencia de la API REST", "REFERENCIA_API.md"),
    "mcp": ("Guía del Servidor MCP y Conectores", "GUIA_MCP.md"),
    "cli": ("Referencia de la CLI de Aulento", "REFERENCIA_CLI.md"),
}
DOCUMENTOS_EMPAQUETADOS = Path(__file__).resolve().parents[1] / "documentos"
DOCUMENTOS_DEL_REPO = Path(__file__).resolve().parents[3] / "docs"

RUTA_DE_INGRESO = "/login"
CAMPOS_PUBLICOS_DE_VALIDACION = ("type", "loc", "msg")

DEFAULT_ALLOWED_ORIGINS = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://127.0.0.1:8001",
    "http://localhost:8001",
    "http://127.0.0.1:8080",
    "http://localhost:8080",
]

DEFAULT_ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
    "*.localhost",
    "[::1]",
    "testserver",
]


def ruta_del_documento(nombre: str) -> Path | None:
    """Dónde está un documento de la app: la copia del paquete, el repo o `docs/` de la carpeta de trabajo."""
    for carpeta in (DOCUMENTOS_EMPAQUETADOS, DOCUMENTOS_DEL_REPO, Path("docs")):
        ruta = carpeta / nombre
        if ruta.is_file():
            return ruta
    logger.warning("No se encontró el documento %s: la app muestra el texto de reemplazo", nombre)
    return None


def leer_documento(nombre: str) -> str | None:
    """El texto del documento sin el frontmatter, o None si no está."""
    ruta = ruta_del_documento(nombre)
    if ruta is None:
        return None
    return re.sub(r"^---\r?\n[\s\S]*?\r?\n---\r?\n?", "", ruta.read_text(encoding="utf-8")).lstrip()


def get_allowed_origins() -> list[str]:
    """Obtiene la lista de orígenes permitidos desde configuración o defaults locales."""
    env_origins = os.getenv("AULENTO_ALLOWED_ORIGINS", "")
    if env_origins.strip():
        extra = [o.strip() for o in env_origins.split(",") if o.strip()]
        return DEFAULT_ALLOWED_ORIGINS + extra
    return DEFAULT_ALLOWED_ORIGINS


def get_allowed_hosts() -> list[str]:
    """Obtiene los hosts permitidos para mitigar ataques de DNS Rebinding y Host Header."""
    env_hosts = os.getenv("AULENTO_ALLOWED_HOSTS", "")
    if env_hosts.strip():
        extra = [h.strip() for h in env_hosts.split(",") if h.strip()]
        return DEFAULT_ALLOWED_HOSTS + extra
    return DEFAULT_ALLOWED_HOSTS


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inyecta cabeceras de seguridad HTTP defensivas para mitigar ataques web."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/mcp"):
            return await call_next(request)
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        path = request.url.path
        if path.endswith("/interactive-map"):
            response.headers["X-Frame-Options"] = "SAMEORIGIN"
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; "
                "font-src 'self' data:; "
                "connect-src 'self'; "
                "img-src 'self' data: blob: https:; "
                "media-src 'self' data: blob:; "
                "worker-src 'self' blob:; "
                "object-src 'none'; "
                "base-uri 'self'; "
                "frame-ancestors 'self'; "
                "form-action 'self';"
            )
        elif path.startswith(("/docs", "/redoc")) or path == "/openapi.json":
            # Swagger UI y ReDoc cargan sus bundles, CSS y favicon desde cdn.jsdelivr.net y fastapi.tiangolo.com
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com data:; "
                "connect-src 'self'; "
                "img-src 'self' data: https: https://fastapi.tiangolo.com; "
                "worker-src 'self' blob:; "
                "object-src 'none'; "
                "base-uri 'self'; "
                "frame-ancestors 'none'; "
                "form-action 'self';"
            )
        else:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; "
                "font-src 'self'; "
                "connect-src 'self'; "
                "img-src 'self' data: https:; "
                "media-src 'self' data: blob:; "
                "object-src 'none'; "
                "base-uri 'self'; "
                "frame-ancestors 'none'; "
                "form-action 'self';"
            )
        if path.startswith("/static/") and path.endswith(EXTENSIONES_DE_MEDIOS_CACHEABLES):
            # Videos e imágenes pesados: se cachean un día para no bajarlos de
            # nuevo en cada vuelta de la vitrina ni en cada visita.
            response.headers["Cache-Control"] = "public, max-age=86400"
        elif path == "/" or path == RUTA_DE_INGRESO or path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


CLIENTES_DE_PRUEBA = frozenset({"testclient", "testserver"})
EXTENSIONES_DE_MEDIOS_CACHEABLES = (".webm", ".mp4", ".webp")


def es_cliente_del_propio_equipo(host: str | None) -> bool:
    """Indica si el pedido viene de esta misma máquina (bucle local) o del cliente de pruebas de Starlette."""
    if not host:
        return False
    if host in CLIENTES_DE_PRUEBA:
        return True
    try:
        direccion = ipaddress.ip_address(host)
    except ValueError:
        return False
    mapeada = getattr(direccion, "ipv4_mapped", None)
    return (mapeada or direccion).is_loopback


class SoloElPropioEquipoEnModoLocal(BaseHTTPMiddleware):
    """En modo local no hay login: rechaza con 403 a todo cliente que no sea esta misma máquina (ADR 017).

    Es la red de seguridad para cuando Uvicorn se lanza a mano en otra interfaz (`--host 0.0.0.0`) sin la CLI,
    que ya se niega. No cubre un túnel que corra en la misma máquina: ese llega desde 127.0.0.1.
    """

    async def dispatch(self, request: Request, call_next):
        if is_local_mode():
            host = request.client.host if request.client else None
            if not es_cliente_del_propio_equipo(host):
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "El modo local solo atiende a esta máquina. Para abrirlo a otros equipos usá "
                        "AULENTO_MODE=saas."
                    },
                )
        return await call_next(request)


def _propio_origen(request: Request) -> str | None:
    """El origen del propio servidor tal como lo escribe un navegador: minúsculas y sin el puerto por defecto."""
    host = (request.headers.get("host") or "").strip().lower()
    if not host:
        return None
    esquema = request.url.scheme.lower()
    puerto_por_defecto = {"http": ":80", "https": ":443"}.get(esquema)
    if puerto_por_defecto and host.endswith(puerto_por_defecto):
        host = host[: -len(puerto_por_defecto)]
    return f"{esquema}://{host}"


class LocalOriginAuthMiddleware(BaseHTTPMiddleware):
    """Valida que peticiones cross-origin del navegador provengan únicamente de orígenes locales autorizados o del propio host."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/mcp"):
            return await call_next(request)
        origin = request.headers.get("origin")
        if origin:
            allowed = get_allowed_origins()
            # El propio origen también vale: el navegador manda `Origin` en los POST de la misma página, y con otro
            # puerto (`--port 9000`) la lista fija lo rechazaría. Un sitio ajeno no puede hacerse pasar por él; el DNS
            # rebinding, que sí podría, llega con un `Host` ajeno y lo frena `TrustedHostMiddleware`.
            if origin not in allowed and origin != _propio_origen(request):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Forbidden: cross-origin request not permitted from this origin"},
                )

        # Bloquear mutaciones de estado cross-site iniciadas por navegadores modernos
        sec_fetch_site = request.headers.get("sec-fetch-site")
        if sec_fetch_site == "cross-site" and request.method in ("POST", "PUT", "DELETE", "PATCH"):
            return JSONResponse(
                status_code=403,
                content={"detail": "Forbidden: cross-site state mutation blocked"},
            )

        return await call_next(request)


class McpPathMiddleware:
    """Asegura que las peticiones a /mcp sin barra final entren directo a la sub-aplicación sin redirección 307."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] == "http" and scope["path"] == "/mcp":
            scope = dict(scope)
            scope["path"] = "/mcp/"
        await self.app(scope, receive, send)


class McpDispatcherApp:
    """Despacha peticiones a la sub-aplicación ASGI MCP activa en app.state."""

    def __init__(self, web_app: FastAPI) -> None:
        self.web_app = web_app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        mcp_app = getattr(self.web_app.state, "mcp_app", None)
        if mcp_app is not None:
            await mcp_app(scope, receive, send)
            return
        # Sin servidor MCP listo: respuesta explícita en lugar de dejar el pedido colgado
        await JSONResponse({"detail": "El servidor MCP no está disponible."}, status_code=503)(scope, receive, send)


from contextlib import asynccontextmanager


@asynccontextmanager
async def app_lifespan(fastapi_app: FastAPI):
    """Migra la base (la del core y las tablas de cada extensión) y conecta las suscripciones de las extensiones.

    No siembra datos: eso lo pide una cuenta. En modo local se niega a arrancar si hay un proxy público delante.
    """
    from aulento.db.connection import get_connection
    from aulento.db.migrations import ErrorDeMigracion
    from aulento.db.schema import init_db

    exigir_modo_compatible_con_la_exposicion()
    extensiones: Sequence[Extension] = getattr(fastapi_app.state, "extensiones", ())

    conn = get_connection()
    try:
        init_db(conn)
        for extension in extensiones:
            aplicar_migraciones_de_extension(conn, extension)
        for extension in extensiones:
            for al_arrancar in extension.al_arrancar:
                al_arrancar(conn)
        if not is_saas_mode():
            # La cuenta local (y la importación de los archivos anteriores) se prepara al arrancar, no en el primer
            # pedido de la página, que llega junto con muchos otros (051, R7)
            LocalIdentityProvider(conn).get_usuario()
    except ErrorDeMigracion as error:
        logger.critical("El servidor no arranca: %s", error)
        raise
    finally:
        conn.close()

    desregistrar = registrar_extensiones(extensiones)

    server = getattr(fastapi_app.state, "mcp_server", None)
    if server is None or getattr(server.session_manager, "_has_started", False):
        from aulento.mcp.server import create_mcp_asgi_app

        allowed_hosts = getattr(fastapi_app.state, "mcp_allowed_hosts", None)
        server, sub_app = create_mcp_asgi_app(allowed_hosts=allowed_hosts)
        fastapi_app.state.mcp_server = server
        fastapi_app.state.mcp_app = sub_app

    registro = None
    try:
        # En local, lo que se avisa queda en un archivo que lee el diagnóstico (051, R9). Si no se puede abrir (la
        # carpeta es de solo lectura, otro proceso lo tiene tomado), el servidor arranca igual: es solo diagnóstico.
        if not is_saas_mode():
            try:
                registro = abrir_registro_local()
            except OSError as error:
                logger.warning("No se pudo abrir el archivo de registro local: %s", error)
        async with server.session_manager.run():
            yield
    finally:
        desregistrar()
        if registro is not None:
            cerrar_registro_local(registro)


async def responder_accion_no_permitida(request: Request, exc: AccionNoPermitida) -> JSONResponse:
    """Una regla de una extensión negó la acción (062): 403 con su motivo; lo que la cuenta ya tenía no cambia."""
    return JSONResponse({"detail": exc.motivo}, status_code=403, headers={"X-Accion-No-Permitida": exc.accion})


async def responder_validacion_sin_datos_recibidos(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Responde 422 sin devolver nada de lo recibido: el cuerpo puede traer contraseñas o códigos."""
    detalle = [
        {campo: error[campo] for campo in CAMPOS_PUBLICOS_DE_VALIDACION if campo in error} for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(detalle)})


# Código HTTP de cada error de IA que llega a la web sin que la operación tenga un resultado sin IA.
# El primero que coincide manda; lo que no figura (red caída, proveedor caído, negativa del modelo) es 503.
ESTADO_POR_ERROR_DE_IA: tuple[tuple[type[IANoDisponibleError], int], ...] = (
    # Falta cargar algo: el mismo 503 con `detail` que la interfaz ya muestra sin IA
    (FaltaClaveDeIA, 503),
    (FaltaElegirModelo, 503),
    # La configuración de IA de la cuenta no sirve para este pedido: hay que corregirla en Configuración
    (ClaveRechazada, 409),
    (ModeloInexistente, 409),
    (PedidoInvalido, 409),
    (CapacidadNoSoportada, 409),
    (CuotaAgotada, 429),
)
ESTADO_DE_IA_NO_DISPONIBLE = 503


def estado_de_error_de_ia(error: IANoDisponibleError) -> int:
    """El código HTTP con el que se responde un error de IA."""
    return next((estado for tipo, estado in ESTADO_POR_ERROR_DE_IA if isinstance(error, tipo)), ESTADO_DE_IA_NO_DISPONIBLE)


async def responder_ia_no_disponible(request: Request, exc: IANoDisponibleError) -> JSONResponse:
    """Una operación que exige IA no la tuvo: el código del caso y, en `detail`, el mensaje propio del error.

    El mensaje ya viene sin la clave y sin el texto de la respuesta del proveedor.
    """
    return JSONResponse(status_code=estado_de_error_de_ia(exc), content={"detail": str(exc)})


async def responder_secreto_ilegible(request: Request, exc: SecretoIlegible) -> JSONResponse:
    """Un secreto guardado no se pudo descifrar: se dice eso, no «sin clave» ni un 500 sin explicación."""
    if exc.nombre in SECRETOS_DE_CLAVES:
        detalle = MENSAJE_CLAVE_ILEGIBLE
    else:
        detalle = MENSAJE_SECRETO_ILEGIBLE
    logger.warning("Secreto ilegible: «%s» de la cuenta %s.", exc.nombre, exc.user_id)
    return JSONResponse(status_code=503, content={"detail": detalle})


async def responder_clave_maestra_invalida(request: Request, exc: ClaveMaestraInvalida) -> JSONResponse:
    """La clave maestra del servidor está mal formada: 503 que dice cómo se resuelve, sin la clave ni su ubicación."""
    logger.error("%s", exc)
    return JSONResponse(status_code=503, content={"detail": MENSAJE_CLAVE_MAESTRA_INVALIDA})


async def responder_ruta_fuera_del_vault(request: Request, exc: RutaFueraDelVaultError) -> JSONResponse:
    """Una ruta, identificador o nombre de nota que sale del vault de la cuenta: 404, como una nota que no existe."""
    return JSONResponse(status_code=404, content={"detail": MENSAJE_NOTA_NO_ENCONTRADA})


async def responder_vault_no_disponible(request: Request, exc: VaultNoDisponibleError) -> JSONResponse:
    """La carpeta que la cuenta fijó como vault externo ya no existe: se dice eso y no se usa otro vault."""
    return JSONResponse(status_code=409, content={"detail": str(exc)})


ETIQUETAS_DE_LA_API: list[dict[str, str]] = [
    {
        "name": "Health",
        "description": "Comprobación de estado y disponibilidad del servidor.",
    },
    {
        "name": "Frontend",
        "description": "Páginas HTML principales de la aplicación web (ingreso y panel principal).",
    },
    {
        "name": "Cuenta",
        "description": "La cuenta que hace el pedido.",
    },
    {
        "name": "Onboarding",
        "description": "Diagnóstico de configuración y progreso del asistente de primer ingreso.",
    },
    {
        "name": "Hub",
        "description": "Gestión de plataformas académicas (Digital House, Coursera, etc.) y cursos de estudio.",
    },
    {
        "name": "Books",
        "description": "Seguimiento de lectura de libros técnicos (capítulos, páginas y porcentaje de avance).",
    },
    {
        "name": "Schedule",
        "description": "Cronograma de bloques horarios semanales, exportación iCalendar y enlaces de Google Calendar.",
    },
    {
        "name": "FSRS",
        "description": "Motor de repetición espaciada FSRS v5 para inglés técnico, pronunciación, audio y drills de consultoría.",
    },
    {
        "name": "Macro-FSRS",
        "description": "Repaso espaciado de alto nivel para temas completados del roadmap y micro-quizzes Feynman.",
    },
    {
        "name": "Actividad",
        "description": "Métricas de consistencia diaria, racha de estudio y mapa de calor de actividad.",
    },
    {
        "name": "Focus Timer",
        "description": "Temporizador de sesiones de estudio Pomodoro y registro de minutos estudiados.",
    },
    {
        "name": "Roadmaps",
        "description": "Rutas de aprendizaje, árbol de módulos/temas, grafo DAG de prelaciones y diseño pedagógico.",
    },
    {
        "name": "Vault",
        "description": "Integración con notas Markdown del vault de Obsidian, generación de apuntes y digest semanal.",
    },
    {
        "name": "Exams",
        "description": "Generación adaptativa de exámenes con Active Recall y evaluación conceptual con Técnica Feynman.",
    },
    {
        "name": "Duolingo",
        "description": "Sincronización de perfil de idioma, racha y experiencia (XP) con Duolingo.",
    },
    {
        "name": "IA & Providers",
        "description": "Gestión de proveedores de IA (Gemini, Anthropic, OpenAI), claves cifradas, modelos y pruebas de conexión.",
    },
    {
        "name": "Analytics & Config",
        "description": "Métricas de uso de tokens, costos estimados, logs de API y configuración de claves duales.",
    },
    {
        "name": "MCP",
        "description": "Tutor sobre los materiales de la cuenta (preguntas, apuntes y cosecha de tarjetas) y tokens MCP por cuenta.",
    },
    {
        "name": "Materiales",
        "description": "Materiales de estudio que cada cuenta sube desde la PC (PDF, Markdown y texto), con 200 MB por cuenta.",
    },
    {
        "name": "Vectors / Semantic Search",
        "description": "Base vectorial (PostgreSQL + pgvector), embeddings y búsqueda semántica de documentos y notas.",
    },
    {
        "name": "Planificador Adaptativo",
        "description": "Motor de recomendación y planificación adaptativa de estudio diario y semanal balanceando FSRS, Deep Work y Lectura Activa.",
    },
    {
        "name": "Diagnostics",
        "description": "Diagnóstico del motor, comprobaciones de salud del sistema, logs y exportación de reportes.",
    },
]

DESCRIPCION_DE_LA_API = (
    "Sistema Maestro de Estudio Inteligente (Local First): Hub de plataformas, FSRS v5 de inglés técnico, "
    "tracking de lectura, rutas pedagógicas DAG, materiales subidos desde la PC con un tutor, servidor MCP y búsqueda semántica.\n\n"
    "### Una sola persona, en esta máquina\n"
    "El core es monousuario y no tiene ingreso: atiende solo a esta misma máquina y todo pedido es de la cuenta local. "
    "Las rutas que reciben datos de otras apps (webhooks de libros y cursos, feed del calendario, servidor MCP) se "
    "autentican con su propio token en un encabezado o en la ruta.\n\n"
    "### Seguridad y Defensa de Origen\n"
    "Las operaciones mutantes (`POST`, `PUT`, `DELETE`, `PATCH`) validan la cabecera `Origin` o `Sec-Fetch-Site` para evitar ataques "
    "CSRF cross-site.\n\n"
    "Para detalles completos de cada endpoint, códigos de error y ejemplos de uso, consultá [docs/REFERENCIA_API.md](docs/REFERENCIA_API.md)."
)


def create_app(extensiones: Sequence[Extension] = ()) -> FastAPI:
    """Crea la aplicación con sus routers y su interfaz; `extensiones` le suma lo de otros paquetes (ADR 017)."""
    extensiones = tuple(extensiones)
    validar_extensiones(extensiones)
    etiquetas = list(ETIQUETAS_DE_LA_API)
    for extension in extensiones:
        etiquetas.extend(dict(etiqueta) for etiqueta in extension.etiquetas_openapi)
    if is_saas_mode() and not any(extension.identidad is not None for extension in extensiones):
        raise SinProveedorDeIdentidad()
    descripcion = next(
        (extension.descripcion_openapi for extension in extensiones if extension.descripcion_openapi),
        DESCRIPCION_DE_LA_API,
    )
    web_app = FastAPI(
        title="Aulento API & Web Dashboard",
        description=descripcion,
        version="0.1.0",
        lifespan=app_lifespan,
        openapi_tags=etiquetas,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    web_app.state.extensiones = extensiones
    web_app.add_exception_handler(RequestValidationError, responder_validacion_sin_datos_recibidos)
    web_app.add_exception_handler(IANoDisponibleError, responder_ia_no_disponible)
    web_app.add_exception_handler(AccionNoPermitida, responder_accion_no_permitida)
    web_app.add_exception_handler(SecretoIlegible, responder_secreto_ilegible)
    web_app.add_exception_handler(ClaveMaestraInvalida, responder_clave_maestra_invalida)
    web_app.add_exception_handler(RutaFueraDelVaultError, responder_ruta_fuera_del_vault)
    web_app.add_exception_handler(VaultNoDisponibleError, responder_vault_no_disponible)
    for extension in extensiones:
        for tipo, manejador in extension.manejadores_de_excepciones.items():
            web_app.add_exception_handler(tipo, manejador)

    allowed_origins = get_allowed_origins()
    allowed_hosts = get_allowed_hosts()

    # Mitigación de DNS Rebinding y Host Header injection
    web_app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    # Reescribe /mcp a /mcp/ para evitar redirecciones 307
    web_app.add_middleware(McpPathMiddleware)

    # Middleware de cabeceras de seguridad y autenticación de origen local
    web_app.add_middleware(SecurityHeadersMiddleware)
    web_app.add_middleware(LocalOriginAuthMiddleware)
    web_app.add_middleware(SoloElPropioEquipoEnModoLocal)

    # CORS restringido a orígenes locales confiables
    web_app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["Mcp-Session-Id"],
    )

    # El más externo (el último que se agrega): hosts permitidos, freno de intentos y cookie ven la dirección
    # y el esquema reales, pero solo si el pedido llega desde un proxy declarado en AULENTO_TRUSTED_PROXIES
    proxies = proxies_de_confianza()
    if proxies:
        web_app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=proxies)

    # Todo router de datos cuelga de este: ninguna de sus rutas responde sin sesión
    con_sesion = APIRouter(dependencies=[Depends(usuario_actual)])
    con_sesion.include_router(hub_router)
    con_sesion.include_router(schedule_router)
    con_sesion.include_router(fsrs_router)
    con_sesion.include_router(mcp_router)
    con_sesion.include_router(vault_router)
    con_sesion.include_router(exams_router)
    con_sesion.include_router(duolingo_router)
    con_sesion.include_router(focus_router)
    con_sesion.include_router(roadmap_router)
    con_sesion.include_router(analytics_router)
    con_sesion.include_router(activity_router)
    con_sesion.include_router(macro_fsrs_router)
    con_sesion.include_router(vectors_router)
    con_sesion.include_router(materiales_router)
    con_sesion.include_router(ia_router)
    con_sesion.include_router(onboarding_router)
    con_sesion.include_router(planner_router)
    con_sesion.include_router(diagnostics_router)
    con_sesion.include_router(capacidades_router)
    for extension in extensiones:
        for router in extension.routers:
            con_sesion.include_router(router)
    web_app.include_router(con_sesion)

    # Libros soporta sesión interactiva y webhooks con Bearer token / Atajos
    web_app.include_router(books_router)

    # Webhook universal de cursos (soporta Bearer token / Atajos)
    web_app.include_router(hub_webhook_router)

    # Feed del calendario: sin sesión, con su propio token de solo lectura en la URL (061)
    web_app.include_router(schedule_feed_publico)

    # Quién soy: la cuenta del pedido, según el proveedor de identidad
    web_app.include_router(cuenta_router)

    # Rutas públicas aportadas por las extensiones
    for extension in extensiones:
        for router in extension.routers_publicos:
            web_app.include_router(router)

    # Documentación interactiva, solo con sesión
    @web_app.get("/openapi.json", include_in_schema=False, dependencies=[Depends(usuario_actual)])
    def get_openapi_schema():
        """Devuelve el esquema OpenAPI de la aplicación."""
        return JSONResponse(web_app.openapi())

    @web_app.get("/docs", include_in_schema=False, dependencies=[Depends(usuario_actual)])
    def get_docs():
        """Sirve Swagger UI sobre el esquema protegido."""
        return get_swagger_ui_html(openapi_url="/openapi.json", title=f"{web_app.title} - Swagger UI")

    @web_app.get("/redoc", include_in_schema=False, dependencies=[Depends(usuario_actual)])
    def get_redoc():
        """Sirve ReDoc sobre el esquema protegido."""
        return get_redoc_html(openapi_url="/openapi.json", title=f"{web_app.title} - ReDoc")

    @web_app.get("/api/docs/manual", tags=["Frontend"], dependencies=[Depends(usuario_actual)])
    def get_user_manual(doc: str = "manual"):
        """Devuelve el contenido del documento solicitado en formato Markdown."""
        title, filename = DOCUMENTOS_DE_LA_APP.get(doc, ("Manual de Usuario", "MANUAL_DE_USUARIO.md"))
        contenido = leer_documento(filename)
        if contenido is not None:
            return {"doc": doc, "title": title, "content": contenido}
        return {"doc": doc, "title": title, "content": f"# {title}\n\nDocumentación en preparación."}

    @web_app.get("/manual", response_class=HTMLResponse, include_in_schema=False, dependencies=[Depends(usuario_actual)])
    def get_manual_standalone():
        """Sirve el Manual de Usuario como vista de lectura independiente."""
        import json
        clean_text = leer_documento("MANUAL_DE_USUARIO.md") or "# Manual de Usuario"
        # "</" escapado: el texto no puede cerrar el <script> en el que viaja
        content_json = json.dumps(clean_text).replace("</", "<\\/")
        html = f"""<!DOCTYPE html>
<html lang="es" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Manual de Usuario — Aulento</title>
  <link rel="stylesheet" href="/static/css/tailwind.css">
  <script src="/static/vendor/marked.min.js"></script>
  <script src="/static/vendor/purify.min.js"></script>
  <style>
    body {{ background: #0b1120; color: #cbd5e1; font-family: ui-sans-serif, system-ui, sans-serif; }}
    .prose h1 {{ font-size: 1.875rem; font-weight: 800; color: #ffffff; margin-top: 1.5rem; margin-bottom: 0.75rem; border-bottom: 1px solid #1e293b; padding-bottom: 0.5rem; }}
    .prose h2 {{ font-size: 1.35rem; font-weight: 700; color: #38bdf8; margin-top: 1.5rem; margin-bottom: 0.5rem; }}
    .prose h3 {{ font-size: 1.1rem; font-weight: 600; color: #818cf8; margin-top: 1rem; margin-bottom: 0.25rem; }}
    .prose p {{ margin-bottom: 0.75rem; line-height: 1.625; }}
    .prose ul {{ list-style-type: disc; padding-left: 1.25rem; margin-bottom: 0.75rem; }}
    .prose li {{ margin-bottom: 0.25rem; }}
    .prose pre {{ background: #020617; border: 1px solid #1e293b; border-radius: 0.75rem; padding: 1rem; overflow-x: auto; font-family: monospace; font-size: 0.8125rem; margin-bottom: 1rem; color: #e2e8f0; }}
    .prose code {{ background: #0f172a; border: 1px solid #1e293b; border-radius: 0.375rem; padding: 0.125rem 0.375rem; font-family: monospace; font-size: 0.85em; color: #38bdf8; }}
    .prose blockquote {{ border-left: 3px solid #38bdf8; padding-left: 1rem; font-style: italic; color: #94a3b8; }}
  </style>
</head>
<body class="min-h-screen p-4 sm:p-8">
  <div class="max-w-4xl mx-auto space-y-6">
    <div class="flex items-center justify-between pb-4 border-b border-slate-800">
      <div class="flex items-center gap-3">
        <a href="/" class="p-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 transition text-sm flex items-center gap-1.5 border border-slate-700">
          <span>←</span> Volver al Sistema
        </a>
        <h1 class="text-xl font-bold text-white">Manual de Usuario</h1>
      </div>
      <div class="flex items-center gap-2 text-xs">
        <a href="/docs" target="_blank" class="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-sky-400 font-semibold border border-slate-700">📚 Swagger API</a>
        <a href="/redoc" target="_blank" class="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-indigo-400 font-semibold border border-slate-700">📑 ReDoc</a>
      </div>
    </div>
    <div id="manual-content" class="prose bg-slate-900 border border-slate-800 rounded-3xl p-6 sm:p-10 shadow-2xl">
      Cargando manual...
    </div>
  </div>
  <script>
    const raw = {content_json};
    document.getElementById('manual-content').innerHTML = DOMPurify.sanitize(marked.parse(raw));
  </script>
</body>
</html>"""
        return HTMLResponse(html)

    # Endpoint de salud
    cache_salud: dict[str, tuple[float, dict[str, Any]]] = {}

    @web_app.get("/api/health", tags=["Health"])
    def health_check():
        ahora = time.monotonic()
        res = {"status": "ok", "app": "aulento", "version": "0.1.0"}
        for extension in extensiones:
            if extension.salud is not None:
                expira, cached = cache_salud.get(extension.nombre, (0.0, {}))
                if ahora < expira:
                    info = cached
                else:
                    try:
                        info = dict(extension.salud())
                    except Exception as err:  # noqa: BLE001
                        logger.warning("Fallo al consultar salud de extensión %s: %s", extension.nombre, err)
                        info = {}
                    cache_salud[extension.nombre] = (ahora + 30.0, info)
                for k, v in info.items():
                    if k != "status":
                        res[k] = v
        return res

    # Servidor MCP montado en /mcp (058)
    from aulento.mcp.server import create_mcp_asgi_app

    web_app.state.mcp_allowed_hosts = allowed_hosts
    mcp_server, mcp_asgi_app = create_mcp_asgi_app(allowed_hosts=allowed_hosts)
    web_app.state.mcp_server = mcp_server
    web_app.state.mcp_app = mcp_asgi_app
    web_app.mount("/mcp", McpDispatcherApp(web_app))

    # Los estáticos de cada extensión van antes que /static: Starlette usa el primer montaje que coincide
    for extension in extensiones:
        if extension.estaticos is not None:
            web_app.mount(
                extension.prefijo_de_estaticos,
                StaticFiles(directory=str(extension.estaticos)),
                name=f"static-ext-{extension.nombre}",
            )

    # Montaje de archivos estáticos si la carpeta existe
    if STATIC_DIR.exists():
        web_app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Servir la SPA en el root; en saas exige sesión, en local ingresa directo
    @web_app.get("/", response_class=HTMLResponse, tags=["Frontend"])
    def get_index(request: Request, conn: Annotated[sqlite3.Connection, Depends(get_db_connection)]):
        """Sirve la aplicación. En SaaS redirige al login a quien no tiene sesión; en local pasa directo."""
        if is_saas_mode() and obtener_proveedor_de_identidad(request, conn).get_usuario_opcional() is None:
            for extension in extensiones:
                if extension.portada is not None and extension.portada.is_file():
                    return FileResponse(
                        str(extension.portada),
                        media_type="text/html",
                        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
                    )
            return RedirectResponse(RUTA_DE_INGRESO, status_code=303)

        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            contenido = index_file.read_text(encoding="utf-8")
            contenido = insertar_etiquetas(contenido, extensiones)
            modo_actual = "saas" if is_saas_mode() else "local"
            contenido = contenido.replace("<body", f'<body data-modo="{modo_actual}"', 1)

            return HTMLResponse(
                contenido,
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )

        return HTMLResponse(
            "<h1>Aulento</h1><p>Frontend estático en preparación en <code>/static/index.html</code></p>"
        )

    return web_app


_app: FastAPI | None = None


def __getattr__(nombre: str):
    """`app` se arma la primera vez que alguien lo pide (`uvicorn aulento.web.app:app`), no al importar el módulo.

    Así importar el core en modo multiusuario (lo hace la extensión que lo arranca) no exige una identidad; pedir
    la app del core sola en ese modo sí, y frena con `SinProveedorDeIdentidad`.
    """
    global _app
    if nombre == "app":
        if _app is None:
            _app = create_app()
        return _app
    raise AttributeError(f"module {__name__!r} has no attribute {nombre!r}")
