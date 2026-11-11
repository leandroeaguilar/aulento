"""Plantillas pre-curadas de Rutas de Aprendizaje para roles técnicos de alta demanda."""

from aulento.models.roadmap import (
    RoadmapCreate,
    RoadmapModuleCreate,
    RoadmapTopicCreate,
    EstadoTema,
    FuenteTema,
)


def get_curated_templates() -> list[RoadmapCreate]:
    """Retorna las 4 plantillas canónicas de la industria para Aulento."""
    return [
        RoadmapCreate(
            titulo="Data Engineer Senior (Cloud, Streaming & Lakehouse)",
            descripcion="Ruta integral de ingeniería de datos moderna: almacenamiento columnar, lakehouses con Iceberg, streaming distribuido con Kafka, orquestación y gobernanza.",
            categoria="data_engineering",
            nivel_objetivo="Senior",
            metadata_json={"tags": ["GCP", "Kafka", "Iceberg", "dbt", "Airflow", "Spark"]},
            modulos=[
                RoadmapModuleCreate(
                    titulo="1. Almacenamiento Distribuido & Lakehouse",
                    descripcion="Formatos abiertos, particionamiento, metadata layers y query engines",
                    orden=1,
                    temas=[
                        RoadmapTopicCreate(titulo="Apache Iceberg: Arquitectura de Metadatos y Snapshots", orden=1),
                        RoadmapTopicCreate(titulo="Formatos Columnar: Parquet, ORC y Técnicas de Encoding", orden=2),
                        RoadmapTopicCreate(titulo="BigQuery / Snowflake: Particionamiento, Clustering y Pruning", orden=3),
                        RoadmapTopicCreate(titulo="ACID Transactions y Time Travel en Lakehouses", orden=4),
                    ],
                ),
                RoadmapModuleCreate(
                    titulo="2. Streaming & Procesamiento en Tiempo Real",
                    descripcion="Event driven architectures, log-based messaging y backpressure",
                    orden=2,
                    temas=[
                        RoadmapTopicCreate(titulo="Kafka Brokers, Topics, Partitions y Replication Factor", orden=1),
                        RoadmapTopicCreate(titulo="Productores Idempotentes, Acks y Semánticas Exactly-Once", orden=2),
                        RoadmapTopicCreate(titulo="Consumer Groups, Rebalancing y Gestión de Offsets", orden=3),
                        RoadmapTopicCreate(titulo="Change Data Capture (CDC) con Debezium y Kafka Connect", orden=4),
                    ],
                ),
                RoadmapModuleCreate(
                    titulo="3. Transformaciones Masivas & Data Modeling",
                    descripcion="Procesamiento distribuido con Spark, SQL declarativo con dbt y contratos",
                    orden=3,
                    temas=[
                        RoadmapTopicCreate(titulo="Apache Spark: RDDs vs DataFrames, Catalyst Optimizer y Shuffling", orden=1),
                        RoadmapTopicCreate(titulo="Transformaciones dbt: Modelos Incremental, Snapshots y Tests", orden=2),
                        RoadmapTopicCreate(titulo="Data Contracts & Schema Evolution con Protobuf/Avro", orden=3),
                    ],
                ),
                RoadmapModuleCreate(
                    titulo="4. Orquestación, Data Ops & Calidad",
                    descripcion="Pipelines resilientes, observabilidad y validación automatizada",
                    orden=4,
                    temas=[
                        RoadmapTopicCreate(titulo="Apache Airflow: DAG Authoring, Dynamic Tasks y Sensors", orden=1),
                        RoadmapTopicCreate(titulo="Pruebas de Calidad de Datos con Great Expectations / Soda", orden=2),
                        RoadmapTopicCreate(titulo="CI/CD para Pipelines de Datos y Rollback Seguro", orden=3),
                    ],
                ),
                RoadmapModuleCreate(
                    titulo="5. Data Governance, FinOps & Seguridad Cloud",
                    descripcion="Control de costos, RBAC, Data Catalog y cumplimiento normativo",
                    orden=5,
                    temas=[
                        RoadmapTopicCreate(titulo="FinOps: Optimización de Slots BigQuery y Compute Elasticity", orden=1),
                        RoadmapTopicCreate(titulo="Linaje de Datos y Gobernanza con Data Catalog / Purview", orden=2),
                        RoadmapTopicCreate(titulo="Seguridad y Cifrado: KMS, VPC Service Controls e IAM", orden=3),
                    ],
                ),
            ],
        ),
        RoadmapCreate(
            titulo="AI Solutions Architect & LLM Engineer",
            descripcion="Diseño e implementación de sistemas generativos empresariales, RAG avanzado, agentes autónomos y protocolos MCP.",
            categoria="artificial_intelligence",
            nivel_objetivo="Staff / Principal",
            metadata_json={"tags": ["LLM", "RAG", "MCP", "LangChain", "VectorDB", "FineTuning"]},
            modulos=[
                RoadmapModuleCreate(
                    titulo="1. Fundamentos de Modelos de Lenguaje & Transformers",
                    descripcion="Mecanismos de atención, embeddings y ventanas de contexto",
                    orden=1,
                    temas=[
                        RoadmapTopicCreate(titulo="Arquitectura Transformer: Multi-Head Attention y Feed-Forward", orden=1),
                        RoadmapTopicCreate(titulo="Modelos de Embeddings y Medidas de Similitud Coseno/Dot Product", orden=2),
                        RoadmapTopicCreate(titulo="Prompt Engineering Avanzado: CoT, ReAct y Few-Shot", orden=3),
                    ],
                ),
                RoadmapModuleCreate(
                    titulo="2. Arquitectura RAG Empresarial (Retrieval-Augmented)",
                    descripcion="Chunking inteligente, bases vectoriales y re-ranking semántico",
                    orden=2,
                    temas=[
                        RoadmapTopicCreate(titulo="Estrategias de Chunking Jerárquico y Parsing de Documentos Complejos", orden=1),
                        RoadmapTopicCreate(titulo="Bases de Datos Vectoriales: HNSW, IVF y Filtrado de Metadatos", orden=2),
                        RoadmapTopicCreate(titulo="Búsqueda Híbrida (Dense + Sparse BM25) y Rerankers (Cohere/Cross-Encoders)", orden=3),
                        RoadmapTopicCreate(titulo="Graph RAG y Extracción de Entidades Semánticas", orden=4),
                    ],
                ),
                RoadmapModuleCreate(
                    titulo="3. Agentes Autónomos & Protocolo MCP (Model Context Protocol)",
                    descripcion="Sistemas multi-agente, herramientas contextuales y orquestación",
                    orden=3,
                    temas=[
                        RoadmapTopicCreate(titulo="Model Context Protocol (MCP): Servidores, Recursos y Herramientas", orden=1),
                        RoadmapTopicCreate(titulo="Patrones de Agentes: Planning, Memory y Tool Calling", orden=2),
                        RoadmapTopicCreate(titulo="Multi-Agent Collaboration y Protocolos de Comunicación", orden=3),
                    ],
                ),
                RoadmapModuleCreate(
                    titulo="4. Fine-Tuning, Cuantización & MLOps",
                    descripcion="Adaptación eficiente de pesos, inferencia optimizada y evaluación",
                    orden=4,
                    temas=[
                        RoadmapTopicCreate(titulo="Técnicas PEFT: LoRA y QLoRA para Modelos Abiertos", orden=1),
                        RoadmapTopicCreate(titulo="Motores de Inferencia: vLLM, PagedAttention y TGI", orden=2),
                        RoadmapTopicCreate(titulo="Evaluación de RAG y LLMs: Ragas, TruLens y Grounding Metrics", orden=3),
                    ],
                ),
            ],
        ),
        RoadmapCreate(
            titulo="Cloud Infrastructure & FinOps",
            descripcion="Infraestructura como código declarativa, clusters Kubernetes elásticos y gestión financiera de la nube.",
            categoria="cloud_devops",
            nivel_objetivo="Senior",
            metadata_json={"tags": ["Terraform", "Kubernetes", "FinOps", "GCP", "Observability"]},
            modulos=[
                RoadmapModuleCreate(
                    titulo="1. Infraestructura como Código (IaC)",
                    descripcion="Gestión declarativa, state locking y testing de infraestructura",
                    orden=1,
                    temas=[
                        RoadmapTopicCreate(titulo="Terraform: Módulos Reutilizables, Remote State y Locks", orden=1),
                        RoadmapTopicCreate(titulo="Drift Detection y Automatización de CI/CD para IaC", orden=2),
                    ],
                ),
                RoadmapModuleCreate(
                    titulo="2. Contenedores & Orquestación",
                    descripcion="Kubernetes para cargas de datos y servicios micro",
                    orden=2,
                    temas=[
                        RoadmapTopicCreate(titulo="Kubernetes: Pod Scheduling, DaemonSets y StatefulSets", orden=1),
                        RoadmapTopicCreate(titulo="Autoscaling: HPA, VPA y Cluster Autoscaler", orden=2),
                    ],
                ),
                RoadmapModuleCreate(
                    titulo="3. Cultura y Prácticas FinOps",
                    descripcion="Asignación de costos, presupuestos y compromisos de consumo",
                    orden=3,
                    temas=[
                        RoadmapTopicCreate(titulo="Unit Economics: Costo por Consulta, Pipeline y Usuario", orden=1),
                        RoadmapTopicCreate(titulo="Compromisos de Capacidad: CUDs, RIs y Spot Workloads", orden=2),
                    ],
                ),
            ],
        ),
        RoadmapCreate(
            titulo="BI & Strategic Data Storytelling",
            descripcion="Modelado dimensional Kimball, cálculos analíticos en DAX y visualización persuasiva para comités directivos.",
            categoria="business_intelligence",
            nivel_objetivo="Lead",
            metadata_json={"tags": ["Kimball", "DAX", "PowerBI", "Storytelling", "KPIs"]},
            modulos=[
                RoadmapModuleCreate(
                    titulo="1. Arquitectura de Modelado Dimensional",
                    descripcion="Esquemas estrella, granularidad y dimensiones que cambian en el tiempo",
                    orden=1,
                    temas=[
                        RoadmapTopicCreate(titulo="Esquema Estrella vs Copo de Nieve: Hechos y Dimensiones", orden=1),
                        RoadmapTopicCreate(titulo="Dimensiones Degeneradas, Conformes y Role-Playing", orden=2),
                        RoadmapTopicCreate(titulo="Slowly Changing Dimensions (SCD Tipo 1, 2 y 3)", orden=3),
                    ],
                ),
                RoadmapModuleCreate(
                    titulo="2. Cálculos DAX Avanzados & Context Transition",
                    descripcion="Filtros de contexto, iteradores y funciones de inteligencia temporal",
                    orden=2,
                    temas=[
                        RoadmapTopicCreate(titulo="Transición de Contexto: Row Context a Filter Context con CALCULATE", orden=1),
                        RoadmapTopicCreate(titulo="Time Intelligence: YTD, MTD, Rolling Averages y SamePeriodLastYear", orden=2),
                    ],
                ),
                RoadmapModuleCreate(
                    titulo="3. Data Storytelling & Visualización Ejecutiva",
                    descripcion="Comunicación de impacto para líderes C-Level",
                    orden=3,
                    temas=[
                        RoadmapTopicCreate(titulo="Principios Gestalt y Jerarquía Visual en Reportes", orden=1),
                        RoadmapTopicCreate(titulo="Estructura Narrativa: Contexto, Conflicto y Recomendación", orden=2),
                    ],
                ),
            ],
        ),
    ]


def get_template_by_title(title: str | None) -> RoadmapCreate | None:
    """Busca una plantilla cuyo título completo sea igual al texto recibido.

    La comparación ignora mayúsculas y espacios en los extremos. Un texto vacío o una
    coincidencia parcial no devuelven plantilla: usarla es una elección explícita.
    """
    t_clean = (title or "").strip().lower()
    if not t_clean:
        return None
    for tmpl in get_curated_templates():
        if tmpl.titulo.strip().lower() == t_clean:
            return tmpl
    return None
