"""Comandos CLI del servidor Model Context Protocol y de sus tokens."""

import os

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from aulento.auth import servicio
from aulento.auth.modelos import TokenMcpNoEncontrado
from aulento.auth.repositorio import RepositorioAuth
from aulento.cli.contexto import (
    CuentaNoResuelta,
    resolver_cuenta_de_la_cli,
    terminar_por_migracion_fallida,
)
from aulento.core.exposicion import (
    AVISO_HTTP_SIN_CIFRAR,
    ExposicionRechazada,
    ProxyDeConfianzaInvalido,
    es_bucle_local,
    exigir_condiciones_para_exponerse,
)
from aulento.core.extensiones import (
    cargar_extensiones_del_entorno,
    registrar_extensiones,
)
from aulento.db.connection import get_connection
from aulento.db.migrations import ErrorDeMigracion, migrar
from aulento.mcp.server import (
    normalizar_host_permitido,
    run_sse_server,
    run_stdio_server,
)

mcp_app = typer.Typer(help="Servidor Model Context Protocol con las herramientas académicas y sus tokens")
token_app = typer.Typer(help="Tokens con los que cada cuenta entra al servidor MCP por red (administración)")
mcp_app.add_typer(token_app, name="token")
console = Console()
# En stdio la salida estándar es el canal del protocolo MCP: los avisos van por stderr
err_console = Console(stderr=True)

# Cómo se dicen en el servidor MCP los avisos de exposición, donde lo que protege el acceso es el token
AVISOS_DEL_SERVIDOR_MCP = {
    AVISO_HTTP_SIN_CIFRAR: (
        "[bold yellow]⚠ Acceso remoto sin cifrar:[/bold yellow] el servidor acepta conexiones de otros equipos "
        "por HTTP. Solo el token lo protege: usalo en una red de confianza o detrás de un túnel cifrado."
    ),
}

@mcp_app.command("serve")
def cmd_mcp_serve(
    transport: str = typer.Option("stdio", "--transport", "-t", help="Transporte MCP: 'stdio', 'http' (Streamable HTTP, recomendado por red) o 'sse'"),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host para modo SSE/HTTP"),
    port: int = typer.Option(8000, "--port", "-p", help="Puerto TCP para modo SSE/HTTP"),
    read_only: bool = typer.Option(False, "--read-only", help="Activar modo seguro de solo lectura"),
    allow_remote: bool = typer.Option(False, "--allow-remote", help="Permitir conexiones de otros equipos (escucha en 0.0.0.0); exige la clave maestra por variable y certificado, proxy de confianza o --insecure-http"),
    ssl_certfile: str | None = typer.Option(None, "--ssl-certfile", help="Certificado TLS (PEM) para servir por HTTPS"),
    ssl_keyfile: str | None = typer.Option(None, "--ssl-keyfile", help="Clave privada TLS (PEM) del certificado"),
    insecure_http: bool = typer.Option(False, "--insecure-http", help="Aceptar --allow-remote sin cifrado (solo en una red de confianza)"),
    allowed_host: list[str] | None = typer.Option(None, "--allowed-host", help="Host permitido en la cabecera Host/Origin (repetible), ej. mi-pc.local"),  # noqa: B008
):
    """Ejecuta el servidor MCP de Aulento para Claude Desktop, Cursor o clientes remotos."""
    extensiones = cargar_extensiones_del_entorno()
    desregistrar = registrar_extensiones(extensiones)
    try:
        t = transport.lower().strip()
        if t == "stdio":
            try:
                cuenta = resolver_cuenta_de_la_cli()
            except CuentaNoResuelta as error:
                err_console.print(f"[bold red]Error:[/bold red] {escape(str(error))}", soft_wrap=True)
                raise typer.Exit(code=1) from None
            except ErrorDeMigracion as error:
                raise terminar_por_migracion_fallida(error, consola=err_console) from None
            err_console.print(
                f"[dim]Iniciando Aulento MCP Server en stdio como '{escape(cuenta.nombre_usuario)}' "
                "(Modo seguro por subproceso)...[/dim]"
            )
            if read_only:
                err_console.print("[yellow]🛡️ Modo READ-ONLY activado: Herramientas de modificación desactivadas.[/yellow]")
            run_stdio_server(user_id=cuenta.id, read_only=read_only)
        elif t in ("sse", "http", "streamable-http"):
            red = "sse" if t == "sse" else "http"
            bind_host = "0.0.0.0" if allow_remote else host
            if bool(ssl_certfile) != bool(ssl_keyfile):
                console.print("[bold red]Error:[/bold red] --ssl-certfile y --ssl-keyfile van juntos: falta uno de los dos.")
                raise typer.Exit(code=1)
            for archivo in (ssl_certfile, ssl_keyfile):
                if archivo and not os.path.isfile(archivo):
                    console.print(f"[bold red]Error:[/bold red] No existe el archivo TLS: {archivo}")
                    raise typer.Exit(code=1)
            cifrado = bool(ssl_certfile and ssl_keyfile)
            # Cuenta la dirección en la que se escucha, no el flag: `--host 0.0.0.0` también expone el servidor
            expuesto = not es_bucle_local(bind_host)
            try:
                hosts_permitidos = [normalizar_host_permitido(h) for h in (allowed_host or [])]
            except ValueError as e:
                console.print(f"[bold red]Error:[/bold red] {e}")
                raise typer.Exit(code=1)
            try:
                avisos = exigir_condiciones_para_exponerse(bind_host, cifrado=cifrado, insecure_http=insecure_http)
            except (ExposicionRechazada, ProxyDeConfianzaInvalido) as error:
                console.print(f"[bold red]Error:[/bold red] {escape(str(error))}")
                raise typer.Exit(code=1) from None

            esquema = "https" if cifrado else "http"
            ruta = "/sse" if red == "sse" else "/mcp"
            nombre = "SSE" if red == "sse" else "Streamable HTTP"
            console.print(f"[bold cyan]🚀 Iniciando Aulento MCP Server en {nombre} en {esquema}://{bind_host}:{port}{ruta}[/bold cyan]")
            if red == "sse":
                console.print(
                    "[yellow]Aviso: con la versión instalada de la librería MCP, el transporte SSE responde a los mensajes del cliente "
                    "con una respuesta HTTP mal formada y los clientes estrictos cortan la sesión. Por red usá --transport http.[/yellow]"
                )
            if read_only:
                console.print("[yellow]🛡️ Modo READ-ONLY activado.[/yellow]")
            for aviso in avisos:
                console.print(AVISOS_DEL_SERVIDOR_MCP.get(aviso, f"[bold yellow]⚠[/bold yellow] {escape(aviso)}"))
            if expuesto and not hosts_permitidos:
                console.print(
                    "[yellow]Sin --allowed-host no se controla la cabecera Host/Origin de las peticiones remotas.[/yellow]"
                )
            run_sse_server(
                host=bind_host,
                port=port,
                read_only=read_only,
                ssl_certfile=ssl_certfile,
                ssl_keyfile=ssl_keyfile,
                allowed_hosts=hosts_permitidos or None,
                transport=red,
            )
        else:
            console.print(f"[bold red]Error:[/bold red] Transporte '{transport}' no reconocido. Use 'stdio', 'http' o 'sse'.")
            raise typer.Exit(code=1)
    finally:
        desregistrar()


def _cuenta_por_nombre(conn, usuario: str):
    fila = RepositorioAuth(conn).usuario_por_nombre(usuario.strip().lower())
    if fila is None:
        console.print(f"[bold red]Error:[/bold red] No existe una cuenta llamada '{escape(usuario)}'.")
        raise typer.Exit(code=1)
    return fila


@token_app.command("create")
def cmd_mcp_token_create(
    usuario: str = typer.Argument(..., help="Nombre de la cuenta dueña del token"),
    name: str | None = typer.Option(None, "--name", "-n", help="Etiqueta para reconocer el token (ej. 'Claude Desktop')"),
):
    """Crea un token MCP para una cuenta y lo muestra una única vez."""
    conn = get_connection()
    try:
        migrar(conn)
        fila = _cuenta_por_nombre(conn, usuario)
        if not fila["activo"]:
            console.print(f"[bold red]Error:[/bold red] La cuenta '{escape(usuario)}' está desactivada.")
            raise typer.Exit(code=1)
        emitido = servicio.crear_token_mcp(conn, fila["id"], name)
    finally:
        conn.close()

    console.print(f"[bold green]✔ Token MCP {emitido.id} creado para '{escape(fila['nombre_usuario'])}'.[/bold green]")
    # Sin formato ni recorte: el token se copia tal cual
    console.print(emitido.token, markup=False, highlight=False, soft_wrap=True)
    console.print(
        "[yellow]Guardalo ahora: no se vuelve a mostrar.[/yellow] "
        "[dim]El cliente lo envía en el encabezado 'Authorization: Bearer <token>'.[/dim]"
    )


@token_app.command("list")
def cmd_mcp_token_list(
    usuario: str | None = typer.Argument(None, help="Nombre de la cuenta; sin indicarla, los tokens de todas"),
):
    """Lista los tokens MCP (de una cuenta o de todas) sin mostrar ninguno."""
    conn = get_connection()
    try:
        migrar(conn)
        usuario_id = _cuenta_por_nombre(conn, usuario)["id"] if usuario is not None else None
        tokens = servicio.listar_tokens_mcp(conn, usuario_id)
    finally:
        conn.close()

    if not tokens:
        console.print("[yellow]No hay tokens MCP.[/yellow] Creá uno con 'aulento mcp token create <usuario>'.")
        return

    table = Table(title="🔑 Tokens del servidor MCP")
    table.add_column("ID", style="dim")
    table.add_column("Cuenta", style="bold cyan")
    table.add_column("Nombre")
    table.add_column("Creado")
    table.add_column("Último uso")
    table.add_column("Estado")
    for t in tokens:
        table.add_row(
            str(t["id"]),
            escape(t["nombre_usuario"]),
            escape(t["nombre"] or "-"),
            t["creado_en"][:16].replace("T", " "),
            t["ultimo_uso"][:16].replace("T", " ") if t["ultimo_uso"] else "Nunca",
            f"[red]Revocado {t['revocado_en'][:10]}[/red]" if t["revocado_en"] else "[green]Vigente[/green]",
        )
    console.print(table)


@token_app.command("revoke")
def cmd_mcp_token_revoke(
    token_id: int = typer.Argument(..., help="ID del token tal como lo muestra 'mcp token list'"),
):
    """Revoca un token MCP: el cliente que lo usa deja de entrar en el acto."""
    conn = get_connection()
    try:
        migrar(conn)
        try:
            servicio.revocar_token_mcp(conn, token_id)
        except TokenMcpNoEncontrado:
            console.print(f"[bold red]Error:[/bold red] No hay un token vigente con ID {token_id}.")
            raise typer.Exit(code=1) from None
    finally:
        conn.close()
    console.print(f"[bold green]✔ Token MCP {token_id} revocado.[/bold green]")
