"""Mazo inicial de 100 colocaciones de inglés técnico profesional (BI, Cloud, IA)."""

from typing import Sequence
import sqlite3
from aulento.db.fsrs_repository import FSRSRepository
from aulento.models.fsrs_card import FSRSCardCreate

DECK_100_ITEMS: list[dict[str, str]] = [
    # ── CATEGORÍA 1: DATA ENGINEERING & PIPELINES (20 items) ──────────────────
    {
        "categoria": "data_engineering",
        "item_pregunta": "¿Cómo decir 'cuello de botella en el pipeline'?",
        "respuesta_esperada": "bottleneck in the pipeline",
        "contexto_uso": "We identified a severe bottleneck in the data ingestion pipeline.",
    },
    {
        "categoria": "data_engineering",
        "item_pregunta": "¿Cómo decir 'trabajo idempotente' (que puede reintentarse sin duplicar)?",
        "respuesta_esperada": "idempotent job",
        "contexto_uso": "Make sure the Spark batch transformation is an idempotent job.",
    },
    {
        "categoria": "data_engineering",
        "item_pregunta": "¿Cómo decir 'rellenado retroactivo de datos'?",
        "respuesta_esperada": "backfilling historical data",
        "contexto_uso": "We will trigger an Airflow DAG for backfilling historical data from 2025.",
    },
    {
        "categoria": "data_engineering",
        "item_pregunta": "¿Cómo decir 'desviación del esquema' (cuando los datos entrantes cambian)?",
        "respuesta_esperada": "schema drift",
        "contexto_uso": "Our ingestion service automatically alerts on unexpected schema drift.",
    },
    {
        "categoria": "data_engineering",
        "item_pregunta": "¿Cómo decir 'desduplicar registros'?",
        "respuesta_esperada": "deduplicate records",
        "contexto_uso": "We need to deduplicate records before loading them into BigQuery.",
    },
    {
        "categoria": "data_engineering",
        "item_pregunta": "¿Cómo decir 'rendimiento de lectura/escritura'?",
        "respuesta_esperada": "read/write throughput",
        "contexto_uso": "We increased the read/write throughput by tuning partitions.",
    },
    {
        "categoria": "data_engineering",
        "item_pregunta": "¿Cómo decir 'procesamiento en tiempo real'?",
        "respuesta_esperada": "real-time stream processing",
        "contexto_uso": "Apache Beam handles real-time stream processing with low latency.",
    },
    {
        "categoria": "data_engineering",
        "item_pregunta": "¿Cómo decir 'gestionar la contrapresión'?",
        "respuesta_esperada": "handle backpressure",
        "contexto_uso": "The streaming consumer needs to handle backpressure from Kafka.",
    },
    {
        "categoria": "data_engineering",
        "item_pregunta": "¿Cómo decir 'fuente única de la verdad'?",
        "respuesta_esperada": "single source of truth",
        "contexto_uso": "The centralized data warehouse serves as the single source of truth.",
    },
    {
        "categoria": "data_engineering",
        "item_pregunta": "¿Cómo decir 'migración de esquema'?",
        "respuesta_esperada": "schema migration",
        "contexto_uso": "We ran a schema migration script to add the new timestamp columns.",
    },
    {
        "categoria": "data_engineering",
        "item_pregunta": "¿Cómo decir 'retraso de datos' (diferencia entre evento e ingestión)?",
        "respuesta_esperada": "data freshness lag",
        "contexto_uso": "The client SLA requires a data freshness lag under 15 minutes.",
    },
    {
        "categoria": "data_engineering",
        "item_pregunta": "¿Cómo decir 'descarga o volcado de datos crudos'?",
        "respuesta_esperada": "raw data dump",
        "contexto_uso": "We export a raw data dump into the GCS landing bucket daily.",
    },
    {
        "categoria": "data_engineering",
        "item_pregunta": "¿Cómo decir 'procesamiento por lotes'?",
        "respuesta_esperada": "batch processing window",
        "contexto_uso": "The nightly batch processing window starts at midnight UTC.",
    },
    {
        "categoria": "data_engineering",
        "item_pregunta": "¿Cómo decir 'linaje de datos'?",
        "respuesta_esperada": "data lineage tracking",
        "contexto_uso": "Dataform provides automatic data lineage tracking for governance.",
    },
    {
        "categoria": "data_engineering",
        "item_pregunta": "¿Cómo decir 'bloqueo de tabla'?",
        "respuesta_esperada": "table locking contention",
        "contexto_uso": "Concurrent writes caused table locking contention on PostgreSQL.",
    },
    {
        "categoria": "data_engineering",
        "item_pregunta": "¿Cómo decir 'escaneo completo de tabla'?",
        "respuesta_esperada": "full table scan",
        "contexto_uso": "Avoid a full table scan by filtering on the partitioned date column.",
    },
    {
        "categoria": "data_engineering",
        "item_pregunta": "¿Cómo decir 'datos desordenados o tardíos'?",
        "respuesta_esperada": "late-arriving data",
        "contexto_uso": "Our pipeline handles late-arriving data with watermarks.",
    },
    {
        "categoria": "data_engineering",
        "item_pregunta": "¿Cómo decir 'mecanismo de reintento con retroceso exponencial'?",
        "respuesta_esperada": "exponential backoff retry",
        "contexto_uso": "The API client implements exponential backoff retry logic.",
    },
    {
        "categoria": "data_engineering",
        "item_pregunta": "¿Cómo decir 'desbordamiento de memoria'?",
        "respuesta_esperada": "out-of-memory error",
        "contexto_uso": "The Spark executor crashed due to an out-of-memory error during join.",
    },
    {
        "categoria": "data_engineering",
        "item_pregunta": "¿Cómo decir 'formato de almacenamiento columnar'?",
        "respuesta_esperada": "columnar storage format",
        "contexto_uso": "Parquet is an efficient columnar storage format for analytical queries.",
    },

    # ── CATEGORÍA 2: BUSINESS INTELLIGENCE & ANALYTICS (20 items) ─────────────
    {
        "categoria": "business_intelligence",
        "item_pregunta": "¿Cómo decir 'análisis detallado o desglose'?",
        "respuesta_esperada": "drill-down analysis",
        "contexto_uso": "Let's perform a drill-down analysis on churn rate by region.",
    },
    {
        "categoria": "business_intelligence",
        "item_pregunta": "¿Cómo decir 'alineación con partes interesadas'?",
        "respuesta_esperada": "stakeholder alignment",
        "contexto_uso": "We need stakeholder alignment before locking in the quarterly KPIs.",
    },
    {
        "categoria": "business_intelligence",
        "item_pregunta": "¿Cómo decir 'optimización de consultas'?",
        "respuesta_esperada": "query optimization",
        "contexto_uso": "Query optimization reduced our BigQuery compute costs by 40%.",
    },
    {
        "categoria": "business_intelligence",
        "item_pregunta": "¿Cómo decir 'información accionable'?",
        "respuesta_esperada": "actionable insights",
        "contexto_uso": "The executive dashboard translates raw metrics into actionable insights.",
    },
    {
        "categoria": "business_intelligence",
        "item_pregunta": "¿Cómo decir 'tasa de abandono de clientes'?",
        "respuesta_esperada": "customer churn rate",
        "contexto_uso": "The marketing team wants to predict and lower customer churn rate.",
    },
    {
        "categoria": "business_intelligence",
        "item_pregunta": "¿Cómo decir 'ingresos recurrentes mensuales'?",
        "respuesta_esperada": "monthly recurring revenue",
        "contexto_uso": "Our monthly recurring revenue surpassed the forecast by 12%.",
    },
    {
        "categoria": "business_intelligence",
        "item_pregunta": "¿Cómo decir 'modelo en estrella o copo de nieve'?",
        "respuesta_esperada": "star schema dimensional modeling",
        "contexto_uso": "We structured the data mart using star schema dimensional modeling.",
    },
    {
        "categoria": "business_intelligence",
        "item_pregunta": "¿Cómo decir 'tabla de hechos y dimensiones'?",
        "respuesta_esperada": "fact and dimension tables",
        "contexto_uso": "We joined the sales fact and dimension tables on customer_id.",
    },
    {
        "categoria": "business_intelligence",
        "item_pregunta": "¿Cómo decir 'discrepancia en los datos'?",
        "respuesta_esperada": "data discrepancy",
        "contexto_uso": "Finance flagged a data discrepancy between Stripe and our ERP.",
    },
    {
        "categoria": "business_intelligence",
        "item_pregunta": "¿Cómo decir 'frecuencia de actualización del dashboard'?",
        "respuesta_esperada": "dashboard refresh frequency",
        "contexto_uso": "We scheduled the dashboard refresh frequency to every morning at 8 AM.",
    },
    {
        "categoria": "business_intelligence",
        "item_pregunta": "¿Cómo decir 'desviación respecto al presupuesto'?",
        "respuesta_esperada": "variance against budget",
        "contexto_uso": "The report highlights the operational variance against budget.",
    },
    {
        "categoria": "business_intelligence",
        "item_pregunta": "¿Cómo decir 'análisis de cohortes'?",
        "respuesta_esperada": "cohort retention analysis",
        "contexto_uso": "A cohort retention analysis shows improved engagement after onboarding.",
    },
    {
        "categoria": "business_intelligence",
        "item_pregunta": "¿Cómo decir 'indicador rezagado vs líder'?",
        "respuesta_esperada": "leading and lagging indicators",
        "contexto_uso": "NPS is a leading indicator while total revenue is a lagging indicator.",
    },
    {
        "categoria": "business_intelligence",
        "item_pregunta": "¿Cómo decir 'adopción de usuarios'?",
        "respuesta_esperada": "user adoption rate",
        "contexto_uso": "The product rollout drove a 35% increase in user adoption rate.",
    },
    {
        "categoria": "business_intelligence",
        "item_pregunta": "¿Cómo decir 'agregación a nivel de resumen'?",
        "respuesta_esperada": "summary-level aggregation",
        "contexto_uso": "We pre-calculated the summary-level aggregation for fast rendering.",
    },
    {
        "categoria": "business_intelligence",
        "item_pregunta": "¿Cómo decir 'definición de métricas de negocio'?",
        "respuesta_esperada": "business metric definition",
        "contexto_uso": "We documented the standardized business metric definition in our catalog.",
    },
    {
        "categoria": "business_intelligence",
        "item_pregunta": "¿Cómo decir 'valor de vida del cliente'?",
        "respuesta_esperada": "customer lifetime value",
        "contexto_uso": "Optimizing customer lifetime value requires targeted email journeys.",
    },
    {
        "categoria": "business_intelligence",
        "item_pregunta": "¿Cómo decir 'análisis de embudo'?",
        "respuesta_esperada": "funnel conversion drop-off",
        "contexto_uso": "We discovered a major funnel conversion drop-off on the checkout page.",
    },
    {
        "categoria": "business_intelligence",
        "item_pregunta": "¿Cómo decir 'detección de anomalías'?",
        "respuesta_esperada": "anomaly detection threshold",
        "contexto_uso": "We set an anomaly detection threshold to catch sudden traffic drops.",
    },
    {
        "categoria": "business_intelligence",
        "item_pregunta": "¿Cómo decir 'capa semántica'?",
        "respuesta_esperada": "semantic layer abstraction",
        "contexto_uso": "Using Cube or Looker as a semantic layer abstraction simplifies queries.",
    },

    # ── CATEGORÍA 3: AI & MACHINE LEARNING ENGINEERING (20 items) ─────────────
    {
        "categoria": "ai_machine_learning",
        "item_pregunta": "¿Cómo decir 'mitigar alucinaciones en LLMs'?",
        "respuesta_esperada": "mitigate hallucinations",
        "contexto_uso": "We use retrieval grounding and guardrails to mitigate hallucinations.",
    },
    {
        "categoria": "ai_machine_learning",
        "item_pregunta": "¿Cómo decir 'compromisos en el ajuste fino'?",
        "respuesta_esperada": "fine-tuning tradeoffs",
        "contexto_uso": "We evaluated the fine-tuning tradeoffs between LoRA and full weights.",
    },
    {
        "categoria": "ai_machine_learning",
        "item_pregunta": "¿Cómo decir 'agotamiento de la ventana de contexto'?",
        "respuesta_esperada": "context window exhaustion",
        "contexto_uso": "Long chat histories can lead to context window exhaustion and high costs.",
    },
    {
        "categoria": "ai_machine_learning",
        "item_pregunta": "¿Cómo decir 'latencia de inferencia'?",
        "respuesta_esperada": "inference latency benchmark",
        "contexto_uso": "The model achieved a median inference latency benchmark of 180ms.",
    },
    {
        "categoria": "ai_machine_learning",
        "item_pregunta": "¿Cómo decir 'desviación del modelo en producción'?",
        "respuesta_esperada": "concept drift monitoring",
        "contexto_uso": "We set up Evidently AI for continuous concept drift monitoring.",
    },
    {
        "categoria": "ai_machine_learning",
        "item_pregunta": "¿Cómo decir 'búsqueda de similitud vectorial'?",
        "respuesta_esperada": "vector similarity search",
        "contexto_uso": "We use pgvector to execute cosine vector similarity search.",
    },
    {
        "categoria": "ai_machine_learning",
        "item_pregunta": "¿Cómo decir 'generación aumentada por recuperación'?",
        "respuesta_esperada": "retrieval-augmented generation",
        "contexto_uso": "Our documentation assistant is powered by retrieval-augmented generation.",
    },
    {
        "categoria": "ai_machine_learning",
        "item_pregunta": "¿Cómo decir 'ingeniería de prompts asistida'?",
        "respuesta_esperada": "few-shot prompt engineering",
        "contexto_uso": "Providing two examples in the prompt is few-shot prompt engineering.",
    },
    {
        "categoria": "ai_machine_learning",
        "item_pregunta": "¿Cómo decir 'registro de modelos y versiones'?",
        "respuesta_esperada": "model registry versioning",
        "contexto_uso": "MLflow manages model registry versioning across staging and production.",
    },
    {
        "categoria": "ai_machine_learning",
        "item_pregunta": "¿Cómo decir 'estrategia de troceado o segmentación de texto'?",
        "respuesta_esperada": "chunking strategy",
        "contexto_uso": "We chose a recursive character chunking strategy with 200 tokens overlap.",
    },
    {
        "categoria": "ai_machine_learning",
        "item_pregunta": "¿Cómo decir 'salida estructurada (JSON)'?",
        "respuesta_esperada": "structured output enforcement",
        "contexto_uso": "We enabled JSON mode for strict structured output enforcement.",
    },
    {
        "categoria": "ai_machine_learning",
        "item_pregunta": "¿Cómo decir 'tasa de acierto de recuperación'?",
        "respuesta_esperada": "retrieval recall hit rate",
        "contexto_uso": "Hybrid search improved our retrieval recall hit rate to 92%.",
    },
    {
        "categoria": "ai_machine_learning",
        "item_pregunta": "¿Cómo decir 'sobreajuste en el entrenamiento'?",
        "respuesta_esperada": "overfitting on training data",
        "contexto_uso": "Regularization techniques prevent the classifier from overfitting on training data.",
    },
    {
        "categoria": "ai_machine_learning",
        "item_pregunta": "¿Cómo decir 'inyección de prompts maliciosos'?",
        "respuesta_esperada": "prompt injection vulnerability",
        "contexto_uso": "We sanitized external input to prevent a prompt injection vulnerability.",
    },
    {
        "categoria": "ai_machine_learning",
        "item_pregunta": "¿Cómo decir 'enrutamiento de agentes autónomos'?",
        "respuesta_esperada": "autonomous agent routing",
        "contexto_uso": "The supervisor node performs autonomous agent routing based on intent.",
    },
    {
        "categoria": "ai_machine_learning",
        "item_pregunta": "¿Cómo decir 'cuantización de pesos del modelo'?",
        "respuesta_esperada": "model weight quantization",
        "contexto_uso": "We applied 4-bit model weight quantization to run the LLM locally.",
    },
    {
        "categoria": "ai_machine_learning",
        "item_pregunta": "¿Cómo decir 'curva ROC y área bajo la curva'?",
        "respuesta_esperada": "ROC-AUC evaluation curve",
        "contexto_uso": "The fraud detection model scored 0.94 on the ROC-AUC evaluation curve.",
    },
    {
        "categoria": "ai_machine_learning",
        "item_pregunta": "¿Cómo decir 'llamada a herramientas de función'?",
        "respuesta_esperada": "function calling tool-use",
        "contexto_uso": "The model triggers SQL queries via function calling tool-use.",
    },
    {
        "categoria": "ai_machine_learning",
        "item_pregunta": "¿Cómo decir 'conjunto de datos de validación'?",
        "respuesta_esperada": "held-out test set",
        "contexto_uso": "We reserved 20% of customer interactions as a held-out test set.",
    },
    {
        "categoria": "ai_machine_learning",
        "item_pregunta": "¿Cómo decir 'evaluación de sesgo algorítmico'?",
        "respuesta_esperada": "algorithmic bias audit",
        "contexto_uso": "We conducted an algorithmic bias audit before deploying the credit scoring model.",
    },

    # ── CATEGORÍA 4: CLOUD INFRASTRUCTURE & OPS (20 items) ───────────────────
    {
        "categoria": "cloud_infrastructure",
        "item_pregunta": "¿Cómo decir 'despliegue sin tiempo de inactividad'?",
        "respuesta_esperada": "zero-downtime deployment",
        "contexto_uso": "Blue-green releases allow zero-downtime deployment during peak hours.",
    },
    {
        "categoria": "cloud_infrastructure",
        "item_pregunta": "¿Cómo decir 'límite de velocidad de peticiones'?",
        "respuesta_esperada": "API rate limiting",
        "contexto_uso": "We encountered HTTP 429 errors because of strict API rate limiting.",
    },
    {
        "categoria": "cloud_infrastructure",
        "item_pregunta": "¿Cómo decir 'aprovisionamiento de infraestructura como código'?",
        "respuesta_esperada": "infrastructure as code provisioning",
        "contexto_uso": "Terraform automates our infrastructure as code provisioning on GCP.",
    },
    {
        "categoria": "cloud_infrastructure",
        "item_pregunta": "¿Cómo decir 'arranque en frío de funciones serverless'?",
        "respuesta_esperada": "cold start latency",
        "contexto_uso": "Keeping min-instances at 1 eliminates the Cloud Run cold start latency.",
    },
    {
        "categoria": "cloud_infrastructure",
        "item_pregunta": "¿Cómo decir 'política de rotación de secretos'?",
        "respuesta_esperada": "secret rotation policy",
        "contexto_uso": "Security compliance enforces an automated 90-day secret rotation policy.",
    },
    {
        "categoria": "cloud_infrastructure",
        "item_pregunta": "¿Cómo decir 'balanceador de carga de tráfico'?",
        "respuesta_esperada": "traffic load balancer",
        "contexto_uso": "The global traffic load balancer routes users to the closest region.",
    },
    {
        "categoria": "cloud_infrastructure",
        "item_pregunta": "¿Cómo decir 'conmutación por error ante desastres'?",
        "respuesta_esperada": "disaster recovery failover",
        "contexto_uso": "We tested the disaster recovery failover scenario in the secondary region.",
    },
    {
        "categoria": "cloud_infrastructure",
        "item_pregunta": "¿Cómo decir 'escalado automático horizontal'?",
        "respuesta_esperada": "horizontal autoscaling",
        "contexto_uso": "Kubernetes triggers horizontal autoscaling when CPU exceeds 75%.",
    },
    {
        "categoria": "cloud_infrastructure",
        "item_pregunta": "¿Cómo decir 'control de acceso basado en roles'?",
        "respuesta_esperada": "role-based access control",
        "contexto_uso": "We configured role-based access control (RBAC) following least privilege.",
    },
    {
        "categoria": "cloud_infrastructure",
        "item_pregunta": "¿Cómo decir 'política de ciclo de vida de almacenamiento'?",
        "respuesta_esperada": "storage lifecycle policy",
        "contexto_uso": "A GCS storage lifecycle policy moves 30-day-old logs to Coldline.",
    },
    {
        "categoria": "cloud_infrastructure",
        "item_pregunta": "¿Cómo decir 'red de nube privada virtual'?",
        "respuesta_esperada": "virtual private cloud peering",
        "contexto_uso": "We established virtual private cloud peering between GCP and AWS.",
    },
    {
        "categoria": "cloud_infrastructure",
        "item_pregunta": "¿Cómo decir 'alerta de degradación de servicio'?",
        "respuesta_esperada": "service degradation alert",
        "contexto_uso": "PagerDuty fired a service degradation alert due to database replica lag.",
    },
    {
        "categoria": "cloud_infrastructure",
        "item_pregunta": "¿Cómo decir 'análisis forense de registros'?",
        "respuesta_esperada": "audit log inspection",
        "contexto_uso": "Security began an audit log inspection to trace unauthorized API calls.",
    },
    {
        "categoria": "cloud_infrastructure",
        "item_pregunta": "¿Cómo decir 'aislamiento de red perimetral'?",
        "respuesta_esperada": "network perimeter isolation",
        "contexto_uso": "VPC Service Controls guarantee network perimeter isolation for BigQuery.",
    },
    {
        "categoria": "cloud_infrastructure",
        "item_pregunta": "¿Cómo decir 'disponibilidad de alta redundancia'?",
        "respuesta_esperada": "high-availability cluster",
        "contexto_uso": "We deployed a multi-zone high-availability cluster for Cloud SQL.",
    },
    {
        "categoria": "cloud_infrastructure",
        "item_pregunta": "¿Cómo decir 'ancho de banda de salida'?",
        "respuesta_esperada": "network egress bandwidth",
        "contexto_uso": "Cross-region network egress bandwidth accounted for 15% of the invoice.",
    },
    {
        "categoria": "cloud_infrastructure",
        "item_pregunta": "¿Cómo decir 'punto de enlace de servicio'?",
        "respuesta_esperada": "private service endpoint",
        "contexto_uso": "Connect through the private service endpoint without public IP exposure.",
    },
    {
        "categoria": "cloud_infrastructure",
        "item_pregunta": "¿Cómo decir 'despliegue canario'?",
        "respuesta_esperada": "canary release rollout",
        "contexto_uso": "We routed 5% of production traffic to the canary release rollout.",
    },
    {
        "categoria": "cloud_infrastructure",
        "item_pregunta": "¿Cómo decir 'acuerdo de nivel de servicio'?",
        "respuesta_esperada": "service level agreement",
        "contexto_uso": "Our 99.9% uptime is guaranteed under the customer service level agreement.",
    },
    {
        "categoria": "cloud_infrastructure",
        "item_pregunta": "¿Cómo decir 'reversión rápida de versión'?",
        "respuesta_esperada": "fast rollback mechanism",
        "contexto_uso": "If error rates spike, the pipeline triggers a fast rollback mechanism.",
    },

    # ── CATEGORÍA 5: SCRUM & WORKPLACE TECHNICAL DISCUSSIONS (20 items) ───────
    {
        "categoria": "scrum_workplace",
        "item_pregunta": "¿Cómo decir 'rechazar o empujar una fecha límite' (con respeto profesional)?",
        "respuesta_esperada": "push back on the deadline",
        "contexto_uso": "Given the technical debt, we should push back on the deadline by one sprint.",
    },
    {
        "categoria": "scrum_workplace",
        "item_pregunta": "¿Cómo decir 'evaluar los pros y contras / compromisos'?",
        "respuesta_esperada": "evaluate the trade-offs",
        "contexto_uso": "Before choosing between GraphQL and REST, let's evaluate the trade-offs.",
    },
    {
        "categoria": "scrum_workplace",
        "item_pregunta": "¿Cómo decir 'aclarar el alcance del requerimiento'?",
        "respuesta_esperada": "clarify the scope",
        "contexto_uso": "Can we jump on a quick call to clarify the scope of this user story?",
    },
    {
        "categoria": "scrum_workplace",
        "item_pregunta": "¿Cómo decir 'revisión exhaustiva de código'?",
        "respuesta_esperada": "thorough code review",
        "contexto_uso": "Please submit this PR for a thorough code review before merging.",
    },
    {
        "categoria": "scrum_workplace",
        "item_pregunta": "¿Cómo decir 'impedimento bloqueante'?",
        "respuesta_esperada": "blocking impediment",
        "contexto_uso": "I cannot proceed with the deployment because of a blocking impediment in IAM.",
    },
    {
        "categoria": "scrum_workplace",
        "item_pregunta": "¿Cómo decir 'posponer para la próxima iteración'?",
        "respuesta_esperada": "defer to the next iteration",
        "contexto_uso": "Let's defer non-critical refactoring to the next iteration.",
    },
    {
        "categoria": "scrum_workplace",
        "item_pregunta": "¿Cómo decir 'reunión de retrospectiva'?",
        "respuesta_esperada": "sprint retrospective meeting",
        "contexto_uso": "We discussed communication silos during the sprint retrospective meeting.",
    },
    {
        "categoria": "scrum_workplace",
        "item_pregunta": "¿Cómo decir 'estimación de puntos de historia'?",
        "respuesta_esperada": "story point estimation",
        "contexto_uso": "The team agreed on a 5-point story point estimation for the API integration.",
    },
    {
        "categoria": "scrum_workplace",
        "item_pregunta": "¿Cómo decir 'definición de terminado'?",
        "respuesta_esperada": "definition of done",
        "contexto_uso": "A feature only satisfies the definition of done when unit tests are green.",
    },
    {
        "categoria": "scrum_workplace",
        "item_pregunta": "¿Cómo decir 'gestionar expectativas'?",
        "respuesta_esperada": "manage stakeholder expectations",
        "contexto_uso": "It is critical to manage stakeholder expectations regarding delivery dates.",
    },
    {
        "categoria": "scrum_workplace",
        "item_pregunta": "¿Cómo decir 'prueba de concepto funcional'?",
        "respuesta_esperada": "working proof of concept",
        "contexto_uso": "I built a working proof of concept to validate the vector database performance.",
    },
    {
        "categoria": "scrum_workplace",
        "item_pregunta": "¿Cómo decir 'cambio abrupto de contexto'?",
        "respuesta_esperada": "costly context switching",
        "contexto_uso": "Too many interruptions cause costly context switching for the engineers.",
    },
    {
        "categoria": "scrum_workplace",
        "item_pregunta": "¿Cómo decir 'refactorización para reducir deuda técnica'?",
        "respuesta_esperada": "refactor technical debt",
        "contexto_uso": "We allocated 20% of sprint capacity to refactor technical debt.",
    },
    {
        "categoria": "scrum_workplace",
        "item_pregunta": "¿Cómo decir 'sincronización rápida / daily standup'?",
        "respuesta_esperada": "daily stand-up sync",
        "contexto_uso": "Keep updates concise during the 15-minute daily stand-up sync.",
    },
    {
        "categoria": "scrum_workplace",
        "item_pregunta": "¿Cómo decir 'caso límite o extremo'?",
        "respuesta_esperada": "edge case scenario",
        "contexto_uso": "The unit test covers the edge case scenario where user input is empty.",
    },
    {
        "categoria": "scrum_workplace",
        "item_pregunta": "¿Cómo decir 'acuerdo de equipo'?",
        "respuesta_esperada": "team working agreement",
        "contexto_uso": "Our team working agreement specifies no meetings on Friday afternoons.",
    },
    {
        "categoria": "scrum_workplace",
        "item_pregunta": "¿Cómo decir 'documentación desactualizada'?",
        "respuesta_esperada": "outdated documentation drift",
        "contexto_uso": "We opened an issue to fix outdated documentation drift in our wiki.",
    },
    {
        "categoria": "scrum_workplace",
        "item_pregunta": "¿Cómo decir 'revisión posterior a incidentes (postmortem)'?",
        "respuesta_esperada": "blameless post-mortem review",
        "contexto_uso": "We conducted a blameless post-mortem review to find root causes of the outage.",
    },
    {
        "categoria": "scrum_workplace",
        "item_pregunta": "¿Cómo decir 'discutir fuera de línea / en otro momento'?",
        "respuesta_esperada": "take this discussion offline",
        "contexto_uso": "To stay on schedule, let's take this technical discussion offline.",
    },
    {
        "categoria": "scrum_workplace",
        "item_pregunta": "¿Cómo decir 'alineación entre equipos cruzados'?",
        "respuesta_esperada": "cross-functional collaboration",
        "contexto_uso": "The initiative requires close cross-functional collaboration with DevOps and QA.",
    },
]


def seed_fsrs_deck(conn: sqlite3.Connection, user_id: int) -> int:
    """Inserta de forma idempotente, para una cuenta, las colocaciones clásicas y el mazo progresivo (A1..C1)."""
    from aulento.fsrs.progressive_deck import get_all_progressive_items

    repo = FSRSRepository(conn, user_id)
    insertados = 0
    all_items = DECK_100_ITEMS + get_all_progressive_items()
    for item in all_items:
        repo.create_card(
            FSRSCardCreate(
                categoria=item["categoria"],
                item_pregunta=item["item_pregunta"],
                respuesta_esperada=item["respuesta_esperada"],
                contexto_uso=item["contexto_uso"],
            )
        )
        insertados += 1
    return insertados
