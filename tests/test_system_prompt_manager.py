"""Pruebas unitarias para SystemPromptManager (Persistencia y personalización de prompts)."""

import pytest
from conftest import cuenta_de_prueba
from aulento.roadmap.system_prompt_manager import (
    SystemPromptManager,
    DEFAULT_ROADMAP_SYSTEM_PROMPT,
    DEFAULT_LESSON_SYSTEM_PROMPT,
)


@pytest.fixture
def prompts(memory_db) -> SystemPromptManager:
    return SystemPromptManager(memory_db, cuenta_de_prueba(memory_db).id)


def test_system_prompt_manager_defaults(prompts):
    # Por defecto, devuelve las plantillas base
    r_prompt = prompts.get_roadmap_system_prompt()
    l_prompt = prompts.get_lesson_system_prompt()

    assert r_prompt == DEFAULT_ROADMAP_SYSTEM_PROMPT
    assert l_prompt == DEFAULT_LESSON_SYSTEM_PROMPT
    assert "Taxonomía de Bloom" in r_prompt
    assert "Educador Pedagógico" in l_prompt

    status = prompts.get_all_prompts_status()
    assert status["roadmap"]["is_customized"] is False
    assert status["lesson"]["is_customized"] is False


def test_system_prompt_manager_custom_and_reset(prompts):
    # Personalizar prompt de rutas
    custom_roadmap = "Eres un mentor personalizado con foco en programación cuántica."
    prompts.save_roadmap_system_prompt(custom_roadmap)

    assert prompts.get_roadmap_system_prompt() == custom_roadmap
    status = prompts.get_all_prompts_status()
    assert status["roadmap"]["is_customized"] is True

    # Restablecer a default
    prompts.reset_roadmap_system_prompt()
    assert prompts.get_roadmap_system_prompt() == DEFAULT_ROADMAP_SYSTEM_PROMPT
    assert prompts.get_all_prompts_status()["roadmap"]["is_customized"] is False
