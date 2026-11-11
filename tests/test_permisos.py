"""Enganche `puede(cuenta, accion)` del core (062, R4 y R5): por defecto permite; una regla de una extensión frena
solo la acción nueva, con su motivo, y no toca lo que la cuenta ya tenía."""

import pytest
from fastapi.testclient import TestClient

from aulento.core import permisos
from aulento.core.extensiones import Extension
from aulento.db.connection import get_connection
from aulento.web.app import create_app

CURSO = {"nombre_curso": "Curso", "url_aula": "https://aula.test/curso", "progreso_pct": 0.0}
RUTA = {"titulo": "Ruta", "modulos": [{"titulo": "Módulo", "orden": 1, "temas": [{"titulo": "Tema", "orden": 1}]}]}


def _plataforma(cliente) -> int:
    respuesta = cliente.post("/api/hub/platforms", json={"nombre": "Plataforma", "url_acceso": "https://p.test"})
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["id"]


def _niega(accion_negada: str, motivo: str):
    vistas = []

    def regla(*, user_id, accion, conn, **detalle):
        vistas.append((accion, detalle))
        if accion == accion_negada:
            return permisos.Decision(permitido=False, motivo=motivo)
        return None

    return regla, vistas


def test_r4_sin_reglas_todo_esta_permitido(cuenta):
    conn = get_connection()
    try:
        for accion in permisos.ACCIONES:
            assert permisos.puede(cuenta, accion, conn) == permisos.PERMITIDO
    finally:
        conn.close()
    with pytest.raises(ValueError):
        permisos.puede(cuenta, "accion_inventada", get_connection())


def test_r4_r5_una_regla_que_niega_frena_solo_el_curso_nuevo_con_su_motivo():
    regla, vistas = _niega(permisos.CREAR_CURSO, "Tope de cursos de prueba.")

    with TestClient(create_app()) as libre:
        plataforma = _plataforma(libre)
        assert libre.post("/api/hub/courses", json={**CURSO, "plataforma_id": plataforma}).status_code == 201

    with TestClient(create_app(extensiones=[Extension(nombre="tope", permisos=(regla,))])) as cliente:
        frenado = cliente.post("/api/hub/courses", json={**CURSO, "nombre_curso": "Otro", "plataforma_id": plataforma})
        cursos = cliente.get("/api/hub/courses").json()

    assert frenado.status_code == 403
    assert frenado.json()["detail"] == "Tope de cursos de prueba."
    assert [curso["nombre_curso"] for curso in cursos] == ["Curso"]
    assert vistas == [(permisos.CREAR_CURSO, {})]


def test_r4_la_regla_frena_rutas_y_materiales_con_el_peso_del_archivo():
    regla_de_rutas, _ = _niega(permisos.CREAR_RUTA, "Tope de rutas de prueba.")
    regla_de_materiales, vistas = _niega(permisos.SUBIR_MATERIAL, "Tope de materiales de prueba.")
    extension = Extension(nombre="topes", permisos=(regla_de_rutas, regla_de_materiales))

    with TestClient(create_app(extensiones=[extension])) as cliente:
        ruta = cliente.post("/api/roadmap", json=RUTA)
        material = cliente.post("/api/materiales", files={"archivo": ("apunte.md", b"# Apunte\n", "text/markdown")})
        rutas = cliente.get("/api/roadmap").json()
        materiales = cliente.get("/api/materiales").json()["materiales"]

    assert (ruta.status_code, ruta.json()["detail"]) == (403, "Tope de rutas de prueba.")
    assert (material.status_code, material.json()["detail"]) == (403, "Tope de materiales de prueba.")
    assert rutas == [] and materiales == []
    assert (permisos.SUBIR_MATERIAL, {"bytes": len(b"# Apunte\n")}) in vistas


def test_r4_al_apagar_la_app_sus_reglas_dejan_de_valer(cuenta):
    regla, _ = _niega(permisos.CREAR_CURSO, "No.")

    with TestClient(create_app(extensiones=[Extension(nombre="tope", permisos=(regla,))])):
        conn = get_connection()
        try:
            assert not permisos.puede(cuenta, permisos.CREAR_CURSO, conn).permitido
        finally:
            conn.close()

    conn = get_connection()
    try:
        assert permisos.puede(cuenta, permisos.CREAR_CURSO, conn).permitido
    finally:
        conn.close()


def test_r4_el_core_no_nombra_planes():
    """Las acciones son neutras: qué tope tiene cada una lo decide la extensión."""
    from pathlib import Path

    texto = Path(permisos.__file__).read_text(encoding="utf-8").lower()
    for palabra in ("plan gratis", "gratuito", "premium", "free"):
        assert palabra not in texto
