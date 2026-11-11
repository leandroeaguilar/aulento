"""Router del tutor sobre los materiales de la cuenta y de los tokens del servidor MCP."""

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from aulento.auth import servicio
from aulento.auth.modelos import (
    PedidoTokenMcp,
    Resultado,
    TokenMcpCreado,
    TokenMcpListado,
    TokenMcpNoEncontrado,
)
from aulento.core.materiales import MaterialNoEncontrado
from aulento.mcp.agent import PreguntaAlTutor, RespuestaDelTutor
from aulento.vault.rutas import (
    exigir_nombre_de_nota,
    nombre_de_archivo_seguro,
    resolver_en_vault,
)
from aulento.web.dependencies import (
    Conexion,
    Cuenta,
    SinCuentaCompartida,
    TutorDeLaCuenta,
    VaultDeLaSesion,
    no_encontrado,
)

router = APIRouter(prefix="/api/mcp", tags=["MCP"])


# --- TOKENS DEL SERVIDOR MCP ---


@router.get("/tokens", response_model=list[TokenMcpListado], summary="Listar los tokens MCP de la cuenta")
def list_mcp_tokens(usuario: Cuenta, conn: Conexion):
    """Tokens con los que la cuenta de la sesión entra al servidor MCP por red; nunca incluye el token."""
    return [TokenMcpListado(**dict(fila)) for fila in servicio.listar_tokens_mcp(conn, usuario.id)]


HOSTS_LOCALES = {"127.0.0.1", "localhost", "::1"}


@router.get("/connection-info", summary="Datos para conectar un asistente al servidor MCP", dependencies=[SinCuentaCompartida])
def mcp_connection_info(usuario: Cuenta, request: Request) -> dict[str, Any]:
    """Lo que necesita la pantalla 'Conectar tu asistente' para armar la configuración lista para copiar.

    El modo local hace que el asistente arranque `aulento mcp serve` con este mismo Python y esta misma
    carpeta de datos, así que solo le sirve a quien está en la máquina del servidor: las rutas del servidor van
    únicamente a una cuenta administradora (una cuenta común nunca las recibe) y las demás se conectan por red.
    La clave maestra nunca viaja: solo se avisa si sale de una variable de entorno, porque el asistente también
    la necesita. Una cuenta compartida no lo ve.
    """
    import os
    import sys

    from aulento.auth.modelos import ROL_ADMIN
    from aulento.config import (
        VARIABLE_DEL_DIRECTORIO_DE_DATOS,
        get_data_dir,
        get_db_path,
    )
    from aulento.core.secretos import VARIABLE_DE_LA_CLAVE_MAESTRA

    nombre = request.url.hostname or "127.0.0.1"
    host = f"[{nombre}]" if ":" in nombre else nombre
    puerto = request.url.port or (443 if request.url.scheme == "https" else 80)
    url_base = str(request.base_url).rstrip("/")
    datos: dict[str, Any] = {
        "usuario": usuario.nombre_usuario,
        "local_disponible": usuario.rol == ROL_ADMIN,
        "puerto_red": puerto,
        # El mismo origen con el que se abrió la app web
        "url_red": f"{url_base}/mcp",
        "host_red": host,
        "red_remota": nombre not in HOSTS_LOCALES,
    }
    if usuario.rol != ROL_ADMIN:
        return datos

    directorio_de_datos = get_data_dir()
    variables = {VARIABLE_DEL_DIRECTORIO_DE_DATOS: str(directorio_de_datos)}
    if get_db_path() != directorio_de_datos / "study_engine.db":
        variables["AULENTO_DB_PATH"] = str(get_db_path())
    return {
        **datos,
        "python": sys.executable,
        "directorio": os.getcwd(),
        "variables": variables,
        "clave_maestra_por_variable": bool(os.environ.get(VARIABLE_DE_LA_CLAVE_MAESTRA)),
        "variable_de_la_clave_maestra": VARIABLE_DE_LA_CLAVE_MAESTRA,
    }


@router.post("/tokens", response_model=TokenMcpCreado, status_code=201, summary="Crear un token MCP para la cuenta", dependencies=[SinCuentaCompartida])
def create_mcp_token(usuario: Cuenta, conn: Conexion, data: PedidoTokenMcp | None = None):
    """Crea un token MCP de la cuenta de la sesión. Es la única respuesta que lo lleva en claro."""
    emitido = servicio.crear_token_mcp(conn, usuario.id, data.nombre if data else None)
    return TokenMcpCreado(id=emitido.id, token=emitido.token, nombre=emitido.nombre, creado_en=emitido.creado_en)


@router.delete("/tokens/{token_id}", response_model=Resultado, summary="Revocar un token MCP de la cuenta", dependencies=[SinCuentaCompartida])
def revoke_mcp_token(token_id: int, usuario: Cuenta, conn: Conexion):
    """Revoca un token de la cuenta de la sesión; uno ajeno, inexistente o ya revocado responde 404."""
    try:
        servicio.revocar_token_mcp(conn, token_id, usuario.id)
    except TokenMcpNoEncontrado:
        raise no_encontrado("Token", token_id) from None
    return Resultado()


# --- TUTOR SOBRE LOS MATERIALES DE LA CUENTA ---


@router.post("/agent/ask", response_model=RespuestaDelTutor)
def preguntar_al_tutor(data: PreguntaAlTutor, tutor: TutorDeLaCuenta):
    """Consulta al tutor sobre los materiales subidos y los fragmentos vectoriales de la cuenta.

    Un `material_id` de otra cuenta responde 404, igual que uno inexistente.
    """
    try:
        return tutor.ask(
            query=data.query,
            material_id=data.material_id,
            provider=data.provider,
            mode=data.mode or "explain",
            historial=data.historial,
        )
    except MaterialNoEncontrado as error:
        raise no_encontrado("Material", error.identificador) from None


class SaveAgentNoteRequest(BaseModel):
    title: str = Field(..., description="Título de la nota")
    content: str = Field(..., max_length=200_000, description="Contenido Markdown de la nota")
    folder: str | None = Field("Cloud Notes", description="Subcarpeta dentro de 04 Knowledge/Cursos/")


@router.post("/agent/save-note", dependencies=[SinCuentaCompartida])
def save_agent_note_to_vault(data: SaveAgentNoteRequest, vault: VaultDeLaSesion):
    """Guarda la nota sintetizada por el Agente en el vault de la cuenta de la sesión.

    Un título o una carpeta que en realidad son una ruta (con `..`, absoluta o con unidad) responden 404.
    """
    safe_folder = nombre_de_archivo_seguro(exigir_nombre_de_nota(data.folder or ""), "Cloud Notes")
    safe_filename = nombre_de_archivo_seguro(exigir_nombre_de_nota(data.title), "Nota Cloud")
    rel_path = f"04 Knowledge/Cursos/{safe_folder}/{safe_filename}.md"
    target = resolver_en_vault(vault, rel_path)

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(data.content, encoding="utf-8")

    return {
        "status": "saved",
        "relative_path": rel_path,
        "filename": f"{safe_filename}.md",
        "message": f"Apunte guardado exitosamente en '{rel_path}'",
    }


class HarvestAgentCardsRequest(BaseModel):
    concepts: list[str] = Field(default_factory=list, description="Lista de conceptos técnicos a convertir en flashcards")
    source: str | None = Field("Tutor de Aulento", description="Origen de los conceptos")
    sources: list[str] | None = Field(default=None, description="Fuentes citadas por el tutor")
    context: str | None = Field(default=None, description="Contexto de la respuesta del tutor")


@router.post("/agent/harvest-cards", dependencies=[SinCuentaCompartida])
def harvest_agent_cards_to_fsrs(data: HarvestAgentCardsRequest, usuario: Cuenta, conn: Conexion):
    """Cosecha conceptos del agente en el mazo FSRS v5 de la cuenta descartando sus duplicados."""
    from aulento.fsrs.harvester import HarvestCandidateCard, OmniHarvester
    from aulento.mcp.agent import TutorDeMateriales

    tutor = TutorDeMateriales(usuario.id)
    fuentes = data.sources or ([data.source] if data.source else [])
    tarjetas_dicts, is_fallback, motivo = tutor.generar_tarjetas(
        conceptos=data.concepts,
        fuentes=fuentes,
        contexto=data.context or "",
    )

    cards: list[HarvestCandidateCard] = [HarvestCandidateCard(**t) for t in tarjetas_dicts]

    if not cards:
        return {
            "harvested_count": 0,
            "total_submitted": 0,
            "duplicates": 0,
            "is_fallback": is_fallback,
            "rotulo": "sin IA" if is_fallback else None,
            "motivo_sin_ia": motivo if is_fallback else None,
        }

    # Solo deduplica y guarda: no lee el vault
    harvester = OmniHarvester()
    checked = harvester.check_duplicates(conn, usuario.id, cards)
    new_cards = [c for c in checked if not c.is_duplicate]
    count = harvester.commit_harvest(conn, usuario.id, new_cards) if new_cards else 0

    msg = f"Se cosecharon {count} tarjetas nuevas para FSRS (descartadas {len(cards) - count} duplicadas)."
    if is_fallback:
        msg += " [sin IA]"

    return {
        "harvested_count": count,
        "total_submitted": len(cards),
        "duplicates": len(cards) - count,
        "is_fallback": is_fallback,
        "rotulo": "sin IA" if is_fallback else None,
        "motivo_sin_ia": motivo if is_fallback else None,
        "message": msg,
    }

