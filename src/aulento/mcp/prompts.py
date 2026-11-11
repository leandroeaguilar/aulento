"""Plantillas de Prompts de alto nivel expuestas a través del protocolo MCP."""

from typing import Any


def register_mcp_prompts(server: Any) -> None:
    """Registra plantillas de prompts pedagógicos en el servidor MCP."""

    @server.prompt(
        name="crear-clase-magistral",
        title="Crear Clase Magistral con tus Materiales",
        description="Guía al LLM para consultar el master prompt pedagógico de un tema, buscar en los materiales subidos por la cuenta y guardar la lección en Aulento.",
    )
    def prompt_crear_clase_magistral(tema_o_id: str) -> str:
        return (
            f"Actúa como Mentor Pedagógico en Aulento, experto en la disciplina de la ruta a la que pertenece el tema.\n\n"
            f"Objetivo: Desarrollar una clase magistral profunda para el tema o ID: '{tema_o_id}'.\n\n"
            f"Instrucciones de ejecución paso a paso:\n"
            f"1. Si recibes un ID numérico o título, usa la herramienta `study_get_topic_master_prompt` para obtener el Prompt Maestro del tema: rol docente, secciones, tipo de fuentes, enfoque de estudio y nivel objetivo propios de su disciplina.\n"
            f"2. Busca entre los materiales que subió el usuario con `materials_search` el tipo de fuentes que indica ese Prompt Maestro, y lee los pasajes del tema con `materials_read(material_id, query)`.\n"
            f"3. Redacta la clase siguiendo exactamente las directivas del Prompt Maestro (rol, secciones en su orden y formato): no agregues secciones, código ni diagramas que el Prompt Maestro no pida. Cierra con el bloque ```cards-fsrs de tarjetas `Q:` / `A:`.\n"
            f"4. Guarda la clase ejecutando la herramienta `study_create_or_update_lesson(topic_id, markdown_content)`, asegurando que se extraigan las flashcards y se sincronice con el Obsidian Vault. Si el tema ya tiene una clase, la herramienta no la reemplaza: preguntale al usuario y, solo si acepta, repetí la llamada con `overwrite=true`.\n"
        )

    @server.prompt(
        name="repaso-socratico-ingles",
        title="Drill Socrático de Inglés Técnico Profesional",
        description="Inicia una sesión de active recall interactiva de colocaciones de inglés técnico profesional.",
    )
    def prompt_repaso_socratico(enfoque: str = "profesional") -> str:
        return (
            f"Actúa como Coach de Inglés Técnico Profesional en el área de {enfoque}.\n\n"
            f"1. Ejecuta la herramienta `study_get_fsrs_due_cards` para obtener las tarjetas que vencen hoy.\n"
            f"2. Preséntale al usuario una pregunta a la vez en inglés con contexto técnico o profesional.\n"
            f"3. Evalúa la respuesta del usuario con feedback constructivo.\n"
            f"4. Tras la respuesta del usuario, invoca la herramienta `study_review_fsrs_card(card_id, rating)` según su desempeño (1=Again, 2=Hard, 3=Good, 4=Easy).\n"
        )

    @server.prompt(
        name="resumen-semanal-estudio",
        title="Reporte de Estado y Avance de Estudio",
        description="Genera un reporte analítico del progreso actual en cursos, lectura de libros y agenda.",
    )
    def prompt_resumen_semanal() -> str:
        return (
            "Actúa como Asesor Estratégico de Aprendizaje.\n\n"
            "1. Consulta el estado de los cursos con `study_list_courses`.\n"
            "2. Consulta el avance de lectura con `study_list_books` (presta atención a páginas y capítulos leídos).\n"
            "3. Consulta la agenda de hoy con `study_get_today_schedule`.\n"
            "4. Genera un resumen ejecutivo destacando hitos completados, próximos pasos y recomendaciones para la semana.\n"
        )
