"""Motor Inteligente Study Copilot Router para el Servidor MCP.

Procesa lenguaje natural, clasifica intenciones compuestas, extrae entidades
(libros, páginas relativas/absolutas, cursos, minutos) y orquesta las herramientas
académicas de Aulento en un solo comando unificado con recomendación de Next Best Action.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
import logging
from pathlib import Path
import re
from typing import Any
import unicodedata

from aulento.db.connection import get_connection
from aulento.db.repository import (
    LibroRepository,
    CursoRepository,
    BloqueHorarioRepository,
)
from aulento.db.focus_repository import FocusRepository
from aulento.models.focus_session import FocusSessionCreate
from aulento.db.fsrs_repository import FSRSRepository
from aulento.db.roadmap_repository import RoadmapRepository
from aulento.models.libro import EstadoLibro
from aulento.models.roadmap import EstadoTema
from aulento.mcp.security import cuenta_mcp_actual, herramienta_auditada, log_mcp_tool_execution

logger = logging.getLogger(__name__)


@dataclass
class CopilotIntent:
    """Intención detectada a partir de la instrucción."""
    name: str  # 'BRIEFING', 'READING_UPDATE', 'COURSE_UPDATE', 'ROADMAP_QUERY', 'FSRS_STATUS', 'SCHEDULE_LOG'
    confidence: float
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class CopilotExecutionResult:
    """Resultado unificado de la ejecución orquestada por el Copilot."""
    instruction: str
    actions_taken: list[str] = field(default_factory=list)
    status_summary: dict[str, Any] = field(default_factory=dict)
    next_best_action: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Formatea el resultado en Markdown limpio y estructurado."""
        lines = ["# 🧠 Aulento Copilot — Resumen de Acción"]
        lines.append(f"> *Instrucción:* \"{self.instruction}\"\n")

        if self.actions_taken:
            lines.append("### ✅ Acciones Ejecutadas:")
            for act in self.actions_taken:
                lines.append(f"- {act}")
            lines.append("")

        if self.warnings:
            lines.append("### ⚠️ Advertencias:")
            for w in self.warnings:
                lines.append(f"- {w}")
            lines.append("")

        if self.status_summary:
            lines.append("### 📊 Estado Actual del Estudiante:")
            for k, v in self.status_summary.items():
                lines.append(f"- **{k}:** {v}")
            lines.append("")

        if self.next_best_action:
            lines.append("### 🎯 Próxima Mejor Acción Recomendada (NBA):")
            lines.append(f"{self.next_best_action}\n")

        return "\n".join(lines)


PALABRAS_GENERICAS = frozenset({
    "curso", "cursos", "libro", "libros", "para", "with", "from", "data", "the", "and", "como", "sobre",
    "introduccion", "introduction", "avance", "pagina", "paginas", "capitulo", "module", "modulo",
    "for", "con", "del", "los", "las", "una", "uno", "por", "que", "mis", "sus", "hoy", "voy", "lei", "pag", "min",
})

VERBO_DE_AVANCE = r"\b(?:le[ií]|voy|llegu[eé]|termin[eé]|avanc[eé]|qued[eé]|estoy|pas[eé])\b"
# Lo que sigue a "página N de …" o "capítulo N del …": algo nombrado que no es "el libro"
NOMBRADO_TRAS_AVANCE = re.compile(
    r"(?:p[aá]ginas?|p[aá]gs?\.?|cap[ií]tulos?)\s*\d*\s*(?:de|del)\s+(?!(?:el\s+|mi\s+)?libro\b)(\w+)"
)


VERBO_DE_ESTUDIO = r"\b(?:estudi[eé]|estuve\s+estudiando|practiqu[eé]|repas[eé])\b"
NUMEROS_EN_PALABRAS = {"un": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4}
# Verbos en pasado con los que se cuenta un avance
VERBO_EN_PASADO = (
    r"\b(?:le[ií]|estudi[eé]|termin[eé]|complet[eé]|avanc[eé]|llegu[eé]|qued[eé]|practiqu[eé]|repas[eé]"
    r"|hice|met[ií]|dediqu[eé]|sum[eé]|estuve|fueron)\b|\bvoy\s+(?:en|por)\b"
)
# Una cantidad hecha: el número va antes de la unidad ("20 páginas", "40 minutos", "30%"), no "capítulo 3"
CANTIDAD_HECHA = r"\d\s*(?:p[aá]ginas?\b|p[aá]gs?\b|cap[ií]tulos?\b|%|mins?\b|minutos?\b|hs?\b|horas?\b)|\bmedia\s+hora\b"
# Un pedido ("configurá un pomodoro de 25 min", "explicame…") no informa un avance
ES_UN_PEDIDO = r"\b(?:configur|program|agend|planific|record|pon[eé]\b|arm[aá]\b|cre[aá]\b|quiero|quisiera|necesito|dame|decime|mostrame|explic|resum)"
# Una duración: "2 horas", "1,5 hs", "una hora y media", "2 horas y 15 minutos", "hora y media", "media hora", "45 min"
DURACION = re.compile(
    r"\b(?P<horas>\d+(?:[.,]\d+)?|un|una|dos|tres|cuatro)\s*(?:hs?|horas?)\b"
    r"(?:(?P<y_media>\s+y\s+media\b)|(?P<y_cuarto>\s+y\s+cuarto\b)|(?:\s+y)?\s+(?P<resto_min>\d+)\s*(?:mins?|minutos?)\b)?"
    r"|\b(?P<hora_y_media>hora\s+y\s+media)\b"
    r"|\b(?P<media_hora>media\s+hora)\b"
    r"|\b(?P<minutos>\d+)\s*(?:mins?|minutos?)\b"
)
# Horas de reloj o comparaciones: no son una duración que se pueda registrar con seguridad
DURACION_DUDOSA = re.compile(r"\bde\s+\d+\s+a\s+\d+|\b(?:hasta|desde|a)\s+las?\s+\d|\d:\d|\ben\s+vez\s+de\b|\bme\s+faltan?\b|\by\s+(?:pico|algo|tanto)\b|\bcasi\b")


def _minutos_estudiados(text: str) -> int | None:
    """Minutos de estudio que afirma la instrucción ("estudié 45 min", "2 horas", "una hora y media").

    Devuelve None ante la duda: una negación, una pregunta, una hora de reloj o más de una duración.
    """
    # La cláusula llega hasta la primera coma o signo; el punto o la coma entre dígitos son decimales
    m = re.search(VERBO_DE_ESTUDIO + r"(?P<resto>(?:[^.;:!?¿,\n]|(?<=\d)[.,:](?=\d)){0,60})", text)
    if not m or _en_pregunta(text, m.start("resto")):
        return None
    if re.search(r"\b(?:no|nunca|ni)\s+(?:\w+\s+)?$", text[: m.start()]):
        return None
    resto = m.group("resto")
    duraciones = list(DURACION.finditer(resto))
    if len(duraciones) != 1 or DURACION_DUDOSA.search(resto):
        return None
    d = duraciones[0]
    if d.group("minutos"):
        total = float(d.group("minutos"))
    elif d.group("media_hora"):
        total = 30.0
    elif d.group("hora_y_media"):
        total = 90.0
    else:
        cantidad = d.group("horas")
        total = 60 * (NUMEROS_EN_PALABRAS[cantidad] if cantidad in NUMEROS_EN_PALABRAS else float(cantidad.replace(",", ".")))
        if d.group("y_media"):
            total += 30
        if d.group("y_cuarto"):
            total += 15
        if d.group("resto_min"):
            total += int(d.group("resto_min"))
    return round(total) if total > 0 else None


def _parece_avance(text: str) -> bool:
    """La instrucción afirma (no pregunta ni pide) haber hecho algo: trae un verbo de avance
    o una cantidad con su unidad."""
    if re.search(ES_UN_PEDIDO, text):
        return False
    return any(
        not _en_pregunta(text, m.end())
        for patron in (VERBO_EN_PASADO, CANTIDAD_HECHA)
        for m in re.finditer(patron, text)
    )


def _en_pregunta(texto: str, pos: int) -> bool:
    """Indica si la posición cae en una oración interrogativa."""
    for i in range(pos, len(texto)):
        if texto[i] == "?":
            return True
        if texto[i] == "¿":
            # La pregunta empieza después: lo anterior es una afirmación
            return False
        # Un punto entre dígitos o tras una abreviatura ("pág. 12") no cierra la oración
        if texto[i] in "!;\n" or (texto[i] == "." and texto[i + 1 : i + 2] in ("", " ") and texto[max(0, i - 3) : i] not in ("pag", "pág")):
            return False
    return False


def _sin_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")


def _palabras(texto: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", _sin_acentos(texto)))


def identificar_por_nombre(texto: str, candidatos: list[tuple[Any, str]]) -> tuple[Any | None, bool]:
    """Elige el candidato cuyo nombre comparte más palabras significativas con el texto.

    Devuelve `(candidato, ambiguo)`: sin coincidencias `(None, False)`; con empate en el
    mejor puntaje `(None, True)`.
    """
    en_texto = _palabras(texto)
    puntajes: list[tuple[int, Any]] = []
    for candidato, nombre in candidatos:
        significativas = {p for p in _palabras(nombre) if len(p) >= 3 and p not in PALABRAS_GENERICAS}
        puntaje = len(significativas & en_texto)
        if puntaje:
            puntajes.append((puntaje, candidato))
    if not puntajes:
        return None, False
    mejor = max(p for p, _ in puntajes)
    mejores = [c for p, c in puntajes if p == mejor]
    if len(mejores) > 1:
        return None, True
    return mejores[0], False


class StudyCopilotEngine:
    """Motor de análisis semántico, extracción de entidades y orquestación del Copilot."""

    def __init__(self, db_path: Path | str | None = None, read_only: bool = False):
        self.db_path = db_path
        self.read_only = read_only

    def classify_intents(self, instruction: str) -> list[CopilotIntent]:
        """Clasifica una instrucción en una o varias intenciones atómicas."""
        text = instruction.lower().strip()
        intents: list[CopilotIntent] = []

        # 1. BRIEFING DIARIO / STATUS GENERAL
        briefing_patterns = [
            r"\bresumen\b", r"\bbriefing\b", r"\bstatus\b", r"\bc[oó]mo voy\b",
            r"\bqu[eé] hago hoy\b", r"\bmi avance\b", r"\bplanific",
            r"\bestado general\b", r"\binicio de sesi[oó]n\b",
        ]
        if any(re.search(p, text) for p in briefing_patterns) and not ("página" in text or "pagina" in text):
            intents.append(CopilotIntent(name="BRIEFING", confidence=0.9))

        # 2. ACTUALIZACIÓN DE LECTURA (LIBROS)
        # Ej: "leí 20 páginas", "voy por la página 45", "avancé al capítulo 3 de Designing Data"
        reading_patterns = [
            r"\ble[ií]\b", r"\ble[ií]do\b", r"\bp[aá]ginas?\b", r"\bp[aá]gs?\b", r"\bcap[ií]tulos?\b",
            r"\blibros?\b", r"\btermin[eé] de leer\b",
        ]
        if any(re.search(p, text) for p in reading_patterns):
            params: dict[str, Any] = {}
            # Solo cuenta como avance lo que se afirma con un verbo de avance; una pregunta no lo es
            hay_verbo = re.search(VERBO_DE_AVANCE, text) is not None

            def afirmados(patron: str) -> list[re.Match]:
                return [m for m in re.finditer(patron, text) if hay_verbo and not _en_pregunta(text, m.end())]

            # Páginas absolutas: "página 45", "pag. 120". En "desde la página 40 hasta la 90" vale la última
            abs_pages = afirmados(r"\b(?:p[aá]gina|p[aá]g\.?)\s*(\d+)")
            # Páginas relativas: "leí 20 pags", "leí unas 20 páginas"
            rel_pages = afirmados(r"\b(?:le[ií]|avanc[eé])\s+(?:\w+\s+){0,2}?(\d+)\s*(?:p[aá]ginas?|p[aá]gs?)\b")

            if abs_pages:
                params["target_page"] = int(abs_pages[-1].group(1))
            elif rel_pages:
                params["page_delta"] = int(rel_pages[0].group(1))

            caps = afirmados(r"\bcap[ií]tulo\s*(\d+)")
            if caps:
                params["target_chapter"] = int(caps[-1].group(1))

            if params:
                nombrado = NOMBRADO_TRAS_AVANCE.search(text)
                if nombrado:
                    params["named"] = nombrado.group(1)

            intents.append(CopilotIntent(name="READING_UPDATE", confidence=0.85, parameters=params))

        # 3. ACTUALIZACIÓN DE CURSOS
        course_patterns = [r"\bcursos?\b", r"\bplataforma\b", r"\bdigital house\b", r"\bcoursera\b", r"\bhumai\b", r"\banthropic\b"]
        # Un porcentaje es un avance solo si la frase lo dice ("llevo", "voy", "completé", "al 50%")
        sin_urls = re.sub(r"https?://\S+", " ", text)
        dice_avance = re.search(r"\b(?:avance|avanc[eé]|llevo|voy|va|complet[eé]|termin[eé])\b|\bal\s+-?\d", sin_urls) is not None
        porcentajes = set()
        if dice_avance:
            porcentajes = {float(p.replace(",", ".")) for p in re.findall(r"(?<![\w.,])(-?\d+(?:[.,]\d+)?)\s*%", sin_urls)}
        menciona_curso = any(re.search(p, text) for p in course_patterns)
        solo_libro = re.search(r"\blibros?\b", text) is not None and not menciona_curso
        if (porcentajes and not solo_libro) or (menciona_curso and ("avance" in text or "complet" in text or "http" in text)):
            params = {}
            m_url = re.search(r"(https?://\S+)", instruction)
            if m_url:
                params["url"] = m_url.group(1)
            if len(porcentajes) == 1:
                params["progress_pct"] = porcentajes.pop()
            elif porcentajes:
                params["ambiguous_pct"] = True
            intents.append(CopilotIntent(name="COURSE_UPDATE", confidence=0.8, parameters=params))

        # 4. CONSULTA DE RUTA / ROADMAP
        roadmap_patterns = [
            r"\brutas?\b", r"\broadmaps?\b", r"\bqu[eé] estudiar\b", r"\bsiguiente tema\b",
            r"\bpr[oó]ximo tema\b", r"\btema pendiente\b", r"\bprelaci[oó]n", r"\bdag\b",
            r"\bclase magistral\b", r"\bqu[eé] clase me toca\b",
        ]
        if any(re.search(p, text) for p in roadmap_patterns):
            intents.append(CopilotIntent(name="ROADMAP_QUERY", confidence=0.85))

        # 5. FSRS / TARJETAS / INGLÉS
        fsrs_patterns = [
            r"\btarjetas?\b", r"\bflashcards?\b", r"\bfsrs\b", r"\brepasos?\b", r"\brepasar\b",
            r"\bdue\b", r"\bingl[eé]s\b", r"\bcolocaci[oó]n", r"\bvocabulario\b",
        ]
        if any(re.search(p, text) for p in fsrs_patterns):
            intents.append(CopilotIntent(name="FSRS_STATUS", confidence=0.85))

        # 6. LOG DE SESIÓN / TIEMPO / AGENDA
        schedule_patterns = [
            r"\bpomodoro\b", r"\bsesi[oó]n de estudio\b",
            r"\btiempo estudiado\b", r"\bagenda de hoy\b", r"\bhorarios?\b",
        ]
        minutos = _minutos_estudiados(text)
        if minutos or any(re.search(p, text) for p in schedule_patterns):
            params = {}
            if minutos:
                params["minutes"] = minutos
            intents.append(CopilotIntent(name="SCHEDULE_LOG", confidence=0.8, parameters=params))

        # Si ninguna intención específica se activó, caemos por defecto en BRIEFING
        if not intents:
            intents.append(CopilotIntent(name="BRIEFING", confidence=0.5))

        return intents

    def execute_plan(self, instruction: str, action: str = "auto") -> CopilotExecutionResult:
        """Ejecuta de forma orquestada las intenciones correspondientes a la instrucción."""
        result = CopilotExecutionResult(instruction=instruction)

        intents = self.classify_intents(instruction)
        forzada = {"briefing": "BRIEFING", "reading": "READING_UPDATE", "roadmap": "ROADMAP_QUERY", "fsrs": "FSRS_STATUS"}.get(action)
        if forzada:
            # Se conserva lo que la instrucción trae para esa intención (páginas, capítulo)
            intents = [it for it in intents if it.name == forzada] or [CopilotIntent(name=forzada, confidence=1.0)]

        # 1. EJECUTAR ACCIONES DE MUTACIÓN: el fallo de una no impide las demás
        manejadores = {
            "READING_UPDATE": self._handle_reading_update,
            "COURSE_UPDATE": self._handle_course_update,
            "SCHEDULE_LOG": self._handle_schedule_log,
        }
        for it in intents:
            manejador = manejadores.get(it.name)
            if manejador is None:
                continue
            try:
                manejador(it, result)
            except Exception as e:
                logger.exception("Fallo en la acción %s del copilot", it.name)
                result.warnings.append(f"No se pudo completar la acción {it.name}: {e}")

        # Un avance que no se supo interpretar no se ignora en silencio
        if not result.actions_taken and not result.warnings and _parece_avance(instruction.lower()):
            if self.read_only:
                result.warnings.append("No se registró ningún cambio: el servidor está en modo Read-Only.")
            else:
                result.warnings.append(
                    "No se registró ningún cambio: la instrucción parece informar un avance, pero no se pudo interpretar "
                    "con seguridad. Para registrarlo usá las herramientas directas con valores explícitos: "
                    "study_update_book_progress (libro y página o capítulo), study_update_course_progress "
                    "(curso y porcentaje) o study_log_study_session (minutos)."
                )

        # 2. RECOPILAR ESTADO CONSOLIDADO Y CONSULTAS
        self._gather_status_summary(result)

        # 3. GENERAR NEXT BEST ACTION
        result.next_best_action = self._generate_next_best_action(result.status_summary)

        return result

    def _handle_reading_update(self, intent: CopilotIntent, result: CopilotExecutionResult) -> None:
        """Actualiza el progreso de lectura de un libro, solo si la instrucción trae página o capítulo."""
        params = intent.parameters
        if not any(k in params for k in ("target_page", "page_delta", "target_chapter")):
            # Una pregunta sobre libros no es una actualización
            return

        if self.read_only:
            result.warnings.append("Servidor en modo Read-Only: No se actualizó el avance de lectura.")
            return

        conn = get_connection(self.db_path)
        try:
            repo = LibroRepository(conn, cuenta_mcp_actual())
            books = repo.list_all()
            if not books:
                result.warnings.append("No hay libros registrados para actualizar lectura.")
                return

            target_book, ambiguo = identificar_por_nombre(result.instruction, [(b, b.titulo) for b in books])
            if ambiguo:
                result.warnings.append("La instrucción coincide con más de un libro: no se actualizó la lectura. Indicá el título completo.")
                return
            if not target_book and params.get("named"):
                # Nombró algo que no es un libro registrado: no se asume que habla del libro en lectura
                if re.match(r"cursos?$", params["named"]):
                    return
                result.warnings.append(
                    "La instrucción nombra algo que no coincide con ningún libro registrado: no se actualizó la lectura."
                )
                return
            if not target_book:
                leyendo = [b for b in books if b.estado == EstadoLibro.LEYENDO]
                if len(leyendo) != 1:
                    result.warnings.append(
                        "No se pudo saber a qué libro te referís: no se actualizó la lectura. Indicá el título del libro."
                    )
                    return
                target_book = leyendo[0]

            new_page = None
            if "target_page" in params:
                new_page = params["target_page"]
            elif "page_delta" in params:
                new_page = target_book.pagina_actual + params["page_delta"]
                if target_book.total_paginas and new_page > target_book.total_paginas:
                    result.warnings.append(
                        f"Las {params['page_delta']} páginas indicadas superan lo que queda de «{target_book.titulo}»: "
                        f"se dejó en su última página ({target_book.total_paginas})."
                    )
                    new_page = target_book.total_paginas
            new_chap = params.get("target_chapter")

            try:
                updated_book = repo.update_progress(id=target_book.id, capitulo_actual=new_chap, pagina_actual=new_page)
            except ValueError as e:
                result.warnings.append(f"No se actualizó la lectura de «{target_book.titulo}»: {e}")
                return
            if not updated_book:
                result.warnings.append(f"No se pudo actualizar la lectura de «{target_book.titulo}».")
                return

            tot_p = f"/{updated_book.total_paginas}" if updated_book.total_paginas else ""
            result.actions_taken.append(
                f"📖 Lectura actualizada: **{updated_book.titulo}** a la Pág. {updated_book.pagina_actual}{tot_p} "
                f"(Cap. {updated_book.capitulo_actual}) → **{updated_book.porcentaje_leido:.1f}%** completado."
            )
        finally:
            conn.close()

    def _handle_course_update(self, intent: CopilotIntent, result: CopilotExecutionResult) -> None:
        """Actualiza el avance de un curso identificado sin ambigüedad por su URL o su nombre."""
        pct = intent.parameters.get("progress_pct")
        if pct is None:
            if intent.parameters.get("ambiguous_pct") and not self.read_only:
                result.warnings.append("La instrucción trae más de un porcentaje: no se actualizó ningún curso. Indicá un solo avance.")
            return

        if self.read_only:
            result.warnings.append("Servidor en modo Read-Only: No se actualizó el avance del curso.")
            return

        if pct < 0.0 or pct > 100.0:
            result.warnings.append(f"El avance {pct:g}% no es válido (debe estar entre 0 y 100): no se actualizó ningún curso.")
            return

        conn = get_connection(self.db_path)
        try:
            repo = CursoRepository(conn, cuenta_mcp_actual())
            courses = repo.list_all()
            if not courses:
                result.warnings.append("No hay cursos registrados en el hub.")
                return

            target_course = None
            url = intent.parameters.get("url")
            if url:
                url_limpia = url.rstrip(".,;:)").rstrip("/")
                coinciden = [c for c in courses if (c.url_aula or "").rstrip("/") == url_limpia]
                if len(coinciden) != 1:
                    result.warnings.append("La URL indicada no coincide con ningún curso registrado: no se actualizó ninguno.")
                    return
                target_course = coinciden[0]
            if not target_course:
                sin_url = re.sub(r"https?://\S+", " ", result.instruction)
                target_course, ambiguo = identificar_por_nombre(sin_url, [(c, c.nombre_curso) for c in courses])
                if ambiguo:
                    result.warnings.append("La instrucción coincide con más de un curso: no se actualizó ninguno. Indicá el nombre completo o la URL del aula.")
                    return
            if not target_course:
                result.warnings.append("No se pudo saber a qué curso te referís: no se actualizó ninguno. Indicá su nombre o la URL del aula.")
                return

            repo.update_progress(target_course.id, pct)
            result.actions_taken.append(
                f"🎓 Curso actualizado: **{target_course.nombre_curso}** al **{pct:.1f}%**."
            )
        finally:
            conn.close()

    def _handle_schedule_log(self, intent: CopilotIntent, result: CopilotExecutionResult) -> None:
        """Registra tiempo de estudio, solo si la instrucción dice cuántos minutos."""
        minutes = intent.parameters.get("minutes")
        if minutes is None:
            # Preguntar por la agenda o el horario no registra nada
            return

        if self.read_only:
            result.warnings.append("Servidor en modo Read-Only: No se registró la sesión de estudio.")
            return

        if minutes <= 0:
            result.warnings.append("La duración debe ser mayor a 0 minutos: no se registró la sesión.")
            return

        conn = get_connection(self.db_path)
        try:
            repo = FocusRepository(conn, cuenta_mcp_actual())
            repo.record_session(FocusSessionCreate(
                duracion_minutos=minutes,
                tipo="otro",
                notas=f"Registrado automáticamente desde instrucción: {result.instruction}",
            ))
            result.actions_taken.append(f"⏱️ Sesión registrada: **{minutes} minutos** de estudio hoy.")
        finally:
            conn.close()

    def _gather_status_summary(self, result: CopilotExecutionResult) -> None:
        """Recopila el estado consolidado de FSRS, Roadmaps, Libros y Agenda."""
        conn = get_connection(self.db_path)
        try:
            # 1. FSRS v5 Due count
            fsrs_repo = FSRSRepository(conn, cuenta_mcp_actual())
            due_cards = fsrs_repo.get_due_cards(limit=100)
            result.status_summary["Tarjetas FSRS Vencidas Hoy"] = f"{len(due_cards)} pendientes"

            # 2. Libro en lectura activa
            book_repo = LibroRepository(conn, cuenta_mcp_actual())
            reading_books = book_repo.list_all(estado=EstadoLibro.LEYENDO)
            if reading_books:
                b = reading_books[0]
                tot = f"/{b.total_paginas}" if b.total_paginas else ""
                result.status_summary["Libro Activo"] = f"{b.titulo} (Pág. {b.pagina_actual}{tot}, {b.porcentaje_leido:.1f}%)"
            else:
                result.status_summary["Libro Activo"] = "Ninguno en estado 'leyendo'"

            # 3. Siguiente tema en el Roadmap
            roadmap_repo = RoadmapRepository(cuenta_mcp_actual(), self.db_path)
            roadmaps = roadmap_repo.get_roadmaps()
            if roadmaps:
                active_rm = roadmaps[0]
                rm_detail = roadmap_repo.get_roadmap(active_rm.id)
                next_topic = None
                if rm_detail and rm_detail.modulos:
                    for m in rm_detail.modulos:
                        for t in m.temas:
                            if t.estado in (EstadoTema.PENDIENTE, EstadoTema.EN_PROGRESO):
                                next_topic = t
                                break
                        if next_topic:
                            break

                if next_topic:
                    result.status_summary["Ruta Activa"] = f"{active_rm.titulo} ({active_rm.progreso_pct:.1f}%)"
                    result.status_summary["Próximo Tema Desbloqueado"] = f"Tema #{next_topic.id}: {next_topic.titulo} ({next_topic.estado.value})"
                else:
                    result.status_summary["Ruta Activa"] = f"{active_rm.titulo} (100% completada 🎉)"
            else:
                result.status_summary["Rutas de Aprendizaje"] = "Sin rutas creadas aún"

            # 4. Minutos estudiados hoy
            focus_repo = FocusRepository(conn, cuenta_mcp_actual())
            stats = focus_repo.get_weekly_stats()
            total_min = stats.get("minutos_hoy", 0)
            result.status_summary["Tiempo de Estudio Hoy"] = f"{total_min} minutos"
        finally:
            conn.close()

    def _generate_next_best_action(self, summary: dict[str, Any]) -> str:
        """Calcula la recomendación proactiva más prioritaria según la ciencia del aprendizaje."""
        fsrs_info = summary.get("Tarjetas FSRS Vencidas Hoy", "")
        # Extraer número de tarjetas
        m_due = re.search(r"(\d+)", fsrs_info)
        due_count = int(m_due.group(1)) if m_due else 0

        if due_count > 0:
            return (
                f"🔥 **Prioridad 1 (Retención Activa):** Tienes **{due_count} tarjetas FSRS** vencidas para hoy. "
                "Haz un sprint de 5 a 10 minutos de Active Recall para consolidar tu vocabulario técnico antes de agregar nuevo contenido."
            )

        topic_info = summary.get("Próximo Tema Desbloqueado")
        if topic_info and "100%" not in summary.get("Ruta Activa", ""):
            return (
                f"🚀 **Prioridad 2 (Avance Curricular):** Tu siguiente hito crítico es **{topic_info}**. "
                "Pídeme generar la **Clase Magistral** con sus laboratorios prácticos y flashcards para avanzar en la ruta."
            )

        libro_info = summary.get("Libro Activo")
        if libro_info and "Ninguno" not in libro_info:
            return (
                f"📖 **Prioridad 3 (Lectura Profunda):** Continúa tu bloque de lectura en **{libro_info}**. "
                "Avanzar 10 o 15 páginas hoy mantendrá tu racha de estudio activa."
            )

        return (
            "🎉 **¡Estás al día!** Has completado tus repasos y actividades programadas. "
            "Puedes explorar un nuevo libro técnico o crear una nueva ruta de aprendizaje en Aulento."
        )


def register_copilot_tool(server: Any, read_only: bool = False, db_path: Path | str | None = None) -> None:
    """Registra la meta-herramienta study_copilot en el servidor MCP."""
    tool = herramienta_auditada(server, db_path)

    @tool()
    def study_copilot(
        instruction: str,
        action: str = "auto",
        context: dict[str, Any] | None = None,
    ) -> str:
        """Asistente de estudio inteligente unificado y router de intención en un solo comando.
        
        Permite consultar o actualizar el estado del estudiante en lenguaje natural:
        - Actualizar avance de lectura: 'Leí 20 páginas de Designing Data-Intensive' o 'voy por la página 85'.
        - Consultar ruta crítica y qué estudiar: '¿Qué tema me toca estudiar hoy?' o 'consulta mi ruta'.
        - Briefing diario consolidado: 'Dame un resumen de mi día y cómo va mi progreso'.
        - Registrar sesiones de estudio: 'Estudié 45 minutos de Apache Beam'.

        Interpreta la instrucción con reglas, no con IA: solo escribe lo que la frase afirma con claridad,
        y si no la entiende lo dice en "Advertencias" sin registrar nada. Cuando ya conocés el libro, el
        curso o los minutos exactos, usá las herramientas directas (study_update_book_progress,
        study_update_course_progress, study_log_study_session).
        
        Args:
            instruction: Instrucción o consulta en lenguaje natural del usuario.
            action: 'auto' (detecta la intención automáticamente), 'briefing', 'reading', 'roadmap', o 'fsrs'.
            context: Metadatos o contexto adicional opcional.
        """
        try:
            engine = StudyCopilotEngine(db_path=db_path, read_only=read_only)
            result = engine.execute_plan(instruction=instruction, action=action)
            log_mcp_tool_execution(
                "study_copilot",
                {"instruction": instruction, "action": action},
                status="success",
                db_path=db_path,
            )
            return result.to_markdown()
        except Exception as e:
            logger.exception("Error al ejecutar study_copilot")
            log_mcp_tool_execution(
                "study_copilot",
                {"instruction": instruction, "action": action},
                status="error",
                error_message=str(e),
                db_path=db_path,
            )
            return f"Error en study_copilot: {e}"
