"""Comandos CLI para consultar y sincronizar el perfil y racha de Duolingo de la cuenta."""

from typing import Optional

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from aulento.cli.contexto import cuenta_de_la_cli
from aulento.connectors.duolingo import ESTADO_SIN_CONFIGURAR, DuolingoClient, DuolingoSinConfigurar
from aulento.db.connection import get_connection

duolingo_app = typer.Typer(help="Comandos para sincronización de racha y estadísticas de Duolingo")
console = Console()


@duolingo_app.command("set-user")
def cmd_duolingo_set_user(
    username: Optional[str] = typer.Argument(None, help="Nombre de usuario público en Duolingo"),
    clear: bool = typer.Option(False, "--clear", help="Quitar el usuario configurado y su caché"),
):
    """Fija (o quita, con --clear) el usuario de Duolingo de la cuenta."""
    if clear == bool(username and username.strip()):
        console.print("[bold red]✖ Indicá un usuario de Duolingo o --clear, no las dos cosas.[/bold red]")
        raise typer.Exit(code=1)

    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        vigente = DuolingoClient(conn, cuenta.id).fijar_usuario(None if clear else username)
    finally:
        conn.close()

    if vigente is None:
        console.print(f"[green]✔ La cuenta {escape(cuenta.nombre_usuario)} quedó sin usuario de Duolingo.[/green]")
    else:
        console.print(
            f"[green]✔ Usuario de Duolingo de la cuenta {escape(cuenta.nombre_usuario)}: "
            f"[bold]{escape(vigente)}[/bold].[/green]"
        )


@duolingo_app.command("status")
def cmd_duolingo_status(
    username: Optional[str] = typer.Option(
        None,
        "--username",
        "-u",
        help="Usuario público en Duolingo a consultar; por defecto, el configurado para la cuenta",
    ),
):
    """Consulta el estado actual de racha, XP y cursos de Duolingo."""
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        profile = DuolingoClient(conn, cuenta.id).get_profile(username=username)
    except DuolingoSinConfigurar as e:
        console.print(f"[bold yellow]⚠ {escape(str(e))}[/bold yellow]", soft_wrap=True)
        raise typer.Exit(code=1) from None
    except Exception as e:
        console.print(f"[bold red]✖ Error al consultar Duolingo:[/bold red] {e}")
        raise typer.Exit(code=1)
    finally:
        conn.close()

    source_badge = "[dim](Datos en Caché Local)[/dim]" if profile.is_cached else "[green](Conexión en Vivo)[/green]"

    info_text = (
        f"[bold white]{profile.name}[/bold white] (@{profile.username}) {source_badge}\n\n"
        f"🔥 [bold yellow]Racha Actual:[/bold yellow] [bold green]{profile.streak} días[/bold green]\n"
        f"⚡ [bold cyan]Puntos de Experiencia (XP):[/bold cyan] [bold]{profile.total_xp:,}[/bold]\n"
        f"🌐 [bold magenta]Idioma de Aprendizaje:[/bold magenta] [bold]{profile.learning_language.upper()}[/bold] ({profile.current_course_title})\n"
    )

    if profile.streak_start_date and profile.streak_end_date:
        info_text += f"📅 [dim]Período de racha activa: {profile.streak_start_date} al {profile.streak_end_date}[/dim]\n"

    console.print(Panel(info_text.strip(), title="🦉 Duolingo — Perfil de Aprendizaje", border_style="green"))

    if profile.courses:
        table = Table(title="Cursos Activos en Duolingo", border_style="dim")
        table.add_column("Curso", style="bold white")
        table.add_column("Idioma Destino", style="cyan")
        table.add_column("XP Acumulado", style="yellow", justify="right")
        table.add_column("Coronas", style="magenta", justify="right")

        for c in profile.courses:
            table.add_row(c.title, c.learning_language.upper(), f"{c.xp:,}", str(c.crowns))

        console.print(table)


@duolingo_app.command("sync")
def cmd_duolingo_sync(
    username: Optional[str] = typer.Option(
        None,
        "--username",
        "-u",
        help="Usuario público en Duolingo; si se indica, pasa a ser el de la cuenta",
    ),
):
    """Fuerza la sincronización en vivo con Duolingo y actualiza la caché de la cuenta."""
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        client = DuolingoClient(conn, cuenta.id)
        a_sincronizar = (username or "").strip().lower() or client.usuario_configurado()
        if a_sincronizar:
            console.print(f"[cyan]Sincronizando perfil de Duolingo para [bold]{escape(a_sincronizar)}[/bold]...[/cyan]")
        result = client.sync(username=username)
    finally:
        conn.close()

    if result.status == ESTADO_SIN_CONFIGURAR:
        console.print(f"[bold yellow]⚠ {escape(result.message)}[/bold yellow]", soft_wrap=True)
        raise typer.Exit(code=1)
    if result.status == "error":
        console.print(f"[bold red]✖ {result.message}[/bold red]")
        raise typer.Exit(code=1)

    source_tag = "[green]en vivo[/green]" if result.source == "live" else "[yellow]desde caché[/yellow]"
    console.print(
        f"[bold green]✔ Sincronización exitosa ({source_tag}):[/bold green] "
        f"Racha: [bold yellow]🔥 {result.streak} días[/bold yellow] | "
        f"XP Total: [bold cyan]⚡ {result.total_xp:,}[/bold cyan]."
    )
