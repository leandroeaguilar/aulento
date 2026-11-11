"""Mazo progresivo graduado de inglés técnico y consultoría en 5 niveles (A1 a C1)."""

from typing import Any, Dict, List, Optional

# Metadatos descriptivos de cada nivel
LEVEL_METADATA: Dict[str, Dict[str, Any]] = {
    "a1_foundations": {
        "code": "a1",
        "name": "Nivel 1: Bases Fundacionales de Trabajo (A1)",
        "badge": "A1 Survival",
        "color": "emerald",
        "description": "Preguntas de cortesía, verbos auxiliares, números, plazos y operaciones informáticas básicas.",
        "target_audience": "Personas arrancando desde inglés básico o con miedo a hablar.",
    },
    "a2_daily_work": {
        "code": "a2",
        "name": "Nivel 2: Trabajo Diario & Daily Standups (A2)",
        "badge": "A2 Standup",
        "color": "sky",
        "description": "Actualizaciones de equipo, qué hiciste ayer/harás hoy, bloqueos y pedidos de clarificación.",
        "target_audience": "Desarrolladores y analistas participando en reuniones ágiles/Scrum.",
    },
    "b1_data_storytelling": {
        "code": "b1",
        "name": "Nivel 3: Storytelling con Datos & Negocios (B1)",
        "badge": "B1 Business",
        "color": "amber",
        "description": "Presentar dashboards, describir variaciones y tendencias, explicar causa-raíz y recomendar acciones.",
        "target_audience": "Analistas de BI y Product Managers presentando ante gerentes.",
    },
    "b2_tech_data_ai": {
        "code": "b2",
        "name": "Nivel 4: Inglés Técnico en Datos & IA (B2)",
        "badge": "B2 Tech & AI",
        "color": "indigo",
        "description": "Arquitectura de datos, pipelines ETL, optimización cloud, RAG, embeddings y modelos de IA.",
        "target_audience": "Data Engineers, ML Engineers y Arquitectos Cloud.",
    },
    "c1_consulting_ai": {
        "code": "c1",
        "name": "Nivel 5: Consultoría de Negocios, Transformación Digital & IA (C1)",
        "badge": "C1 Consulting",
        "color": "purple",
        "description": "Discovery calls, cálculo de ROI, comunicación con C-Levels, gestión de riesgos y adopción del cambio.",
        "target_audience": "Consultores de IA, líderes de transformación digital y directores de proyectos.",
    },
}

# --- NIVEL 1: BASES FUNDACIONALES PARA EL TRABAJO (A1) ---
A1_FOUNDATIONS_ITEMS: List[Dict[str, str]] = [
    {
        "categoria": "a1_foundations",
        "item_pregunta": "¿Cómo pedir de forma cortés: '¿Podrías por favor compartir tu pantalla?'?",
        "respuesta_esperada": "Could you please share your screen?",
        "contexto_uso": "Could you please share your screen so we can review the table together?",
    },
    {
        "categoria": "a1_foundations",
        "item_pregunta": "¿Cómo preguntar: '¿Dónde está guardado el archivo de datos?'?",
        "respuesta_esperada": "Where is the data file stored?",
        "contexto_uso": "Where is the data file stored so I can download it?",
    },
    {
        "categoria": "a1_foundations",
        "item_pregunta": "¿Cómo solicitar: '¿Puedo tener acceso a esta carpeta?'?",
        "respuesta_esperada": "Can I have access to this folder?",
        "contexto_uso": "Can I have access to this folder to check the project files?",
    },
    {
        "categoria": "a1_foundations",
        "item_pregunta": "¿Cómo decir: 'La fecha límite es el próximo viernes a las 5 PM'?",
        "respuesta_esperada": "The deadline is next Friday at 5 PM.",
        "contexto_uso": "Remember that the deadline is next Friday at 5 PM.",
    },
    {
        "categoria": "a1_foundations",
        "item_pregunta": "¿Cómo agradecer en un correo: 'Gracias por adelantado por tu ayuda'?",
        "respuesta_esperada": "Thanks in advance for your help.",
        "contexto_uso": "Please let me know if this works. Thanks in advance for your help.",
    },
    {
        "categoria": "a1_foundations",
        "item_pregunta": "¿Cómo decir: 'Avísame si necesitas algo más'?",
        "respuesta_esperada": "Let me know if you need anything else.",
        "contexto_uso": "Here are the query results. Let me know if you need anything else.",
    },
    {
        "categoria": "a1_foundations",
        "item_pregunta": "¿Cómo decir: 'He subido los nuevos archivos al servidor'?",
        "respuesta_esperada": "I uploaded the new files to the server.",
        "contexto_uso": "I uploaded the new files to the server this morning.",
    },
    {
        "categoria": "a1_foundations",
        "item_pregunta": "¿Cómo decir: 'Por favor actualiza tu navegador o la página'?",
        "respuesta_esperada": "Please refresh your browser or page.",
        "contexto_uso": "If you don't see the changes, please refresh your browser or page.",
    },
    {
        "categoria": "a1_foundations",
        "item_pregunta": "¿Cómo decir: 'El enlace no está funcionando'?",
        "respuesta_esperada": "The link is not working.",
        "contexto_uso": "I tried to open the document, but the link is not working.",
    },
    {
        "categoria": "a1_foundations",
        "item_pregunta": "¿Cómo decir: '¿Cuál es el objetivo principal de este proyecto?'?",
        "respuesta_esperada": "What is the main goal of this project?",
        "contexto_uso": "Before we begin, what is the main goal of this project?",
    },
    {
        "categoria": "a1_foundations",
        "item_pregunta": "¿Cómo decir: 'Hemos completado el 80 por ciento de las tareas'?",
        "respuesta_esperada": "We have completed 80 percent of the tasks.",
        "contexto_uso": "Good progress today: we have completed 80 percent of the tasks.",
    },
    {
        "categoria": "a1_foundations",
        "item_pregunta": "¿Cómo preguntar: '¿A qué hora es nuestra próxima llamada?'?",
        "respuesta_esperada": "What time is our next call?",
        "contexto_uso": "What time is our next call tomorrow?",
    },
    {
        "categoria": "a1_foundations",
        "item_pregunta": "¿Cómo decir: 'Estoy listo para empezar'?",
        "respuesta_esperada": "I am ready to start.",
        "contexto_uso": "I reviewed the requirements and I am ready to start.",
    },
    {
        "categoria": "a1_foundations",
        "item_pregunta": "¿Cómo despedir un correo formal: 'Saludos cordiales'?",
        "respuesta_esperada": "Best regards / Kind regards",
        "contexto_uso": "Best regards, Alex.",
    },
    {
        "categoria": "a1_foundations",
        "item_pregunta": "¿Cómo decir: 'Por favor revisa el archivo adjunto'?",
        "respuesta_esperada": "Please check the attached file.",
        "contexto_uso": "Please check the attached file for the updated schema.",
    },
]

# --- NIVEL 2: TRABAJO DIARIO Y STANDUPS (A2) ---
A2_DAILY_WORK_ITEMS: List[Dict[str, str]] = [
    {
        "categoria": "a2_daily_work",
        "item_pregunta": "¿Cómo decir en standup: 'Ayer trabajé en la limpieza de datos'?",
        "respuesta_esperada": "Yesterday I worked on data cleaning.",
        "contexto_uso": "Yesterday I worked on data cleaning for the customer table.",
    },
    {
        "categoria": "a2_daily_work",
        "item_pregunta": "¿Cómo decir en standup: 'Hoy voy a construir el nuevo reporte'?",
        "respuesta_esperada": "Today I am going to build the new report.",
        "contexto_uso": "Today I am going to build the new report in Power BI.",
    },
    {
        "categoria": "a2_daily_work",
        "item_pregunta": "¿Cómo reportar un bloqueo: 'Actualmente estoy bloqueado por falta de credenciales'?",
        "respuesta_esperada": "I am currently blocked by missing credentials.",
        "contexto_uso": "I am currently blocked by missing credentials for the BigQuery service account.",
    },
    {
        "categoria": "a2_daily_work",
        "item_pregunta": "¿Cómo decir: 'Necesito aprobación del líder técnico para continuar'?",
        "respuesta_esperada": "I need approval from the tech lead to proceed.",
        "contexto_uso": "The PR is ready, but I need approval from the tech lead to proceed.",
    },
    {
        "categoria": "a2_daily_work",
        "item_pregunta": "¿Cómo pedir clarificación: '¿Podrías repetir eso más despacio, por favor?'?",
        "respuesta_esperada": "Could you repeat that more slowly, please?",
        "contexto_uso": "Could you repeat that more slowly, please? The audio cut out.",
    },
    {
        "categoria": "a2_daily_work",
        "item_pregunta": "¿Cómo decir: 'Permíteme asegurarme de que entendí bien'?",
        "respuesta_esperada": "Let me make sure I understood correctly.",
        "contexto_uso": "Let me make sure I understood correctly: we need the report by Thursday?",
    },
    {
        "categoria": "a2_daily_work",
        "item_pregunta": "¿Cómo decir: 'Te responderé antes de que termine el día'?",
        "respuesta_esperada": "I'll get back to you by end of day.",
        "contexto_uso": "I'm checking the logs now, and I'll get back to you by end of day.",
    },
    {
        "categoria": "a2_daily_work",
        "item_pregunta": "¿Cómo proponer: 'Sincronicemos en una breve llamada después de esta reunión'?",
        "respuesta_esperada": "Let's sync up after this meeting.",
        "contexto_uso": "Let's sync up after this meeting for 5 minutes to align on priorities.",
    },
    {
        "categoria": "a2_daily_work",
        "item_pregunta": "¿Cómo decir: 'Creé un Pull Request para revisión'?",
        "respuesta_esperada": "I created a pull request for review.",
        "contexto_uso": "I created a pull request for review; please take a look when you have time.",
    },
    {
        "categoria": "a2_daily_work",
        "item_pregunta": "¿Cómo decir: 'Todo va según lo previsto para la entrega'?",
        "respuesta_esperada": "Everything is on track for the release.",
        "contexto_uso": "No blockers on my end; everything is on track for the release.",
    },
    {
        "categoria": "a2_daily_work",
        "item_pregunta": "¿Cómo decir: 'Encontré un error inesperado en el script'?",
        "respuesta_esperada": "I encountered an unexpected bug in the script.",
        "contexto_uso": "I encountered an unexpected bug in the script while parsing JSON dates.",
    },
    {
        "categoria": "a2_daily_work",
        "item_pregunta": "¿Cómo decir: 'Estoy de acuerdo con ese enfoque'?",
        "respuesta_esperada": "I agree with that approach.",
        "contexto_uso": "That makes total sense, I agree with that approach.",
    },
]

# --- NIVEL 3: DATA STORYTELLING Y NEGOCIOS (B1) ---
B1_DATA_STORYTELLING_ITEMS: List[Dict[str, str]] = [
    {
        "categoria": "b1_data_storytelling",
        "item_pregunta": "¿Cómo describir un aumento: 'Los ingresos aumentaron un 15% comparado con el trimestre anterior'?",
        "respuesta_esperada": "Revenue increased by 15% compared to the previous quarter.",
        "contexto_uso": "As shown in the chart, revenue increased by 15% compared to the previous quarter.",
    },
    {
        "categoria": "b1_data_storytelling",
        "item_pregunta": "¿Cómo describir una caída: 'Notamos una marcada caída en la retención de usuarios'?",
        "respuesta_esperada": "We noticed a sharp drop in user retention.",
        "contexto_uso": "After the latest update, we noticed a sharp drop in user retention.",
    },
    {
        "categoria": "b1_data_storytelling",
        "item_pregunta": "¿Cómo describir estabilidad: 'La tasa de conversión se mantuvo constante a lo largo del mes'?",
        "respuesta_esperada": "The conversion rate remained steady throughout the month.",
        "contexto_uso": "Despite market volatility, the conversion rate remained steady throughout the month.",
    },
    {
        "categoria": "b1_data_storytelling",
        "item_pregunta": "¿Cómo explicar causa raíz: 'La causa raíz fue un formato de fecha inconsistente entre sucursales'?",
        "respuesta_esperada": "The root cause was inconsistent date formatting across branches.",
        "contexto_uso": "Our audit revealed that the root cause was inconsistent date formatting across branches.",
    },
    {
        "categoria": "b1_data_storytelling",
        "item_pregunta": "¿Cómo hacer una recomendación: 'En base a los datos, recomiendo automatizar el proceso de reconciliación'?",
        "respuesta_esperada": "Based on the data insights, I recommend automating the reconciliation process.",
        "contexto_uso": "Based on the data insights, I recommend automating the reconciliation process to save hours.",
    },
    {
        "categoria": "b1_data_storytelling",
        "item_pregunta": "¿Cómo decir: 'Existe una fuerte correlación entre el tiempo de carga y el rebote de clientes'?",
        "respuesta_esperada": "There is a strong correlation between load time and customer churn.",
        "contexto_uso": "The analysis shows there is a strong correlation between load time and customer churn.",
    },
    {
        "categoria": "b1_data_storytelling",
        "item_pregunta": "¿Cómo decir: 'Este valor atípico distorsiona el promedio general'?",
        "respuesta_esperada": "This outlier skews the overall average.",
        "contexto_uso": "We should use the median because this single outlier skews the overall average.",
    },
    {
        "categoria": "b1_data_storytelling",
        "item_pregunta": "¿Cómo decir: 'Desglosemos las métricas por segmento de cliente'?",
        "respuesta_esperada": "Let's break down the metrics by customer segment.",
        "contexto_uso": "To uncover patterns, let's break down the metrics by customer segment.",
    },
    {
        "categoria": "b1_data_storytelling",
        "item_pregunta": "¿Cómo expresar la conclusión principal: 'La conclusión clave de este reporte es...'?",
        "respuesta_esperada": "The key takeaway from this report is...",
        "contexto_uso": "The key takeaway from this report is that mobile conversion requires immediate attention.",
    },
    {
        "categoria": "b1_data_storytelling",
        "item_pregunta": "¿Cómo decir: 'Esta anomalía requiere una investigación más profunda'?",
        "respuesta_esperada": "This anomaly requires further investigation.",
        "contexto_uso": "We detected an unexpected spike on Sunday; this anomaly requires further investigation.",
    },
]

# --- NIVEL 4: INGLÉS TÉCNICO EN DATOS E IA (B2) ---
B2_TECH_DATA_AI_ITEMS: List[Dict[str, str]] = [
    {
        "categoria": "b2_tech_data_ai",
        "item_pregunta": "¿Cómo decir: 'cuello de botella en el pipeline'?",
        "respuesta_esperada": "bottleneck in the pipeline",
        "contexto_uso": "We identified a severe bottleneck in the data ingestion pipeline.",
    },
    {
        "categoria": "b2_tech_data_ai",
        "item_pregunta": "¿Cómo decir: 'trabajo idempotente' (que puede reintentarse sin duplicar)?",
        "respuesta_esperada": "idempotent job",
        "contexto_uso": "Make sure the Spark batch transformation is an idempotent job.",
    },
    {
        "categoria": "b2_tech_data_ai",
        "item_pregunta": "¿Cómo decir: 'desviación del esquema' (cambio imprevisto en los datos entrantes)?",
        "respuesta_esperada": "schema drift",
        "contexto_uso": "Our ingestion service automatically alerts on unexpected schema drift.",
    },
    {
        "categoria": "b2_tech_data_ai",
        "item_pregunta": "¿Cómo decir: 'generación aumentada por recuperación' (RAG)?",
        "respuesta_esperada": "retrieval-augmented generation (RAG)",
        "contexto_uso": "We implemented retrieval-augmented generation (RAG) to ground the chatbot in internal manuals.",
    },
    {
        "categoria": "b2_tech_data_ai",
        "item_pregunta": "¿Cómo decir: 'mitigación de alucinaciones en modelos de lenguaje'?",
        "respuesta_esperada": "hallucination mitigation in LLMs",
        "contexto_uso": "Strict system prompts and vector search are key for hallucination mitigation in LLMs.",
    },
    {
        "categoria": "b2_tech_data_ai",
        "item_pregunta": "¿Cómo decir: 'fuente única de la verdad'?",
        "respuesta_esperada": "single source of truth",
        "contexto_uso": "The centralized data warehouse serves as the single source of truth.",
    },
    {
        "categoria": "b2_tech_data_ai",
        "item_pregunta": "¿Cómo decir: 'rellenado retroactivo de datos históricos'?",
        "respuesta_esperada": "backfilling historical data",
        "contexto_uso": "We will trigger an Airflow DAG for backfilling historical data from 2025.",
    },
    {
        "categoria": "b2_tech_data_ai",
        "item_pregunta": "¿Cómo decir: 'rendimiento de lectura y escritura'?",
        "respuesta_esperada": "read/write throughput",
        "contexto_uso": "We increased the read/write throughput by tuning table partitions in BigQuery.",
    },
    {
        "categoria": "b2_tech_data_ai",
        "item_pregunta": "¿Cómo decir: 'ventana de contexto del modelo'?",
        "respuesta_esperada": "model context window",
        "contexto_uso": "Gemini 2.0 has an extended context window that easily accommodates entire codebases.",
    },
    {
        "categoria": "b2_tech_data_ai",
        "item_pregunta": "¿Cómo decir: 'flujo de trabajo agéntico con herramientas'?",
        "respuesta_esperada": "agentic workflow with tool calling",
        "contexto_uso": "The agentic workflow with tool calling allows the LLM to query the database directly.",
    },
]

# --- NIVEL 5: CONSULTORÍA DE NEGOCIOS, TRANSFORMACIÓN DIGITAL E IA (C1) ---
C1_CONSULTING_AI_ITEMS: List[Dict[str, str]] = [
    {
        "categoria": "c1_consulting_ai",
        "item_pregunta": "¿Cómo preguntar en llamada de discovery: '¿Cuál es el cuello de botella más grande en sus operaciones actuales?'?",
        "respuesta_esperada": "What is the single biggest bottleneck in your current business operations?",
        "contexto_uso": "In our initial discovery call, I always ask: what is the single biggest bottleneck in your current business operations?",
    },
    {
        "categoria": "c1_consulting_ai",
        "item_pregunta": "¿Cómo indagar el impacto del dolor: '¿Cuántas horas manuales pierde su equipo cada semana en este proceso?'?",
        "respuesta_esperada": "How many manual hours does your team spend on this process each week?",
        "contexto_uso": "To size the opportunity, how many manual hours does your team spend on this process each week?",
    },
    {
        "categoria": "c1_consulting_ai",
        "item_pregunta": "¿Cómo preguntar por consecuencias: '¿Qué impacto aguas abajo sufre el negocio cuando ocurre un error en estos datos?'?",
        "respuesta_esperada": "What are the downstream consequences when an error occurs in this data?",
        "contexto_uso": "Beyond the immediate fix, what are the downstream consequences when an error occurs in this data?",
    },
    {
        "categoria": "c1_consulting_ai",
        "item_pregunta": "¿Cómo justificar el valor: 'Al automatizar este pipeline con agentes de IA, reduciremos el tiempo de respuesta de 3 días a 15 minutos'?",
        "respuesta_esperada": "By automating this pipeline with AI agents, we will reduce turnaround time from 3 days to 15 minutes.",
        "contexto_uso": "The business case is clear: by automating this pipeline with AI agents, we will reduce turnaround time from 3 days to 15 minutes.",
    },
    {
        "categoria": "c1_consulting_ai",
        "item_pregunta": "¿Cómo presentar el retorno económico: 'El retorno de inversión proyectado se alcanza en los primeros 4 meses'?",
        "respuesta_esperada": "The projected return on investment (ROI) is achieved within the first 4 months.",
        "contexto_uso": "Through labor savings and error reduction, the projected return on investment is achieved within the first 4 months.",
    },
    {
        "categoria": "c1_consulting_ai",
        "item_pregunta": "¿Cómo calmar el miedo del cliente: 'El objetivo no es reemplazar personas, sino potenciar la capacidad operativa del equipo'?",
        "respuesta_esperada": "The objective is not to replace people, but to augment your team's operational bandwidth.",
        "contexto_uso": "We emphasize to stakeholders: the objective is not to replace people, but to augment your team's operational bandwidth.",
    },
    {
        "categoria": "c1_consulting_ai",
        "item_pregunta": "¿Cómo aconsejar a directivos (C-Level): 'Desde una perspectiva estratégica, recomendamos un despliegue por fases en lugar de un lanzamiento abrupto'?",
        "respuesta_esperada": "From a strategic standpoint, we recommend a phased rollout rather than a big-bang deployment.",
        "contexto_uso": "To mitigate operational risk, from a strategic standpoint, we recommend a phased rollout rather than a big-bang deployment.",
    },
    {
        "categoria": "c1_consulting_ai",
        "item_pregunta": "¿Cómo proponer una prueba de concepto: 'Proponemos una Prueba de Concepto de dos semanas para des-riesgar la inversión'?",
        "respuesta_esperada": "We propose a two-week Proof of Concept (PoC) to de-risk the investment.",
        "contexto_uso": "Before signing a multi-month contract, we propose a two-week Proof of Concept to de-risk the investment.",
    },
    {
        "categoria": "c1_consulting_ai",
        "item_pregunta": "¿Cómo explicar un dilema arquitectónico: 'El trade-off clave radica en gobernanza de datos y costo total de propiedad'?",
        "respuesta_esperada": "The key trade-off lies in data governance and total cost of ownership (TCO).",
        "contexto_uso": "When evaluating build vs buy, the key trade-off lies in data governance and total cost of ownership.",
    },
    {
        "categoria": "c1_consulting_ai",
        "item_pregunta": "¿Cómo hablar de adopción y gestión del cambio: 'El éxito de este proyecto dependerá de la gestión del cambio y la capacitación'?",
        "respuesta_esperada": "The success of this initiative will depend on change management and user onboarding.",
        "contexto_uso": "Technology is only half the battle; the success of this initiative will depend on change management and user onboarding.",
    },
    {
        "categoria": "c1_consulting_ai",
        "item_pregunta": "¿Cómo definir el alcance del proyecto: 'Detallaremos los entregables y criterios de aceptación en el Statement of Work (SOW)'?",
        "respuesta_esperada": "We will detail the deliverables and acceptance criteria in the Statement of Work (SOW).",
        "contexto_uso": "To ensure mutual alignment, we will detail the deliverables and acceptance criteria in the Statement of Work.",
    },
    {
        "categoria": "c1_consulting_ai",
        "item_pregunta": "¿Cómo evaluar la madurez: 'Primero realizaremos una evaluación de madurez de datos para validar la viabilidad'?",
        "respuesta_esperada": "We will first conduct a data maturity assessment to validate feasibility.",
        "contexto_uso": "Before designing the AI agent architecture, we will first conduct a data maturity assessment to validate feasibility.",
    },
]


def get_all_progressive_items() -> List[Dict[str, str]]:
    """Devuelve la lista unificada de todas las tarjetas graduadas en los 5 niveles."""
    return (
        A1_FOUNDATIONS_ITEMS
        + A2_DAILY_WORK_ITEMS
        + B1_DATA_STORYTELLING_ITEMS
        + B2_TECH_DATA_AI_ITEMS
        + C1_CONSULTING_AI_ITEMS
    )


def filter_items_by_level(arg1: Any, arg2: Optional[str] = None) -> List[Dict[str, Any]]:
    """Filtra tarjetas por código de nivel.
    
    Acepta tanto filter_items_by_level('a1') como filter_items_by_level(items, 'a1').
    """
    if arg2 is None and isinstance(arg1, str):
        level = arg1
        items = get_all_progressive_items()
    elif isinstance(arg2, str):
        items = arg1
        level = arg2
    else:
        level = str(arg1)
        items = get_all_progressive_items()

    lvl = level.lower().strip()
    if lvl in ("all", "todos", "*"):
        return items

    prefix_map = {
        "a1": "a1",
        "a1_foundations": "a1",
        "a2": "a2",
        "a2_daily_work": "a2",
        "b1": "b1",
        "b1_data_storytelling": "b1",
        "b2": "b2",
        "b2_tech_data_ai": "b2",
        "c1": "c1",
        "c1_consulting_ai": "c1",
    }

    target_prefix = prefix_map.get(lvl, lvl)
    return [i for i in items if i.get("categoria", "").startswith(target_prefix)]
