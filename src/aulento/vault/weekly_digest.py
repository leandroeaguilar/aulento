"""Exportador de Resumen Semanal (Weekly Digest) formateado para el Weekly Dashboard de Obsidian."""

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from aulento.db.connection import get_connection
from aulento.db.cuenta import exigir_cuenta
from aulento.db.repository import (
    CursoRepository,
    LibroRepository,
    BloqueHorarioRepository,
    PlataformaRepository,
)
from aulento.db.focus_repository import FocusRepository
from aulento.fsrs.stats import get_full_fsrs_stats
from aulento.vault.rutas import resolver_en_vault, vault_de_la_cuenta, vault_de_la_cuenta_con_conexion_propia
from aulento.connectors.duolingo import DuolingoClient, DuolingoSinConfigurar


class WeeklyDigestExporter:
    """Compila el progreso de estudio de una cuenta y exporta un resumen Markdown a su vault."""

    def __init__(self, user_id: int, conn: Optional[sqlite3.Connection] = None, vault_path: Optional[Path] = None):
        self.user_id = exigir_cuenta(user_id)
        self._conn = conn
        self._vault_path = vault_path

    @property
    def vault_path(self) -> Path:
        """Vault de la cuenta: la carpeta recibida al construir o, si no, la que resuelve `vault_de_la_cuenta`."""
        if self._vault_path is not None:
            return self._vault_path
        if self._conn:
            return vault_de_la_cuenta(self._conn, self.user_id)
        return vault_de_la_cuenta_con_conexion_propia(self.user_id)

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn:
            return self._conn
        return get_connection()

    def get_current_week_label(self) -> str:
        """Retorna el código de semana ISO estándar (ej. 2026-W39)."""
        now = datetime.now(timezone.utc)
        iso_year, iso_week, _ = now.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"

    def build_digest(self, week_label: Optional[str] = None) -> Dict[str, Any]:
        """Compila los datos de SQLite y produce el documento Markdown del Weekly Digest."""
        if week_label:
            clean_label = week_label.strip()
            if not re.match(r"^[A-Za-z0-9_-]+$", clean_label):
                raise ValueError(f"Etiqueta de semana inválida o insegura: '{week_label}'")
            label = clean_label
        else:
            label = self.get_current_week_label()
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        conn = self._get_conn()
        try:
            curso_repo = CursoRepository(conn, self.user_id)
            libro_repo = LibroRepository(conn, self.user_id)
            bloque_repo = BloqueHorarioRepository(conn, self.user_id)
            plat_repo = PlataformaRepository(conn, self.user_id)
            focus_repo = FocusRepository(conn, self.user_id)

            courses = curso_repo.list_all()
            platforms = {p.id: p.nombre for p in plat_repo.list_all()}
            books = libro_repo.list_all()
            blocks = bloque_repo.list_all()
            fsrs_stats = get_full_fsrs_stats(conn, self.user_id)
            focus_stats = focus_repo.get_weekly_stats()
        finally:
            if not self._conn:
                conn.close()

        # Tabla de cursos
        if courses:
            courses_rows = []
            for c in courses:
                p_name = platforms.get(c.plataforma_id, "Plataforma")
                courses_rows.append(f"| {c.nombre_curso} | {p_name} | {c.progreso_pct:.0f}% | {c.estado} | {c.prioridad} |")
            courses_table = "\n".join(courses_rows)
        else:
            courses_table = "| Sin cursos registrados | - | 0% | - | - |"

        # Tabla de libros
        if books:
            books_rows = []
            for b in books:
                pct = (b.capitulo_actual / b.total_capitulos * 100) if b.total_capitulos > 0 else 0
                books_rows.append(f"| {b.titulo} | {b.capitulo_actual}/{b.total_capitulos} | {pct:.0f}% | {b.estado} |")
            books_table = "\n".join(books_rows)
        else:
            books_table = "| Sin libros en lectura | 0/0 | 0% | - |"

        # Bloques de horario y cálculo de horas planificadas
        dias = {1: "Lunes", 2: "Martes", 3: "Miércoles", 4: "Jueves", 5: "Viernes", 6: "Sábado", 7: "Domingo"}
        total_planned_minutes = 0
        if blocks:
            blocks_text = "\n".join([f"- **{dias.get(b.dia_semana, 'Día')} ({b.hora_inicio} - {b.hora_fin}):** {b.descripcion} [{b.tipo}]" for b in blocks])
            for b in blocks:
                try:
                    h_in, m_in = map(int, b.hora_inicio.split(":"))
                    h_out, m_out = map(int, b.hora_fin.split(":"))
                    diff = (h_out * 60 + m_out) - (h_in * 60 + m_in)
                    total_planned_minutes += max(0, diff)
                except Exception:
                    total_planned_minutes += 60
        else:
            blocks_text = "- Sin bloques de estudio estructurados en la agenda."

        planned_hours = round(total_planned_minutes / 60.0, 1)
        actual_hours = focus_stats["horas_semana"]
        compliance_pct = (actual_hours / planned_hours * 100.0) if planned_hours > 0 else 0.0

        if focus_stats["por_tipo_minutos"]:
            focus_type_lines = "\n".join([f"  - **{t}:** {m} min ({round(m/60.0, 1)} hrs)" for t, m in focus_stats["por_tipo_minutos"].items()])
        else:
            focus_type_lines = "  - *Sin registros detallados de foco esta semana.*"

        # Consulta resiliente de Duolingo, con el usuario de la cuenta
        duo_text = ""
        conn = self._get_conn()
        try:
            duo_profile = DuolingoClient(conn, self.user_id).get_profile()
            cached_suffix = " *(datos locales en caché)*" if duo_profile.is_cached else ""
            duo_text = (
                f"- **Duolingo (@{duo_profile.username}):** 🔥 **{duo_profile.streak} días de racha** • "
                f"⚡ **{duo_profile.total_xp:,} XP** ({duo_profile.current_course_title}){cached_suffix}.\n"
                f"- **Google Labs (LLL):** Micro-lecciones activas con IA y práctica conversacional.\n"
            )
        except DuolingoSinConfigurar:
            duo_text = "- **Duolingo:** Sin usuario configurado.\n"
        except Exception:
            duo_text = "- **Duolingo:** Sincronización pendiente o sin conexión.\n"
        finally:
            if not self._conn:
                conn.close()

        # Markdown completo
        content = (
            "---\n"
            "type: WeeklyDigest\n"
            f"title: \"Weekly Digest — {label}\"\n"
            f"semana: \"{label}\"\n"
            f"fecha: \"{today_str}\"\n"
            "tags: [weekly, dashboard, estudio, metricas, obsidian]\n"
            "---\n\n"
            f"# 📊 Weekly Study Digest — {label}\n\n"
            f"> **Semana:** `{label}`  \n"
            f"> **Generado automáticamente por:** Aulento (Local-First)  \n"
            f"> **Fecha:** {today_str}\n\n"
            "## 🧠 1. Memoria Espaciada e Inglés Técnico (FSRS v5)\n"
            f"- **Racha Actual:** 🔥 **{fsrs_stats['streak_days']} días** continuos de repaso.\n"
            f"- **Retención Estimada:** 🎯 **{fsrs_stats['retention_rate']:.1f}%**.\n"
            f"- **Repasos Históricos Realizados:** 📚 **{fsrs_stats['total_reviews']}** calificaciones.\n"
            f"- **Tarjetas Pendientes Hoy:** {fsrs_stats['due_today']} de {fsrs_stats['total_cards']} tarjetas en el mazo.\n"
            f"- **Estado Cognitivo:** {fsrs_stats['learning']} en aprendizaje, {fsrs_stats['review']} dominadas, {fsrs_stats['relearning']} en relearning.\n\n"
            "### 🦉 Hábitos de Idioma & Práctica Diaria (Duolingo & Google Labs)\n"
            f"{duo_text}\n"
            "## 🏛 2. Progreso de Cursos Académicos\n"
            "| Curso | Plataforma | Progreso | Estado | Prioridad |\n"
            "|---|---|---|---|---|\n"
            f"{courses_table}\n\n"
            "## 📖 3. Reading Tracker de Libros Técnicos\n"
            "| Título del Libro | Capítulos Leídos | Avance % | Estado |\n"
            "|---|---|---|---|\n"
            f"{books_table}\n\n"
            "## 🗓 4. Compromisos de la Agenda de Estudio\n"
            f"{blocks_text}\n\n"
            "## ⏱️ 5. Horas Reales Estudiadas (Focus & Pomodoro)\n"
            f"- **Horas Reales Ejecutadas esta Semana:** ⏱️ **{actual_hours} hrs** ({focus_stats['minutos_semana']} min en {focus_stats['sesiones_semana']} sesiones).\n"
            f"- **Horas Planificadas en la Agenda:** 🗓️ **{planned_hours} hrs**.\n"
            f"- **Cumplimiento de Enfoque:** **{compliance_pct:.0f}%** de la meta planificada.\n"
            f"- **Desglose por Modalidad:**\n{focus_type_lines}\n\n"
            "## 🎯 6. Foco y Compromisos para la Próxima Semana\n"
            "- [ ] Mantener la racha diaria en Duolingo y FSRS v5 (Listening & Shadowing).\n"
            "- [ ] Completar al menos un módulo o clase de los cursos con prioridad alta.\n"
            "- [ ] Ejecutar sesión de examen Active Recall y comprobación de la Técnica Feynman sobre las notas de la semana.\n"
        )

        relative_path = f"02 MOCs/Weekly-Digest-{label}.md"

        return {
            "week_label": label,
            "title": f"Weekly Digest — {label}",
            "relative_path": relative_path,
            "content": content,
            "metrics": {
                "courses_count": len(courses),
                "books_count": len(books),
                "fsrs_due": fsrs_stats["due_today"],
                "streak": fsrs_stats["streak_days"],
                "retention": fsrs_stats["retention_rate"],
                "focus_hours": actual_hours,
                "focus_sessions": focus_stats["sesiones_semana"],
                "planned_hours": planned_hours,
                "compliance_pct": round(compliance_pct, 1),
            }
        }

    def save_digest_to_vault(self, week_label: Optional[str] = None) -> Path:
        """Guarda físicamente el documento Weekly Digest en 02 MOCs/ del Vault."""
        digest = self.build_digest(week_label)
        target_file = resolver_en_vault(self.vault_path, digest["relative_path"])
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(digest["content"], encoding="utf-8")
        return target_file
