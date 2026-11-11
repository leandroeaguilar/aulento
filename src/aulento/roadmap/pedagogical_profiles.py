"""Biblioteca de arquetipos pedagógicos y resolución del perfil de enseñanza de cada ruta.

El perfil pedagógico es la capa del Prompt Maestro que cambia por disciplina: se genera una vez
por ruta (con IA o desde un arquetipo) y se guarda en `rutas_aprendizaje.metadata_json`.
"""

import re
import unicodedata
from typing import Any

from pydantic import ValidationError

from aulento.models.roadmap import (
    FlashcardEjemplo,
    PerfilPedagogico,
    RoadmapModuleCreate,
    RoadmapTopicCreate,
    SeccionClase,
)

CLAVE_PERFIL = "perfil_pedagogico"
ARQUETIPO_GENERAL = "general"


def _perfil(
    arquetipo: str,
    disciplina: str,
    rol_docente: str,
    secciones: list[tuple[str, str]],
    tipo_fuentes: str,
    flashcards: list[tuple[str, str]],
    usa_codigo: bool = False,
    usa_diagramas: bool = False,
) -> PerfilPedagogico:
    return PerfilPedagogico(
        disciplina=disciplina,
        arquetipo=arquetipo,
        rol_docente=rol_docente,
        secciones=[SeccionClase(titulo=t, instruccion=i) for t, i in secciones],
        usa_codigo=usa_codigo,
        usa_diagramas=usa_diagramas,
        tipo_fuentes=tipo_fuentes,
        flashcards_ejemplo=[FlashcardEjemplo(pregunta=q, respuesta=a) for q, a in flashcards],
        origen="arquetipo",
    )


ARQUETIPOS: dict[str, PerfilPedagogico] = {
    "tech": _perfil(
        arquetipo="tech",
        disciplina="Ingeniería de software, datos e IA",
        rol_docente="Distinguished Engineer, Educador Pedagógico y Mentor Senior",
        usa_codigo=True,
        usa_diagramas=True,
        tipo_fuentes=(
            "libros técnicos (ej: O'Reilly, Manning), papers, documentación oficial vigente "
            "y artículos de ingeniería de producción"
        ),
        secciones=[
            (
                "Conceptos Clave & Analogía Feynman",
                ("- Explica la esencia del concepto como si hablaras con alguien inteligente pero sin contexto técnico previo.\n"
                "- Proporciona una analogía cotidiana intuitiva que fije la idea mentalmente."),
            ),
            (
                "Diagrama de Arquitectura",
                "- Ilustra con un diagrama el flujo de datos, la interacción entre componentes o la topología de la solución.",
            ),
            (
                "Desarrollo Técnico, Código & Mini-Labs Prácticos",
                ("- Explicación técnica exhaustiva con ejemplos comentados (Python, SQL, YAML de infraestructura o Bash).\n"
                "- Un mini-ejercicio práctico o lab con pasos de prueba y verificación de resultados."),
            ),
            (
                "Buenas Prácticas & Errores Comunes",
                "- Buenas prácticas de ingeniería y errores comunes en producción, con cómo evitarlos.",
            ),
            (
                "Caso Real de Negocio & Preguntas de Entrevista Técnica",
                ("- Un caso real de negocio: problema, métricas afectadas (latencia, costo, downtime) y resolución.\n"
                "- 2 o 3 preguntas desafiantes de entrevista técnica para nivel Senior/Staff con sus respuestas modelo."),
            ),
            (
                "Conexiones Sistémicas (Cross-Domain)",
                "- Explica cómo este concepto se conecta con otras áreas: Datos ↔ IA Generativa ↔ Cloud FinOps ↔ Negocio.",
            ),
        ],
        flashcards=[
            ("¿Pregunta concreta y conceptual que fuerce active recall?", "Respuesta precisa, sin rodeos y técnicamente exacta."),
            ("¿Segunda pregunta técnica sobre este tema?", "Segunda respuesta."),
        ],
    ),
    "idiomas": _perfil(
        arquetipo="idiomas",
        disciplina="Idiomas e inglés profesional",
        rol_docente="Profesor Experto de Inglés para Profesionales y Lingüista Aplicado (especialista en niveles CEFR)",
        tipo_fuentes=(
            "libros de gramática, diccionarios de colocaciones y recursos lingüísticos oficiales "
            "(ej: English Grammar in Use, Oxford Collocations, Cambridge, Merriam-Webster)"
        ),
        secciones=[
            (
                "Concepto Gramatical & Comunicación en Contexto",
                ("- Explica la regla o función comunicativa de forma clara, intuitiva y directa, sin tecnicismos lingüísticos confusos.\n"
                "- Regla mnemotécnica o analogía para recordar el patrón al hablar o escribir."),
            ),
            (
                "Colocaciones Laborales & Vocabulario de Alta Frecuencia",
                ("- Tabla de 5 a 8 colocaciones / phrasal verbs clave de uso diario en reuniones, correos electrónicos, llamadas o networking.\n"
                "- Cada colocación debe incluir su traducción al español y un ejemplo en una oración real de trabajo."),
            ),
            (
                "Guía Fonética & Pronunciación (Dificultades de Hispanohablantes)",
                ("- Fonemas clave con transcripción fonética simplificada (IPA) y cómo articular el sonido con la boca/lengua.\n"
                "- Pares mínimos o sonidos tramposos (ej. vocales cortas vs largas, terminaciones -ed /t/, /d/, /ɪd/, 'th', 'v' vs 'b').\n"
                "- Ejemplos de *Connected Speech* (cómo los nativos unen las palabras y reducciones cotidianas)."),
            ),
            (
                "Diálogo Situacional Realista (Roleplay Profesional)",
                ("- Un diálogo práctico y bidireccional entre dos personas en el ámbito profesional "
                "(ej. standup meeting, llamada con un cliente o feedback)."),
            ),
            (
                "Errores Comunes de Hispanohablantes (False Friends & Spanglish)",
                ("- Cómo expresarlo de forma fluida y nativa (Natural English).\n"
                "- El error típico de traducir literal desde el español (Common Mistake / False Friend)."),
            ),
            (
                "Ejercicios Prácticos de Aplicación",
                ("- 3 ejercicios de completar espacios (Fill in the blanks) con soluciones comentadas.\n"
                "- 2 oraciones para traducción inversa (del español al inglés) para fijar la estructura activa.\n"
                "- Un drill breve de pronunciación (Shadowing)."),
            ),
        ],
        flashcards=[
            (
                "¿Cómo se expresa formalmente 'retrasar una reunión' en inglés laboral?",
                "To push back a meeting (ej: 'Can we push back the sync by 15 minutes?').",
            ),
            (
                "¿Cuál es el error en: 'I have 5 years working here'?",
                "Lo correcto es 'I have been working here for 5 years' (Present Perfect Continuous con 'for').",
            ),
        ],
    ),
    "negocio": _perfil(
        arquetipo="negocio",
        disciplina="Negocio, producto y gestión",
        rol_docente="Principal Product Manager, Head de Estrategia de Negocio y Mentor Ejecutivo",
        usa_diagramas=True,
        tipo_fuentes="marcos de trabajo de producto, libros de estrategia empresarial, OKRs, casos de estudio y diapositivas relevantes",
        secciones=[
            (
                "Conceptos Clave & Valor de Negocio",
                ("- Explica el concepto y por qué es crucial para el negocio o el usuario final sin jerga corporativa vacía.\n"
                "- Analogía cotidiana intuitiva."),
            ),
            (
                "Diagrama de Flujo de Valor o Métricas",
                "- Ilustra con un diagrama el embudo, el flujo de usuario o el árbol de decisiones.",
            ),
            (
                "Frameworks Prácticos, Fórmulas & Dashboards",
                ("- Fórmulas clave de métricas (ej. CAC, LTV, Retention, Churn, ROI), queries analíticas o plantillas de priorización (RICE, MoSCoW).\n"
                "- Mini-ejercicio práctico de análisis o priorización."),
            ),
            (
                "Buenas Prácticas & Errores de Producto",
                "- Buenas prácticas de producto y liderazgo, y errores comunes de gestión con cómo evitarlos.",
            ),
            (
                "Caso Real de Negocio & Preguntas de Entrevista",
                ("- Caso real de estudio: problema del usuario/negocio, métricas afectadas y estrategia implementada.\n"
                "- 2 o 3 preguntas desafiantes de entrevista para Product Manager / Business Analyst."),
            ),
            (
                "Conexiones Sistémicas",
                "- Conexión entre Producto ↔ Datos ↔ Ingeniería ↔ Impacto Financiero.",
            ),
        ],
        flashcards=[
            (
                "¿Cuál es la fórmula del LTV (Customer Lifetime Value) en un modelo SaaS?",
                "LTV = (ARPU * Margen Bruto) / Churn Rate mensual.",
            ),
            (
                "¿Qué diferencia a un Output de un Outcome en gestión de producto?",
                "El Output es la funcionalidad entregada; el Outcome es el cambio de comportamiento medible en el usuario.",
            ),
        ],
    ),
    "humanidades": _perfil(
        arquetipo="humanidades",
        disciplina="Humanidades",
        rol_docente="Profesor universitario de humanidades, riguroso con los textos y claro al exponer",
        tipo_fuentes="textos primarios de los autores, ediciones críticas y bibliografía secundaria académica",
        secciones=[
            (
                "Problema y contexto",
                "- Plantea la pregunta o el problema que el tema intenta responder y su contexto histórico e intelectual.",
            ),
            (
                "Texto o autor primario",
                "- Presenta al autor o el texto central, su tesis y los conceptos que introduce, con referencias a la obra.",
            ),
            (
                "Reconstrucción del argumento",
                "- Reconstruye el argumento paso a paso: premisas, inferencias y conclusión, en lenguaje llano.",
            ),
            (
                "Objeciones y réplicas",
                "- Expone las objeciones más fuertes que recibió la posición y cómo se respondió a ellas.",
            ),
            (
                "Vigencia y conexiones",
                "- Relaciona el tema con otros autores, corrientes y debates actuales.",
            ),
            (
                "Pregunta de ensayo",
                "- Propone una pregunta de ensayo abierta y un esquema breve de cómo abordarla.",
            ),
        ],
        flashcards=[
            (
                "¿Qué distingue, para los estoicos, lo que depende de nosotros de lo que no?",
                "Dependen de nosotros los juicios, deseos e impulsos; no dependen el cuerpo, la reputación ni los bienes externos.",
            ),
            (
                "¿Cuál es la objeción clásica al imperativo categórico de Kant?",
                "Su formalismo: puede universalizarse una máxima sin que quede claro qué deber concreto se sigue de ella.",
            ),
        ],
    ),
    "ciencias_sociales_salud": _perfil(
        arquetipo="ciencias_sociales_salud",
        disciplina="Ciencias sociales y de la salud",
        rol_docente="Docente universitario e investigador, preciso con la evidencia y cuidadoso con sus límites",
        tipo_fuentes="manuales universitarios, artículos revisados por pares, metaanálisis y guías profesionales o clínicas",
        secciones=[
            (
                "Concepto y definiciones",
                "- Define el concepto con precisión y distingue sus usos técnicos del uso cotidiano.",
            ),
            (
                "Teorías y autores",
                "- Presenta las principales teorías o modelos explicativos y los autores que los formularon.",
            ),
            (
                "Evidencia empírica y estudios clásicos",
                "- Resume la evidencia empírica que sostiene o cuestiona cada teoría: estudios clásicos, diseño, muestra y hallazgos.",
            ),
            (
                "Caso aplicado",
                "- Desarrolla un caso o viñeta realista que muestre cómo se aplica el concepto en la práctica.",
            ),
            (
                "Consideraciones éticas",
                "- Señala los resguardos éticos y profesionales que corresponden al tema.",
            ),
            (
                "Críticas, límites y replicabilidad",
                "- Indica las críticas principales, los límites de la evidencia y si los hallazgos se han replicado.",
            ),
        ],
        flashcards=[
            (
                "¿Qué es el sesgo de confirmación?",
                "La tendencia a buscar, interpretar y recordar la información de modo que confirme las creencias previas.",
            ),
            (
                "¿Qué diferencia a un estudio correlacional de uno experimental?",
                "El experimental manipula una variable y asigna al azar, lo que permite inferir causalidad; el correlacional solo mide asociación.",
            ),
        ],
    ),
    "ciencias_formales": _perfil(
        arquetipo="ciencias_formales",
        disciplina="Ciencias formales y exactas",
        rol_docente="Profesor de ciencias exactas, que construye primero la intuición y después el rigor",
        tipo_fuentes="libros de texto con demostraciones, apuntes de cátedra y guías de ejercicios resueltos",
        secciones=[
            (
                "Intuición",
                "- Presenta la idea con un ejemplo concreto o una imagen geométrica antes de formalizar.",
            ),
            (
                "Definiciones formales",
                "- Enuncia las definiciones y la notación con precisión.",
            ),
            (
                "Resultado principal y demostración",
                "- Enuncia el teorema o resultado central y desarrolla su demostración justificando cada paso.",
            ),
            (
                "Ejemplos resueltos paso a paso",
                "- Resuelve 2 o 3 ejemplos de dificultad creciente mostrando todo el procedimiento.",
            ),
            (
                "Ejercicios graduados",
                "- Propone ejercicios de menor a mayor dificultad, con la solución o una pista al final.",
            ),
            (
                "Errores típicos",
                "- Señala los errores de razonamiento y de cálculo más frecuentes y cómo detectarlos.",
            ),
        ],
        flashcards=[
            (
                "¿Cuándo es invertible una matriz cuadrada?",
                "Cuando su determinante es distinto de cero (equivalentemente, cuando sus columnas son linealmente independientes).",
            ),
            (
                "¿Qué afirma el teorema fundamental del cálculo?",
                "Que derivar e integrar son operaciones inversas: la integral de f entre a y b es F(b) - F(a) para cualquier primitiva F de f.",
            ),
        ],
    ),
    "arte_hobby": _perfil(
        arquetipo="arte_hobby",
        disciplina="Arte, oficios y aficiones",
        rol_docente="Maestro de taller paciente y entusiasta, que enseña mostrando y haciendo practicar",
        tipo_fuentes="libros de referencia, catálogos de obras, tutoriales y material de maestros reconocidos",
        secciones=[
            (
                "Qué es y por qué importa",
                "- Explica de qué se trata el tema y qué aporta dominarlo, sin dar nada por sabido.",
            ),
            (
                "Contexto e historia",
                "- Ubica el tema en su tradición: de dónde viene, quiénes lo desarrollaron y cómo evolucionó.",
            ),
            (
                "Técnica o elementos clave",
                "- Describe la técnica o los elementos esenciales paso a paso, con qué observar en cada uno.",
            ),
            (
                "Obras o ejemplos de referencia",
                "- Comenta 2 o 3 obras, piezas o ejemplos de referencia y qué se aprende de cada uno.",
            ),
            (
                "Práctica guiada",
                "- Propone una práctica concreta y breve para hacer hoy, con criterios para evaluar el resultado.",
            ),
        ],
        flashcards=[
            (
                "¿Qué es la regla de los tercios en composición?",
                "Dividir el encuadre en una cuadrícula de 3×3 y ubicar los elementos de interés sobre las líneas o sus intersecciones.",
            ),
            (
                "¿Qué notas forman un acorde mayor?",
                "La fundamental, la tercera mayor y la quinta justa.",
            ),
        ],
    ),
    ARQUETIPO_GENERAL: _perfil(
        arquetipo=ARQUETIPO_GENERAL,
        disciplina="General",
        rol_docente="Docente experto en la disciplina, claro, riguroso y cercano",
        tipo_fuentes="libros de referencia, apuntes y materiales de estudio confiables sobre la disciplina",
        secciones=[
            (
                "Concepto",
                "- Explica qué es el tema y por qué importa, definiendo los términos necesarios.",
            ),
            (
                "Desarrollo",
                "- Desarrolla las ideas principales en orden lógico, de lo simple a lo complejo.",
            ),
            (
                "Ejemplos",
                "- Da 2 o 3 ejemplos concretos que muestren el concepto en distintas situaciones.",
            ),
            (
                "Aplicación práctica",
                "- Propone una actividad o ejercicio para aplicar lo aprendido.",
            ),
            (
                "Errores comunes",
                "- Señala las confusiones más frecuentes y cómo evitarlas.",
            ),
        ],
        flashcards=[
            ("¿Pregunta concreta que obligue a recordar una idea central del tema?", "Respuesta breve, precisa y autocontenida."),
            ("¿Segunda pregunta sobre otro concepto clave del tema?", "Segunda respuesta."),
        ],
    ),
}


# Categorías cuyo valor exacto decide el arquetipo sin mirar las palabras del título.
_CATEGORIAS_DECISIVAS: dict[str, str] = {
    **{nombre: nombre for nombre in ARQUETIPOS if nombre != ARQUETIPO_GENERAL},
    "english_communication": "idiomas",
    "product_management": "negocio",
    "business_intelligence": "negocio",
}

# Categorías técnicas que el usuario elige a propósito: suman a favor de `tech` sin decidir solas.
# `data_ai` queda afuera porque fue el valor por defecto histórico y no dice nada de la disciplina.
_CATEGORIAS_TECNICAS: frozenset[str] = frozenset(
    {
        "data_engineering", "artificial_intelligence", "data_science", "software_eng", "cloud_devops",
        "frontend_web", "mobile_dev", "cybersecurity",
    }
)

_PESO_FUERTE = 3
_PESO_DEBIL = 1
_PESO_CATEGORIA_TECNICA = 2

# Palabras completas (sin tildes) por arquetipo: (nombre, fuertes, débiles).
# Fuertes: nombran la disciplina. Débiles: palabras de uso general que también aparecen en títulos de
# otras áreas ("history", "salud", "arte", "data"). Una entrada con espacios es una frase contigua.
_PALABRAS_POR_ARQUETIPO: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = [
    (
        "idiomas",
        (
            "ingles", "english", "frances", "french", "aleman", "german", "italiano", "italian",
            "portugues", "portuguese", "japones", "japanese", "chino", "mandarin", "coreano", "korean",
            "idioma", "idiomas", "cefr", "toefl", "ielts",
            "foreign language", "lengua extranjera", "segunda lengua",
        ),
        (
            "grammar", "gramatica", "vocabulario", "vocabulary", "collocation", "collocations",
            "colocaciones", "fonetica", "pronunciacion", "listening",
        ),
    ),
    (
        "ciencias_sociales_salud",
        (
            "psicologia", "psicoterapia", "psicoanalisis", "psiquiatria", "neuropsicologia", "neurociencia",
            "neurociencias", "sociologia", "antropologia", "pedagogia", "criminologia", "economia",
            "medicina", "enfermeria", "nutricion", "epidemiologia", "farmacologia", "anatomia",
            "fisiologia", "biologia",
            "psychology", "psychiatry", "neuroscience", "sociology", "anthropology", "economics",
            "medicine", "nursing", "biology",
            "ciencia politica", "ciencias politicas", "trabajo social", "ciencias sociales",
        ),
        ("salud", "health", "clinica", "clinico", "terapia", "therapy"),
    ),
    (
        "humanidades",
        (
            "filosofia", "filosofico", "filosofica", "estoicismo", "estoico", "estoica", "metafisica",
            "epistemologia", "literatura", "linguistica", "teologia", "mitologia", "humanidades", "retorica",
            "philosophy", "stoicism", "literature", "humanities",
        ),
        ("historia", "history", "etica", "ethics", "religion", "derecho", "juridico", "juridica", "law"),
    ),
    (
        "ciencias_formales",
        (
            "matematica", "matematicas", "algebra", "geometria", "trigonometria", "aritmetica",
            "topologia", "fisica", "quimica",
            "mathematics", "math", "maths", "calculus", "geometry", "physics", "chemistry",
            "analisis matematico", "teoria de numeros", "ecuaciones diferenciales",
        ),
        ("calculo", "estadistica", "statistics", "probabilidad", "probability", "logica", "logic"),
    ),
    (
        "arte_hobby",
        (
            "pintura", "dibujo", "acuarela", "escultura", "ceramica", "ilustracion", "caligrafia",
            "musica", "guitarra", "piano", "fotografia", "danza", "cocina", "gastronomia", "jardineria",
            "ajedrez", "artesania",
            "painting", "drawing", "music", "guitar", "photography", "cooking", "chess", "gardening",
        ),
        ("arte", "art", "cine", "canto", "teatro", "hobby"),
    ),
    (
        "negocio",
        (
            "agile", "scrum", "okr", "okrs", "kpi", "kpis", "marketing", "finanzas", "emprendimiento",
            "contabilidad", "mba",
            "business intelligence", "product management", "product manager", "project management",
        ),
        ("product", "producto", "negocio", "negocios", "ventas", "liderazgo", "startup"),
    ),
    (
        "tech",
        (
            "llm", "llms", "mlops", "cloud", "software", "programacion", "programming", "python", "java",
            "javascript", "typescript", "rust", "golang", "sql", "kubernetes", "docker", "devops", "sre",
            "finops", "backend", "frontend", "fullstack", "aws", "gcp", "azure", "ec2", "kafka", "spark",
            "terraform", "linux", "lakehouse", "fastapi", "git", "github", "ciberseguridad", "cybersecurity",
            "infosec", "pentesting", "engineer", "developer", "algoritmos", "algorithms",
            "machine learning", "deep learning", "language model", "language models",
            "inteligencia artificial", "artificial intelligence",
        ),
        (
            "data", "datos", "ai", "ia", "ml", "web", "mobile", "api", "apis", "s3", "security",
            "architect", "architecture", "infrastructure", "infraestructura", "codigo", "code",
        ),
    ),
]

_PALABRAS_INGLES: frozenset[str] = frozenset({"ingles", "english", "toefl", "ielts"})


def _sin_tildes(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto.replace("ñ", "\0"))
    limpio = "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")
    return limpio.replace("\0", "ñ")


def una_linea(texto: str | None) -> str:
    """Colapsa saltos de línea y espacios repetidos."""
    return " ".join((texto or "").split())


def tokenizar(texto: str) -> list[str]:
    """Separa un texto en palabras completas en minúsculas y sin tildes."""
    return [_sin_tildes(p) for p in re.findall(r"[a-záéíóúüñ0-9]+", (texto or "").lower())]


def _contiene(tokens: list[str], entrada: str) -> bool:
    frase = entrada.split()
    if len(frase) == 1:
        return entrada in tokens
    largo = len(frase)
    return any(tokens[i : i + largo] == frase for i in range(len(tokens) - largo + 1))


def resolver_arquetipo(categoria: str | None, titulo: str | None, objetivo: str | None = "") -> str:
    """Elige un arquetipo de forma determinista comparando palabras completas, nunca subcadenas.

    Puntúa cada arquetipo con las palabras del título y del objetivo (las que nombran una disciplina
    pesan más que las de uso general). La categoría no se tokeniza: solo decide cuando es inequívoca
    y, si es una categoría técnica elegida por el usuario, suma a favor de `tech`.
    Sin ninguna coincidencia devuelve `general`.
    """
    categoria_limpia = (categoria or "").strip().lower()
    if categoria_limpia in _CATEGORIAS_DECISIVAS:
        return _CATEGORIAS_DECISIVAS[categoria_limpia]

    tokens = tokenizar(f"{titulo or ''} | {objetivo or ''}")
    puntajes: dict[str, int] = {}
    for nombre, fuertes, debiles in _PALABRAS_POR_ARQUETIPO:
        puntajes[nombre] = _PESO_FUERTE * sum(_contiene(tokens, e) for e in fuertes) + _PESO_DEBIL * sum(
            _contiene(tokens, e) for e in debiles
        )
    if categoria_limpia in _CATEGORIAS_TECNICAS:
        puntajes["tech"] += _PESO_CATEGORIA_TECNICA

    mejor = max(puntajes.values())
    if mejor == 0:
        return ARQUETIPO_GENERAL
    empatados = [nombre for nombre, puntaje in puntajes.items() if puntaje == mejor]
    return "tech" if "tech" in empatados else empatados[0]


def es_ruta_de_ingles(categoria: str | None, *textos: str | None) -> bool:
    """Indica si una ruta de idiomas es específicamente de inglés."""
    if (categoria or "").strip().lower() == "english_communication":
        return True
    return bool(_PALABRAS_INGLES & set(tokenizar(" | ".join(t or "" for t in textos))))


VARIANTE_IDIOMA_NEUTRO = "idiomas_neutro"

# Variante del arquetipo `idiomas` para lenguas que no son inglés: misma forma de clase, sin
# ejemplos, fonética ni bibliografía propios del inglés.
_PERFIL_IDIOMA_NEUTRO = _perfil(
    arquetipo="idiomas",
    disciplina="Idiomas",
    rol_docente="Profesor del idioma con experiencia enseñando a hispanohablantes (referencia de niveles CEFR)",
    tipo_fuentes="gramáticas de referencia, diccionarios y manuales del idioma con ejemplos de uso real",
    secciones=[
        (
            "Concepto Gramatical & Comunicación en Contexto",
            ("- Explica la regla o función comunicativa de forma clara e intuitiva, sin tecnicismos lingüísticos confusos.\n"
            "- Regla mnemotécnica o analogía para recordar el patrón al hablar o escribir."),
        ),
        (
            "Vocabulario & Expresiones de Alta Frecuencia",
            ("- Tabla de 5 a 8 expresiones o combinaciones de palabras de uso frecuente sobre el tema.\n"
            "- Cada una con su traducción al español y un ejemplo en una oración real."),
        ),
        (
            "Pronunciación (Dificultades de Hispanohablantes)",
            ("- Sonidos del idioma que no existen en español, con transcripción fonética simplificada (IPA) y cómo articularlos.\n"
            "- Pares de palabras que se confunden al oído y cómo distinguirlos."),
        ),
        (
            "Diálogo Situacional Realista",
            "- Un diálogo práctico entre dos personas en una situación cotidiana o profesional donde aparezca el tema.",
        ),
        (
            "Errores Comunes de Hispanohablantes",
            ("- Los falsos amigos y las traducciones literales desde el español más frecuentes en este tema.\n"
            "- Cómo decirlo de forma natural."),
        ),
        (
            "Ejercicios Prácticos de Aplicación",
            ("- 3 ejercicios de completar espacios con soluciones comentadas.\n"
            "- 2 oraciones para traducir del español al idioma que se estudia.\n"
            "- Un ejercicio breve de pronunciación en voz alta."),
        ),
    ],
    flashcards=[
        ("¿Cómo se dice en el idioma que se estudia una expresión clave del tema?", "La expresión, con un ejemplo de uso en una oración."),
        ("¿Cuál es el error en una oración traducida literalmente desde el español?", "La forma correcta y la regla que la explica."),
    ],
)


def perfil_desde_arquetipo(nombre: str, disciplina: str | None = None) -> PerfilPedagogico:
    """Devuelve una copia del arquetipo pedido con `origen="arquetipo"` y la disciplina de la ruta."""
    if nombre == VARIANTE_IDIOMA_NEUTRO:
        base = _PERFIL_IDIOMA_NEUTRO
    else:
        base = ARQUETIPOS.get(nombre, ARQUETIPOS[ARQUETIPO_GENERAL])
    perfil = base.model_copy(deep=True)
    perfil.origen = "arquetipo"
    disciplina_limpia = una_linea(disciplina)[:120]
    if disciplina_limpia:
        perfil.disciplina = disciplina_limpia
    return perfil


def variante_de_arquetipo(arquetipo: str, categoria: str | None, *textos: str | None) -> str:
    """Devuelve la variante concreta a usar: `idiomas` solo conserva su contenido de inglés si la ruta es de inglés."""
    if arquetipo == "idiomas" and not es_ruta_de_ingles(categoria, *textos):
        return VARIANTE_IDIOMA_NEUTRO
    return arquetipo


def perfil_resuelto(
    categoria: str | None, titulo: str | None, objetivo: str | None = "", disciplina: str | None = None
) -> PerfilPedagogico:
    """Resuelve el arquetipo de una ruta sin perfil propio y devuelve su perfil."""
    arquetipo = resolver_arquetipo(categoria, titulo, objetivo)
    return perfil_desde_arquetipo(variante_de_arquetipo(arquetipo, categoria, titulo, objetivo), disciplina or titulo)


def _texto(valor: Any, maximo: int) -> str:
    return valor.strip()[:maximo] if isinstance(valor, str) else ""


def parsear_perfil(raw: Any) -> PerfilPedagogico | None:
    """Valida un perfil recibido como dict (IA o guardado); devuelve None si no cumple el contrato.

    Lo recuperable se recorta en vez de descartar el perfil entero: secciones de más, textos demasiado
    largos y flashcards mal formadas. Menos de 3 secciones válidas o un campo obligatorio vacío sí lo invalidan.
    """
    if not isinstance(raw, dict):
        return None

    secciones_crudas = raw.get("secciones")
    secciones = [
        {"titulo": _texto(s.get("titulo"), 200), "instruccion": _texto(s.get("instruccion"), 2000)}
        for s in (secciones_crudas if isinstance(secciones_crudas, list) else [])
        if isinstance(s, dict) and _texto(s.get("titulo"), 200) and _texto(s.get("instruccion"), 2000)
    ][:8]

    tarjetas_crudas = raw.get("flashcards_ejemplo")
    tarjetas = [
        {"pregunta": _texto(t.get("pregunta"), 500), "respuesta": _texto(t.get("respuesta"), 1000)}
        for t in (tarjetas_crudas if isinstance(tarjetas_crudas, list) else [])
        if isinstance(t, dict) and _texto(t.get("pregunta"), 500) and _texto(t.get("respuesta"), 1000)
    ][:6]

    datos = {
        "disciplina": _texto(raw.get("disciplina"), 120),
        "arquetipo": raw.get("arquetipo") if raw.get("arquetipo") in ARQUETIPOS else ARQUETIPO_GENERAL,
        "rol_docente": _texto(raw.get("rol_docente"), 300),
        "secciones": secciones,
        "usa_codigo": raw.get("usa_codigo") is True,
        "usa_diagramas": raw.get("usa_diagramas") is True,
        "tipo_fuentes": _texto(raw.get("tipo_fuentes"), 500),
        "flashcards_ejemplo": tarjetas,
        "origen": raw.get("origen") if raw.get("origen") in ("ia", "arquetipo", "editado") else "ia",
    }

    try:
        return PerfilPedagogico.model_validate(datos)
    except ValidationError:
        return None


def perfil_de_ruta(metadata_json: dict[str, Any] | None, categoria: str | None, titulo: str | None) -> PerfilPedagogico:
    """Lee el perfil guardado en la ruta o, si no hay uno válido, lo resuelve al vuelo desde un arquetipo."""
    guardado = parsear_perfil((metadata_json or {}).get(CLAVE_PERFIL))
    if guardado:
        return guardado
    return perfil_resuelto(categoria, titulo)


# --- Esqueletos de ruta para construir una ruta sin IA (fallback) ---
# Cada bloque: (título del módulo, descripción, temas). `{t}` se reemplaza por el objetivo de la ruta.

_ESQUELETOS: dict[str, list[tuple[str, str, list[str]]]] = {
    "tech": [
        (
            "1. Fundamentos & Arquitectura de {t}",
            "Bases teóricas, componentes centrales y protocolos estándar",
            [
                "Principios y Diseño Arquitectónico de {t}",
                "Patrones Estándar y Estructura de Proyecto en {t}",
                "Configuraciones Clave y Buenas Prácticas de Desarrollo",
            ],
        ),
        (
            "2. Implementación Práctica & Casos de Uso Reales",
            "Desarrollo hands-on, integración de servicios y pruebas",
            [
                "Desarrollo de Módulos Centrales y Flujos de Datos",
                "Manejo Robusto de Excepciones, Validaciones y Logs",
                "Pruebas Automatizadas y Verificación de Resultados",
            ],
        ),
        (
            "3. Escalabilidad, Seguridad & Despliegue en Producción",
            "Rendimiento, optimización y preparación para entrevistas",
            [
                "Estrategias de Escalabilidad y Optimización de Rendimiento",
                "Seguridad, Control de Accesos y Buenas Prácticas en Producción",
                "Preguntas Desafiantes de Entrevista Técnica y Casos de Negocio",
            ],
        ),
    ],
    "idiomas": [
        (
            "1. Gramática en Contexto & Estructuras Clave",
            "Reglas gramaticales explicadas de forma intuitiva y aplicada a situaciones reales",
            [
                "Simple Past vs Past Continuous en Conversaciones de Trabajo",
                "Verbos Modales para Peticiones Diplomáticas (Could, Would, Should)",
                "Conectores Lógicos y Cohesión de Ideas (However, Therefore, Although)",
                "Estructuras Condicionales para Escenarios y Propuestas Hipotéticas",
            ],
        ),
        (
            "2. Comunicación Laboral & Entorno Profesional",
            "Vocabulario de alta frecuencia, colocaciones de negocios y redacción de emails",
            [
                "Colocaciones y Frases Clave para Daily Standups y Sprint Reviews",
                "Redacción Efectiva de Correos Técnicos, Tickets y Slack Updates",
                "Expresar Acuerdo, Desacuerdo Diplomático y Pedir Aclaraciones",
                "Presentación de Avances y Explicación de Bloqueos a Stakeholders",
            ],
        ),
        (
            "3. Guía Fonética, Pronunciación & Connected Speech",
            "Entrenamiento auditivo, reducción de acento y fluidez conversacional",
            [
                "Sonidos de Terminaciones Regulares (-ed: /t/, /d/, /ɪd/) y Plurales (-s)",
                "Pares Mínimos y Fonemas Tramposos para Hispanohablantes (v/b, sh/ch, vocales)",
                "Connected Speech: Reducciones Nativas, Linking y Acentuación Rítmica",
                "Técnicas de Shadowing y Modelado de Dicción Profesional",
            ],
        ),
        (
            "4. Simulaciones, Roleplays & Entrevistas en Inglés",
            "Casos prácticos de diálogo interactivo, entrevistas y discovery calls",
            [
                "Estructura STAR en Inglés para Entrevistas Laborales Técnicas",
                "Roleplay: Negociación de Plazos, Prioridades y Alcance de Proyectos",
                "Manejo de Preguntas Difíciles e Imprevistas en Reuniones en Vivo",
            ],
        ),
    ],
    "idiomas_neutro": [
        (
            "1. Bases del idioma: {t}",
            "Sonidos, escritura y estructuras mínimas para empezar a comunicarse",
            [
                "Sonidos y pronunciación básicos",
                "Estructura de la oración simple",
                "Vocabulario esencial y expresiones de supervivencia",
            ],
        ),
        (
            "2. Gramática en contexto",
            "Reglas explicadas de forma intuitiva y aplicadas a situaciones reales",
            [
                "Tiempos verbales para hablar del presente, el pasado y el futuro",
                "Preguntas, negaciones y peticiones",
                "Conectores para unir ideas",
            ],
        ),
        (
            "3. Comunicación en situaciones reales",
            "Comprensión y producción oral y escrita",
            [
                "Conversaciones cotidianas y presentaciones personales",
                "Comprensión de textos y audios breves",
                "Escritura de mensajes y correos",
            ],
        ),
        (
            "4. Fluidez y errores típicos",
            "Práctica guiada y corrección de los errores de hispanohablantes",
            [
                "Falsos amigos y traducciones literales frecuentes",
                "Práctica de diálogo y pronunciación en voz alta",
                "Repaso integrador y próximos pasos",
            ],
        ),
    ],
    "negocio": [
        (
            "1. Product Discovery & Definición del Problema",
            "Investigación de usuarios, hipótesis de valor y customer journey",
            [
                "Frameworks de Product Discovery e Investigación Cualitativa",
                "Mapeo de Oportunidades y Definición de Problem Statements",
                "Validación Temprana de Hipótesis y Prototipado Rápido",
            ],
        ),
        (
            "2. Priorización Estratégica & Gestión de Roadmaps",
            "Modelos de decisión, trade-offs y alineación de stakeholders",
            [
                "Frameworks de Priorización: RICE, MoSCoW y Kano Model",
                "Construcción de Roadmaps Basados en Resultados (Outcome vs Output)",
                "Historias de Usuario y Criterios de Aceptación BDD/Gherkin",
            ],
        ),
        (
            "3. Product Analytics, Métricas & OKRs",
            "Definición de KPIs, experimentación A/B y medición de impacto",
            [
                "Métricas Clave SaaS y Negocio: CAC, LTV, Retention, Churn y Cohortes",
                "North Star Metric y Árboles de Métricas Desglosadas",
                "Diseño de Experimentos A/B Testing y Análisis Estadístico",
            ],
        ),
    ],
    "humanidades": [
        (
            "1. Contexto y problemas centrales de {t}",
            "Marco histórico e intelectual y preguntas que organizan el campo",
            [
                "Contexto histórico e intelectual de {t}",
                "Preguntas y problemas fundamentales",
                "Conceptos y vocabulario clave",
            ],
        ),
        (
            "2. Autores y textos primarios",
            "Lectura directa de las fuentes y reconstrucción de sus argumentos",
            [
                "Autores principales de {t} y sus tesis",
                "Lectura guiada de textos primarios",
                "Reconstrucción de los argumentos centrales",
            ],
        ),
        (
            "3. Debates, objeciones y vigencia",
            "Discusión crítica y relación con el presente",
            [
                "Objeciones clásicas y réplicas",
                "Interpretaciones y debates contemporáneos",
                "Escritura de un ensayo argumentativo sobre {t}",
            ],
        ),
    ],
    "ciencias_sociales_salud": [
        (
            "1. Conceptos y marcos teóricos de {t}",
            "Definiciones, teorías y autores de referencia",
            [
                "Objeto de estudio y conceptos fundamentales de {t}",
                "Principales teorías y modelos explicativos",
                "Autores y escuelas de referencia",
            ],
        ),
        (
            "2. Métodos y evidencia",
            "Cómo se investiga y qué se sabe con respaldo empírico",
            [
                "Métodos de investigación y tipos de estudio",
                "Estudios clásicos y hallazgos principales",
                "Lectura crítica de evidencia: validez, sesgos y replicabilidad",
            ],
        ),
        (
            "3. Aplicación, ética y debates actuales",
            "Del concepto a la práctica profesional responsable",
            [
                "Análisis de casos aplicados de {t}",
                "Consideraciones éticas y profesionales",
                "Críticas, límites y debates abiertos",
            ],
        ),
    ],
    "ciencias_formales": [
        (
            "1. Intuición y definiciones de {t}",
            "Ideas de base, notación y definiciones formales",
            [
                "Motivación e intuición detrás de {t}",
                "Definiciones formales y notación",
                "Propiedades básicas y primeros ejemplos",
            ],
        ),
        (
            "2. Resultados principales y demostraciones",
            "Teoremas centrales y las técnicas para demostrarlos",
            [
                "Teoremas y resultados centrales de {t}",
                "Técnicas de demostración",
                "Ejemplos resueltos paso a paso",
            ],
        ),
        (
            "3. Práctica y resolución de problemas",
            "Ejercitación graduada y control de errores",
            [
                "Ejercicios graduados de {t}",
                "Problemas integradores",
                "Errores típicos y cómo detectarlos",
            ],
        ),
    ],
    "arte_hobby": [
        (
            "1. Primer contacto con {t}",
            "De qué se trata, de dónde viene y qué hace falta para empezar",
            [
                "Qué es {t} y por qué vale la pena",
                "Historia y contexto",
                "Materiales, herramientas y vocabulario básico",
            ],
        ),
        (
            "2. Técnica y fundamentos",
            "Los elementos esenciales y cómo se entrenan",
            [
                "Técnicas y elementos fundamentales de {t}",
                "Obras y referentes para observar",
                "Ejercicios guiados para ganar soltura",
            ],
        ),
        (
            "3. Práctica personal",
            "Rutina, primer proyecto propio y mejora continua",
            [
                "Rutina de práctica sostenible",
                "Primer proyecto propio de {t}",
                "Cómo evaluar el progreso y seguir aprendiendo",
            ],
        ),
    ],
    ARQUETIPO_GENERAL: [
        (
            "1. Conceptos fundamentales de {t}",
            "Qué es, para qué sirve y con qué vocabulario se trabaja",
            [
                "Qué es {t} y por qué importa",
                "Conceptos y vocabulario clave",
                "Panorama general del área",
            ],
        ),
        (
            "2. Desarrollo y ejemplos",
            "Las ideas principales en profundidad, con ejemplos",
            [
                "Ideas principales de {t} en profundidad",
                "Ejemplos representativos",
                "Relaciones entre los conceptos",
            ],
        ),
        (
            "3. Aplicación y repaso",
            "Práctica, errores frecuentes y síntesis",
            [
                "Aplicación práctica de {t}",
                "Errores comunes y cómo evitarlos",
                "Síntesis y próximos pasos",
            ],
        ),
    ],
}


def esqueleto_de_arquetipo(nombre: str, objetivo: str) -> list[RoadmapModuleCreate]:
    """Arma los módulos y temas base de un arquetipo, con los títulos parametrizados por el objetivo."""
    bloques = _ESQUELETOS.get(nombre, _ESQUELETOS[ARQUETIPO_GENERAL])
    modulos: list[RoadmapModuleCreate] = []
    for m_idx, (titulo, descripcion, temas) in enumerate(bloques, start=1):
        modulos.append(
            RoadmapModuleCreate(
                titulo=titulo.replace("{t}", objetivo)[:200],
                descripcion=descripcion,
                orden=m_idx,
                temas=[
                    RoadmapTopicCreate(titulo=tema.replace("{t}", objetivo)[:200], orden=t_idx)
                    for t_idx, tema in enumerate(temas, start=1)
                ],
            )
        )
    return modulos
