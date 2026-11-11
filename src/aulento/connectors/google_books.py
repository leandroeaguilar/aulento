"""Conector para Google Play Libros (OAuth 2.0 y Google Books API v1).

Permite vincular la cuenta del usuario con Google Play Libros, consultar las estanterías
personales (leyendo actualmente, leídos) y sincronizar el progreso de lectura y las páginas leídas.
"""

import hashlib
import hmac
import json
import logging
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

from aulento.core.almacenes import ServicioDeCuenta
from aulento.core.cliente_google_compartido import obtener_cliente_compartido
from aulento.core.secretos import AlmacenDeSecretos, SecretoIlegible, clave_maestra
from aulento.db.repository import LibroRepository
from aulento.models.libro import EstadoLibro, LibroCreate

logger = logging.getLogger(__name__)

SECRETO_GOOGLE_BOOKS_CLIENTE = "google_books_cliente"
# El cliente OAuth propio de Google que se cargaba para Google Drive: Google Books lo sigue aceptando
SECRETO_GDRIVE_CLIENTE = "gdrive_cliente"
SECRETO_GOOGLE_BOOKS_AUTORIZACION = "google_books_autorizacion"
AJUSTE_GOOGLE_BOOKS_AUTORIZACION_RECHAZADA = "google_books_autorizacion_rechazada"

GOOGLE_BOOKS_SCOPE = "https://www.googleapis.com/auth/books"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_BOOKS_API_BASE = "https://www.googleapis.com/books/v1"

SHELF_LEYENDO_ACTUALMENTE = 3
SHELF_LEIDOS = 4


class GoogleBooksError(Exception):
    """Error base de interacción con Google Books API."""


class FaltaClienteGoogleBooks(GoogleBooksError):
    """No hay cliente OAuth configurado para Google Books."""


class AutorizacionGoogleBooksInvalida(GoogleBooksError):
    """La autorización de Google Books está vencida, revocada o ausente."""


class EstadoGoogleBooksInvalido(GoogleBooksError):
    """El parámetro state de Google Books es inválido, está alterado o venció."""


DURACION_STATE_SEGUNDOS = 600  # 10 minutos


def _derivar_clave_state() -> bytes:
    km = clave_maestra()
    return hmac.new(km, b"google-books-state", hashlib.sha256).digest()


def generar_state_oauth(user_id: int, duracion_segundos: int = DURACION_STATE_SEGUNDOS) -> str:
    """Genera un state firmado con HMAC-SHA256 que vence en 10 minutos."""
    expira = int(time.time()) + duracion_segundos
    nonce = secrets.token_hex(8)
    clave = _derivar_clave_state()
    mensaje = f"{user_id}.{expira}.{nonce}".encode()
    firma = hmac.new(clave, mensaje, hashlib.sha256).hexdigest()
    return f"{user_id}.{expira}.{nonce}.{firma}"


def verificar_state_oauth(
    state: str | None,
    user_id_sesion: int | None = None,
    ahora: float | None = None,
) -> int:
    """Valida un state firmado; retorna el user_id o levanta EstadoGoogleBooksInvalido."""
    if not state or not isinstance(state, str):
        raise EstadoGoogleBooksInvalido("Falta el parámetro de estado de autorización.")

    partes = state.split(".")
    if len(partes) != 4:
        raise EstadoGoogleBooksInvalido("El formato del estado de autorización es inválido.")

    user_id_str, expira_str, nonce, firma = partes
    try:
        user_id = int(user_id_str)
        expira = int(expira_str)
    except ValueError:
        raise EstadoGoogleBooksInvalido("Los datos del estado de autorización son inválidos.")

    clave = _derivar_clave_state()
    mensaje = f"{user_id}.{expira}.{nonce}".encode()
    esperada = hmac.new(clave, mensaje, hashlib.sha256).hexdigest()
    # Bytes: compare_digest con texto no ASCII levanta TypeError y daría un 500
    if not hmac.compare_digest(firma.encode("utf-8"), esperada.encode("utf-8")):
        raise EstadoGoogleBooksInvalido("La firma del estado de autorización es inválida o fue alterada.")

    momento = time.time() if ahora is None else ahora
    if momento > expira:
        raise EstadoGoogleBooksInvalido("El estado de autorización venció (superó los 10 minutos).")

    if user_id_sesion is not None and user_id_sesion != user_id:
        raise EstadoGoogleBooksInvalido("La cuenta de la sesión no coincide con la del estado de autorización.")

    return user_id


class GoogleBooksConnector(ServicioDeCuenta):
    """Conector por cuenta a la API de Google Play Libros."""

    def __init__(self, conn, user_id: int):
        super().__init__(conn, user_id)
        self.secretos = AlmacenDeSecretos(conn, self.user_id)
        self.libro_repo = LibroRepository(conn, self.user_id)

    def obtener_cliente_oauth(self) -> dict[str, Any] | None:
        """Obtiene la configuración del cliente OAuth (ID y Secret).

        Busca en orden:
        1. Secreto propio `google_books_cliente`.
        2. Cliente OAuth propio de Google guardado como `gdrive_cliente`.
        3. Cliente compartido del servidor (`cliente_google_compartido`).
        """
        # 1. Propio
        try:
            propio = self.secretos.leer(SECRETO_GOOGLE_BOOKS_CLIENTE)
            if propio:
                return json.loads(propio)
        except (SecretoIlegible, json.JSONDecodeError):
            pass

        # 2. Cliente OAuth propio de Google cargado antes para Drive
        try:
            de_drive = self.secretos.leer(SECRETO_GDRIVE_CLIENTE)
            if de_drive:
                datos = json.loads(de_drive)
                sec = datos.get("installed") or datos.get("web")
                if sec:
                    return sec
                return datos
        except (SecretoIlegible, json.JSONDecodeError):
            pass

        # 3. Compartido del servidor
        try:
            comp = obtener_cliente_compartido()
            if comp:
                sec = comp.get("installed") or comp.get("web")
                return sec if sec else comp
        except (OSError, ValueError):
            logger.debug("No se pudo cargar el cliente compartido de Google Books")

        return None

    def esta_autorizado(self) -> bool:
        """Indica si la cuenta posee credenciales guardadas para Google Books."""
        try:
            tokens_raw = self.secretos.leer(SECRETO_GOOGLE_BOOKS_AUTORIZACION)
            if not tokens_raw:
                return False
            tokens = json.loads(tokens_raw)
            return bool(tokens.get("access_token") or tokens.get("refresh_token"))
        except (SecretoIlegible, json.JSONDecodeError):
            return False

    def generar_url_autorizacion(self, redirect_uri: str, state: str) -> str:
        """Genera la URL de consentimiento OAuth 2.0."""
        cliente = self.obtener_cliente_oauth()
        if not cliente or not cliente.get("client_id"):
            raise FaltaClienteGoogleBooks(
                "Google Books no está disponible en esta instalación: quien administra el servidor tiene que configurar el cliente de Google compartido."
            )

        params = {
            "client_id": cliente["client_id"],
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": GOOGLE_BOOKS_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    def canjear_codigo(self, code: str, redirect_uri: str) -> dict[str, Any]:
        """Canjea el código de autorización por tokens de acceso y actualización."""
        cliente = self.obtener_cliente_oauth()
        if not cliente:
            raise FaltaClienteGoogleBooks("No hay cliente OAuth configurado.")

        payload = {
            "code": code,
            "client_id": cliente["client_id"],
            "client_secret": cliente.get("client_secret", ""),
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        response = httpx.post(GOOGLE_TOKEN_URL, data=payload, timeout=15.0)
        if response.status_code != 200:
            raise AutorizacionGoogleBooksInvalida(
                f"Error al canjear código con Google ({response.status_code}): {response.text}"
            )

        tokens = response.json()
        ahora = datetime.now(UTC)
        if "expires_in" in tokens:
            tokens["expires_at"] = (ahora + timedelta(seconds=tokens["expires_in"])).isoformat()

        self.secretos.guardar(SECRETO_GOOGLE_BOOKS_AUTORIZACION, json.dumps(tokens))
        return tokens

    def obtener_token_acceso_valido(self) -> str:
        """Devuelve un access_token vigente, renovándolo si está próximo a vencer."""
        tokens_raw = self.secretos.leer(SECRETO_GOOGLE_BOOKS_AUTORIZACION)
        if not tokens_raw:
            raise AutorizacionGoogleBooksInvalida("La cuenta no está vinculada a Google Books.")

        tokens = json.loads(tokens_raw)
        expires_at_str = tokens.get("expires_at")
        vencido = True
        if expires_at_str:
            try:
                expires_at = datetime.fromisoformat(expires_at_str)
                # Renovar si queda menos de un minuto
                if expires_at > datetime.now(UTC) + timedelta(seconds=60):
                    vencido = False
            except ValueError:
                vencido = True

        if not vencido and tokens.get("access_token"):
            return tokens["access_token"]

        # Intentar refrescar
        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            raise AutorizacionGoogleBooksInvalida("No se puede renovar el acceso a Google Books: falta refresh_token.")

        cliente = self.obtener_cliente_oauth()
        if not cliente:
            raise FaltaClienteGoogleBooks("Falta cliente OAuth para renovar el token.")

        payload = {
            "refresh_token": refresh_token,
            "client_id": cliente["client_id"],
            "client_secret": cliente.get("client_secret", ""),
            "grant_type": "refresh_token",
        }
        response = httpx.post(GOOGLE_TOKEN_URL, data=payload, timeout=15.0)
        if response.status_code != 200:
            raise AutorizacionGoogleBooksInvalida(f"Fallo al renovar token de Google Books: {response.text}")

        nuevos = response.json()
        tokens["access_token"] = nuevos.get("access_token", tokens.get("access_token"))
        if "expires_in" in nuevos:
            tokens["expires_at"] = (datetime.now(UTC) + timedelta(seconds=nuevos["expires_in"])).isoformat()
        if "refresh_token" in nuevos:
            tokens["refresh_token"] = nuevos["refresh_token"]

        self.secretos.guardar(SECRETO_GOOGLE_BOOKS_AUTORIZACION, json.dumps(tokens))
        return tokens["access_token"]

    def desconectar(self) -> bool:
        """Elimina las credenciales guardadas de Google Books."""
        return self.secretos.borrar(SECRETO_GOOGLE_BOOKS_AUTORIZACION)

    def obtener_volumenes_estanteria(self, shelf_id: int) -> list[dict[str, Any]]:
        """Consulta los volúmenes de una estantería en Google Books."""
        token = self.obtener_token_acceso_valido()
        url = f"{GOOGLE_BOOKS_API_BASE}/mylibrary/bookshelves/{shelf_id}/volumes"
        headers = {"Authorization": f"Bearer {token}"}
        response = httpx.get(url, headers=headers, timeout=15.0)
        if response.status_code != 200:
            raise GoogleBooksError(
                f"Error al consultar estantería {shelf_id} de Google Books ({response.status_code}): {response.text}"
            )
        data = response.json()
        return data.get("items", [])

    def obtener_posicion_lectura(self, volume_id: str) -> dict[str, Any] | None:
        """Obtiene la posición de lectura actual registrada en Google Books para un volumen."""
        token = self.obtener_token_acceso_valido()
        url = f"{GOOGLE_BOOKS_API_BASE}/mylibrary/readingpositions/{volume_id}"
        headers = {"Authorization": f"Bearer {token}"}
        response = httpx.get(url, headers=headers, timeout=15.0)
        if response.status_code == 200:
            return response.json()
        if response.status_code == 404:
            return None
        logger.warning("No se pudo obtener posición para volumen %s: %s", volume_id, response.status_code)
        return None

    def sincronizar(self) -> dict[str, Any]:
        """Sincroniza estanterías y posiciones de Google Books con el repositorio local de libros."""
        if not self.esta_autorizado():
            raise AutorizacionGoogleBooksInvalida("La cuenta no está autorizada para sincronizar con Google Books.")

        ahora_iso = datetime.now(UTC).isoformat()
        items_leyendo = self.obtener_volumenes_estanteria(SHELF_LEYENDO_ACTUALMENTE)
        items_leidos = self.obtener_volumenes_estanteria(SHELF_LEIDOS)

        sincronizados = 0
        creados = 0
        actualizados = 0
        detalles = []

        # 1. Procesar libros leyendo actualmente
        for item in items_leyendo:
            vol_id = item.get("id")
            vol_info = item.get("volumeInfo", {})
            titulo = vol_info.get("title", "Sin título").strip()
            total_pag = vol_info.get("pageCount")

            # Intentar obtener posición de lectura
            posicion = self.obtener_posicion_lectura(vol_id) if vol_id else None
            pagina_actual = 0
            if posicion and total_pag:
                # Posición por porcentaje
                pct = posicion.get("percentage")
                if pct is not None and isinstance(pct, (int, float)):
                    pagina_actual = round(pct * total_pag)
                elif posicion.get("pdfPosition"):
                    # Si trae página directa
                    try:
                        pagina_actual = int(posicion["pdfPosition"])
                    except (ValueError, TypeError):
                        pass

            # Buscar libro existente
            libro = self.libro_repo.find_by_google_books_id(vol_id) if vol_id else None
            if not libro and titulo:
                libro = self.libro_repo.find_by_title(titulo)
                if libro and vol_id:
                    self.libro_repo.vincular_google_books(libro.id, vol_id)

            if not libro:
                # Auto-importar libro
                nuevo = self.libro_repo.create(
                    LibroCreate(
                        titulo=titulo,
                        total_capitulos=1,
                        pagina_actual=pagina_actual,
                        total_paginas=total_pag or (pagina_actual if pagina_actual > 0 else 100),
                        estado=EstadoLibro.LEYENDO,
                        google_books_id=vol_id,
                        fuente_sincronizacion="google_books",
                        ultima_sincronizacion=ahora_iso,
                    )
                )
                creados += 1
                sincronizados += 1
                detalles.append({"id": nuevo.id, "titulo": titulo, "accion": "creado", "pagina": pagina_actual})
            else:
                # Actualizar si hay progreso nuevo
                nueva_pag = max(libro.pagina_actual, pagina_actual)
                tot = libro.total_paginas or total_pag
                self.libro_repo.update_progress(
                    libro.id,
                    pagina_actual=nueva_pag,
                    total_paginas=tot,
                    fuente_sincronizacion="google_books",
                    ultima_sincronizacion=ahora_iso,
                    google_books_id=vol_id,
                )
                actualizados += 1
                sincronizados += 1
                detalles.append({"id": libro.id, "titulo": libro.titulo, "accion": "actualizado", "pagina": nueva_pag})

        # 2. Procesar libros leídos (marcar como completados si existen)
        for item in items_leidos:
            vol_id = item.get("id")
            vol_info = item.get("volumeInfo", {})
            titulo = vol_info.get("title", "").strip()

            libro = self.libro_repo.find_by_google_books_id(vol_id) if vol_id else None
            if not libro and titulo:
                libro = self.libro_repo.find_by_title(titulo)

            if libro and libro.estado != EstadoLibro.COMPLETADO:
                tot = libro.total_paginas or libro.pagina_actual
                self.libro_repo.update_progress(
                    libro.id,
                    pagina_actual=tot,
                    total_paginas=tot,
                    estado=EstadoLibro.COMPLETADO,
                    fuente_sincronizacion="google_books",
                    ultima_sincronizacion=ahora_iso,
                    google_books_id=vol_id,
                )
                actualizados += 1
                sincronizados += 1
                detalles.append({"id": libro.id, "titulo": libro.titulo, "accion": "completado", "pagina": tot})

        return {
            "sincronizados": sincronizados,
            "creados": creados,
            "actualizados": actualizados,
            "detalles": detalles,
        }
