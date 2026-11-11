"""Constructor del Prompt Maestro para Clases, armado en tres capas.

1. Núcleo fijo: lo que el parser y la técnica de estudio necesitan, igual para toda materia.
2. Perfil pedagógico de la ruta: rol docente, secciones, fuentes y flashcards propias de la disciplina.
3. Contexto del tema: módulo, nivel, enfoque de estudio, descripción y temas vecinos.
"""

from typing import Any

from aulento.db.cuenta import exigir_repositorio_de_cuenta
from aulento.db.roadmap_repository import RoadmapRepository
from aulento.models.roadmap import (
    LessonPromptRequest,
    LessonPromptResponse,
    PerfilPedagogico,
)
from aulento.roadmap.pedagogical_profiles import perfil_de_ruta, una_linea

DESCRIPCION_ENFOQUE: dict[str, str] = {
    "profesional": "profesional — prioriza competencias aplicables al trabajo, buenas prácticas del área y criterios de decisión.",
    "academico": "académico — prioriza fundamentos teóricos rigurosos, autores y fuentes de referencia, y precisión conceptual.",
    "practico_proyectos": "práctico por proyectos — cada idea debe terminar en algo que el estudiante hace o construye.",
    "personal_hobby": "personal / curiosidad — tono accesible y disfrutable, sin presión laboral ni de examen.",
    "certificacion": "certificación — alinea el contenido con los objetivos y el tipo de preguntas del examen oficial.",
}

INDICACION_EXTENSION: dict[str, str] = {
    "breve": "Extensión breve: entre 600 y 900 palabras. Ve a lo esencial, con un solo ejemplo por idea y sin digresiones.",
    "estandar": "Extensión estándar: entre 1500 y 2500 palabras, desarrollando por completo cada sección.",
    "exhaustiva": ("Extensión exhaustiva: 3500 palabras o más, con varios ejemplos por idea, "
    "casos límite, matices y contraejemplos."),
}


class LessonPromptBuilder:
    """Genera Prompts Maestros adaptados a la disciplina de la ruta para NotebookLM, Claude, ChatGPT o Gemini."""

    def __init__(self, repo: RoadmapRepository) -> None:
        exigir_repositorio_de_cuenta(repo)
        self.repo = repo

    @staticmethod
    def _directivas_de_fuentes(perfil: PerfilPedagogico, options: LessonPromptRequest) -> list[str]:
        tipo_fuentes = una_linea(perfil.tipo_fuentes).rstrip(".")

        if options.sin_herramientas:
            return [
                ("🚫 **Sin herramientas externas:** no tienes buscador ni acceso a archivos en esta sesión. "
                "Trabaja con tu conocimiento y no inventes citas, páginas, estudios ni referencias: "
                "si no estás seguro de un dato o de una fuente, dilo explícitamente.")
            ]

        directivas: list[str] = []
        if options.include_materials:
            directivas.append(
                "📂 **Tus materiales en Aulento (MCP / Archivos):** "
                "Si tienes las herramientas MCP de Aulento, busca entre los materiales del estudiante con "
                "`materials_search` y lee los pasajes del tema con `materials_read`; si este chat tiene acceso a "
                f"carpetas de libros y apuntes, úsalas también. Busca {tipo_fuentes} sobre este tema y cita sus aportes clave."
            )
        if options.include_web_research:
            directivas.append(
                "🌐 **Investigación Web & Fuentes de Referencia:** "
                f"Contrasta el contenido con fuentes actuales y confiables de la disciplina ({tipo_fuentes}) "
                "para evitar información desactualizada."
            )
        if options.target_llm == "notebooklm":
            directivas.append(
                "📓 **Directiva para NotebookLM:** "
                "Sintetiza la clase apoyándote de manera prioritaria en los libros y fuentes PDF subidas a este cuaderno, "
                "extrayendo citas y conceptos de fondo sin perder rigor práctico."
            )
        return directivas

    @staticmethod
    def _nucleo_fijo(
        topic_title: str,
        perfil: PerfilPedagogico,
        options: LessonPromptRequest,
        ctx: dict[str, Any],
    ) -> str:
        reglas = [
            f"Empieza con el encabezado exacto `# {topic_title}`.",
            INDICACION_EXTENSION[options.depth],
            ("Explica cada idea con la Técnica Feynman: lenguaje llano, como a alguien inteligente sin contexto previo, "
            "y con una analogía cotidiana que fije el concepto."),
            "Usa callouts de Obsidian: `> [!tip]` para buenas prácticas e ideas clave y `> [!warning]` para errores comunes y confusiones típicas.",
        ]
        if perfil.usa_diagramas:
            reglas.append(
                "Incluye al menos un diagrama Mermaid (````mermaid graph TD ... ```` o ````sequenceDiagram````) "
                "que ilustre el flujo, la estructura o las relaciones centrales del tema."
            )
        if perfil.usa_codigo:
            reglas.append("Incluye código ejecutable comentado donde ayude a entender o practicar el tema.")
        if options.include_visuals:
            reglas.append(
                "Incluye entre 2 y 4 figuras como bloques ```svg autocontenidos: cada uno con atributo `viewBox`, "
                "texto legible, sin `<script>` y sin recursos externos (imágenes, fuentes u hojas de estilo enlazadas). Da color y trazo con atributos en cada elemento (`fill`, `stroke`, `font-size`): no uses `<style>` ni clases CSS, y usa colores que se lean sobre fondo claro. "
                "Ubica cada figura junto al concepto que ilustra y escribe justo debajo un pie de figura en cursiva "
                "(`*Figura 1. Qué muestra.*`)."
            )
        if options.include_bridge:
            anterior = ctx.get("prev_topic_title")
            siguiente = ctx.get("next_topic_title")
            if anterior:
                reglas.append(
                    f"Abre la clase con un repaso breve (3 a 5 líneas) de lo necesario del tema anterior, «{anterior}», "
                    "antes de introducir contenido nuevo."
                )
            if siguiente:
                reglas.append(
                    f"Cierra la clase con un párrafo «Qué sigue» que conecte lo aprendido con el tema siguiente, «{siguiente}», "
                    "sin desarrollarlo."
                )
        return "## Formato y Reglas Fijas (Markdown para Obsidian):\n" + "\n".join(f"- {r}" for r in reglas)

    @staticmethod
    def _secciones_opcionales(options: LessonPromptRequest) -> list[tuple[str, str]]:
        """Secciones que se numeran tras las del perfil; las tarjetas FSRS van siempre después."""
        secciones: list[tuple[str, str]] = []
        if options.include_glossary:
            cuerpo = (
                "- **Glosario:** define entre 6 y 10 términos clave del tema, uno por línea.\n"
                "- **Lecturas recomendadas:** lista entre 3 y 5 lecturas para profundizar, con autor y título.\n"
                "- No inventes títulos, autores ni enlaces: si no estás seguro de que una obra existe, omítela."
            )
            secciones.append(("Glosario y lecturas recomendadas", cuerpo))
        if options.include_quiz:
            cuerpo = (
                "- Escribe 5 preguntas de opción múltiple numeradas del `1.` al `5.`, cada una con cuatro opciones "
                "`a)`, `b)`, `c)` y `d)` en líneas separadas.\n"
                "- Cierra con un subtítulo `#### Soluciones` que indique la opción correcta de cada pregunta "
                "y explique en una o dos frases por qué lo es.\n"
                "- En esta sección no uses los prefijos `Q:`, `A:`, `Pregunta:`, `Respuesta:`, `P:` ni `R:`: "
                "están reservados para las flashcards."
            )
            secciones.append(("Autoevaluación", cuerpo))
        if options.include_slides:
            ubicacion = (
                "Ubícalo justo antes del bloque de flashcards."
                if options.include_fsrs_cards
                else "Ubícalo al final de la clase."
            )
            cuerpo = (
                "Resume la clase en un bloque delimitado exacto de 6 a 10 diapositivas separadas por una línea `---`. "
                "Cada diapositiva lleva un título `#` y de 3 a 5 viñetas; no anides bloques de código dentro. "
                f"{ubicacion} Sigue este formato:\n"
                "```slides\n"
                "# Título de la primera diapositiva\n"
                "- Idea clave\n"
                "- Idea clave\n"
                "- Idea clave\n"
                "---\n"
                "# Título de la segunda diapositiva\n"
                "- Idea clave\n"
                "- Idea clave\n"
                "- Idea clave\n"
                "```"
            )
            secciones.append(("Diapositivas de repaso", cuerpo))
        return secciones

    @classmethod
    def _estructura(cls, perfil: PerfilPedagogico, options: LessonPromptRequest) -> str:
        secciones = [(una_linea(s.titulo), s.instruccion.strip()) for s in perfil.secciones]
        secciones.extend(cls._secciones_opcionales(options))

        if options.include_fsrs_cards:
            ejemplos = [
                (una_linea(f.pregunta), una_linea(f.respuesta)) for f in perfil.flashcards_ejemplo
            ] or [
                ("¿Pregunta concreta que obligue a recordar una idea central del tema?", "Respuesta breve, precisa y autocontenida."),
            ]
            tarjetas = "\n\n".join(f"Q: {q}\nA: {a}" for q, a in ejemplos)
            cuerpo = (
                "Genera entre 4 y 8 tarjetas de memorización activa de alto impacto en un bloque delimitado exacto, "
                "con pares `Q:` / `A:` como en este ejemplo:\n"
                f"```cards-fsrs\n{tarjetas}\n```"
            )
            secciones.append(("Tarjetas de Active Recall para FSRS v5 (OBLIGATORIO AL FINAL)", cuerpo))

        bloques = [f"### {idx}. {titulo}\n{cuerpo}" for idx, (titulo, cuerpo) in enumerate(secciones, start=1)]
        return "## Estructura Requerida de la Clase:\n\n" + "\n\n".join(bloques)

    def build_prompt(self, topic_id: int, options: LessonPromptRequest) -> LessonPromptResponse:
        """Construye el prompt maestro: núcleo fijo + perfil pedagógico de la ruta + contexto del tema."""
        ctx = self.repo.get_topic_with_context(topic_id)
        if not ctx:
            raise ValueError(f"Tema con ID {topic_id} no encontrado en la base de datos.")

        topic_title = ctx["topic_title"]
        topic_desc = ctx.get("topic_desc") or ""
        module_title = ctx["module_title"]
        roadmap_title = ctx["roadmap_title"]
        target_role = ctx.get("nivel_objetivo") or "Senior"
        enfoque = ctx.get("enfoque_estudio") or "profesional"

        perfil = perfil_de_ruta(ctx.get("metadata_json"), ctx.get("categoria"), roadmap_title)

        contexto = [
            f"🎯 **Tema:** {topic_title}",
            f"📂 **Módulo:** {module_title}",
            f"🗺️ **Ruta de Aprendizaje:** {roadmap_title} (Disciplina: {una_linea(perfil.disciplina)} · Nivel objetivo: {target_role})",
            f"🧭 **Enfoque de estudio:** {DESCRIPCION_ENFOQUE.get(enfoque, enfoque)}",
        ]
        if topic_desc:
            contexto.append(f"📝 **Detalle del tema:** {topic_desc}")
        if ctx.get("prev_topic_title"):
            contexto.append(f"⬅️ **Tema anterior en la ruta:** {ctx['prev_topic_title']} (dalo por visto; no lo vuelvas a desarrollar)")
        if ctx.get("next_topic_title"):
            contexto.append(f"➡️ **Tema siguiente en la ruta:** {ctx['next_topic_title']} (no lo desarrolles)")

        directivas = self._directivas_de_fuentes(perfil, options)
        fuentes = "### Fuentes de Información:\n" + "\n".join(f"- {d}" for d in directivas) if directivas else ""

        partes = [
            (f"**Rol y tono docente:** Actúa como {una_linea(perfil.rol_docente).rstrip('.')}.\n"
            "Necesito que elabores una clase completa y estructurada sobre el siguiente tema:"),
            "\n".join(contexto),
            fuentes,
            self._nucleo_fijo(topic_title, perfil, options, ctx),
            self._estructura(perfil, options),
            "Genera todo el contenido en Markdown limpio, listo para ser importado al Vault de Obsidian"
            + (" y al motor FSRS." if options.include_fsrs_cards else "."),
        ]
        master_prompt = "\n\n".join(p for p in partes if p)

        instructions = (
            "1. Copia este prompt maestro con el botón de abajo.\n"
            f"2. Pégalo en tu entorno de estudio preferido ({options.target_llm.capitalize()}, Claude con MCP, o ChatGPT).\n"
            "3. Una vez generada la clase, copia el texto Markdown completo y regresa aquí para hacer clic en '[📥 Importar Clase]'."
        )

        return LessonPromptResponse(
            topic_id=topic_id,
            topic_title=topic_title,
            roadmap_title=roadmap_title,
            master_prompt=master_prompt,
            instructions=instructions,
        )
