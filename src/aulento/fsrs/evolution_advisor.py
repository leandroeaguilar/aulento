"""Módulo de evaluación evolutiva y recomendación adaptativa de nivel de inglés técnico con la IA de la cuenta."""

import logging
import sqlite3
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from aulento.core.ia.lectura import leer_json, respuesta_inutil
from aulento.core.ia.pasarela import PasarelaDeIA
from aulento.core.ia.tipos import IANoDisponibleError, Pedido, motivo_sin_ia
from aulento.db.cuenta import exigir_cuenta
from aulento.fsrs.progressive_deck import LEVEL_METADATA

logger = logging.getLogger(__name__)

LEVEL_KEYS = [
    "a1_foundations",
    "a2_daily_work",
    "b1_data_storytelling",
    "b2_tech_data_ai",
    "c1_consulting_ai",
]


class LevelMasteryStats(BaseModel):
    level_code: str
    level_key: str
    level_name: str
    total_cards: int
    reviewed_cards: int
    mastered_cards: int
    retention_rate: float
    avg_difficulty: float
    mastery_pct: float
    status: str  # 'not_started', 'in_progress', 'consolidating', 'mastered'


class EvolutionDiagnosis(BaseModel):
    cefr_rating: str = Field(..., description="Nivel estimado actual (ej: A1, A2, B1, B2, C1)")
    recommended_level: str = Field(..., description="Código de nivel recomendado (ej: b1_data_storytelling)")
    recommended_level_name: str = Field(..., description="Nombre amigable del nivel recomendado")
    mastery_score: int = Field(..., ge=0, le=100, description="Índice global de dominio 0..100")
    diagnostic_summary: str = Field(..., description="Explicación pedagógica de la evolución del estudiante")
    strengths: List[str] = Field(default_factory=list, description="Puntos fuertes consolidados")
    focus_areas: List[str] = Field(default_factory=list, description="Áreas que requieren mayor atención")
    next_milestone: str = Field(..., description="Meta concreta inmediata para consolidar el siguiente nivel")
    level_breakdown: List[LevelMasteryStats] = Field(default_factory=list)
    model_used: str = Field("local-heuristic", description="Modelo evaluador, o local-heuristic si se obtuvo sin IA")
    provider_used: Optional[str] = Field(None, description="Proveedor de IA que respondió (gemini, anthropic u openai); vacío sin IA")
    motivo_sin_ia: Optional[str] = Field(None, description="Por qué no hubo IA, cuando la causa no es que falte cargar la clave")


def get_student_evolution_metrics(conn: sqlite3.Connection, user_id: int) -> Dict[str, Any]:
    """Calcula las métricas cuantitativas de dominio por nivel progresivo de una cuenta."""
    exigir_cuenta(user_id)
    cursor = conn.cursor()
    breakdown: List[Dict[str, Any]] = []

    total_all_cards = 0
    total_all_reviewed = 0
    total_all_mastered = 0
    weighted_mastery_sum = 0.0

    for key in LEVEL_KEYS:
        meta = LEVEL_METADATA.get(key, {})
        code = meta.get("code", key)
        name = meta.get("name", key)

        # 1. Total de tarjetas en la categoría
        cursor.execute(
            "SELECT count(*) as total FROM fsrs_items WHERE user_id = ? AND (categoria = ? OR categoria LIKE ?);",
            (user_id, key, f"{code}%"),
        )
        total = cursor.fetchone()["total"]

        # 2. Tarjetas con al menos 1 repaso
        cursor.execute(
            """
            SELECT count(*) as rev, avg(difficulty) as avg_diff, avg(stability) as avg_stab
            FROM fsrs_items
            WHERE user_id = ? AND (categoria = ? OR categoria LIKE ?) AND reps > 0;
            """,
            (user_id, key, f"{code}%"),
        )
        rev_row = cursor.fetchone()
        reviewed = rev_row["rev"] or 0
        avg_diff = round(rev_row["avg_diff"] or 5.0, 1)

        # 3. Tarjetas dominadas (Review state y estabilidad >= 2.5 días)
        cursor.execute(
            """
            SELECT count(*) as mast
            FROM fsrs_items
            WHERE user_id = ? AND (categoria = ? OR categoria LIKE ?) AND state = 2 AND stability >= 2.5;
            """,
            (user_id, key, f"{code}%"),
        )
        mastered = cursor.fetchone()["mast"] or 0

        # 4. Tasa de retención histórica en este nivel
        cursor.execute(
            """
            SELECT count(*) as total_logs, sum(CASE WHEN l.rating IN (3, 4) THEN 1 ELSE 0 END) as remembered
            FROM fsrs_review_logs l
            JOIN fsrs_items i ON l.card_id = i.id
            WHERE i.user_id = ? AND (i.categoria = ? OR i.categoria LIKE ?);
            """,
            (user_id, key, f"{code}%"),
        )
        log_row = cursor.fetchone()
        total_logs = log_row["total_logs"] or 0
        remembered = log_row["remembered"] or 0
        retention = round((remembered / total_logs * 100.0), 1) if total_logs > 0 else 0.0

        # 5. Cálculo de porcentaje de dominio (Mastery Index 0..100)
        if total == 0 or reviewed == 0:
            mastery_pct = 0.0
            status = "not_started"
        else:
            coverage = min(1.0, reviewed / total)
            ret_factor = (retention / 100.0) if total_logs > 0 else 0.5
            val = (coverage * 0.45 + ret_factor * 0.55) * 100.0
            mastery_pct = round(min(100.0, val), 1)

            if mastery_pct >= 75.0:
                status = "mastered"
            elif mastery_pct >= 45.0:
                status = "consolidating"
            else:
                status = "in_progress"

        breakdown.append(
            {
                "level_code": code,
                "level_key": key,
                "level_name": name,
                "total_cards": total,
                "reviewed_cards": reviewed,
                "mastered_cards": mastered,
                "retention_rate": retention,
                "avg_difficulty": avg_diff,
                "mastery_pct": mastery_pct,
                "status": status,
            }
        )

        total_all_cards += total
        total_all_reviewed += reviewed
        total_all_mastered += mastered
        weighted_mastery_sum += mastery_pct

    # Nivel recomendado según el principio de Zona de Desarrollo Próximo
    recommended_key = "a1_foundations"
    cefr = "A1"

    for b in breakdown:
        if b["mastery_pct"] < 70.0:
            recommended_key = b["level_key"]
            cefr = b["level_code"].upper()
            break
    else:
        # Todos dominados al 70%+
        recommended_key = "c1_consulting_ai"
        cefr = "C1"

    global_mastery = int(round(weighted_mastery_sum / max(1, len(breakdown))))

    return {
        "global_mastery": global_mastery,
        "cefr_rating": cefr,
        "recommended_level": recommended_key,
        "recommended_level_name": LEVEL_METADATA.get(recommended_key, {}).get("name", recommended_key),
        "total_cards": total_all_cards,
        "total_reviewed": total_all_reviewed,
        "total_mastered": total_all_mastered,
        "breakdown": breakdown,
    }


def diagnose_evolution(conn: sqlite3.Connection, user_id: int) -> EvolutionDiagnosis:
    """Genera el diagnóstico evolutivo pedagógico de una cuenta con su IA o, sin IA utilizable, el heurístico local."""
    metrics = get_student_evolution_metrics(conn, user_id)

    breakdown_objs = [LevelMasteryStats(**b) for b in metrics["breakdown"]]
    recommended_key = metrics["recommended_level"]
    recommended_name = metrics["recommended_level_name"]
    cefr = metrics["cefr_rating"]
    score = metrics["global_mastery"]

    system_instruction = (
        "Eres un Coach y Asesor Pedagógico de Inglés Técnico Profesional en Cloud, Data e Inteligencia Artificial. "
        "Tu tarea es evaluar la evolución del estudiante basándote en sus estadísticas de memoria FSRS v5. "
        "Responde ÚNICAMENTE en formato JSON con la siguiente estructura exacta:\n"
        "{\n"
        '  "diagnostic_summary": "Párrafo breve y motivador analizando la evolución del estudiante",\n'
        '  "strengths": ["punto fuerte 1", "punto fuerte 2"],\n'
        '  "focus_areas": ["área a reforzar 1", "área a reforzar 2"],\n'
        '  "next_milestone": "Meta concreta a alcanzar en la próxima semana",\n'
        '  "recommended_level": "código_del_nivel_recomendado"\n'
        "}"
    )
    user_content = (
        f"Métricas cuantitativas de estudio del alumno:\n"
        f"- Nivel CEFR estimado: {cefr}\n"
        f"- Índice global de dominio: {score}%\n"
        f"- Tarjetas repasadas: {metrics['total_reviewed']} de {metrics['total_cards']}\n"
        f"- Desglose por nivel:\n"
        + "\n".join(
            f"  * {b.level_name} ({b.level_code.upper()}): Dominio={b.mastery_pct}%, Retención={b.retention_rate}%, Repasadas={b.reviewed_cards}/{b.total_cards}, Estado={b.status}"
            for b in breakdown_objs
        )
        + f"\nNivel heurístico sugerido: {recommended_key}"
    )

    motivo: Optional[str] = None
    try:
        respuesta = PasarelaDeIA(conn, user_id).generar(
            Pedido(sistema=system_instruction, usuario=user_content, json=True, temperatura=0.2), "evolution_diagnosis"
        )
    except IANoDisponibleError as error:
        motivo = motivo_sin_ia(error)
    else:
        try:
            parsed = leer_json(respuesta.texto)
            rec_key = parsed.get("recommended_level", recommended_key)
            if rec_key not in LEVEL_KEYS:
                rec_key = recommended_key
            rec_name = LEVEL_METADATA.get(rec_key, {}).get("name", recommended_name)

            return EvolutionDiagnosis(
                cefr_rating=cefr,
                recommended_level=rec_key,
                recommended_level_name=rec_name,
                mastery_score=score,
                diagnostic_summary=parsed.get(
                    "diagnostic_summary",
                    f"Evolución sólida en {cefr}. El algoritmo recomienda consolidar {rec_name}.",
                ),
                strengths=parsed.get("strengths", ["Constancia de repaso en tarjetas activas"]),
                focus_areas=parsed.get("focus_areas", [f"Consolidar vocabulario de {rec_name}"]),
                next_milestone=parsed.get(
                    "next_milestone",
                    f"Alcanzar 80% de retención en {rec_name} mediante Active Recall.",
                ),
                level_breakdown=breakdown_objs,
                model_used=respuesta.modelo,
                provider_used=respuesta.proveedor,
            )
        except Exception as e:
            logger.warning("No se pudo leer el diagnóstico que devolvió la IA: %s", e)
            motivo = str(respuesta_inutil(respuesta, "devolvió un diagnóstico que no se pudo leer"))

    # Fallback heurístico local (sin clave o ante fallo de red)
    if score == 0:
        summary = (
            "Aún no has iniciado repasos formales. Te recomendamos comenzar con el Nivel 1 (A1 Bases) "
            "o Nivel 2 (A2 Standups) para activar tu memoria a largo plazo con colocaciones esenciales de trabajo."
        )
        strengths = ["Mazo de 100+ tarjetas técnicas listas para estudiar"]
        focus_areas = ["Comenzar la primera sesión de repaso diario", "Practicar shadowing de audio en voz alta"]
        milestone = "Completar tus primeras 10 tarjetas en Nivel A1/A2 con calificación Good o Easy."
    else:
        summary = (
            f"Tu índice de dominio general es del {score}%. El sistema FSRS ha detectado que tu zona de mayor "
            f"impacto formativo se encuentra en '{recommended_name}'. Mantener sesiones diarias de 10 a 15 tarjetas "
            f"afianzará los patrones sintácticos de nivel {cefr}."
        )
        strengths = [
            f"Progreso registrado en {metrics['total_reviewed']} conceptos técnicos",
            f"{metrics['total_mastered']} tarjetas con estabilidad de memoria prolongada",
        ]
        focus_areas = [
            f"Reforzar tarjetas en estado de consolidación en {recommended_name}",
            "Incrementar la práctica oral con el tutor de voz para afianzar entonación profesional",
        ]
        milestone = f"Superar el 75% de dominio en {recommended_name} en las próximas dos semanas."

    return EvolutionDiagnosis(
        cefr_rating=cefr,
        recommended_level=recommended_key,
        recommended_level_name=recommended_name,
        mastery_score=score,
        diagnostic_summary=summary,
        strengths=strengths,
        focus_areas=focus_areas,
        next_milestone=milestone,
        level_breakdown=breakdown_objs,
        model_used="local-heuristic",
        motivo_sin_ia=motivo,
    )
