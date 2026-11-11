"""Módulo de conectores y sincronización automática de progreso para cursos del Hub Académico."""

import json
import logging
import re
import sqlite3
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

from aulento.core import permisos
from aulento.db.cuenta import exigir_cuenta
from aulento.db.focus_repository import FocusRepository
from aulento.db.repository import CursoRepository, PlataformaRepository
from aulento.models.curso import Curso, CursoCreate, EstadoCurso, PrioridadCurso
from aulento.models.focus_session import FocusSessionCreate
from aulento.models.plataforma import PlataformaCreate

logger = logging.getLogger(__name__)


@dataclass
class CourseSyncResult:
    success: bool
    curso_id: int | None
    nombre_curso: str
    progreso_pct: float
    progreso_anterior: float
    estado: str
    fuente: str
    mensaje: str
    detalles: dict[str, Any] = field(default_factory=dict)


HOSTS_PERMITIDOS_SKILLS_BOOST = frozenset(
    {"www.cloudskillsboost.google", "cloudskillsboost.google", "www.skills.google", "skills.google"}
)


class UrlNoPermitidaError(ValueError):
    """La URL no pertenece a los dominios permitidos de Google Cloud Skills Boost o usa un esquema inseguro."""


def _url_permitida(url: str) -> bool:
    """Valida que la URL sea HTTPS, host en Cloud Skills Boost, sin credenciales ni puertos no estándar."""
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url.strip())
    except (ValueError, TypeError):
        return False

    if parsed.scheme != "https":
        return False

    # Sin usuario ni contraseña
    if parsed.username or parsed.password:
        return False

    # Host en lista permitida
    host = (parsed.hostname or "").lower()
    if host not in HOSTS_PERMITIDOS_SKILLS_BOOST:
        return False

    # Sin puerto raro (solo None o 443); un puerto mal escrito también se rechaza
    try:
        return parsed.port in (None, 443)
    except ValueError:
        return False


class SeguroSkillsBoostRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Manejador de redirecciones que restringe los saltos a los hosts permitidos de Skills Boost."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        url_destino = urljoin(req.full_url, newurl)
        if not _url_permitida(url_destino):
            raise UrlNoPermitidaError(
                f"Redirección no permitida: el destino '{url_destino}' no pertenece a los dominios autorizados."
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _crear_opener_seguro() -> urllib.request.OpenerDirector:
    """Crea un OpenerDirector con control estricto de redirecciones para Skills Boost."""
    return urllib.request.build_opener(SeguroSkillsBoostRedirectHandler())


class GoogleCloudSkillsConnector:
    """Conector para sincronización con Google Cloud Skills Boost a partir de perfiles públicos."""

    BASE_URL = "https://www.cloudskillsboost.google/public_profiles/"

    @classmethod
    def normalizar_url_o_id(cls, profile_url_or_id: str) -> tuple[str, str]:
        """Retorna (profile_id, full_url) tras validar que apunte a un host permitido."""
        val = profile_url_or_id.strip()
        if val.startswith(("http://", "https://")) or "://" in val:
            if not _url_permitida(val):
                raise UrlNoPermitidaError(
                    f"URL de Skills Boost no permitida: debe ser https y pertenecer a "
                    f"{' o '.join(sorted(HOSTS_PERMITIDOS_SKILLS_BOOST))} (se recibió '{val}')."
                )
            parts = val.rstrip("/").split("/")
            profile_id = parts[-1]
            return profile_id, val

        full_url = f"{cls.BASE_URL}{val.lstrip('/')}"
        if not _url_permitida(full_url):
            raise UrlNoPermitidaError(
                f"URL generada de Skills Boost no permitida: '{full_url}'."
            )
        return val, full_url

    @classmethod
    def parse_profile_badges(cls, content: str) -> list[dict[str, Any]]:
        """Extrae insignias y cursos completados de una respuesta HTML o JSON del perfil público."""
        content_str = content.strip()
        badges: list[dict[str, Any]] = []

        # 1. Intento parsear como JSON directo (si se proveyó exportación o API interna)
        if content_str.startswith("{") and content_str.endswith("}"):
            try:
                data = json.loads(content_str)
                if "badges" in data and isinstance(data["badges"], list):
                    for b in data["badges"]:
                        badges.append({
                            "titulo": b.get("title") or b.get("nombre") or "",
                            "fecha": b.get("earned") or b.get("fecha") or "",
                            "badge_type": b.get("type", "skill_badge"),
                        })
                    return badges
            except json.JSONDecodeError:
                pass

        # 2. Extracción Regex de insignias en HTML de Cloud Skills Boost
        # En el HTML público las insignias se presentan en elementos con clase ql-title-medium o profile-badge
        title_matches = re.findall(
            r'class="[^"]*(?:ql-title-medium|badge-title)[^"]*">\s*([^<]+?)\s*<',
            content_str,
            re.IGNORECASE,
        )
        date_matches = re.findall(
            r'(?:Earned|Obtenido|Completed)\s*([A-Za-z0-9,\s]+?)\s*<',
            content_str,
            re.IGNORECASE,
        )

        for i, title in enumerate(title_matches):
            t_clean = title.strip()
            if not t_clean or len(t_clean) < 3:
                continue
            earned_date = date_matches[i].strip() if i < len(date_matches) else ""
            badges.append({
                "titulo": t_clean,
                "fecha": earned_date,
                "badge_type": "skill_badge" if "skill" in t_clean.lower() else "course_badge",
            })

        # Búsqueda adicional de títulos en bloques de insignia comunes
        if not badges:
            generic_titles = re.findall(r'<span class="ql-title-large[^"]*">\s*([^<]+?)\s*<', content_str)
            for gt in generic_titles:
                t = gt.strip()
                if t and len(t) > 3:
                    badges.append({"titulo": t, "fecha": "", "badge_type": "course_badge"})

        return badges

    @classmethod
    def fetch_public_profile(cls, profile_url_or_id: str, timeout: int = 10) -> str:
        """Descarga el contenido del perfil público tras validar la URL y sus redirecciones."""
        _, url = cls.normalizar_url_o_id(profile_url_or_id)
        if not _url_permitida(url):
            raise UrlNoPermitidaError(
                f"URL de Skills Boost no permitida: debe ser https y pertenecer a "
                f"{' o '.join(sorted(HOSTS_PERMITIDOS_SKILLS_BOOST))}."
            )
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "StudyEngine/1.0 (CourseProgressSync)"},
        )
        opener = _crear_opener_seguro()
        with opener.open(req, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")


class CourseraConnector:
    """Adaptador para cálculo de progreso de cursos de Coursera."""

    @classmethod
    def parse_progress(cls, payload: dict[str, Any]) -> tuple[float, str]:
        """Determina (progreso_pct, estado) a partir de un payload de Coursera."""
        if "progreso_pct" in payload and payload["progreso_pct"] is not None:
            pct = float(payload["progreso_pct"])
        elif "completed_modules" in payload and "total_modules" in payload:
            tot = int(payload["total_modules"])
            comp = int(payload["completed_modules"])
            pct = (comp / tot * 100.0) if tot > 0 else 0.0
        else:
            pct = 0.0

        pct = max(0.0, min(100.0, round(pct, 1)))
        estado = payload.get("estado")
        if not estado:
            estado = "completado" if pct >= 100.0 else "en_curso"
        return pct, estado


class HumaiConnector:
    """Adaptador para programas y cursos de Humai."""

    @classmethod
    def parse_progress(cls, payload: dict[str, Any]) -> tuple[float, str]:
        if "progreso_pct" in payload and payload["progreso_pct"] is not None:
            pct = float(payload["progreso_pct"])
        elif "clases_completadas" in payload and "total_clases" in payload:
            tot = int(payload["total_clases"])
            comp = int(payload["clases_completadas"])
            pct = (comp / tot * 100.0) if tot > 0 else 0.0
        elif "modulos_completados" in payload and "total_modulos" in payload:
            tot = int(payload["total_modulos"])
            comp = int(payload["modulos_completados"])
            pct = (comp / tot * 100.0) if tot > 0 else 0.0
        else:
            pct = 0.0

        pct = max(0.0, min(100.0, round(pct, 1)))
        estado = payload.get("estado") or ("completado" if pct >= 100.0 else "en_curso")
        return pct, estado


class DigitalHouseConnector:
    """Adaptador para carreras y cursos de Digital House."""

    @classmethod
    def parse_progress(cls, payload: dict[str, Any]) -> tuple[float, str]:
        if "progreso_pct" in payload and payload["progreso_pct"] is not None:
            pct = float(payload["progreso_pct"])
        elif "checkpoints_aprobados" in payload and "total_checkpoints" in payload:
            tot = int(payload["total_checkpoints"])
            comp = int(payload["checkpoints_aprobados"])
            pct = (comp / tot * 100.0) if tot > 0 else 0.0
        elif "clases_asistidas" in payload and "total_clases" in payload:
            tot = int(payload["total_clases"])
            comp = int(payload["clases_asistidas"])
            pct = (comp / tot * 100.0) if tot > 0 else 0.0
        else:
            pct = 0.0

        pct = max(0.0, min(100.0, round(pct, 1)))
        estado = payload.get("estado") or ("completado" if pct >= 100.0 else "en_curso")
        return pct, estado


class CourseSyncManager:
    """Orquestador central para la sincronización e ingesta de cursos en la cuenta."""

    def __init__(self, conn: sqlite3.Connection, user_id: int):
        self.conn = conn
        self.user_id = exigir_cuenta(user_id)
        self.repo = CursoRepository(conn, user_id)
        self.p_repo = PlataformaRepository(conn, user_id)

    def _registrar_actividad_estudio(self, nombre_curso: str, avance_pct: float, fuente: str) -> None:
        """Registra un evento de estudio en sesiones_estudio para alimentar rachas y heatmaps."""
        try:
            FocusRepository(self.conn, self.user_id).record_session(
                FocusSessionCreate(
                    duracion_minutos=15,
                    tipo="curso",
                    notas=f"Sincronización curso '{nombre_curso}' (+{avance_pct:.1f}%) vía {fuente}",
                )
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("No se pudo registrar la sesión de estudio para el curso: %s", e)

    def sync_course(self, course_id: int, payload: dict[str, Any] | None = None) -> CourseSyncResult:
        """Sincroniza un curso existente según su plataforma y configuración de sync."""
        curso = self.repo.get_by_id(course_id)
        if not curso:
            raise ValueError(f"Curso {course_id} no encontrado en la cuenta.")

        config = {}
        if curso.sync_config_json:
            try:
                config = json.loads(curso.sync_config_json)
            except json.JSONDecodeError:
                pass

        if payload:
            config.update(payload)

        plataforma_nombre = (curso.nombre_plataforma or "").lower()
        progreso_anterior = curso.progreso_pct
        nuevo_progreso = progreso_anterior
        nuevo_estado = curso.estado.value
        fuente = curso.fuente_sincronizacion or "manual"
        mensaje = "Sin cambios en el progreso."
        detalles: dict[str, Any] = {}
        badge_match = None

        tiene_progreso_manual = (
            payload is not None
            and "progreso_pct" in payload
            and payload["progreso_pct"] is not None
        )

        # 1. Google Cloud Skills Boost
        if "google" in plataforma_nombre or "skills boost" in plataforma_nombre:
            fuente = "google_cloud_skills"
            profile_url = config.get("profile_url") or config.get("profile_id")
            html_content = config.get("profile_html")
            badges = []

            if html_content:
                badges = GoogleCloudSkillsConnector.parse_profile_badges(html_content)
            elif profile_url:
                try:
                    fetched = GoogleCloudSkillsConnector.fetch_public_profile(profile_url)
                    badges = GoogleCloudSkillsConnector.parse_profile_badges(fetched)
                except Exception as e:  # noqa: BLE001
                    return CourseSyncResult(
                        success=False,
                        curso_id=curso.id,
                        nombre_curso=curso.nombre_curso,
                        progreso_pct=progreso_anterior,
                        progreso_anterior=progreso_anterior,
                        estado=nuevo_estado,
                        fuente=fuente,
                        mensaje=f"Error al consultar perfil de Skills Boost: {e}",
                    )

            detalles["badges_encontradas"] = len(badges)
            # Buscar coincidencia por badge_title, external_id o nombre del curso
            target_badge = config.get("badge_title") or curso.external_id or curso.nombre_curso
            badge_match = next(
                (b for b in badges if target_badge.lower() in b["titulo"].lower() or b["titulo"].lower() in target_badge.lower()),
                None,
            )

            if badge_match:
                nuevo_progreso = 100.0
                nuevo_estado = "completado"
                mensaje = f"Insignia completada detectada: '{badge_match['titulo']}'"
                detalles["badge_match"] = badge_match
            elif payload and "completed_labs" in payload and "total_labs" in payload:
                tot = int(payload["total_labs"])
                comp = int(payload["completed_labs"])
                nuevo_progreso = round((comp / tot * 100.0) if tot > 0 else 0.0, 1)
                nuevo_estado = "completado" if nuevo_progreso >= 100.0 else "en_curso"
                mensaje = f"Progreso actualizado por laboratorios: {comp}/{tot} ({nuevo_progreso}%)"
            elif tiene_progreso_manual:
                nuevo_progreso = float(payload["progreso_pct"])
                nuevo_estado = payload.get("estado") or ("completado" if nuevo_progreso >= 100.0 else "en_curso")
                mensaje = f"Progreso actualizado a {nuevo_progreso}%"

        # 2. Coursera
        elif "coursera" in plataforma_nombre:
            fuente = "coursera"
            if tiene_progreso_manual:
                nuevo_progreso = float(payload["progreso_pct"])
                nuevo_estado = payload.get("estado") or ("completado" if nuevo_progreso >= 100.0 else "en_curso")
                mensaje = f"Progreso Coursera actualizado a {nuevo_progreso}%"
            elif payload and "completed_modules" in payload and "total_modules" in payload:
                nuevo_progreso, nuevo_estado = CourseraConnector.parse_progress(payload)
                mensaje = f"Progreso Coursera actualizado a {nuevo_progreso}%"

        # 3. Humai
        elif "humai" in plataforma_nombre:
            fuente = "humai"
            if tiene_progreso_manual:
                nuevo_progreso = float(payload["progreso_pct"])
                nuevo_estado = payload.get("estado") or ("completado" if nuevo_progreso >= 100.0 else "en_curso")
                mensaje = f"Progreso Humai actualizado a {nuevo_progreso}%"
            elif payload and (("clases_completadas" in payload and "total_clases" in payload) or ("modulos_completados" in payload and "total_modulos" in payload)):
                nuevo_progreso, nuevo_estado = HumaiConnector.parse_progress(payload)
                mensaje = f"Progreso Humai actualizado a {nuevo_progreso}%"

        # 4. Digital House
        elif "digital house" in plataforma_nombre:
            fuente = "digital_house"
            if tiene_progreso_manual:
                nuevo_progreso = float(payload["progreso_pct"])
                nuevo_estado = payload.get("estado") or ("completado" if nuevo_progreso >= 100.0 else "en_curso")
                mensaje = f"Progreso Digital House actualizado a {nuevo_progreso}%"
            elif payload and (("checkpoints_aprobados" in payload and "total_checkpoints" in payload) or ("clases_asistidas" in payload and "total_clases" in payload)):
                nuevo_progreso, nuevo_estado = DigitalHouseConnector.parse_progress(payload)
                mensaje = f"Progreso Digital House actualizado a {nuevo_progreso}%"

        # 5. Adaptador genérico
        else:
            fuente = config.get("fuente", "webhook")
            if tiene_progreso_manual:
                nuevo_progreso = float(payload["progreso_pct"])
                nuevo_estado = payload.get("estado") or ("completado" if nuevo_progreso >= 100.0 else "en_curso")
                mensaje = f"Progreso actualizado a {nuevo_progreso}%"

        if nuevo_progreso == progreso_anterior and not tiene_progreso_manual and not badge_match:
            mensaje = "Sin cambios en el progreso."

        config["progreso_pct"] = nuevo_progreso
        config["estado"] = nuevo_estado

        # Persistir
        self.repo.update_sync_progress(
            id=curso.id,
            nuevo_progreso=nuevo_progreso,
            nuevo_estado=nuevo_estado,
            fuente=fuente,
            external_id=config.get("external_id") or curso.external_id,
            sync_config_json=json.dumps(config),
        )

        # Si hubo avance de progreso, registrar en sesiones_estudio
        if nuevo_progreso > progreso_anterior:
            self._registrar_actividad_estudio(curso.nombre_curso, nuevo_progreso - progreso_anterior, fuente)

        return CourseSyncResult(
            success=True,
            curso_id=curso.id,
            nombre_curso=curso.nombre_curso,
            progreso_pct=nuevo_progreso,
            progreso_anterior=progreso_anterior,
            estado=nuevo_estado,
            fuente=fuente,
            mensaje=mensaje,
            detalles=detalles,
        )

    def process_webhook(self, payload: dict[str, Any]) -> CourseSyncResult:
        """Procesa una llamada webhook estructurada para actualizar o dar de alta el progreso de un curso."""
        curso_id = payload.get("course_id")
        external_id = payload.get("external_id")
        nombre = payload.get("curso") or payload.get("nombre_curso")
        fuente = payload.get("fuente", "webhook")
        plataforma_nombre = payload.get("plataforma")

        curso: Curso | None = None
        if curso_id:
            curso = self.repo.get_by_id(int(curso_id))
        elif external_id:
            curso = self.repo.find_by_external_id(str(external_id))
        elif nombre:
            curso = self.repo.find_by_name(str(nombre))

        if not curso:
            # Si no existe y se proveyó plataforma, crear el curso automáticamente
            if nombre and plataforma_nombre:
                # Antes de crear la plataforma: si la cuenta no puede crear otro curso, no queda una plataforma
                # vacía (062)
                permisos.exigir(self.repo.user_id, permisos.CREAR_CURSO, self.repo.conn)
                # Buscar o crear plataforma
                plat = next((p for p in self.p_repo.list_all() if p.nombre.lower() == plataforma_nombre.lower()), None)
                if not plat:
                    plat = self.p_repo.create(
                        PlataformaCreate(
                            nombre=plataforma_nombre,
                            url_acceso="https://aulento.local",
                            color_badge="blue",
                        )
                    )

                pct = float(payload.get("progreso_pct", 0.0))
                st = EstadoCurso.COMPLETADO if pct >= 100.0 else EstadoCurso.EN_CURSO
                curso = self.repo.create(
                    CursoCreate(
                        plataforma_id=plat.id,
                        nombre_curso=str(nombre),
                        url_aula=payload.get("url_aula", "https://aulento.local/aula"),
                        progreso_pct=pct,
                        estado=st,
                        prioridad=PrioridadCurso.MEDIA,
                        external_id=external_id,
                        fuente_sincronizacion=fuente,
                        sync_config_json=json.dumps(payload),
                    )
                )
                if pct > 0:
                    self._registrar_actividad_estudio(curso.nombre_curso, pct, fuente)

                return CourseSyncResult(
                    success=True,
                    curso_id=curso.id,
                    nombre_curso=curso.nombre_curso,
                    progreso_pct=pct,
                    progreso_anterior=0.0,
                    estado=st.value,
                    fuente=fuente,
                    mensaje=f"Curso '{nombre}' importado y registrado vía webhook con {pct}%",
                )
            raise ValueError(f"No se pudo identificar el curso para el webhook: {payload}")

        return self.sync_course(curso.id, payload=payload)

    def sync_google_skills_profile(
        self,
        profile_url_or_id: str,
        profile_html: str | None = None,
        auto_import: bool = False,
    ) -> list[CourseSyncResult]:
        """Sincroniza todos los cursos vinculados a Google Cloud Skills Boost con el perfil público."""
        if profile_html:
            content = profile_html
        else:
            content = GoogleCloudSkillsConnector.fetch_public_profile(profile_url_or_id)

        badges = GoogleCloudSkillsConnector.parse_profile_badges(content)
        # Buscar plataforma Google Cloud Skills Boost en la cuenta
        plat = next(
            (p for p in self.p_repo.list_all() if "skills boost" in p.nombre.lower() or "google skills" in p.nombre.lower()),
            None,
        )
        if auto_import and not plat:
            plat = self.p_repo.create(
                PlataformaCreate(
                    nombre="Google Cloud Skills Boost",
                    url_acceso="https://www.cloudskillsboost.google",
                    color_badge="blue",
                )
            )

        resultados: list[CourseSyncResult] = []
        cursos = self.repo.list_all(plataforma_id=plat.id) if plat and plat.id else []

        for curso in cursos:
            res = self.sync_course(
                curso.id,
                payload={
                    "profile_url": profile_url_or_id,
                    "profile_html": content,
                },
            )
            resultados.append(res)

        # Si se solicita auto-importación de insignias ganadas que no están en el hub
        if auto_import and plat and plat.id:
            nombres_existentes = {c.nombre_curso.lower() for c in cursos}
            for b in badges:
                if b["titulo"].lower() not in nombres_existentes:
                    # Con un tope de cursos se importan las que entran y se avisa por qué paró (062)
                    decision = permisos.puede(self.repo.user_id, permisos.CREAR_CURSO, self.repo.conn)
                    if not decision.permitido:
                        resultados.append(
                            CourseSyncResult(
                                success=False,
                                curso_id=None,
                                nombre_curso=b["titulo"],
                                progreso_pct=100.0,
                                progreso_anterior=0.0,
                                estado="no_importado",
                                fuente="google_cloud_skills",
                                mensaje=decision.motivo,
                            )
                        )
                        break
                    nuevo_curso = self.repo.create(
                        CursoCreate(
                            plataforma_id=plat.id,
                            nombre_curso=b["titulo"],
                            url_aula="https://www.cloudskillsboost.google",
                            progreso_pct=100.0,
                            estado=EstadoCurso.COMPLETADO,
                            prioridad=PrioridadCurso.MEDIA,
                            fuente_sincronizacion="google_cloud_skills",
                            sync_config_json=json.dumps({"badge": b, "profile": profile_url_or_id}),
                        )
                    )
                    resultados.append(
                        CourseSyncResult(
                            success=True,
                            curso_id=nuevo_curso.id,
                            nombre_curso=nuevo_curso.nombre_curso,
                            progreso_pct=100.0,
                            progreso_anterior=0.0,
                            estado="completado",
                            fuente="google_cloud_skills",
                            mensaje=f"Insignia '{b['titulo']}' importada automáticamente como curso completado.",
                            detalles={"badge": b},
                        )
                    )

        return resultados
