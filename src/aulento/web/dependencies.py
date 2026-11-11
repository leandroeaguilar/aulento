"""Dependencias e inyección para la API web de Aulento.

Cada fábrica entrega un repositorio o servicio ya atado a la cuenta de la sesión: los handlers no
construyen ninguno a mano, así que no pueden equivocarse de cuenta.
"""

import sqlite3
from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from aulento.audio.gemini_tutor import GeminiTutorClient
from aulento.auth.dependencias import (
    usuario_actual,
    usuario_de_sesion_o_token,
    usuario_para_el_avance_de_libros,
)
from aulento.auth.modelos import Usuario
from aulento.connectors.duolingo import DuolingoClient
from aulento.core.activity_tracker import ActivityTracker
from aulento.core.gemini_gateway import GeminiGateway
from aulento.core.ia.pasarela import PasarelaDeIA
from aulento.core.knowledge_rag import KnowledgeRAGService
from aulento.core.materiales import AlmacenDeMateriales
from aulento.core.secretos import AjustesDeCuenta, AlmacenDeSecretos
from aulento.core.study_planner import StudyPlannerEngine
from aulento.db.connection import get_db_connection
from aulento.db.focus_repository import FocusRepository
from aulento.db.fsrs_repository import FSRSRepository
from aulento.db.repository import (
    BloqueHorarioRepository,
    CursoRepository,
    LibroRepository,
    PlataformaRepository,
)
from aulento.db.roadmap_repository import RoadmapRepository
from aulento.fsrs.engine import FSRSEngine
from aulento.mcp.agent import TutorDeMateriales
from aulento.roadmap.engine import RoadmapEngine
from aulento.roadmap.lesson_studio import LessonStudio
from aulento.roadmap.macro_fsrs import MacroFSRSEngine, MacroFSRSRepository
from aulento.roadmap.pdf_comparator import RoadmapPDFComparator
from aulento.roadmap.system_prompt_manager import SystemPromptManager
from aulento.vault.carpetas import carpetas_del_tutor
from aulento.vault.cloud_notes import MaterialNoteGenerator
from aulento.vault.reader import VaultReader
from aulento.vault.rutas import vault_de_la_cuenta
from aulento.vault.sop_course import CourseNoteGenerator
from aulento.vault.weekly_digest import WeeklyDigestExporter

__all__ = ["get_db_connection"]

Conexion = Annotated[sqlite3.Connection, Depends(get_db_connection)]
Cuenta = Annotated[Usuario, Depends(usuario_actual)]

MENSAJE_CUENTA_COMPARTIDA = (
    "Esta cuenta es compartida: no permite cargar claves, conectar servicios "
    "ni cambiar dónde se guardan las notas."
)


def es_cuenta_compartida(request: Request, usuario: Usuario) -> bool:
    """Si alguna extensión dice que la cuenta la comparten varias personas (por ejemplo, una de demostración)."""
    extensiones = getattr(getattr(request, "app", None), "state", None)
    return any(
        extension.cuenta_compartida is not None and extension.cuenta_compartida(usuario)
        for extension in getattr(extensiones, "extensiones", ())
    )


def rechazar_cuenta_compartida(request: Request, usuario: Cuenta) -> None:
    """Corta con 403 si la cuenta es compartida.

    La comparten varias personas: una clave, una conexión o un token que cargue una quedaría a la vista y al alcance
    de la siguiente. Se aplica con `dependencies=[SinCuentaCompartida]` en las rutas que los guardan.
    """
    if es_cuenta_compartida(request, usuario):
        # La cabecera le dice al frontend que muestre el aviso, sea cual sea el botón que lo disparó
        raise HTTPException(
            status_code=403, detail=MENSAJE_CUENTA_COMPARTIDA, headers={"X-Cuenta-Compartida": "1"}
        )


SinCuentaCompartida = Depends(rechazar_cuenta_compartida)
def cuenta_o_api_key(usuario: Annotated[Usuario, Depends(usuario_de_sesion_o_token)]) -> Usuario:
    """Cuenta autenticada por sesión interactiva (cookie) o token MCP / Bearer."""
    return usuario


CuentaOApiKey = Annotated[Usuario, Depends(cuenta_o_api_key)]


def cuenta_del_avance_de_libros(usuario: Annotated[Usuario, Depends(usuario_para_el_avance_de_libros)]) -> Usuario:
    """Cuenta del webhook de libros: token de alcance `libros`, o sesión / token MCP por compatibilidad (061)."""
    return usuario


CuentaDelAvanceDeLibros = Annotated[Usuario, Depends(cuenta_del_avance_de_libros)]


# Lo que la API puede no encontrar por su identificador, con la terminación de «encontrado» que le corresponde
TERMINACION_POR_SUSTANTIVO = {
    "Bloque": "o",
    "Clase": "a",
    "Curso": "o",
    "Libro": "o",
    "Material": "o",
    "Módulo": "o",
    "Plataforma": "a",
    "Ruta": "a",
    "Tarjeta": "a",
    "Tema": "o",
    "Token": "o",
    "Versión": "a",
}


def no_encontrado(que: str, identificador: object) -> HTTPException:
    """El 404 de un identificador que no existe o es de otra cuenta: el mismo cuerpo en los dos casos.

    `que` es uno de los sustantivos de `TERMINACION_POR_SUSTANTIVO`; uno que no está ahí es un error de programación.
    """
    terminacion = TERMINACION_POR_SUSTANTIVO[que]
    return HTTPException(status_code=404, detail=f"{que} con ID {identificador} no encontrad{terminacion}.")


def repo_plataformas(usuario: Cuenta, conn: Conexion) -> PlataformaRepository:
    """Plataformas de la cuenta de la sesión."""
    return PlataformaRepository(conn, usuario.id)


def repo_cursos(usuario: Cuenta, conn: Conexion) -> CursoRepository:
    """Cursos de la cuenta de la sesión."""
    return CursoRepository(conn, usuario.id)


def repo_cursos_o_api_key(usuario: CuentaOApiKey, conn: Conexion) -> CursoRepository:
    """Cursos de la cuenta que autentica por sesión o por token MCP / API Key."""
    return CursoRepository(conn, usuario.id)


RepoCursosOApiKey = Annotated[CursoRepository, Depends(repo_cursos_o_api_key)]


def repo_libros(usuario: Cuenta, conn: Conexion) -> LibroRepository:
    """Libros de la cuenta de la sesión."""
    return LibroRepository(conn, usuario.id)


def repo_libros_o_api_key(usuario: CuentaOApiKey, conn: Conexion) -> LibroRepository:
    """Libros de la cuenta que autentica por sesión o por token MCP / API Key."""
    return LibroRepository(conn, usuario.id)


RepoLibrosOApiKey = Annotated[LibroRepository, Depends(repo_libros_o_api_key)]


def repo_bloques(usuario: Cuenta, conn: Conexion) -> BloqueHorarioRepository:
    """Bloques horarios de la cuenta de la sesión."""
    return BloqueHorarioRepository(conn, usuario.id)


def repo_fsrs(usuario: Cuenta, conn: Conexion) -> FSRSRepository:
    """Tarjetas y repasos de la cuenta de la sesión."""
    return FSRSRepository(conn, usuario.id)


def repo_focus(usuario: Cuenta, conn: Conexion) -> FocusRepository:
    """Sesiones de estudio de la cuenta de la sesión."""
    return FocusRepository(conn, usuario.id)


def repo_rutas(usuario: Cuenta) -> RoadmapRepository:
    """Rutas de aprendizaje y registros de consumo de IA de la cuenta de la sesión."""
    return RoadmapRepository(usuario.id)


def motor_fsrs(repo: Annotated[FSRSRepository, Depends(repo_fsrs)]) -> FSRSEngine:
    """Motor de repaso sobre las tarjetas de la cuenta de la sesión."""
    return FSRSEngine(repo)


def tracker_actividad(usuario: Cuenta, conn: Conexion) -> ActivityTracker:
    """Mapa de actividad y rachas de la cuenta de la sesión."""
    return ActivityTracker(usuario.id, conn=conn)


def motor_macro_fsrs(usuario: Cuenta, conn: Conexion) -> MacroFSRSEngine:
    """Retención macro de los temas de las rutas de la cuenta de la sesión."""
    return MacroFSRSEngine(usuario.id, repository=MacroFSRSRepository(usuario.id, conn=conn))


def motor_de_rutas(repo: Annotated[RoadmapRepository, Depends(repo_rutas)]) -> RoadmapEngine:
    """Generación y expansión de rutas de la cuenta de la sesión."""
    return RoadmapEngine(repo=repo)


def estudio_de_clases(
    request: Request, usuario: Cuenta, repo: Annotated[RoadmapRepository, Depends(repo_rutas)]
) -> LessonStudio:
    """Clases de los temas de las rutas de la cuenta de la sesión, que se exportan a su vault."""
    return LessonStudio(repo=repo, cuenta_compartida=es_cuenta_compartida(request, usuario))


def vault_de_la_sesion(usuario: Cuenta, conn: Conexion) -> Path:
    """Carpeta del vault de la cuenta de la sesión; si su vault externo ya no existe, el pedido lo informa."""
    return vault_de_la_cuenta(conn, usuario.id)


def lector_del_vault(usuario: Cuenta, conn: Conexion, vault: Annotated[Path, Depends(vault_de_la_sesion)]) -> VaultReader:
    """Lectura de las notas del vault de la cuenta de la sesión, en las carpetas que eligió para el tutor."""
    return VaultReader(vault, carpetas=carpetas_del_tutor(conn, usuario.id))


def apuntes_de_materiales(usuario: Cuenta, conn: Conexion) -> MaterialNoteGenerator:
    """Apuntes desde los materiales subidos por la cuenta de la sesión, asociados a sus cursos y guardados en su vault."""
    return MaterialNoteGenerator(usuario.id, conn)


def apuntes_de_curso(usuario: Cuenta, conn: Conexion) -> CourseNoteGenerator:
    """Plantillas de apunte de los cursos de la cuenta de la sesión, que se guardan en su vault."""
    return CourseNoteGenerator(usuario.id, conn)


def resumen_semanal(usuario: Cuenta, conn: Conexion) -> WeeklyDigestExporter:
    """Resumen semanal con los datos de la cuenta de la sesión, que se guarda en su vault."""
    return WeeklyDigestExporter(usuario.id, conn)


def busqueda_semantica(usuario: Cuenta) -> KnowledgeRAGService:
    """Indexación y búsqueda sobre los fragmentos vectoriales de la cuenta de la sesión."""
    return KnowledgeRAGService(usuario.id)


def almacen_de_materiales(usuario: Cuenta) -> AlmacenDeMateriales:
    """Materiales que subió la cuenta de la sesión; abre su conexión en cada operación (la subida corre en otro hilo)."""
    return AlmacenDeMateriales.con_conexion_propia(usuario.id)


def tutor_de_materiales(usuario: Cuenta) -> TutorDeMateriales:
    """Tutor sobre los materiales subidos, los fragmentos vectoriales y la clave de IA de la cuenta de la sesión."""
    return TutorDeMateriales(usuario.id)


def secretos_de_la_cuenta(usuario: Cuenta, conn: Conexion) -> AlmacenDeSecretos:
    """Secretos cifrados de la cuenta de la sesión."""
    return AlmacenDeSecretos(conn, usuario.id)


def ajustes_de_la_cuenta(usuario: Cuenta, conn: Conexion) -> AjustesDeCuenta:
    """Ajustes no secretos de la cuenta de la sesión."""
    return AjustesDeCuenta(conn, usuario.id)


def pasarela_de_ia(usuario: Cuenta, conn: Conexion) -> PasarelaDeIA:
    """Llamadas a la IA con el proveedor activo, la clave y el modelo de la cuenta de la sesión."""
    return PasarelaDeIA(conn, usuario.id)


def claves_de_gemini(usuario: Cuenta, conn: Conexion) -> GeminiGateway:
    """Las dos claves de Gemini, el nivel activo y el modelo de Gemini de la cuenta de la sesión."""
    return GeminiGateway(conn, usuario.id)


def tutor_de_voz(pasarela: Annotated[PasarelaDeIA, Depends(pasarela_de_ia)]) -> GeminiTutorClient:
    """Tutor de voz con la IA de la cuenta de la sesión; sin IA utilizable evalúa en local."""
    return GeminiTutorClient(pasarela)


def comparador_de_temarios(pasarela: Annotated[PasarelaDeIA, Depends(pasarela_de_ia)]) -> RoadmapPDFComparator:
    """Comparación de un temario en PDF con la IA de la cuenta de la sesión."""
    return RoadmapPDFComparator(pasarela)


def prompts_de_la_cuenta(usuario: Cuenta, conn: Conexion) -> SystemPromptManager:
    """System prompts propios de la cuenta de la sesión."""
    return SystemPromptManager(conn, usuario.id)


def duolingo_de_la_cuenta(usuario: Cuenta, conn: Conexion) -> DuolingoClient:
    """Usuario y caché de Duolingo de la cuenta de la sesión."""
    return DuolingoClient(conn, usuario.id)


def motor_planificador(usuario: Cuenta, conn: Conexion) -> StudyPlannerEngine:
    """Motor de cálculo y optimización de planes de estudio adaptativos de la cuenta."""
    return StudyPlannerEngine(conn, usuario.id)


RepoPlataformas = Annotated[PlataformaRepository, Depends(repo_plataformas)]
RepoCursos = Annotated[CursoRepository, Depends(repo_cursos)]
RepoLibros = Annotated[LibroRepository, Depends(repo_libros)]
RepoBloques = Annotated[BloqueHorarioRepository, Depends(repo_bloques)]
RepoFsrs = Annotated[FSRSRepository, Depends(repo_fsrs)]
RepoFocus = Annotated[FocusRepository, Depends(repo_focus)]
RepoRutas = Annotated[RoadmapRepository, Depends(repo_rutas)]
MotorFsrs = Annotated[FSRSEngine, Depends(motor_fsrs)]
TrackerActividad = Annotated[ActivityTracker, Depends(tracker_actividad)]
MotorMacroFsrs = Annotated[MacroFSRSEngine, Depends(motor_macro_fsrs)]
MotorDeRutas = Annotated[RoadmapEngine, Depends(motor_de_rutas)]
EstudioDeClases = Annotated[LessonStudio, Depends(estudio_de_clases)]
VaultDeLaSesion = Annotated[Path, Depends(vault_de_la_sesion)]
LectorDelVault = Annotated[VaultReader, Depends(lector_del_vault)]
ApuntesDeMateriales = Annotated[MaterialNoteGenerator, Depends(apuntes_de_materiales)]
ApuntesDeCurso = Annotated[CourseNoteGenerator, Depends(apuntes_de_curso)]
ResumenSemanal = Annotated[WeeklyDigestExporter, Depends(resumen_semanal)]
BusquedaSemantica = Annotated[KnowledgeRAGService, Depends(busqueda_semantica)]
Materiales = Annotated[AlmacenDeMateriales, Depends(almacen_de_materiales)]
TutorDeLaCuenta = Annotated[TutorDeMateriales, Depends(tutor_de_materiales)]
SecretosDeLaCuenta = Annotated[AlmacenDeSecretos, Depends(secretos_de_la_cuenta)]
AjustesDeLaCuenta = Annotated[AjustesDeCuenta, Depends(ajustes_de_la_cuenta)]
IADeLaCuenta = Annotated[PasarelaDeIA, Depends(pasarela_de_ia)]
ClavesDeGemini = Annotated[GeminiGateway, Depends(claves_de_gemini)]
TutorDeVoz = Annotated[GeminiTutorClient, Depends(tutor_de_voz)]
ComparadorDeTemarios = Annotated[RoadmapPDFComparator, Depends(comparador_de_temarios)]
PromptsDeLaCuenta = Annotated[SystemPromptManager, Depends(prompts_de_la_cuenta)]
DuolingoDeLaCuenta = Annotated[DuolingoClient, Depends(duolingo_de_la_cuenta)]
MotorPlanificador = Annotated[StudyPlannerEngine, Depends(motor_planificador)]
