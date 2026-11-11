import json
import os
import sys
import webbrowser
from pathlib import Path

import typer
import uvicorn
from rich.console import Console
from rich.markup import escape

from aulento.config import ModoInvalido
from aulento.core.exposicion import (
    ExposicionRechazada,
    ProxyDeConfianzaInvalido,
    es_bucle_local,
    exigir_condiciones_para_exponerse,
    exigir_modo_compatible_con_la_exposicion,
)

console = Console()
web_app = typer.Typer(name="web", help="Servidor y dashboard web local de Aulento", no_args_is_help=False)

VARIABLE_DE_HOSTS_PERMITIDOS = "AULENTO_ALLOWED_HOSTS"
APLICACION_DEL_CORE = "aulento.web.app:app"


def run_web_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
    open_browser: bool = False,
    ssl_certfile: str | None = None,
    ssl_keyfile: str | None = None,
    insecure_http: bool = False,
    aplicacion: str = APLICACION_DEL_CORE,
) -> None:
    """Arranca el servidor web con las reglas de exposición del ADR 013 y del modo (ADR 017).

    Sale con código 1 si no se cumplen. `aplicacion` es la ruta `modulo:variable` que levanta Uvicorn: la del
    core por defecto, o la de un paquete que lo extiende (por ejemplo, la de la nube).
    """
    if bool(ssl_certfile) != bool(ssl_keyfile):
        console.print("[bold red]Error:[/bold red] --ssl-certfile y --ssl-keyfile van juntos: falta uno de los dos.")
        raise typer.Exit(code=1)
    for archivo in (ssl_certfile, ssl_keyfile):
        if archivo and not os.path.isfile(archivo):
            console.print(f"[bold red]Error:[/bold red] No existe el archivo TLS: {escape(archivo)}")
            raise typer.Exit(code=1)
    cifrado = bool(ssl_certfile and ssl_keyfile)
    try:
        exigir_modo_compatible_con_la_exposicion(host)
        avisos = exigir_condiciones_para_exponerse(host, cifrado=cifrado, insecure_http=insecure_http)
    except (ExposicionRechazada, ProxyDeConfianzaInvalido, ModoInvalido) as error:
        console.print(f"[bold red]Error:[/bold red] {escape(str(error))}", soft_wrap=True)
        raise typer.Exit(code=1) from None

    local = es_bucle_local(host)
    esquema = "https" if cifrado else "http"
    # Una dirección IPv6 va entre corchetes en la URL
    host_en_url = f"[{host}]" if ":" in host and not host.startswith("[") else host
    url = f"{esquema}://{host_en_url}:{port}/"
    console.print(f"[bold cyan]⚡ Iniciando Aulento Web Dashboard en:[/bold cyan] [bold underline green]{url}[/bold underline green]")
    for aviso in avisos:
        console.print(f"[bold yellow]⚠[/bold yellow] {escape(aviso)}", soft_wrap=True)
    # Mismo criterio que `web.app.get_allowed_hosts`: cuentan solo los nombres no vacíos de la lista
    hosts_extra = [h.strip() for h in os.getenv(VARIABLE_DE_HOSTS_PERMITIDOS, "").split(",") if h.strip()]
    if not local and not hosts_extra:
        console.print(
            f"[yellow]Sin {VARIABLE_DE_HOSTS_PERMITIDOS} el servidor solo responde a pedidos dirigidos a un nombre "
            "local (127.0.0.1, localhost): agregá ahí el nombre o la IP con que lo van a abrir.[/yellow]",
            soft_wrap=True,
        )
    console.print("[dim]Presioná Ctrl+C para detener el servidor.[/dim]\n")

    # El navegador se abre en esta máquina: solo tiene sentido si el servidor escucha en ella
    if open_browser and local:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001, S110
            pass

    opciones: dict = {"host": host, "port": port, "reload": reload, "proxy_headers": False}
    if cifrado:
        opciones.update(ssl_certfile=ssl_certfile, ssl_keyfile=ssl_keyfile)
    # Las cabeceras de proxy las resuelve la aplicación con AULENTO_TRUSTED_PROXIES, no Uvicorn
    uvicorn.run(aplicacion, **opciones)


OPCION_HOST = typer.Option("127.0.0.1", "--host", "-h", help="Dirección IP del servidor")
OPCION_PUERTO = typer.Option(8000, "--port", "-p", help="Puerto HTTP")
OPCION_RELOAD = typer.Option(False, "--reload", help="Habilitar autoreload para desarrollo")
OPCION_NAVEGADOR = typer.Option(True, "--open-browser/--no-open-browser", help="Abrir automáticamente el navegador")
OPCION_CERTIFICADO = typer.Option(None, "--ssl-certfile", help="Certificado TLS (PEM) para servir por HTTPS")
OPCION_CLAVE_TLS = typer.Option(None, "--ssl-keyfile", help="Clave privada TLS (PEM) del certificado")
OPCION_SIN_CIFRAR = typer.Option(
    False, "--insecure-http", help="Escuchar fuera de esta máquina sin cifrado (solo en una red de confianza)"
)
OPCION_APLICACION = typer.Option(
    APLICACION_DEL_CORE,
    "--app",
    hidden=True,
    help="Aplicación que levanta Uvicorn (modulo:variable); la del core por defecto",
)
OPCION_OUTPUT = typer.Option(
    None,
    "--output",
    "-o",
    help="Ruta de archivo donde escribir el esquema OpenAPI (si se omite, sale por stdout).",
)


@web_app.callback(invoke_without_command=True)
def main_web(
    ctx: typer.Context,
    host: str = OPCION_HOST,
    port: int = OPCION_PUERTO,
    reload: bool = OPCION_RELOAD,
    open_browser: bool = OPCION_NAVEGADOR,
    ssl_certfile: str | None = OPCION_CERTIFICADO,
    ssl_keyfile: str | None = OPCION_CLAVE_TLS,
    insecure_http: bool = OPCION_SIN_CIFRAR,
):
    """Inicia el servidor web local con FastAPI y Uvicorn."""
    if ctx.invoked_subcommand is None:
        run_web_server(host, port, reload, open_browser, ssl_certfile, ssl_keyfile, insecure_http)


@web_app.command(name="start")
def start_server(
    host: str = OPCION_HOST,
    port: int = OPCION_PUERTO,
    reload: bool = OPCION_RELOAD,
    open_browser: bool = OPCION_NAVEGADOR,
    ssl_certfile: str | None = OPCION_CERTIFICADO,
    ssl_keyfile: str | None = OPCION_CLAVE_TLS,
    insecure_http: bool = OPCION_SIN_CIFRAR,
    aplicacion: str = OPCION_APLICACION,
):
    """Inicia explícitamente el servidor web."""
    run_web_server(host, port, reload, open_browser, ssl_certfile, ssl_keyfile, insecure_http, aplicacion)


def esquema_openapi_canonico() -> str:
    """Retorna el esquema OpenAPI de la aplicación web serializado en JSON canónico."""
    from aulento.web.app import app

    esquema = app.openapi()
    return json.dumps(esquema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


@web_app.command(name="openapi")
def exportar_openapi(
    output: Path | None = OPCION_OUTPUT,
) -> None:
    """Exporta el esquema OpenAPI canónico en JSON hacia un archivo o stdout."""
    contenido = esquema_openapi_canonico()
    if output is None:
        sys.stdout.write(contenido)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(contenido, encoding="utf-8")
    console.print(f"[bold green]✔[/bold green] Esquema OpenAPI exportado en [cyan]{output}[/cyan]")
