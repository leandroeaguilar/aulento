"""Pruebas del modelo de perfil pedagógico, la biblioteca de arquetipos y su resolvedor."""

import pytest
from pydantic import ValidationError

from aulento.models.roadmap import (
    AlcanceRuta,
    PerfilPedagogico,
    RoadmapTopicCreate,
)
from aulento.roadmap.pedagogical_profiles import (
    ARQUETIPOS,
    parsear_perfil,
    perfil_de_ruta,
    perfil_desde_arquetipo,
    perfil_resuelto,
    resolver_arquetipo,
)

ARQUETIPOS_NO_TECNICOS = ["humanidades", "ciencias_sociales_salud", "ciencias_formales", "arte_hobby", "general"]


def _perfil_raw(n_secciones: int = 3) -> dict:
    return {
        "disciplina": "Psicología cognitiva",
        "arquetipo": "ciencias_sociales_salud",
        "rol_docente": "Docente de psicología",
        "secciones": [{"titulo": f"Sección {i}", "instruccion": f"Consigna {i}"} for i in range(1, n_secciones + 1)],
        "usa_codigo": False,
        "usa_diagramas": False,
        "tipo_fuentes": "manuales y papers",
        "flashcards_ejemplo": [{"pregunta": "¿Qué es la memoria de trabajo?", "respuesta": "Un sistema de capacidad limitada."}],
    }


# --- R1: modelo ---

def test_perfil_pedagogico_tiene_los_campos_de_r1():
    perfil = PerfilPedagogico.model_validate(_perfil_raw())
    assert set(perfil.model_dump().keys()) == {
        "disciplina", "arquetipo", "rol_docente", "secciones", "usa_codigo",
        "usa_diagramas", "tipo_fuentes", "flashcards_ejemplo", "origen",
    }
    assert perfil.secciones[0].titulo == "Sección 1"
    assert perfil.secciones[0].instruccion == "Consigna 1"
    assert perfil.flashcards_ejemplo[0].pregunta == "¿Qué es la memoria de trabajo?"


@pytest.mark.parametrize("n", [2, 9])
def test_perfil_pedagogico_exige_entre_3_y_8_secciones(n):
    with pytest.raises(ValidationError):
        PerfilPedagogico.model_validate(_perfil_raw(n))


def test_perfil_pedagogico_rechaza_origen_desconocido():
    raw = _perfil_raw()
    raw["origen"] = "inventado"
    with pytest.raises(ValidationError):
        PerfilPedagogico.model_validate(raw)


def test_alcance_y_prerrequisitos_de_transporte():
    assert [a.value for a in AlcanceRuta] == ["curso", "especializacion", "carrera"]
    assert RoadmapTopicCreate(titulo="Tema").prerrequisitos == []
    assert RoadmapTopicCreate(titulo="Tema", prerrequisitos=["Previo"]).prerrequisitos == ["Previo"]


# --- R2: arquetipos y resolvedor ---

def test_biblioteca_tiene_los_siete_arquetipos_y_general():
    assert set(ARQUETIPOS) == {
        "tech", "idiomas", "negocio", "humanidades",
        "ciencias_sociales_salud", "ciencias_formales", "arte_hobby", "general",
    }
    for nombre, perfil in ARQUETIPOS.items():
        assert perfil.arquetipo == nombre
        assert 3 <= len(perfil.secciones) <= 8
        assert perfil.origen == "arquetipo"


@pytest.mark.parametrize(
    "categoria, titulo, objetivo, esperado",
    [
        ("", "Psicología Cognitiva", "", "ciencias_sociales_salud"),
        ("data_ai", "Introducción a la psicología", "", "ciencias_sociales_salud"),
        ("", "Filosofía estoica", "", "humanidades"),
        ("data_ai", "Ruta", "Quiero estudiar filosofía antigua", "humanidades"),
        ("", "Álgebra Lineal", "", "ciencias_formales"),
        ("data_engineering", "Productores Idempotentes", "", "tech"),
        ("", "EC2", "", "tech"),
        ("", "Large Language Models", "", "tech"),
        ("", "Programming Language Design in Rust", "", "tech"),
        ("", "ingles A2", "", "idiomas"),
        ("english_communication", "Data Engineering", "", "idiomas"),
        ("product_management", "Ruta", "", "negocio"),
        ("humanidades", "Kubernetes", "", "humanidades"),
        ("general", "Filosofía estoica", "", "humanidades"),
        ("", "Scrum para equipos", "", "negocio"),
        ("", "Acuarela para principiantes", "", "arte_hobby"),
        ("", "Apicultura urbana", "", "general"),
        (None, None, None, "general"),
    ],
)
def test_resolver_arquetipo_por_palabras_completas(categoria, titulo, objetivo, esperado):
    assert resolver_arquetipo(categoria, titulo, objetivo) == esperado


@pytest.mark.parametrize("categoria", ["data_ai", "general", "", None])
@pytest.mark.parametrize("titulo", ["Apicultura urbana", "Carpintería", "Astronomía", "Periodismo"])
def test_resolver_devuelve_general_con_las_categorias_por_defecto(categoria, titulo):
    # `data_ai` fue el valor por defecto histórico y `general` es el actual: ninguno dice nada de la
    # disciplina, así que un objetivo sin palabras reconocidas no puede caer en el molde técnico.
    assert resolver_arquetipo(categoria, titulo, titulo) == "general"


@pytest.mark.parametrize(
    "categoria, titulo, esperado",
    [
        # Una palabra de uso general no le gana a una que nombra la disciplina.
        ("", "Health checks en Kubernetes", "tech"),
        ("", "State of the art en LLMs", "tech"),
        ("", "Lógica de programación", "tech"),
        ("", "Git history internals", "tech"),
        ("", "Historia de Roma", "humanidades"),
        # La categoría técnica elegida suma a favor de tech, pero no tapa el nombre de otra disciplina.
        ("data_engineering", "Psicología cognitiva", "ciencias_sociales_salud"),
        ("cloud_devops", "Buenas prácticas del equipo", "tech"),
        # Los códigos CEFR sueltos no identifican un idioma.
        ("", "Vitamina B1 y C2 del complemento", "general"),
        ("", "Francés B1", "idiomas"),
    ],
)
def test_resolver_pondera_palabras_fuertes_debiles_y_categoria(categoria, titulo, esperado):
    assert resolver_arquetipo(categoria, titulo, "") == esperado


def test_perfil_de_idiomas_solo_es_de_ingles_si_la_ruta_es_de_ingles():
    frances = perfil_resuelto("", "Francés B1", "Francés B1")
    assert frances.arquetipo == "idiomas"
    texto = " ".join([frances.rol_docente, frances.tipo_fuentes, *(f"{s.titulo} {s.instruccion}" for s in frances.secciones)])
    for ingles in ["Inglés", "English", "-ed", "Oxford"]:
        assert ingles not in texto

    assert "Inglés" in perfil_resuelto("", "Inglés B2 para reuniones", "").rol_docente
    assert "Inglés" in perfil_resuelto("english_communication", "Comunicación profesional", "").rol_docente


def test_resolver_no_coincide_por_subcadenas():
    # "productores" contiene "product"; "EC2" contiene "c2"; "artesanal" contiene "arte".
    assert resolver_arquetipo("", "Productores", "") == "general"
    assert resolver_arquetipo("", "Instancias EC2", "") != "idiomas"
    assert resolver_arquetipo("", "Pan artesanal", "") == "general"


@pytest.mark.parametrize("nombre", ARQUETIPOS_NO_TECNICOS)
def test_arquetipos_no_tecnicos_sin_codigo_produccion_ni_entrevistas(nombre):
    perfil = ARQUETIPOS[nombre]
    assert perfil.usa_codigo is False
    texto = " ".join(f"{s.titulo} {s.instruccion}" for s in perfil.secciones).lower()
    for prohibida in ["código", "codigo", "producción", "entrevista", "mermaid", "arquitectura"]:
        assert prohibida not in texto, f"{nombre} menciona '{prohibida}'"


def test_arquetipo_general_no_pide_codigo_ni_diagramas():
    general = ARQUETIPOS["general"]
    assert general.usa_codigo is False
    assert general.usa_diagramas is False


def test_perfil_desde_arquetipo_devuelve_copia_con_disciplina():
    perfil = perfil_desde_arquetipo("humanidades", "Filosofía estoica")
    assert perfil.disciplina == "Filosofía estoica"
    assert perfil.arquetipo == "humanidades"
    assert perfil.origen == "arquetipo"

    perfil.secciones.pop()
    assert len(ARQUETIPOS["humanidades"].secciones) == 6
    assert ARQUETIPOS["humanidades"].disciplina == "Humanidades"

    assert perfil_desde_arquetipo("inexistente").arquetipo == "general"


# --- parsear_perfil / perfil_de_ruta ---

def test_parsear_perfil_acepta_perfil_valido():
    perfil = parsear_perfil(_perfil_raw())
    assert perfil is not None
    assert perfil.origen == "ia"
    assert [s.titulo for s in perfil.secciones] == ["Sección 1", "Sección 2", "Sección 3"]


def test_parsear_perfil_rechaza_menos_de_tres_secciones():
    assert parsear_perfil(_perfil_raw(2)) is None


@pytest.mark.parametrize("raw", [None, "texto", [], {}, {"disciplina": "X"}])
def test_parsear_perfil_rechaza_entradas_invalidas(raw):
    assert parsear_perfil(raw) is None


def test_parsear_perfil_rechaza_textos_en_blanco():
    raw = _perfil_raw()
    raw["secciones"][1]["instruccion"] = "   "
    assert parsear_perfil(raw) is None


def test_parsear_perfil_descarta_flashcards_malformadas_y_normaliza_arquetipo():
    raw = _perfil_raw()
    raw["arquetipo"] = "astrologia"
    raw["flashcards_ejemplo"] = [{"pregunta": "¿Sin respuesta?"}, "basura", {"pregunta": "¿P?", "respuesta": "R"}]
    perfil = parsear_perfil(raw)
    assert perfil is not None
    assert perfil.arquetipo == "general"
    assert [(f.pregunta, f.respuesta) for f in perfil.flashcards_ejemplo] == [("¿P?", "R")]


def test_perfil_de_ruta_usa_el_guardado():
    guardado = _perfil_raw()
    guardado["origen"] = "editado"
    perfil = perfil_de_ruta({"perfil_pedagogico": guardado}, "data_ai", "Cloud Architecture")
    assert perfil.disciplina == "Psicología cognitiva"
    assert perfil.origen == "editado"


@pytest.mark.parametrize("metadata", [None, {}, {"perfil_pedagogico": {"secciones": []}}])
def test_perfil_de_ruta_resuelve_al_vuelo_si_no_hay_perfil_valido(metadata):
    perfil = perfil_de_ruta(metadata, "data_ai", "Filosofía estoica")
    assert perfil.arquetipo == "humanidades"
    assert perfil.origen == "arquetipo"
    assert perfil.disciplina == "Filosofía estoica"


# --- Robustez del perfil recibido de la IA ---

def test_parsear_perfil_recorta_en_vez_de_descartar():
    raw = _perfil_raw(9)
    raw["secciones"][0]["instruccion"] = "x" * 5000
    raw["flashcards_ejemplo"].append({"pregunta": "¿Larga?", "respuesta": "y" * 3000})
    raw["disciplina"] = "D" * 400

    perfil = parsear_perfil(raw)
    assert perfil is not None
    assert [s.titulo for s in perfil.secciones] == [f"Sección {i}" for i in range(1, 9)]
    assert len(perfil.secciones[0].instruccion) == 2000
    assert len(perfil.flashcards_ejemplo[1].respuesta) == 1000
    assert len(perfil.disciplina) == 120


@pytest.mark.parametrize(
    "cambio",
    [
        {"rol_docente": "   "},
        {"tipo_fuentes": None},
        {"secciones": [{"titulo": "Solo", "instruccion": "una"}, {"titulo": " ", "instruccion": "vacía"}, "x"]},
    ],
)
def test_parsear_perfil_rechaza_lo_irrecuperable(cambio):
    assert parsear_perfil({**_perfil_raw(), **cambio}) is None


def test_perfil_pedagogico_no_acepta_textos_en_blanco():
    raw = _perfil_raw()
    raw["secciones"][0]["titulo"] = "   "
    with pytest.raises(ValidationError):
        PerfilPedagogico.model_validate(raw)
