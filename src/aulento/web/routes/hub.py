"""Router para la gestión del Hub de Plataformas Académicas y Cursos."""

import os
import platform
import subprocess

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from aulento.connectors.course_sync import CourseSyncManager
from aulento.models.curso import Curso, CursoCreate, CursoUpdate, EstadoCurso
from aulento.models.plataforma import (
    Plataforma,
    PlataformaCreate,
    PlataformaUpdate,
)
from aulento.web.dependencies import (
    Conexion,
    Cuenta,
    CuentaOApiKey,
    RepoCursos,
    RepoPlataformas,
    SinCuentaCompartida,
    no_encontrado,
)

router = APIRouter(prefix="/api/hub", tags=["Hub"])
router_webhook = APIRouter(prefix="/api/hub", tags=["Hub"])

DIRECCIONES_DE_BUCLE_LOCAL = frozenset({"127.0.0.1", "::1"})
CABECERAS_DE_PROXY = (
    "forwarded",
    "x-forwarded-for",
    "x-forwarded-host",
    "x-forwarded-proto",
    "x-real-ip",
    "x-client-ip",
    "via",
    "cf-connecting-ip",
    "true-client-ip",
)


def llega_desde_la_misma_maquina(request: Request) -> bool:
    """El pedido viene del bucle local y no lo reenvió un proxy en nombre de otra máquina."""
    if request.client is None or request.client.host not in DIRECCIONES_DE_BUCLE_LOCAL:
        return False
    return not any(cabecera in request.headers for cabecera in CABECERAS_DE_PROXY)


class ProgressUpdateRequest(BaseModel):
    progreso_pct: float = Field(..., ge=0.0, le=100.0, description="Porcentaje de avance (0 a 100)")
    estado: EstadoCurso | None = None


class PlatformWithCourses(BaseModel):
    id: int
    nombre: str
    url_acceso: str
    icono_color: str
    cursos: list[Curso] = []


class CourseWebhookPayload(BaseModel):
    curso: str | None = Field(default=None, description="Nombre del curso para correlación")
    course_id: int | None = Field(default=None, description="ID del curso")
    external_id: str | None = Field(default=None, description="Identificador externo del curso")
    progreso_pct: float | None = Field(default=None, ge=0.0, le=100.0, description="Porcentaje de avance (0 a 100)")
    modulos_completados: int | None = Field(default=None, ge=0)
    total_modulos: int | None = Field(default=None, gt=0)
    clases_completadas: int | None = Field(default=None, ge=0)
    total_clases: int | None = Field(default=None, gt=0)
    checkpoints_aprobados: int | None = Field(default=None, ge=0)
    total_checkpoints: int | None = Field(default=None, gt=0)
    estado: EstadoCurso | None = None
    plataforma: str | None = Field(default=None, description="Nombre de la plataforma para auto-crear si no existe")
    url_aula: str | None = Field(default=None, description="URL del aula virtual")
    fuente: str = Field(default="webhook", max_length=50, description="Fuente del webhook")
    notas: str | None = None


class CourseSyncRequest(BaseModel):
    profile_url: str | None = None
    profile_id: str | None = None
    profile_html: str | None = None
    badge_title: str | None = None
    completed_labs: int | None = None
    total_labs: int | None = None
    completed_modules: int | None = None
    total_modules: int | None = None
    progreso_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    fuente: str | None = None


class GoogleSkillsSyncRequest(BaseModel):
    profile_url_or_id: str = Field(..., min_length=1, description="URL o UUID del perfil público de Google Cloud Skills Boost")
    profile_html: str | None = Field(default=None, description="HTML opcional del perfil")
    auto_import: bool = Field(default=False, description="Importar automáticamente insignias no registradas")


class CourseSyncResponse(BaseModel):
    success: bool
    curso_id: int | None = None
    nombre_curso: str
    progreso_pct: float
    progreso_anterior: float
    estado: str
    fuente: str
    mensaje: str
    detalles: dict = {}


@router.get("/platforms", response_model=list[PlatformWithCourses])
def list_platforms_with_courses(p_repo: RepoPlataformas, c_repo: RepoCursos):
    """Obtiene las plataformas de la cuenta y anida sus cursos asociados."""
    platforms = p_repo.list_all()
    results = []
    for p in platforms:
        courses = c_repo.list_all(plataforma_id=p.id) if p.id else []
        results.append(
            PlatformWithCourses(
                id=p.id or 0,
                nombre=p.nombre,
                url_acceso=p.url_acceso,
                icono_color=p.icono_color,
                cursos=courses,
            )
        )
    return results


@router.post("/platforms", response_model=Plataforma, status_code=status.HTTP_201_CREATED)
def create_platform(data: PlataformaCreate, p_repo: RepoPlataformas):
    """Crea una nueva plataforma educativa."""
    return p_repo.create(data)


@router.get("/courses", response_model=list[Curso])
def list_courses(c_repo: RepoCursos):
    """Lista los cursos de la cuenta."""
    return c_repo.list_all()


@router.post("/courses", response_model=Curso, status_code=status.HTTP_201_CREATED)
def create_course(data: CursoCreate, p_repo: RepoPlataformas, c_repo: RepoCursos):
    """Registra un nuevo curso en una plataforma de la cuenta."""
    if not p_repo.get_by_id(data.plataforma_id):
        raise no_encontrado("Plataforma", data.plataforma_id)
    return c_repo.create(data)


@router.put("/platforms/{platform_id}", response_model=Plataforma)
def update_platform(platform_id: int, data: PlataformaUpdate, p_repo: RepoPlataformas):
    """Actualiza los datos de una plataforma existente."""
    if not p_repo.get_by_id(platform_id):
        raise no_encontrado("Plataforma", platform_id)
    return p_repo.update(platform_id, data)


@router.delete("/platforms/{platform_id}", status_code=status.HTTP_200_OK, dependencies=[SinCuentaCompartida])
def delete_platform(platform_id: int, p_repo: RepoPlataformas):
    """Elimina una plataforma y sus cursos asociados en cascada."""
    if not p_repo.get_by_id(platform_id):
        raise no_encontrado("Plataforma", platform_id)
    success = p_repo.delete(platform_id)
    return {"ok": success, "message": f"Plataforma {platform_id} eliminada con éxito."}


@router.put("/courses/{course_id}", response_model=Curso)
def update_course(course_id: int, data: CursoUpdate, c_repo: RepoCursos):
    """Actualiza los datos de un curso existente."""
    if not c_repo.get_by_id(course_id):
        raise no_encontrado("Curso", course_id)
    return c_repo.update(course_id, data)


@router.post("/courses/{course_id}/progress", response_model=Curso)
def update_course_progress(course_id: int, data: ProgressUpdateRequest, c_repo: RepoCursos):
    """Actualiza de forma reactiva el porcentaje de avance y estado de un curso."""
    if not c_repo.get_by_id(course_id):
        raise no_encontrado("Curso", course_id)

    updated = c_repo.update_progress(course_id, data.progreso_pct, data.estado)
    if not updated:
        raise HTTPException(status_code=500, detail="No se pudo actualizar el progreso.")
    return updated


@router.delete("/courses/{course_id}", status_code=status.HTTP_200_OK, dependencies=[SinCuentaCompartida])
def delete_course(course_id: int, c_repo: RepoCursos):
    """Elimina un curso externo."""
    if not c_repo.get_by_id(course_id):
        raise no_encontrado("Curso", course_id)
    success = c_repo.delete(course_id)
    return {"ok": success, "message": f"Curso {course_id} eliminado con éxito."}


@router.post("/courses/{course_id}/open-local")
def open_course_local_folder(course_id: int, request: Request, usuario: Cuenta, c_repo: RepoCursos):
    """Abre la carpeta local del curso en el explorador de archivos de la máquina que hospeda el servidor.

    Solo para un administrador que llega desde esa misma máquina: a cualquier otro pedido responde 403.
    """
    if not usuario.es_admin or not llega_desde_la_misma_maquina(request):
        raise HTTPException(
            status_code=403,
            detail="Abrir carpetas del servidor es solo para un administrador que usa la aplicación en esa misma máquina.",
        )
    existing = c_repo.get_by_id(course_id)
    if not existing:
        raise no_encontrado("Curso", course_id)
    if not existing.ruta_local:
        raise HTTPException(status_code=400, detail="Este curso no tiene una carpeta local configurada.")

    path = os.path.abspath(existing.ruta_local)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"La ruta local no existe en el disco: {path}")
    if not os.path.isdir(path):
        raise HTTPException(
            status_code=400,
            detail="La ruta configurada debe ser una carpeta o directorio, no un archivo ejecutable.",
        )

    try:
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)
        return {"ok": True, "message": f"Carpeta abierta en el explorador: {path}", "path": path}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Error al abrir la carpeta: {e!s}")



# ----------------------------------------------------------------------
# Endpoints de Sincronización Automática e Ingesta de Cursos (Feature 043)
# ----------------------------------------------------------------------


@router.post("/courses/{course_id}/sync", response_model=CourseSyncResponse)
def sync_course(
    course_id: int,
    usuario: Cuenta,
    conn: Conexion,
    c_repo: RepoCursos,
    data: CourseSyncRequest | None = None,
):
    """Sincroniza un curso bajo demanda consultando su plataforma o configuración."""
    if not c_repo.get_by_id(course_id):
        raise no_encontrado("Curso", course_id)
    manager = CourseSyncManager(conn, usuario.id)
    payload = data.model_dump(exclude_unset=True) if data else {}
    res = manager.sync_course(course_id, payload=payload)
    return CourseSyncResponse(
        success=res.success,
        curso_id=res.curso_id,
        nombre_curso=res.nombre_curso,
        progreso_pct=res.progreso_pct,
        progreso_anterior=res.progreso_anterior,
        estado=res.estado,
        fuente=res.fuente,
        mensaje=res.mensaje,
        detalles=res.detalles,
    )


@router_webhook.post("/sync/webhook", response_model=CourseSyncResponse, status_code=status.HTTP_200_OK)
def webhook_course_sync(
    data: CourseWebhookPayload,
    usuario: CuentaOApiKey,
    conn: Conexion,
):
    """Webhook universal para sincronizar o registrar avance de cursos desde scripts externos o cURL."""
    manager = CourseSyncManager(conn, usuario.id)
    payload = data.model_dump(exclude_unset=True)
    try:
        res = manager.process_webhook(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return CourseSyncResponse(
        success=res.success,
        curso_id=res.curso_id,
        nombre_curso=res.nombre_curso,
        progreso_pct=res.progreso_pct,
        progreso_anterior=res.progreso_anterior,
        estado=res.estado,
        fuente=res.fuente,
        mensaje=res.mensaje,
        detalles=res.detalles,
    )


@router.get("/sync/webhook-info")
def get_course_webhook_info(request: Request, usuario: Cuenta):
    """Instrucciones y especificación del webhook universal de progreso de cursos."""
    base_url = str(request.base_url).rstrip("/")
    return {
        "webhook_url": f"{base_url}/api/hub/sync/webhook",
        "metodo": "POST",
        "autenticacion": "Encabezado Authorization: Bearer <mcp_token> o X-MCP-Token: <mcp_token>",
        "ejemplo_payload": {
            "curso": "Google Cloud Skills Boost: Cloud Architect",
            "progreso_pct": 80.0,
            "estado": "en_curso",
            "fuente": "userscript",
            "plataforma": "Google Cloud Skills Boost",
        },
        "instrucciones": (
            "Podés enviar una petición POST a este endpoint con tu token MCP en la cabecera "
            "'Authorization: Bearer <token>' o 'X-MCP-Token: <token>' desde extensiones "
            "de navegador (Tampermonkey), Atajos de iOS o scripts de automatización. "
            "El token en la URL no se acepta."
        ),
    }


@router.post("/sync/platforms/google-skills", response_model=list[CourseSyncResponse])
def sync_google_skills_platform(
    data: GoogleSkillsSyncRequest,
    usuario: Cuenta,
    conn: Conexion,
):
    """Sincroniza todos los cursos de Google Cloud Skills Boost a partir de un perfil público."""
    manager = CourseSyncManager(conn, usuario.id)
    try:
        results = manager.sync_google_skills_profile(
            profile_url_or_id=data.profile_url_or_id,
            profile_html=data.profile_html,
            auto_import=data.auto_import,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Error al sincronizar perfil: {e}")
    return [
        CourseSyncResponse(
            success=r.success,
            curso_id=r.curso_id,
            nombre_curso=r.nombre_curso,
            progreso_pct=r.progreso_pct,
            progreso_anterior=r.progreso_anterior,
            estado=r.estado,
            fuente=r.fuente,
            mensaje=r.mensaje,
            detalles=r.detalles,
        )
        for r in results
    ]


@router.get("/sync/status")
def get_course_sync_status(c_repo: RepoCursos):
    """Obtiene el resumen y estadísticas de sincronización de cursos de la cuenta."""
    return c_repo.get_sync_status()
