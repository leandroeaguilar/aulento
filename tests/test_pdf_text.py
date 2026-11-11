"""Extracción del texto de los PDF que sube cada cuenta (`mcp/pdf_text.py`) y las dependencias que la sostienen."""

import io
import json
import tomllib
from pathlib import Path

import pytest
from materiales_de_prueba import pdf_con_lineas, pdf_de_varias_paginas
from pypdf import PageObject, PdfReader, PdfWriter
from pypdf.errors import DependencyError

from aulento.mcp import pdf_text
from aulento.mcp.pdf_text import PdfSinTextoError, extraer_texto_pdf

RAIZ = Path(__file__).resolve().parents[1]


def _cifrado(texto: str) -> bytes:
    escritor = PdfWriter()
    escritor.append(PdfReader(io.BytesIO(pdf_con_lineas([texto]))))
    escritor.encrypt("clave-de-prueba")
    salida = io.BytesIO()
    escritor.write(salida)
    return salida.getvalue()


def test_pypdf_es_dependencia_base_y_no_queda_el_extra_de_drive():
    """pypdf está fijada y en las dependencias base; sin Drive ni OneDrive no queda el extra `cloud` (048, R12)."""
    assert "pypdf==" in (RAIZ / "requirements.txt").read_text(encoding="utf-8")
    proyecto = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    assert any(dep.startswith("pypdf") for dep in proyecto["project"]["dependencies"])
    extras = proyecto["project"].get("optional-dependencies", {})
    assert "cloud" not in extras
    todas = [dep for deps in [proyecto["project"]["dependencies"], *extras.values()] for dep in deps]
    for paquete in ("google-api-python-client", "google-auth-oauthlib"):
        assert not any(dep.startswith(paquete) for dep in todas), paquete


def test_pdf_protegido_avisa():
    """Un PDF con contraseña no se puede leer y lo dice."""
    with pytest.raises(PdfSinTextoError, match="protegido con contraseña"):
        extraer_texto_pdf(_cifrado("Contenido reservado"), 1000)


def test_pdf_deja_de_leer_paginas_al_alcanzar_el_maximo(monkeypatch):
    """Alcanzado el máximo de caracteres no se extraen las páginas siguientes."""
    datos = pdf_de_varias_paginas(["Primera pagina con texto"], ["Segunda pagina"], ["Tercera pagina"], ["Cuarta pagina"])
    llamadas = []
    original = PageObject.extract_text

    def contando(self, *args, **kwargs):
        llamadas.append(1)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(PageObject, "extract_text", contando)

    assert extraer_texto_pdf(datos, 10) == "Primera pa"
    assert len(llamadas) == 1

    llamadas.clear()
    completo = extraer_texto_pdf(datos, 5000)
    assert len(llamadas) == 4
    assert "Cuarta pagina" in completo
    assert completo.count("\n\n") == 3


def test_pdf_texto_sale_limpio_de_controles_y_sustitutos(monkeypatch):
    """Un PDF puede traer NUL, controles o sustitutos Unicode sueltos: no deben llegar al vault, a la API ni a la base."""
    sucio = "ab\x00cd\x01\x7f" + chr(0xD800) + " fin\r\notra\tlinea"
    monkeypatch.setattr(PageObject, "extract_text", lambda self, *a, **k: sucio)

    texto = extraer_texto_pdf(pdf_con_lineas(["x"]), 1000)
    assert texto == "abcd fin\notra\tlinea"
    texto.encode("utf-8")
    json.dumps(texto)


def test_pdf_saltea_paginas_con_contenido_enorme(monkeypatch):
    """Una página con un contenido de varios MB tardaría minutos en procesarse: se saltea."""
    datos = pdf_de_varias_paginas(
        ["Pagina normal uno"], ["Pagina con un contenido largo " * 20], ["Pagina normal tres"]
    )
    monkeypatch.setattr(pdf_text, "MAX_BYTES_CONTENIDO_PAGINA", 200)

    texto = pdf_text.extraer_texto_pdf(datos, 5000)
    assert "Pagina normal uno" in texto
    assert "Pagina normal tres" in texto
    assert "contenido largo" not in texto


def test_pdf_cifrado_sin_cryptography_lo_dice(monkeypatch):
    """Sin la librería de cifrado, un PDF con AES no se informa como dañado."""

    def sin_cryptography(self, *args, **kwargs):
        raise DependencyError("cryptography>=3.1 is required for AES algorithm")

    datos = _cifrado("Contenido cifrado")
    monkeypatch.setattr(PdfReader, "decrypt", sin_cryptography)

    with pytest.raises(PdfSinTextoError, match="falta instalar la librería cryptography"):
        extraer_texto_pdf(datos, 1000)
