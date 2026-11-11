"""Extracción de texto de los PDFs que sube cada cuenta."""

import io
import logging
import re
import time

logger = logging.getLogger(__name__)

# Extraer el texto de una página crece más que linealmente con su tamaño: una página
# de varios MB de operadores puede tardar minutos, aunque el PDF comprimido pese poco.
MAX_BYTES_CONTENIDO_PAGINA = 1024 * 1024
MAX_PAGINAS = 1_000
MAX_BYTES_DECODIFICADOS_TOTALES = 50 * 1024 * 1024
MAX_SEGUNDOS_EXTRACCION = 15.0

# Caracteres de control (salvo tabulación y salto de línea) que un PDF puede traer y que
# rompen después: PostgreSQL rechaza el NUL en texto.
_CONTROLES = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class PdfSinTextoError(Exception):
    """El PDF no tiene texto que extraer o no se pudo abrir; el mensaje dice por qué."""


class PdfRechazado(PdfSinTextoError):
    """El PDF fue rechazado por límites de seguridad (páginas, bytes, tiempo) o cifrado."""


def _limpiar(texto: str) -> str:
    """Quita sustitutos Unicode sueltos (no se pueden codificar en UTF-8) y caracteres de control."""
    texto = texto.encode("utf-8", "ignore").decode("utf-8")
    return _CONTROLES.sub("", texto.replace("\r\n", "\n").replace("\r", "\n"))


def _pagina_demasiado_grande(pagina) -> bool:
    contenido = pagina.get_contents()
    return contenido is not None and len(contenido.get_data()) > MAX_BYTES_CONTENIDO_PAGINA


def extraer_texto_pdf(datos: bytes, max_caracteres: int) -> str:
    """Devuelve el texto del PDF, página por página, hasta `max_caracteres`.

    Lanza PdfSinTextoError si falta pypdf, si el PDF está protegido o dañado, o si no tiene
    capa de texto (por ejemplo, un escaneo).
    """
    try:
        from pypdf import PdfReader
        from pypdf.errors import DependencyError
    except ImportError as e:
        raise PdfSinTextoError("falta instalar la librería pypdf") from e

    try:
        lector = PdfReader(io.BytesIO(datos))
        if lector.is_encrypted and not lector.decrypt(""):
            raise PdfRechazado("el PDF está protegido con contraseña")
        if len(lector.pages) > MAX_PAGINAS:
            raise PdfRechazado(f"el PDF supera el máximo permitido de {MAX_PAGINAS} páginas")

        tiempo_limite = time.monotonic() + MAX_SEGUNDOS_EXTRACCION
        bytes_decodificados_totales = 0
        partes: list[str] = []
        total = 0
        for pagina in lector.pages:
            if time.monotonic() > tiempo_limite:
                raise PdfRechazado("la extracción de texto del PDF superó el tiempo límite")

            contenido = pagina.get_contents()
            if contenido is not None:
                try:
                    datos_contenido = contenido.get_data() if hasattr(contenido, "get_data") else b""
                except (AttributeError, ValueError, TypeError, OSError, RuntimeError):
                    datos_contenido = b""
                bytes_pagina = len(datos_contenido)
                if bytes_pagina > MAX_BYTES_CONTENIDO_PAGINA:
                    continue
                bytes_decodificados_totales += bytes_pagina
                if bytes_decodificados_totales > MAX_BYTES_DECODIFICADOS_TOTALES:
                    raise PdfRechazado("el PDF supera el límite de contenido decodificado permitido")

            texto = _limpiar(pagina.extract_text() or "").strip()
            if time.monotonic() > tiempo_limite:
                raise PdfRechazado("la extracción de texto del PDF superó el tiempo límite")
            if not texto:
                continue
            partes.append(texto)
            total += len(texto) + 2
            if total >= max_caracteres:
                break
        if time.monotonic() > tiempo_limite:
            raise PdfRechazado("la extracción de texto del PDF superó el tiempo límite")
    except PdfSinTextoError:
        raise
    except DependencyError as e:
        raise PdfRechazado("el PDF está cifrado y falta instalar la librería cryptography para abrirlo") from e
    except Exception as e:
        logger.warning("No se pudo leer el PDF: %s", e)
        raise PdfSinTextoError("el PDF está dañado o tiene un formato que no se pudo leer") from e

    contenido = "\n\n".join(partes)[:max_caracteres]
    if not contenido.strip():
        raise PdfSinTextoError("el PDF no tiene texto seleccionable (parece un escaneo)")
    return contenido
