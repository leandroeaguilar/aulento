"""Archivos de prueba para los materiales subidos (048): PDFs armados a mano, sin depender de nada externo."""

import io

LINEA_DE_RELLENO = "Texto de relleno para que el material sea largo y el pasaje buscado quede lejos del principio."


def texto_largo(caracteres: int, al_final: str = "") -> str:
    """Texto de al menos `caracteres` caracteres, en líneas, con `al_final` como última línea."""
    lineas = []
    total = 0
    numero = 0
    while total < caracteres:
        linea = f"{numero:05d} {LINEA_DE_RELLENO}"
        lineas.append(linea)
        total += len(linea) + 1
        numero += 1
    if al_final:
        lineas.append(al_final)
    return "\n".join(lineas)


def pdf_con_lineas(lineas: list[str]) -> bytes:
    """PDF de una página con esas líneas como capa de texto."""
    partes = ["BT /F1 12 Tf 72 720 Td 14 TL"]
    for linea in lineas:
        escapada = linea.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        partes.append(f"({escapada}) Tj T*")
    partes.append("ET")
    return _armar_pdf("\n".join(partes).encode("latin-1"))


def pdf_de_varias_paginas(*paginas: list[str]) -> bytes:
    """Une un PDF de una página por cada lista de líneas."""
    from pypdf import PdfReader, PdfWriter

    escritor = PdfWriter()
    for lineas in paginas:
        escritor.append(PdfReader(io.BytesIO(pdf_con_lineas(lineas))))
    salida = io.BytesIO()
    escritor.write(salida)
    return salida.getvalue()


def pdf_sin_texto() -> bytes:
    """PDF válido de una página sin capa de texto, como un escaneo."""
    return _armar_pdf(b"0 0 m 100 100 l S")


def _armar_pdf(contenido: bytes) -> bytes:
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>"
        ),
        b"<< /Length " + str(len(contenido)).encode() + b" >>\nstream\n" + contenido + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    salida = bytearray(b"%PDF-1.4\n")
    posiciones = []
    for numero, cuerpo in enumerate(objetos, start=1):
        posiciones.append(len(salida))
        salida += str(numero).encode() + b" 0 obj\n" + cuerpo + b"\nendobj\n"
    inicio_xref = len(salida)
    salida += b"xref\n0 " + str(len(objetos) + 1).encode() + b"\n0000000000 65535 f \n"
    for posicion in posiciones:
        salida += f"{posicion:010d} 00000 n \n".encode()
    salida += (
        b"trailer\n<< /Size " + str(len(objetos) + 1).encode() + b" /Root 1 0 R >>\nstartxref\n"
        + str(inicio_xref).encode() + b"\n%%EOF\n"
    )
    return bytes(salida)
