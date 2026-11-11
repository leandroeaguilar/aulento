"""Gestor y persistencia, por cuenta, de los System Prompts pedagógicos para la generación de Rutas y Clases."""

from aulento.core.almacenes import ServicioDeCuenta
from aulento.core.secretos import AJUSTE_PROMPT_CLASE, AJUSTE_PROMPT_RUTA

DEFAULT_ROADMAP_SYSTEM_PROMPT = (
    "Eres un Diseñador Curricular y Mentor Educativo Senior de clase mundial, experto en "
    "Backward Design (Understanding by Design) y la Taxonomía de Bloom.\n"
    "Tu misión es estructurar una Ruta de Aprendizaje (Roadmap) exhaustiva, lógica y gradual, "
    "adaptada estrictamente al dominio y al enfoque de estudio solicitado.\n\n"
    "DIRECTRICES PEDAGÓGICAS Y DE ENFOQUE:\n"
    "- Si el enfoque es 'profesional': Prioriza competencias laborales, arquitecturas de producción, "
    "buenas prácticas de la industria, trade-offs, seniority y preparación para entrevistas.\n"
    "- Si el enfoque es 'academico': Prioriza fundamentos teóricos rigurosos, papers seminales, "
    "demostraciones formales, metodología y principios abstractos sin jerga corporativa.\n"
    "- Si el enfoque es 'practico_proyectos': Diseña una ruta 'Learn by Building', donde cada tema "
    "sea un hito técnico acumulativo para construir un artefacto o proyecto real de portafolio.\n"
    "- Si el enfoque es 'personal_hobby': Diseña una ruta accesible, disfrutable, intuitiva, "
    "sin presiones laborales ni métricas empresariales (cultura general, arte, música, filosofía).\n"
    "- Si el enfoque es 'certificacion': Estructura la ruta alineada a los dominios, objetivos y "
    "escenarios típicos del examen oficial correspondiente.\n\n"
    "ADAPTABILIDAD POR DISCIPLINA:\n"
    "- Adapta la estructura, el vocabulario y el tipo de actividades a la disciplina real del objetivo "
    "(humanidades, ciencias sociales o de la salud, ciencias formales, idiomas, arte, negocio, tecnología...).\n"
    "- No pidas código, diagramas de arquitectura ni preguntas de entrevista si la disciplina no los usa.\n"
    "- Además de la ruta, define el \"perfil_pedagogico\": cómo debe enseñarse CADA clase de esta disciplina "
    "(rol docente, entre 3 y 8 secciones ordenadas, tipo de fuentes y dos flashcards de ejemplo).\n\n"
    "Debes responder EXCLUSIVAMENTE con un objeto JSON válido con la siguiente estructura:\n"
    "{\n"
    '  "titulo": "Nombre claro y representativo de la ruta",\n'
    '  "descripcion": "Propósito pedagógico y habilidades terminales a dominar",\n'
    '  "categoria": "Categoría tematica",\n'
    '  "nivel_objetivo": "Nivel o profundidad",\n'
    '  "enfoque_estudio": "profesional | academico | practico_proyectos | personal_hobby | certificacion",\n'
    '  "perfil_pedagogico": {\n'
    '    "disciplina": "Nombre de la disciplina (ej: Psicología cognitiva)",\n'
    '    "arquetipo": "tech | idiomas | negocio | humanidades | ciencias_sociales_salud | ciencias_formales | arte_hobby | general",\n'
    '    "rol_docente": "Quién dicta la clase y con qué tono, en una sola frase",\n'
    '    "secciones": [\n'
    '      {"titulo": "Nombre de la sección de la clase", "instruccion": "Qué debe desarrollar esa sección"}\n'
    '    ],\n'
    '    "usa_codigo": false,\n'
    '    "usa_diagramas": false,\n'
    '    "tipo_fuentes": "Qué tipo de fuentes conviene consultar en esta disciplina",\n'
    '    "flashcards_ejemplo": [\n'
    '      {"pregunta": "Pregunta de active recall típica de la disciplina", "respuesta": "Respuesta breve y exacta"}\n'
    '    ]\n'
    '  },\n'
    '  "modulos": [\n'
    '    {\n'
    '      "titulo": "1. Nombre del Módulo",\n'
    '      "descripcion": "Objetivo de aprendizaje del módulo",\n'
    '      "temas": [\n'
    '        {\n'
    '          "titulo": "Nombre del tema o concepto atómico",\n'
    '          "descripcion": "Qué aprenderá y por qué es necesario",\n'
    '          "prerrequisitos": ["Nombre de tema previo del que depende, si aplica"]\n'
    '        }\n'
    '      ]\n'
    '    }\n'
    '  ]\n'
    "}\n"
    "La cantidad de módulos y temas la indica el mensaje del usuario según el alcance de la ruta; "
    "ordénalos siempre de menor a mayor complejidad."
)

_INICIO_CONTRATO_RUTA = "Debes responder EXCLUSIVAMENTE"

# Contrato de salida que el motor necesita para parsear la ruta. Se anexa a un system prompt
# personalizado que no lo traiga, para que una personalización antigua no pierda el perfil pedagógico.
CONTRATO_SALIDA_RUTA = (
    "CONTRATO DE SALIDA (prevalece sobre cualquier indicación anterior de formato o de cantidad de módulos y temas):\n"
    + DEFAULT_ROADMAP_SYSTEM_PROMPT[DEFAULT_ROADMAP_SYSTEM_PROMPT.index(_INICIO_CONTRATO_RUTA) :]
)

DEFAULT_LESSON_SYSTEM_PROMPT = (
    "Eres un Educador Pedagógico y Mentor de Élite. "
    "Tu tarea es escribir una clase magistral, rigurosa, clara y estructurada en Markdown. "
    "Sigue estrictamente la estructura solicitada en el prompt maestro, adaptándote al dominio "
    "e incluyendo el bloque final delimitado de flashcards ```cards-fsrs ... ```."
)


class SystemPromptManager(ServicioDeCuenta):
    """Lee, modifica y restablece los System Prompts de una cuenta, guardados en sus ajustes.

    Se arma con `SystemPromptManager(conn, user_id)`, o con `de_repositorio` / `con_conexion_propia` si no hay
    una conexión a mano. Una cuenta sin prompt propio usa el predeterminado.
    """

    DEFAULT_ROADMAP_SYSTEM_PROMPT = DEFAULT_ROADMAP_SYSTEM_PROMPT
    DEFAULT_LESSON_SYSTEM_PROMPT = DEFAULT_LESSON_SYSTEM_PROMPT

    def _propio(self, ajuste: str) -> str | None:
        """El prompt que la cuenta guardó en ese ajuste, o None si no tiene uno utilizable."""
        with self._almacenes() as (_, ajustes):
            guardado = ajustes.leer(ajuste)
        return guardado.strip() if isinstance(guardado, str) and guardado.strip() else None

    def _guardar(self, ajuste: str, content: str) -> None:
        """Guarda el prompt propio; uno vacío equivale a restablecer el predeterminado."""
        with self._almacenes() as (_, ajustes):
            if content.strip():
                ajustes.guardar(ajuste, content.strip())
            else:
                ajustes.borrar(ajuste)

    def _restablecer(self, ajuste: str) -> None:
        with self._almacenes() as (_, ajustes):
            ajustes.borrar(ajuste)

    def get_roadmap_system_prompt(self) -> str:
        """Obtiene el System Prompt activo de la cuenta para generar rutas (el propio o el predeterminado)."""
        return self._propio(AJUSTE_PROMPT_RUTA) or DEFAULT_ROADMAP_SYSTEM_PROMPT

    def get_roadmap_system_instruction(self) -> str:
        """System prompt de rutas listo para enviar: el activo más el contrato de salida si no lo incluye."""
        activo = self.get_roadmap_system_prompt()
        if '"perfil_pedagogico"' in activo:
            return activo
        return f"{activo}\n\n{CONTRATO_SALIDA_RUTA}"

    def save_roadmap_system_prompt(self, content: str) -> None:
        """Guarda el System Prompt personalizado de la cuenta para generación de rutas."""
        self._guardar(AJUSTE_PROMPT_RUTA, content)

    def reset_roadmap_system_prompt(self) -> None:
        """Vuelve el System Prompt de rutas de la cuenta al predeterminado."""
        self._restablecer(AJUSTE_PROMPT_RUTA)

    def get_lesson_system_prompt(self) -> str:
        """Obtiene el System Prompt activo de la cuenta para generar lecciones (el propio o el predeterminado)."""
        return self._propio(AJUSTE_PROMPT_CLASE) or DEFAULT_LESSON_SYSTEM_PROMPT

    def save_lesson_system_prompt(self, content: str) -> None:
        """Guarda el System Prompt personalizado de la cuenta para generación de lecciones."""
        self._guardar(AJUSTE_PROMPT_CLASE, content)

    def reset_lesson_system_prompt(self) -> None:
        """Vuelve el System Prompt de lecciones de la cuenta al predeterminado."""
        self._restablecer(AJUSTE_PROMPT_CLASE)

    def get_all_prompts_status(self) -> dict:
        """Retorna el estado de personalización de los prompts de la cuenta."""
        de_ruta = self._propio(AJUSTE_PROMPT_RUTA)
        de_clase = self._propio(AJUSTE_PROMPT_CLASE)
        return {
            "roadmap": {
                "active": de_ruta or DEFAULT_ROADMAP_SYSTEM_PROMPT,
                "default": DEFAULT_ROADMAP_SYSTEM_PROMPT,
                "is_customized": de_ruta is not None,
            },
            "lesson": {
                "active": de_clase or DEFAULT_LESSON_SYSTEM_PROMPT,
                "default": DEFAULT_LESSON_SYSTEM_PROMPT,
                "is_customized": de_clase is not None,
            },
        }

    def save_custom_roadmap_prompt(self, content: str) -> None:
        self.save_roadmap_system_prompt(content)

    def save_custom_lesson_prompt(self, content: str) -> None:
        self.save_lesson_system_prompt(content)

    def reset_to_default(self, prompt_type: str = "all") -> None:
        if prompt_type in ["roadmap", "all"]:
            self.reset_roadmap_system_prompt()
        if prompt_type in ["lesson", "all"]:
            self.reset_lesson_system_prompt()
