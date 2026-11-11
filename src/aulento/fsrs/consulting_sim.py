"""Simulador de llamadas de consultoría en IA y Transformación Digital (Roleplay y Discovery)."""

import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ConsultingScenario(BaseModel):
    id: str
    title: str
    industry: str
    client_background: str
    client_pain: str
    target_role: str = "COO / CFO / CTO"
    challenge_type: str = "discovery_question"  # discovery_question, roi_pitch, executive_tradeoff
    challenge_prompt: str
    recommended_phrasings: List[str]
    sample_roi_argument: str


class ConsultingSubmission(BaseModel):
    scenario_id: str
    user_response: str
    focus_mode: str = "discovery"  # discovery, roi, executive_advice


class ConsultingFeedback(BaseModel):
    scenario_id: str
    score: int
    readiness_level: str  # Principiante, Profesional Sólido, Consultor Senior
    strengths: List[str]
    improvement_areas: List[str]
    krashen_correction: str
    consulting_tip: str
    recommended_model_answer: str


CONSULTING_SCENARIOS: List[ConsultingScenario] = [
    ConsultingScenario(
        id="fintech-reconciliation",
        title="Automatización de Conciliación en Fintech",
        industry="Fintech & Banking Operations",
        client_background=(
            "Una empresa de pagos procesa 80,000 transacciones diarias. Su equipo de operaciones "
            "dedica 4 horas al día a conciliar extractos bancarios en Excel con discrepancias manuales."
        ),
        client_pain="Errores de digitación manual provocan retrasos de 72 horas en cierres contables y multas regulatorias.",
        target_role="CFO (Chief Financial Officer)",
        challenge_type="discovery_question",
        challenge_prompt=(
            "Formula en inglés una pregunta de descubrimiento (Discovery Question) para indagar el costo "
            "económico del problema y el impacto de los errores en el negocio."
        ),
        recommended_phrasings=[
            "What are the downstream financial consequences when a reconciliation error occurs?",
            "How many manual hours does your finance team spend resolving discrepancies each week?",
            "What is the average cost of regulatory fines associated with delayed settlement cycles?",
        ],
        sample_roi_argument=(
            "By deploying an automated reconciliation pipeline with anomaly detection, we reduce cycle time "
            "from 72 hours to 20 minutes, yielding full ROI within 90 days."
        ),
    ),
    ConsultingScenario(
        id="ecommerce-catalog-enrichment",
        title="Enriquecimiento de Catálogo con Agentes de IA",
        industry="Retail & Ecommerce B2B",
        client_background=(
            "Un distribuidor B2B recibe catálogos de 200 proveedores en PDFs desestructurados y tablas dispares. "
            "Tardan 3 semanas en dar de alta nuevos productos en su tienda digital."
        ),
        client_pain="Pérdida de ventas ante competidores más ágiles y catálogo desactualizado con atributos faltantes.",
        target_role="COO (Chief Operating Officer)",
        challenge_type="roi_pitch",
        challenge_prompt=(
            "Presenta en inglés un argumento de valor (Value Proposition) y ROI que justifique implementar "
            "un pipeline de agentes de IA para extracción y enriquecimiento de productos."
        ),
        recommended_phrasings=[
            "By automating catalog ingestion with AI agents, we can reduce time-to-market from 3 weeks to 2 hours.",
            "Our objective is not to replace your catalog team, but to augment their operational bandwidth by 10x.",
            "This initiative pays for itself through accelerated time-to-revenue and reduced product return rates.",
        ],
        sample_roi_argument=(
            "Accelerating time-to-shelf from 21 days to under 2 hours increases new SKU conversion by 28% "
            "while eliminating $12,000 in monthly manual contractor costs."
        ),
    ),
    ConsultingScenario(
        id="enterprise-rag-knowledge",
        title="Asistente de Conocimiento Corporativo (Enterprise RAG)",
        industry="Legal & Industrial Engineering",
        client_background=(
            "Una firma de ingeniería tiene 15 años de manuales técnicos, normativas ISO y reportes de obra "
            "dispersos en Google Drive, SharePoint y carpetas compartidas sin buscador centralizado."
        ),
        client_pain="Ingenieros senior pierden hasta 6 horas semanales buscando especificaciones técnicas y reutilizando planos obsoletos.",
        target_role="CTO / VP of Engineering",
        challenge_type="executive_tradeoff",
        challenge_prompt=(
            "Explica en inglés al CTO el trade-off estratégico entre comprar un SaaS cerrado o construir "
            "un pipeline RAG personalizado con soberanía de datos sobre infraestructura cloud propia."
        ),
        recommended_phrasings=[
            "The key trade-off lies between off-the-shelf simplicity and strict enterprise data sovereignty.",
            "We propose a two-week Proof of Concept (PoC) to de-risk the investment before full commitment.",
            "From a strategic standpoint, a modular RAG pipeline ensures you are not locked into a single proprietary LLM provider.",
        ],
        sample_roi_argument=(
            "Reclaiming 5 hours weekly per senior engineer translates into $180,000 in recovered engineering billing capacity per year."
        ),
    ),
    ConsultingScenario(
        id="customer-support-agentic",
        title="Agentes de Soporte y Triaje Automatizado",
        industry="SaaS & Customer Operations",
        client_background=(
            "Plataforma B2B con 5,000 tickets mensuales de soporte. El 60% son consultas repetitivas de Nivel 1 "
            "(restablecimiento de accesos, facturación, estado de pedidos)."
        ),
        client_pain="Tiempo medio de primera respuesta (FRT) supera las 18 horas; el equipo de soporte sufre alta rotación por agotamiento.",
        target_role="VP of Customer Success",
        challenge_type="discovery_question",
        challenge_prompt=(
            "Formula en inglés dos preguntas clave para medir la satisfacción actual de los clientes y "
            "la disposición del equipo para adoptar flujos asistidos por IA."
        ),
        recommended_phrasings=[
            "What percentage of Tier-1 support volume is purely repetitive and rule-based?",
            "How does your current 18-hour first response time impact customer churn during contract renewals?",
            "What are your team's main concerns regarding change management and AI adoption?",
        ],
        sample_roi_argument=(
            "Deflecting 60% of Tier-1 inquiries with authenticated AI agents cuts first response time to 30 seconds and frees senior agents for high-value client retention."
        ),
    ),
]


class ConsultingSimulator:
    """Motor de evaluación de simulaciones de consultoría técnica y de negocio."""

    def __init__(self, scenarios: Optional[List[ConsultingScenario]] = None):
        self.scenarios = scenarios or CONSULTING_SCENARIOS

    def list_scenarios(self) -> List[ConsultingScenario]:
        return self.scenarios

    def get_scenario(self, scenario_id: str) -> Optional[ConsultingScenario]:
        for s in self.scenarios:
            if s.id == scenario_id:
                return s
        return None

    def evaluate(self, sub: ConsultingSubmission) -> ConsultingFeedback:
        scen = self.get_scenario(sub.scenario_id)
        if not scen:
            raise ValueError(f"Escenario '{sub.scenario_id}' no encontrado.")

        text = sub.user_response.strip()
        word_count = len(text.split())

        # Keywords clave de consultoría
        consulting_keywords = [
            "bottleneck", "downstream", "consequence", "hours", "cost", "roi",
            "automate", "reduce", "turnaround", "bandwidth", "augment", "risk",
            "proof of concept", "poc", "strategic", "trade-off", "tradeoff",
            "phased", "deployment", "sovereignty", "governance", "adoption",
            "churn", "impact", "metric", "kpi", "lead time", "time-to-market"
        ]

        text_lower = text.lower()
        matched_keywords = [kw for kw in consulting_keywords if kw in text_lower]

        strengths: List[str] = []
        improvement_areas: List[str] = []

        # Análisis de longitud y elaboración
        if word_count < 8:
            score = 45
            improvement_areas.append("Respuesta demasiado escueta para una reunión con directivos (C-Level).")
        elif word_count < 16:
            score = 65
            strengths.append("Directo y al grano.")
            improvement_areas.append("Puedes elaborar un poco más para contextualizar el valor de negocio.")
        else:
            score = 80
            strengths.append("Longitud profesional adecuada con contexto y claridad.")

        # Bonificación por vocabulario de consultoría
        if matched_keywords:
            bonus = min(len(matched_keywords) * 5, 20)
            score = min(score + bonus, 100)
            strengths.append(f"Uso acertado de vocabulario de consultoría: {', '.join(matched_keywords[:4])}.")
        else:
            improvement_areas.append("Incorpora términos de impacto como 'bottleneck', 'turnaround time', 'ROI' o 'downstream consequences'.")

        # Nivel de solvencia
        if score >= 85:
            readiness = "Consultor Senior (C-Level Ready)"
        elif score >= 65:
            readiness = "Profesional Sólido (Good Business English)"
        else:
            readiness = "Nivel Inicial (En Desarrollo)"

        # Generación de corrección Krashen (i+1)
        # Tomamos la idea del usuario y le damos el tono 'consulting polish'
        clean_user = re.sub(r"[?!.]", "", text)
        if "?" in text or sub.focus_mode == "discovery":
            krashen_correction = (
                f"Para sonar como consultor senior ante directivos: "
                f"«To better quantify the business impact, {clean_user.lower().strip()}?»"
            )
        else:
            krashen_correction = (
                f"Formulación de alto impacto: "
                f"«From a strategic and economic standpoint, {clean_user.lower().strip()}.»"
            )

        tip = (
            "En llamadas de Discovery, nunca comiences hablando de la tecnología o algoritmos. "
            "Comienza siempre cuantificando el dolor del cliente: horas hombre perdidas, costos de error y retrasos."
        )

        return ConsultingFeedback(
            scenario_id=scen.id,
            score=score,
            readiness_level=readiness,
            strengths=strengths,
            improvement_areas=improvement_areas,
            krashen_correction=krashen_correction,
            consulting_tip=tip,
            recommended_model_answer=scen.recommended_phrasings[0],
        )
