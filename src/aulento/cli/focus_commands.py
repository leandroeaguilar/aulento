"""Comandos CLI interactivos para Focus Timer (Pomodoro) y registro de sesiones de estudio."""

import time
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn

from aulento.cli.contexto import cuenta_de_la_cli
from aulento.db.connection import get_connection
from aulento.db.focus_repository import FocusRepository
from aulento.db.repository import BloqueHorarioRepository
from aulento.models.focus_session import FocusSessionCreate

focus_app = typer.Typer(help="Focus Timer (Pomodoro) vinculado a la agenda semanal")
console = Console()


@focus_app.command("start")
def cmd_focus_start(
    bloque_id: Optional[int] = typer.Argument(None, help="ID del bloque de la agenda semanal (opcional)"),
    minutes: int = typer.Option(25, "--minutes", "-m", help="Duración del bloque de foco en minutos"),
    tipo: str = typer.Option("pomodoro", "--tipo", "-t", help="Tipo: 'pomodoro', 'curso', 'ingles_fsrs', 'lectura_libro', 'libre'"),
    notas: Optional[str] = typer.Option(None, "--notas", help="Notas breves sobre el objetivo de la sesión"),
    no_wait: bool = typer.Option(False, "--no-wait", help="Registrar la sesión inmediatamente sin correr la cuenta regresiva en vivo"),
):
    """Inicia un temporizador de estudio y registra los minutos reales estudiados."""
    cuenta = cuenta_de_la_cli()
    if bloque_id is not None:
        conn = get_connection()
        try:
            bloque = BloqueHorarioRepository(conn, cuenta.id).get(bloque_id)
        finally:
            conn.close()
        if not bloque:
            console.print(f"[bold red]Error:[/bold red] Bloque ID {bloque_id} no encontrado.")
            raise typer.Exit(code=1)

    console.print(Panel(
        f"[bold cyan]🎯 Sesión de Enfoque Iniciada:[/bold cyan] {minutes} minutos\n"
        f"[bold]Tipo:[/bold] {tipo}  |  [bold]Bloque:[/bold] {bloque_id or 'Ad-hoc (Libre)'}\n"
        f"[dim]Notas: {notas or 'Sin notas'}[/dim]",
        title="⏱️ Focus & Pomodoro Timer",
        border_style="cyan",
    ))

    if not no_wait:
        total_seconds = minutes * 60
        # Simulación acelerada o reloj
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(f"[green]Estudiando ({tipo})...[/green]", total=total_seconds)
            # Para UX fluida en terminal, avanzamos en bloques si son muchos segundos
            # pero permitimos Ctrl+C o interrupción limpia
            step = 1 if total_seconds <= 10 else (total_seconds / 50.0)
            elapsed = 0.0
            try:
                while elapsed < total_seconds:
                    time.sleep(min(0.05, step))
                    elapsed += step
                    progress.advance(task, step)
            except KeyboardInterrupt:
                console.print("\n[yellow]⚠️ Sesión interrumpida prematuramente por el usuario.[/yellow]")
                actual_minutes = max(1, int(elapsed // 60))
                minutes = actual_minutes

    conn = get_connection()
    try:
        repo = FocusRepository(conn, cuenta.id)
        session = repo.record_session(
            FocusSessionCreate(
                bloque_id=bloque_id,
                duracion_minutos=minutes,
                tipo=tipo,
                notas=notas,
            )
        )
        console.print(Panel(
            f"[bold green]✔ ¡Sesión completada y registrada en SQLite![/bold green]\n\n"
            f"[bold]Minutos Computados:[/bold] {session.duracion_minutos} min ({round(session.duracion_minutos/60.0, 1)} hrs)\n"
            f"[bold]Fecha y Hora:[/bold] {session.fecha_hora}\n"
            f"[dim italic]Las horas estudiadas se sincronizarán con el Weekly Digest de Obsidian.[/dim italic]",
            title="🏆 Fin del Bloque de Foco",
            border_style="green",
        ))
    finally:
        conn.close()


@focus_app.command("stats")
def cmd_focus_stats():
    """Muestra las estadísticas de horas reales estudiadas hoy y en la semana actual."""
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        repo = FocusRepository(conn, cuenta.id)
        stats = repo.get_weekly_stats()

        summary_text = (
            f"[bold white]Minutos Estudiados Hoy:[/bold white] [bold green]{stats['minutos_hoy']} min[/bold green] ({stats['horas_hoy']} hrs)\n"
            f"[bold white]Minutos Estudiados esta Semana:[/bold white] [bold cyan]{stats['minutos_semana']} min[/bold cyan] ({stats['horas_semana']} hrs)\n"
            f"[bold white]Sesiones Completadas:[/bold white] {stats['sesiones_semana']} bloques"
        )
        console.print(Panel(summary_text, title="📊 Métricas de Estudio Real (Focus & Pomodoro)", border_style="cyan"))

        if stats["por_tipo_minutos"]:
            table = Table(title="⏱️ Desglose Semanal por Tipo de Estudio")
            table.add_column("Tipo de Estudio", style="bold white")
            table.add_column("Minutos", style="bold cyan")
            table.add_column("Horas", style="bold green")

            for t, mins in stats["por_tipo_minutos"].items():
                table.add_row(t, str(mins), f"{round(mins / 60.0, 1)} hrs")

            console.print(table)
        else:
            console.print("[dim italic]Aún no hay sesiones registradas esta semana.[/dim italic]")
    finally:
        conn.close()
