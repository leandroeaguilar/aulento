"""Cliente OAuth de Google compartido del servidor, la alternativa de Google Books cuando la cuenta no cargó uno propio (ADR 010)."""

import json
import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from aulento.config import get_data_dir

logger = logging.getLogger(__name__)

# Los nombres vienen de cuando lo usaba Google Drive: se conservan para no romper los servidores ya configurados
VARIABLE_CLIENTE_COMPARTIDO_GDRIVE = "AULENTO_GDRIVE_SHARED_CLIENT"
VARIABLE_RUTA_CLIENTE_COMPARTIDO_GDRIVE = "AULENTO_GDRIVE_SHARED_CLIENT_PATH"
ARCHIVO_CLIENTE_COMPARTIDO_GDRIVE = "gdrive_shared_client.json"

MAX_BYTES_CLIENTE_OAUTH = 16 * 1024
SECCIONES_DEL_CLIENTE_OAUTH = ("installed", "web")
CAMPOS_DEL_CLIENTE_OAUTH = ("client_id", "client_secret", "auth_uri", "token_uri")
# El servidor le habla a estas direcciones con el secreto del cliente: solo valen las de Google
HOSTS_DE_GOOGLE = frozenset({"accounts.google.com", "oauth2.googleapis.com", "www.googleapis.com"})


class ClienteOAuthInvalido(ValueError):
    """Lo que se quiso cargar no es un archivo de cliente OAuth de Google; el mensaje no repite su contenido."""


def validar_cliente_oauth(contenido: str) -> dict[str, Any]:
    """Devuelve el cliente OAuth que trae el JSON descargado de Google Cloud Console, con su forma mínima comprobada.

    Levanta `ClienteOAuthInvalido` si no es JSON, no tiene la sección `installed` o `web`, le falta un campo
    o sus direcciones no son de Google.
    """
    if not isinstance(contenido, str) or not contenido.strip():
        raise ClienteOAuthInvalido("El archivo del cliente OAuth está vacío.")
    if len(contenido.encode("utf-8")) > MAX_BYTES_CLIENTE_OAUTH:
        raise ClienteOAuthInvalido(
            f"El archivo del cliente OAuth supera los {MAX_BYTES_CLIENTE_OAUTH // 1024} KB: no parece el de Google."
        )
    try:
        datos = json.loads(contenido)
    except ValueError:
        raise ClienteOAuthInvalido("El archivo del cliente OAuth no es un JSON válido.") from None
    secciones = [
        nombre
        for nombre in SECCIONES_DEL_CLIENTE_OAUTH
        if isinstance(datos, dict) and isinstance(datos.get(nombre), dict)
    ]
    if len(secciones) != 1:
        raise ClienteOAuthInvalido(
            "No es un archivo de cliente OAuth: tiene que ser el JSON que se descarga de Google Cloud Console, "
            "con la sección «installed» o «web»."
        )
    seccion = datos[secciones[0]]
    for campo in CAMPOS_DEL_CLIENTE_OAUTH:
        if not isinstance(seccion.get(campo), str) or not seccion[campo].strip():
            raise ClienteOAuthInvalido(f"Al cliente OAuth le falta el campo «{campo}».")
    for campo in ("auth_uri", "token_uri"):
        try:
            direccion = urlsplit(seccion[campo])
            de_google = direccion.scheme == "https" and direccion.hostname in HOSTS_DE_GOOGLE
        except ValueError:
            de_google = False
        if not de_google:
            raise ClienteOAuthInvalido(f"El campo «{campo}» del cliente OAuth no es una dirección de Google.")
    return {secciones[0]: seccion}


def obtener_cliente_compartido() -> dict[str, Any] | None:
    """Obtiene el cliente OAuth compartido del servidor si está configurado.

    Prioridad:
    1. Variable de entorno AULENTO_GDRIVE_SHARED_CLIENT (JSON en texto).
    2. Variable de entorno AULENTO_GDRIVE_SHARED_CLIENT_PATH (ruta al archivo JSON).
    3. Archivo 'gdrive_shared_client.json' en el directorio de datos del servidor (`get_data_dir()`).
    """
    contenido = os.getenv(VARIABLE_CLIENTE_COMPARTIDO_GDRIVE)
    if contenido and contenido.strip():
        try:
            return validar_cliente_oauth(contenido.strip())
        except (ValueError, KeyError) as e:
            logger.warning(
                "El cliente compartido de Google en %s es inválido: %s",
                VARIABLE_CLIENTE_COMPARTIDO_GDRIVE,
                e,
            )
            return None

    ruta_env = os.getenv(VARIABLE_RUTA_CLIENTE_COMPARTIDO_GDRIVE)
    if ruta_env and ruta_env.strip():
        p = Path(ruta_env.strip())
        if p.is_file():
            try:
                return validar_cliente_oauth(p.read_text(encoding="utf-8"))
            except (ValueError, KeyError, OSError) as e:
                logger.warning("El cliente compartido de Google en %s es inválido: %s", p, e)
                return None

    try:
        archivo_datos = get_data_dir() / ARCHIVO_CLIENTE_COMPARTIDO_GDRIVE
        if archivo_datos.is_file():
            try:
                return validar_cliente_oauth(archivo_datos.read_text(encoding="utf-8"))
            except (ValueError, KeyError, OSError) as e:
                logger.warning("El cliente compartido en %s es inválido: %s", archivo_datos, e)
                return None
    except OSError:
        pass

    return None
