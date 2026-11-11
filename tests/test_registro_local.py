"""El modo local deja lo que avisa en `<data_dir>/aulento.log`, y el diagnóstico lo lee (051, R9)."""

import logging
from logging.handlers import RotatingFileHandler

from conftest import administrador_de_prueba
from fastapi.testclient import TestClient
from identidad_de_prueba import extension_de_identidad, modo_saas

from aulento.config import get_data_dir
from aulento.core.diagnostics import leer_ultimas_lineas_log
from aulento.core.registro import NOMBRE_DEL_ARCHIVO, RESPALDOS, TAMANO_MAXIMO
from aulento.web.app import create_app


def _manejadores_de_archivo() -> list[logging.Handler]:
    return [m for m in logging.getLogger("aulento").handlers if isinstance(m, logging.FileHandler)]


def test_r9_en_local_lo_que_se_avisa_queda_en_el_registro_y_el_diagnostico_lo_lee():
    antes = len(_manejadores_de_archivo())

    with TestClient(create_app()):
        logging.getLogger("aulento.prueba").warning("Aviso de prueba R9 con la clave AIzaSyA0123456789abcdefghijklmn")
        # Rotativo: no crece sin límite
        abiertos = _manejadores_de_archivo()[antes:]
        assert [type(m) for m in abiertos] == [RotatingFileHandler]
        assert abiertos[0].maxBytes == TAMANO_MAXIMO and abiertos[0].backupCount == RESPALDOS

    lineas = leer_ultimas_lineas_log()
    assert (get_data_dir() / NOMBRE_DEL_ARCHIVO).is_file()
    assert any("Aviso de prueba R9" in linea and "WARNING" in linea for linea in lineas)
    # El diagnóstico anonimiza lo que muestra
    assert not any("AIzaSyA0123456789" in linea for linea in lineas)
    # Al apagar se cierra: no queda el archivo abierto ni el manejador sumado
    assert len(_manejadores_de_archivo()) == antes


def test_r9_en_saas_no_se_escribe_el_registro_local(monkeypatch):
    modo_saas(monkeypatch)

    with TestClient(create_app(extensiones=[extension_de_identidad(administrador_de_prueba)])):
        logging.getLogger("aulento.prueba").warning("Aviso en saas")

    assert not (get_data_dir() / NOMBRE_DEL_ARCHIVO).exists()


def test_r9_si_el_registro_no_se_puede_abrir_el_servidor_arranca_igual(monkeypatch, caplog):
    from aulento.web import app as modulo_de_la_app

    def sin_permiso():
        raise PermissionError("el archivo está tomado por otro proceso")

    monkeypatch.setattr(modulo_de_la_app, "abrir_registro_local", sin_permiso)

    with caplog.at_level("WARNING"), TestClient(create_app()) as cliente:
        assert cliente.get("/api/health").status_code == 200

    assert "No se pudo abrir el archivo de registro local" in caplog.text
