"""Motor Algorítmico de Planificación Adaptativa y Recomendación de Estudio Diario y Semanal."""

import logging
import sqlite3
from datetime import UTC, date, datetime, timedelta

from aulento.core.activity_tracker import ActivityTracker
from aulento.db.cuenta import exigir_cuenta
from aulento.db.fsrs_repository import FSRSRepository
from aulento.db.repository import (
    BloqueHorarioRepository,
    CursoRepository,
    LibroRepository,
)
from aulento.models.curso import EstadoCurso, PrioridadCurso
from aulento.models.horario import BloqueHorarioCreate
from aulento.models.libro import EstadoLibro
from aulento.models.study_planner import (
    AdaptivePlanRequest,
    AdaptivePlanResponse,
    ApplyPlanRequest,
    ApplyPlanResponse,
    DailyBriefing,
    PedagogicalPhase,
    PlannedStudyBlock,
)
from aulento.roadmap.macro_fsrs import MacroFSRSEngine, MacroFSRSRepository

logger = logging.getLogger(__name__)



def _ahora_local() -> datetime:
    """La hora de la máquina: "hoy", la agenda y la racha se cuentan en el huso del estudiante, no en UTC."""
    return datetime.now().astimezone()

class StudyPlannerEngine:
    """Motor de cálculo y optimización de planes de estudio adaptativos."""

    def __init__(self, conn: sqlite3.Connection, user_id: int):
        self.conn = conn
        self.user_id = exigir_cuenta(user_id)
        self.curso_repo = CursoRepository(conn, user_id)
        self.libro_repo = LibroRepository(conn, user_id)
        self.horario_repo = BloqueHorarioRepository(conn, user_id)
        self.fsrs_repo = FSRSRepository(conn, user_id)
        macro_repo = MacroFSRSRepository(self.user_id, conn=conn)
        self.macro_engine = MacroFSRSEngine(self.user_id, repository=macro_repo)
        self.tracker = ActivityTracker(user_id=self.user_id, conn=conn)

    def obtener_daily_briefing(self, fecha_objetivo: date | None = None) -> DailyBriefing:
        """Genera el resumen ejecutivo holístico de la cuenta para el día indicado."""
        hoy = fecha_objetivo or _ahora_local().date()
        hoy_str = hoy.isoformat()

        # 1. Métricas de consistencia y racha
        heatmap = self.tracker.get_heatmap(days=7)
        streak = heatmap.streak
        racha_dias = streak.current_streak
        record_racha = streak.longest_streak

        dia_hoy = next((d for d in heatmap.days if d.date == hoy_str), None)
        minutos_hoy = dia_hoy.study_minutes if dia_hoy else 0
        estudiado_hoy = minutos_hoy > 0

        # 2. FSRS v5 inglés técnico
        fsrs_stats = self.fsrs_repo.count_stats()
        fsrs_due_count = fsrs_stats.get("due_today", 0)

        # 3. Macro-FSRS de rutas
        macro_due_topics = []
        try:
            macro_due_topics = self.macro_engine.repo.get_due_topics()
        except Exception as e:  # noqa: BLE001
            logger.warning("No se pudieron consultar temas de Macro-FSRS: %s", e)
        macro_fsrs_due_count = len(macro_due_topics)

        # 4. Curso prioritario sugerido
        cursos_activos = self.curso_repo.list_all(estado=EstadoCurso.EN_CURSO)
        # Ordenar por prioridad: ALTA=1, MEDIA=2, BAJA=3
        prio_map = {PrioridadCurso.ALTA: 1, PrioridadCurso.MEDIA: 2, PrioridadCurso.BAJA: 3}
        cursos_activos.sort(key=lambda c: (prio_map.get(c.prioridad, 2), -c.progreso_pct))
        curso_sugerido = None
        if cursos_activos:
            c = cursos_activos[0]
            curso_sugerido = {
                "id": c.id,
                "nombre_curso": c.nombre_curso,
                "plataforma": c.nombre_plataforma or "Externa",
                "progreso_pct": c.progreso_pct,
                "prioridad": c.prioridad.value,
            }

        # 5. Libro sugerido con tramo pendiente
        libros = self.libro_repo.list_all()
        libros_activos = [
            l
            for l in libros
            if l.estado != EstadoLibro.COMPLETADO
            and (l.total_paginas is None or l.pagina_actual < l.total_paginas)
        ]
        libros_activos.sort(
            key=lambda l: (
                l.estado != EstadoLibro.LEYENDO,
                # Sin total conocido no hay avance que comparar: va después de los que sí lo tienen
                -(l.pagina_actual / l.total_paginas if l.total_paginas else 0.0),
            )
        )
        libro_sugerido = None
        if libros_activos:
            b = libros_activos[0]
            # None si no se sabe cuántas páginas tiene: 0 se leería como "terminado"
            paginas_restantes = max(0, b.total_paginas - (b.pagina_actual or 0)) if b.total_paginas else None
            libro_sugerido = {
                "id": b.id,
                "titulo": b.titulo,
                "pagina_actual": b.pagina_actual,
                "total_paginas": b.total_paginas,
                "paginas_restantes": paginas_restantes,
            }

        # 6. Cálculo de Urgencia (0 - 100)
        score = 15
        if fsrs_due_count > 30:
            score += 35
        elif fsrs_due_count > 10:
            score += 20
        elif fsrs_due_count > 0:
            score += 10

        if macro_fsrs_due_count > 0:
            score += 15

        if curso_sugerido and curso_sugerido.get("prioridad") == PrioridadCurso.ALTA.value:
            score += 20

        if not estudiado_hoy:
            score += 15

        urgency_score = min(100, max(0, score))

        # 7. Mensaje heurístico de enfoque
        if fsrs_due_count > 25:
            mensaje = f"Prioridad alta: tienes {fsrs_due_count} colocaciones de inglés técnico vencidas. Conviene empezar por el mazo FSRS para preservar la retención."
        elif curso_sugerido and curso_sugerido.get("prioridad") == PrioridadCurso.ALTA.value:
            mensaje = f"Día ideal para Deep Work: avanza con '{curso_sugerido['nombre_curso']}' ({curso_sugerido['progreso_pct']:.0f}% completado)."
        elif libro_sugerido:
            mensaje = f"Buen ritmo: dedica tiempo de lectura activa a '{libro_sugerido['titulo']}' y realiza un cuestionario Active Recall."
        else:
            mensaje = "Excelente constancia: mantén tu racha activa dedicando al menos un bloque de 25 minutos hoy."

        return DailyBriefing(
            fecha=hoy_str,
            racha_dias=racha_dias,
            record_racha=record_racha,
            estudiado_hoy=estudiado_hoy,
            minutos_hoy=minutos_hoy,
            fsrs_due_count=fsrs_due_count,
            macro_fsrs_due_count=macro_fsrs_due_count,
            curso_sugerido=curso_sugerido,
            libro_sugerido=libro_sugerido,
            urgency_score=urgency_score,
            mensaje_enfoque=mensaje,
        )

    def _calcular_hora_inicio_por_defecto(self) -> str:
        """Calcula la hora de inicio aproximada al próximo cuarto de hora."""
        ahora = _ahora_local()
        minutos = ahora.minute
        desplazamiento = (15 - (minutos % 15)) % 15
        if desplazamiento == 0:
            desplazamiento = 15
        proximo = ahora + timedelta(minutes=desplazamiento)
        return proximo.strftime("%H:%M")

    def _sumar_minutos_a_hora(self, hora_str: str, minutos: int) -> str:
        """Suma minutos a una hora en formato HH:MM."""
        try:
            dt = datetime.strptime(hora_str, "%H:%M").replace(tzinfo=UTC)
            dt_fin = dt + timedelta(minutes=minutos)
            return dt_fin.strftime("%H:%M")
        except ValueError:
            return hora_str

    def generar_plan_adaptativo(self, req: AdaptivePlanRequest) -> AdaptivePlanResponse:
        """Calcula y estructura los bloques de estudio óptimos según el tiempo y prioridades."""
        total_disp = req.available_minutes
        focus = {f.lower() for f in req.focus_areas} if req.focus_areas else None

        briefing = self.obtener_daily_briefing()
        fsrs_due = briefing.fsrs_due_count
        macro_due = briefing.macro_fsrs_due_count
        curso_sug = briefing.curso_sugerido
        libro_sug = briefing.libro_sugerido

        hora_cursor = req.start_time or self._calcular_hora_inicio_por_defecto()
        bloques: list[PlannedStudyBlock] = []

        # Heurística de fases pedagógicas:
        # FASE 1: Calentamiento & Spaced Repetition (FSRS v5)
        tiempo_fsrs = 0
        if (focus is None or "fsrs" in focus) and (fsrs_due > 0 or focus is not None):
            if total_disp <= 25:
                tiempo_fsrs = min(total_disp, 15)
            elif total_disp <= 45:
                tiempo_fsrs = 10
            elif total_disp <= 75:
                tiempo_fsrs = 15
            else:
                tiempo_fsrs = 20

            hora_fin = self._sumar_minutos_a_hora(hora_cursor, tiempo_fsrs)
            bloques.append(
                PlannedStudyBlock(
                    fase=PedagogicalPhase.WARMUP_FSRS,
                    titulo="Repaso Diario FSRS v5 - Inglés Técnico",
                    descripcion=f"Revisión de tarjetas de inglés técnico profesional vencidas ({fsrs_due} tarjetas pendientes).",
                    duracion_minutos=tiempo_fsrs,
                    recurso_tipo="fsrs",
                    hora_inicio=hora_cursor,
                    hora_fin=hora_fin,
                    meta_especifica=f"Repasar {min(fsrs_due, 20)} tarjetas" if fsrs_due > 0 else "10 colocaciones",
                )
            )
            hora_cursor = hora_fin

        # FASE 1b: Macro-FSRS de Temas de Rutas (si hay temas vencidos y tiempo disponible)
        tiempo_macro = 0
        tiempo_restante = total_disp - sum(b.duracion_minutos for b in bloques)
        if (focus is None or "macro_fsrs" in focus) and macro_due > 0 and tiempo_restante >= 20:
            tiempo_macro = 10
            hora_fin = self._sumar_minutos_a_hora(hora_cursor, tiempo_macro)
            bloques.append(
                PlannedStudyBlock(
                    fase=PedagogicalPhase.MACRO_FSRS,
                    titulo="Micro-Quiz Feynman de Retención Macro",
                    descripcion=f"Evaluación conceptual activa de temas de rutas completadas ({macro_due} temas por repasar).",
                    duracion_minutos=tiempo_macro,
                    recurso_tipo="macro_fsrs",
                    hora_inicio=hora_cursor,
                    hora_fin=hora_fin,
                    meta_especifica="Completar 1 micro-quiz Feynman",
                )
            )
            hora_cursor = hora_fin

        # FASE 2: Deep Work Académico (Cursos / Rutas)
        tiempo_restante = total_disp - sum(b.duracion_minutos for b in bloques)
        if (focus is None or "cursos" in focus) and curso_sug and tiempo_restante >= 20:
            # Determinamos si la sesión permite descanso
            incluir_break = req.include_breaks and total_disp >= 60 and tiempo_restante >= 45
            duracion_curso = 25 if tiempo_restante < 45 else (35 if incluir_break else min(tiempo_restante - 15, 50))

            hora_fin = self._sumar_minutos_a_hora(hora_cursor, duracion_curso)
            bloques.append(
                PlannedStudyBlock(
                    fase=PedagogicalPhase.DEEP_WORK_COURSE,
                    titulo=f"Deep Work: {curso_sug['nombre_curso']}",
                    descripcion=f"Avance en plataforma {curso_sug['plataforma']}. Progreso actual: {curso_sug['progreso_pct']:.0f}%.",
                    duracion_minutos=duracion_curso,
                    recurso_tipo="curso",
                    recurso_id=curso_sug["id"],
                    recurso_nombre=curso_sug["nombre_curso"],
                    hora_inicio=hora_cursor,
                    hora_fin=hora_fin,
                    meta_especifica="Completar al menos 1 lección / módulo",
                )
            )
            hora_cursor = hora_fin

            # Descanso corto si aplica
            if incluir_break:
                hora_fin_break = self._sumar_minutos_a_hora(hora_cursor, 5)
                bloques.append(
                    PlannedStudyBlock(
                        fase=PedagogicalPhase.BREAK,
                        titulo="Descanso Regenerativo (Pomodoro)",
                        descripcion="Pausa breve para hidratación, descanso visual y consolidación neural.",
                        duracion_minutos=5,
                        recurso_tipo="descanso",
                        hora_inicio=hora_cursor,
                        hora_fin=hora_fin_break,
                    )
                )
                hora_cursor = hora_fin_break

        # FASE 3: Consolidación & Lectura Activa (Libros)
        tiempo_restante = total_disp - sum(b.duracion_minutos for b in bloques)
        if (focus is None or "libros" in focus) and libro_sug and tiempo_restante >= 10:
            duracion_lectura = tiempo_restante
            hora_fin = self._sumar_minutos_a_hora(hora_cursor, duracion_lectura)
            meta_paginas = max(5, int(duracion_lectura / 2.0))
            bloques.append(
                PlannedStudyBlock(
                    fase=PedagogicalPhase.ACTIVE_READING_BOOK,
                    titulo=f"Lectura Activa: {libro_sug['titulo']}",
                    descripcion=f"Lectura técnica desde pág. {libro_sug['pagina_actual']} + cuestionario Active Recall / Cosecha FSRS.",
                    duracion_minutos=duracion_lectura,
                    recurso_tipo="libro",
                    recurso_id=libro_sug["id"],
                    recurso_nombre=libro_sug["titulo"],
                    hora_inicio=hora_cursor,
                    hora_fin=hora_fin,
                    meta_especifica=f"Leer ~{meta_paginas} páginas y autoevaluarse",
                )
            )
            hora_cursor = hora_fin
        elif tiempo_restante > 0 and bloques:
            # Si sobraron minutos y no hay libro, sumamos el resto al bloque principal de estudio
            bloques[-1].duracion_minutos += tiempo_restante
            bloques[-1].hora_fin = self._sumar_minutos_a_hora(bloques[-1].hora_inicio or hora_cursor, bloques[-1].duracion_minutos)
        elif not bloques:
            # Si no hay cursos ni tarjetas ni libros cargados
            hora_fin = self._sumar_minutos_a_hora(hora_cursor, total_disp)
            bloques.append(
                PlannedStudyBlock(
                    fase=PedagogicalPhase.DEEP_WORK_COURSE,
                    titulo="Sesión de Estudio Libre",
                    descripcion="Configura nuevos cursos o rutas en el Hub Académico para personalizar tus planes.",
                    duracion_minutos=total_disp,
                    recurso_tipo="curso",
                    hora_inicio=hora_cursor,
                    hora_fin=hora_fin,
                )
            )

        total_planificado = sum(b.duracion_minutos for b in bloques)
        fecha_plan = req.target_date or _ahora_local().date().isoformat()

        resumen = (
            f"Plan adaptado para {total_planificado} minutos estructurado en {len(bloques)} bloque(s): "
            f"calentamiento FSRS para memoria a largo plazo, foco académico en deep work y cierre de lectura activa."
        )

        return AdaptivePlanResponse(
            fecha=fecha_plan,
            total_minutos=total_planificado,
            bloques=bloques,
            resumen_pedagogico=resumen,
            score_urgencia=briefing.urgency_score,
            mensaje_enfoque=briefing.mensaje_enfoque,
        )

    def aplicar_plan_a_agenda(self, req: ApplyPlanRequest) -> ApplyPlanResponse:
        """Inserta los bloques del plan adaptativo en la agenda del usuario."""
        # 1=Lunes, 7=Domingo
        dia_semana = req.dia_semana or _ahora_local().isoweekday()

        # Si se solicita reemplazo, inactivamos o eliminamos bloques previos del día
        if req.reemplazar_existentes:
            existentes = self.horario_repo.list_all(dia_semana=dia_semana)
            for ex in existentes:
                try:
                    self.horario_repo.delete(ex.id)
                except Exception as e:  # noqa: BLE001
                    logger.warning("No se pudo eliminar bloque previo id=%s: %s", ex.id, e)

        bloques_creados_ids: list[int] = []
        hora_cursor = self._calcular_hora_inicio_por_defecto()

        for b in req.bloques:
            inicio = b.hora_inicio or hora_cursor
            fin = b.hora_fin or self._sumar_minutos_a_hora(inicio, b.duracion_minutos)

            # Prefijo amigable en descripción
            desc = f"[{b.fase.value.upper()}] {b.titulo}"
            if b.meta_especifica:
                desc += f" ({b.meta_especifica})"

            nuevo_bloque = self.horario_repo.create(
                BloqueHorarioCreate(
                    dia_semana=dia_semana,
                    hora_inicio=inicio,
                    hora_fin=fin,
                    descripcion=desc,
                    activo=True,
                )
            )
            bloques_creados_ids.append(nuevo_bloque.id)
            hora_cursor = fin

        dias_nombre = {
            1: "Lunes", 2: "Martes", 3: "Miércoles", 4: "Jueves",
            5: "Viernes", 6: "Sábado", 7: "Domingo"
        }
        nombre_dia = dias_nombre.get(dia_semana, f"Día {dia_semana}")

        return ApplyPlanResponse(
            success=True,
            dia_semana=dia_semana,
            bloques_creados=len(bloques_creados_ids),
            bloque_ids=bloques_creados_ids,
            mensaje=f"Se insertaron {len(bloques_creados_ids)} bloques de estudio en la agenda para {nombre_dia}.",
        )
