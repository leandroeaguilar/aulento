"""Tests para SyllabusIngestor (parsing de texto/markdown, PDF y Gap Analysis con IA)."""

import json
import zlib
from unittest.mock import patch, MagicMock
import pytest

from conftest import cuenta_en
from aulento.db.roadmap_repository import RoadmapRepository
from ia_falsa import ia_sustituida, respuesta_de
from aulento.models.roadmap import EnfoqueEstudio
from aulento.roadmap.syllabus_ingestor import SyllabusIngestor


def test_parse_markdown_syllabus():
    md_content = """
    # Módulo 1: Fundamentos de Redes Neuronales (12h)
    - Perceptrón Simple y Funciones de Activación (2h)
    - Descenso de Gradiente y Backpropagation (90 min)
    - Regularización Dropout y Batch Normalization (45 min)

    ## Módulo 2: Visión por Computadora
    * Redes Convolucionales (CNN) y Pooling (3h)
    * Transfer Learning con ResNet (2h)
    """

    modules = SyllabusIngestor.parse_text_to_modules(md_content)
    assert len(modules) == 2
    assert "Módulo 1" in modules[0].titulo
    assert len(modules[0].temas) == 3
    # Check estimated duration in description
    assert "2 h" in modules[0].temas[0].descripcion
    assert "Perceptrón Simple" in modules[0].temas[0].titulo
    assert "(" not in modules[0].temas[0].titulo  # duration stripped from title

    assert "Módulo 2" in modules[1].titulo
    assert len(modules[1].temas) == 2
    assert "3 h" in modules[1].temas[0].descripcion


def test_parse_raw_text_without_explicit_modules():
    raw_text = """
    1. Introducción a Python Moderno
    2. Tipado Estático con Pydantic
    3. Concurrencia con Asyncio y Anyio
    """
    modules = SyllabusIngestor.parse_text_to_modules(raw_text)
    assert len(modules) == 1
    assert "Módulo 1" in modules[0].titulo
    assert len(modules[0].temas) == 3
    assert "Introducción a Python Moderno" in modules[0].temas[0].titulo


def test_extract_text_from_pdf_bytes():
    # Construir un PDF sintetizado válido con stream comprimido FlateDecode
    stream_content = b"BT /F1 12 Tf (Introduccion a Kubernetes) Tj ET"
    compressed_stream = zlib.compress(stream_content)

    pdf_bytes = (
        b"%PDF-1.4\n"
        b"1 0 obj\n"
        b"<< /Length " + str(len(compressed_stream)).encode() + b" /Filter /FlateDecode >>\n"
        b"stream\r\n" + compressed_stream + b"\r\nendstream\n"
        b"endobj\n"
        b"%%EOF"
    )

    extracted = SyllabusIngestor.extract_text_from_pdf_bytes(pdf_bytes)
    assert "Introduccion a Kubernetes" in extracted


def test_enhance_with_ai_fallback():
    modules = SyllabusIngestor.parse_text_to_modules("- Tema 1\n- Tema 2")
    with ia_sustituida(sin_clave=True):
        enhanced, notes = SyllabusIngestor.enhance_with_ai(
            repo=RoadmapRepository(cuenta_en()),
            modules=modules,
            title="Curso Test",
            target_role="Tester",
            enfoque_estudio=EnfoqueEstudio.PRACTICO_PROYECTOS,
        )
        assert len(enhanced) == len(modules)
        assert any("preservó" in n.lower() or "local" in n.lower() for n in notes)


def test_enhance_with_ai_success():
    modules = SyllabusIngestor.parse_text_to_modules("# Modulo 1\n- Variables")
    mock_ai_json = {
        "enhancements": [
            "Se insertó tema de andamiaje: Estructuras de Control",
            "Se agregó proyecto práctico integrador",
        ],
        "modulos": [
            {
                "title": "Módulo 1: Fundamentos Robustos",
                "description": "Bases de programación",
                "estimated_hours": 8,
                "topics": [
                    {"title": "Variables y Tipos", "description": "Tipado", "estimated_minutes": 45},
                    {"title": "Estructuras de Control", "description": "Bucles y condicionales", "estimated_minutes": 60},
                ],
            }
        ],
    }

    mock_res = respuesta_de(mock_ai_json)

    with ia_sustituida(siempre=mock_res):
        enhanced, notes = SyllabusIngestor.enhance_with_ai(
            repo=RoadmapRepository(cuenta_en()),
            modules=modules,
            title="Python desde Cero",
            target_role="Python Developer",
            enfoque_estudio=EnfoqueEstudio.PROFESIONAL,
        )
        assert len(enhanced) == 1
        assert len(enhanced[0].temas) == 2
        assert enhanced[0].temas[1].titulo == "Estructuras de Control"
        assert len(notes) == 2
        assert "Estructuras de Control" in notes[0]
