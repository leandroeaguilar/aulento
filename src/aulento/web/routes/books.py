from aulento.core.book_active_recall import BookActiveRecallService
from aulento.models.book_active_recall import (
    ActiveRecallEvaluateRequest,
    ActiveRecallEvaluateResponse,
    ActiveRecallGenerateRequest,
    ActiveRecallGenerateResponse,
    BookHarvestCommitRequest,
    BookHarvestCommitResponse,
    BookHarvestPreviewRequest,
    BookHarvestPreviewResponse,
)

"""Router para el seguimiento de lectura de libros técnicos (por Páginas y Capítulos),

sincronización con Google Play Libros y Webhooks para Apple Libros (Atajos).
"""

import html
import logging
import os
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from aulento.connectors.google_books import (
    AutorizacionGoogleBooksInvalida,
    EstadoGoogleBooksInvalido,
    FaltaClienteGoogleBooks,
    GoogleBooksConnector,
    GoogleBooksError,
    generar_state_oauth,
    verificar_state_oauth,
)
from aulento.core import tokens_de_alcance
from aulento.core.identity import obtener_proveedor_de_identidad
from aulento.db.repository import LibroRepository
from aulento.models.libro import EstadoLibro, Libro, LibroCreate, LibroUpdate
from aulento.web.dependencies import (
    Conexion,
    Cuenta,
    CuentaDelAvanceDeLibros,
    RepoLibros,
    SinCuentaCompartida,
    no_encontrado,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/books", tags=["Books"])

# Enlace de iCloud a un atajo de Libros ya armado; sin él, la pantalla muestra solo la guía (061, R5)
VARIABLE_ATAJO_LIBROS = "AULENTO_ATAJO_LIBROS_URL"


def enlace_del_atajo_de_libros() -> str | None:
    """El enlace al atajo publicado, si el servidor lo tiene configurado y es https."""
    enlace = os.getenv(VARIABLE_ATAJO_LIBROS, "").strip()
    return enlace if enlace.startswith("https://") else None


class BookProgressUpdate(BaseModel):
    capitulo_actual: int | None = Field(default=None, ge=0, description="Capítulo actual")
    total_capitulos: int | None = Field(default=None, gt=0, description="Total capítulos")
    pagina_actual: int | None = Field(default=None, ge=0, description="Página actual")
    total_paginas: int | None = Field(default=None, gt=0, description="Total páginas")
    estado: EstadoLibro | None = None


class WebhookLecturaPayload(BaseModel):
    titulo: str = Field(..., min_length=1, max_length=200, description="Título del libro leído")
    pagina_actual: int | None = Field(default=None, ge=0, description="Página actual leída")
    total_paginas: int | None = Field(default=None, gt=0, description="Total de páginas estimadas")
    capitulo_actual: int | None = Field(default=None, ge=0, description="Capítulo actual")
    total_capitulos: int | None = Field(default=None, gt=0, description="Total de capítulos")
    porcentaje: float | None = Field(default=None, ge=0.0, le=100.0, description="Porcentaje leído (0-100)")
    fuente: str = Field(default="apple_books", max_length=50, description="Fuente del webhook (apple_books, atajos, etc.)")


# ----------------------------------------------------------------------
# Operaciones CRUD estándar de Libros
# ----------------------------------------------------------------------


@router.get("", response_model=list[Libro])
def list_books(repo: RepoLibros):
    """Obtiene los libros técnicos en seguimiento de la cuenta."""
    return repo.list_all()


@router.post("", response_model=Libro, status_code=status.HTTP_201_CREATED)
def create_book(data: LibroCreate, repo: RepoLibros):
    """Registra un nuevo libro técnico para lectura."""
    return repo.create(data)


@router.patch("/{book_id}/progress", response_model=Libro)
def update_book_progress(book_id: int, data: BookProgressUpdate, repo: RepoLibros):
    """Actualiza páginas, capítulos o estado de un libro."""
    if not repo.get_by_id(book_id):
        raise no_encontrado("Libro", book_id)

    try:
        updated = repo.update_progress(
            id=book_id,
            pagina_actual=data.pagina_actual,
            total_paginas=data.total_paginas,
            capitulo_actual=data.capitulo_actual,
            total_capitulos=data.total_capitulos,
            estado=data.estado,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not updated:
        raise HTTPException(status_code=500, detail="Error al actualizar progreso del libro.")
    return updated


@router.post("/{book_id}/advance", response_model=Libro)
def advance_book_chapter(book_id: int, repo: RepoLibros):
    """Avanza 1 capítulo en la lectura del libro."""
    if not repo.get_by_id(book_id):
        raise no_encontrado("Libro", book_id)

    updated = repo.advance_chapter(book_id, chapters=1)
    if not updated:
        raise HTTPException(status_code=500, detail="Error al actualizar avance del libro.")
    return updated


@router.post("/{book_id}/advance-pages", response_model=Libro)
def advance_book_pages(
    book_id: int,
    repo: RepoLibros,
    pages: int = Query(default=10, ge=1, le=5000, description="Páginas a avanzar (entre 1 y 5000)"),
):
    """Avanza N páginas en la lectura del libro (por defecto +10 páginas)."""
    book = repo.get_by_id(book_id)
    if not book:
        raise no_encontrado("Libro", book_id)

    new_pag = book.pagina_actual + pages
    if book.total_paginas and new_pag > book.total_paginas:
        new_pag = book.total_paginas
    updated = repo.update_progress(id=book_id, pagina_actual=new_pag)
    if not updated:
        raise HTTPException(status_code=500, detail="Error al avanzar páginas del libro.")
    return updated


@router.put("/{book_id}", response_model=Libro)
def update_book(book_id: int, data: LibroUpdate, repo: RepoLibros):
    """Actualiza metadatos y progreso de un libro técnico."""
    if not repo.get_by_id(book_id):
        raise no_encontrado("Libro", book_id)
    try:
        return repo.update(book_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{book_id}", status_code=status.HTTP_200_OK, dependencies=[SinCuentaCompartida])
def delete_book(book_id: int, repo: RepoLibros):
    """Elimina un libro técnico del registro de lecturas."""
    if not repo.get_by_id(book_id):
        raise no_encontrado("Libro", book_id)
    success = repo.delete(book_id)
    return {"ok": success, "message": f"Libro {book_id} eliminado con éxito."}


# ----------------------------------------------------------------------
# Webhook para Apple Libros / Atajos de Apple (R5, R6, R7)
# ----------------------------------------------------------------------


@router.post("/sync/webhook", status_code=status.HTTP_200_OK)
def webhook_sync_reading(
    data: WebhookLecturaPayload,
    usuario: CuentaDelAvanceDeLibros,
    conn: Conexion,
):
    """Webhook para sincronizar avance de lectura desde Atajos de Apple o scripts externos.

    Autentica con el token de libros (`Authorization: Bearer`), que solo sirve para esto; por compatibilidad
    también con cookie de sesión o token MCP.
    """
    repo = LibroRepository(conn, usuario.id)
    ahora_iso = datetime.now(UTC).isoformat()
    titulo_limpio = data.titulo.strip()

    candidatos = repo.buscar_por_titulo(titulo_limpio)
    if len(candidatos) > 1:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": f"Hay más de un libro que coincide con '{titulo_limpio}'.",
                "candidatos": [{"id": l.id, "titulo": l.titulo} for l in candidatos],
            },
        )

    libro = candidatos[0] if len(candidatos) == 1 else None

    # Determinar página actual
    if data.pagina_actual is not None:
        nueva_pag = data.pagina_actual
    elif data.porcentaje is not None:
        tot = data.total_paginas or (libro.total_paginas if libro else None) or 100
        nueva_pag = round((data.porcentaje / 100.0) * tot)
    else:
        nueva_pag = (libro.pagina_actual if libro else 0) + 1

    try:
        if libro is None:
            tot_pag = data.total_paginas or (nueva_pag if nueva_pag > 0 else 100)
            libro = repo.create(
                LibroCreate(
                    titulo=titulo_limpio,
                    capitulo_actual=data.capitulo_actual or 1,
                    total_capitulos=data.total_capitulos or 1,
                    pagina_actual=nueva_pag,
                    total_paginas=tot_pag,
                    estado=EstadoLibro.COMPLETADO if nueva_pag >= tot_pag else EstadoLibro.LEYENDO,
                    fuente_sincronizacion=data.fuente,
                    ultima_sincronizacion=ahora_iso,
                )
            )
            accion = "creado"
        else:
            tot_pag = data.total_paginas or libro.total_paginas
            nueva_pag = max(libro.pagina_actual, nueva_pag)
            cap = data.capitulo_actual or libro.capitulo_actual
            tot_cap = data.total_capitulos or libro.total_capitulos

            libro = repo.update_progress(
                libro.id,
                pagina_actual=nueva_pag,
                total_paginas=tot_pag,
                capitulo_actual=cap,
                total_capitulos=tot_cap,
                estado=None,
                fuente_sincronizacion=data.fuente,
                ultima_sincronizacion=ahora_iso,
            )
            accion = "actualizado"
    except (ValueError, ValidationError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return {
        "status": "ok",
        "accion": accion,
        "libro_id": libro.id if libro else None,
        "titulo": titulo_limpio,
        "pagina_actual": nueva_pag,
        "total_paginas": libro.total_paginas if libro else None,
        "fuente": data.fuente,
    }


@router.get("/sync/webhook-info")
def get_webhook_info(request: Request, usuario: Cuenta):
    """Devuelve los parámetros para configurar Atajos de Apple con Aulento."""
    base_url = str(request.base_url).rstrip("/")
    return {
        "webhook_url": f"{base_url}/api/books/sync/webhook",
        "metodo": "POST",
        "autenticacion": "Cabecera 'Authorization: Bearer <token de libros>' (se crea en esta misma pantalla)",
        "ejemplo_payload": {
            "titulo": "Designing Data-Intensive Applications",
            "pagina_actual": 142,
            "total_paginas": 612,
            "fuente": "apple_books",
        },
        "atajo_url": enlace_del_atajo_de_libros(),
    }


@router.get("/sync/token")
def estado_del_token_de_libros(usuario: Cuenta, conn: Conexion):
    """Dice si la cuenta tiene un token de libros vigente; el token solo se muestra al crearlo."""
    creado_en = tokens_de_alcance.vigente(conn, usuario.id, tokens_de_alcance.LIBROS)
    return {"activo": creado_en is not None, "creado_en": creado_en}


@router.post("/sync/token", dependencies=[SinCuentaCompartida])
def crear_token_de_libros(usuario: Cuenta, conn: Conexion):
    """Crea el token que usa el atajo para anotar el avance de libros; el anterior, si había, deja de valer."""
    token, creado_en = tokens_de_alcance.emitir(conn, usuario.id, tokens_de_alcance.LIBROS)
    return {"activo": True, "creado_en": creado_en, "token": token}


@router.delete("/sync/token", dependencies=[SinCuentaCompartida])
def revocar_token_de_libros(usuario: Cuenta, conn: Conexion):
    """Revoca el token de libros: el atajo deja de poder anotar avances hasta que se cree otro."""
    return {"revocado": tokens_de_alcance.revocar(conn, usuario.id, tokens_de_alcance.LIBROS)}


# ----------------------------------------------------------------------
# Conector y Sincronización con Google Play Libros (R2, R3, R4)
# ----------------------------------------------------------------------


@router.get("/google/status")
def get_google_books_status(usuario: Cuenta, conn: Conexion):
    """Verifica si la cuenta está vinculada a Google Play Libros y si posee cliente OAuth."""
    connector = GoogleBooksConnector(conn, usuario.id)
    return {
        "conectado": connector.esta_autorizado(),
        "tiene_cliente": connector.obtener_cliente_oauth() is not None,
    }


@router.post("/google/authorize", dependencies=[SinCuentaCompartida])
def start_google_books_auth(request: Request, usuario: Cuenta, conn: Conexion):
    """Genera la URL de consentimiento OAuth 2.0 para Google Play Libros."""
    connector = GoogleBooksConnector(conn, usuario.id)
    base_url = str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/api/books/google/oauth-callback"
    state = generar_state_oauth(usuario.id)
    try:
        auth_url = connector.generar_url_autorizacion(redirect_uri, state)
        return {"auth_url": auth_url, "state": state}
    except FaltaClienteGoogleBooks as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/google/oauth-callback", response_class=Response)
def google_books_oauth_callback(
    request: Request,
    conn: Conexion,
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
):
    """Procesa el retorno de la pantalla de consentimiento de Google OAuth 2.0."""
    if error:
        return _render_oauth_callback_html(False, f"Google denegó la autorización: {error}")
    if not code:
        return _render_oauth_callback_html(False, "Falta el código de autorización en el retorno de Google.")

    # Sin sesión no se vincula: si no, alguien podría atar su cuenta de Google a la de otra persona
    usuario_sesion = obtener_proveedor_de_identidad(request, conn).get_usuario_opcional()
    if usuario_sesion is None:
        return _render_oauth_callback_html(False, "Iniciá sesión en Aulento y volvé a vincular Google Libros.")
    try:
        user_id = verificar_state_oauth(state, user_id_sesion=usuario_sesion.id)
    except EstadoGoogleBooksInvalido as e:
        return _render_oauth_callback_html(False, str(e))

    base_url = str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/api/books/google/oauth-callback"

    connector = GoogleBooksConnector(conn, user_id)
    try:
        connector.canjear_codigo(code, redirect_uri)
        return _render_oauth_callback_html(True, "¡Google Play Libros vinculado con éxito!")
    except (GoogleBooksError, Exception) as e:
        logger.exception("Error al canjear código de Google Books")
        return _render_oauth_callback_html(False, f"Error al vincular con Google Books: {e}")


@router.post("/google/sync")
def sync_google_books(usuario: Cuenta, conn: Conexion):
    """Ejecuta la sincronización de estanterías y posiciones de Google Play Libros."""
    connector = GoogleBooksConnector(conn, usuario.id)
    if not connector.esta_autorizado():
        raise HTTPException(status_code=400, detail="Google Play Libros no está vinculado a tu cuenta.")
    try:
        resumen = connector.sincronizar()
        return {"status": "ok", "resultado": resumen}
    except AutorizacionGoogleBooksInvalida as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except GoogleBooksError as e:
        raise HTTPException(status_code=502, detail=f"Error en Google Books API: {e}") from e


@router.delete("/google/authorize", dependencies=[SinCuentaCompartida])
def disconnect_google_books(usuario: Cuenta, conn: Conexion):
    """Desvincula Google Play Libros de la cuenta del usuario."""
    connector = GoogleBooksConnector(conn, usuario.id)
    ok = connector.desconectar()
    return {"status": "desconectado", "ok": ok}


def _render_oauth_callback_html(ok: bool, mensaje: str) -> Response:
    titulo = "Google Play Libros Conectado" if ok else "Autorización No Completada"
    color = "#10b981" if ok else "#ef4444"
    code = 200 if ok else 400

    titulo_escapado = html.escape(titulo)
    mensaje_escapado = html.escape(mensaje)

    html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>{titulo_escapado}</title>
  <style>
    body {{
      font-family: system-ui, -apple-system, sans-serif;
      background: #0f172a;
      color: #f8fafc;
      display: flex;
      align-items: center;
      justify-content: center;
      height: 100vh;
      margin: 0;
    }}
    .card {{
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 1rem;
      padding: 2rem;
      max-width: 420px;
      text-align: center;
    }}
    h1 {{ color: {color}; font-size: 1.25rem; margin-bottom: 0.75rem; }}
    p {{ color: #94a3b8; font-size: 0.875rem; line-height: 1.5; }}
    button {{
      margin-top: 1rem;
      background: #334155;
      color: #fff;
      border: none;
      padding: 0.5rem 1.25rem;
      border-radius: 0.5rem;
      cursor: pointer;
    }}
  </style>
</head>
<body>
  <div class="card">
    <h1>{titulo_escapado}</h1>
    <p>{mensaje_escapado}</p>
    <p style="font-size: 0.75rem; color: #64748b;">Podés cerrar esta ventana para volver a Aulento.</p>
    <button onclick="window.close()">Cerrar ventana</button>
  </div>
  <script>
    try {{
      if (window.opener) {{
        window.opener.postMessage({{ type: 'google_books_auth_complete', ok: {str(ok).lower()} }}, '*');
      }}
    }} catch (e) {{}}
  </script>
</body>
</html>"""
    return Response(content=html_content, media_type="text/html", status_code=code)


# ----------------------------------------------------------------------
# Lectura Activa con IA y Cosecha FSRS (Feature 042)
# ----------------------------------------------------------------------


@router.post("/{book_id}/active-recall/generate", response_model=ActiveRecallGenerateResponse)
def generate_book_active_recall(
    book_id: int,
    usuario: Cuenta,
    conn: Conexion,
    data: ActiveRecallGenerateRequest | None = None,
):
    """Genera un cuestionario de Active Recall conceptual sobre el tramo leído del libro."""
    service = BookActiveRecallService(conn, usuario.id)
    try:
        return service.generar_preguntas(book_id, data)
    except ValueError:
        raise no_encontrado("Libro", book_id)


@router.post("/{book_id}/active-recall/evaluate", response_model=ActiveRecallEvaluateResponse)
def evaluate_book_active_recall(
    book_id: int,
    data: ActiveRecallEvaluateRequest,
    usuario: Cuenta,
    conn: Conexion,
):
    """Evalúa las respuestas provistas por el estudiante para el cuestionario de Active Recall."""
    service = BookActiveRecallService(conn, usuario.id)
    try:
        return service.evaluar_respuestas(book_id, data)
    except ValueError:
        raise no_encontrado("Libro", book_id)


@router.post("/{book_id}/harvest/preview", response_model=BookHarvestPreviewResponse)
def preview_book_harvest(
    book_id: int,
    usuario: Cuenta,
    conn: Conexion,
    data: BookHarvestPreviewRequest | None = None,
):
    """Genera tarjetas candidatas FSRS de vocabulario técnico en inglés extraídas del libro."""
    service = BookActiveRecallService(conn, usuario.id)
    try:
        return service.previsualizar_cosecha(book_id, data)
    except ValueError:
        raise no_encontrado("Libro", book_id)


@router.post("/{book_id}/harvest/commit", response_model=BookHarvestCommitResponse)
def commit_book_harvest(
    book_id: int,
    data: BookHarvestCommitRequest,
    usuario: Cuenta,
    conn: Conexion,
):
    """Inserta las tarjetas seleccionadas en el mazo FSRS de la cuenta."""
    service = BookActiveRecallService(conn, usuario.id)
    try:
        return service.confirmar_cosecha(book_id, data)
    except ValueError:
        raise no_encontrado("Libro", book_id)
