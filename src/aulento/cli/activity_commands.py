"""Comandos CLI para visualización de actividad diaria, rachas y retención macro."""

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from aulento.cli.contexto import cuenta_de_la_cli
from aulento.core.activity_tracker import ActivityTracker
from aulento.roadmap.macro_fsrs import MacroFSRSEngine

activity_app = typer.Typer(name="activity", help="Métricas de consistencia diaria, rachas y Heatmap de estudio.")
console = Console()


@activity_app.command(name="streak")
def show_streak():
    """Muestra la racha de estudio actual y el récord histórico."""
    tracker = ActivityTracker(cuenta_de_la_cli().id)
    data = tracker.get_heatmap(days=7)
    s = data.streak

    panel_text = (
        f"[bold green]🔥 Racha Actual:[/bold green] [bold white]{s.current_streak} días[/bold white]\n"
        f"[bold yellow]🏆 Racha Récord:[/bold yellow] [bold white]{s.longest_streak} días[/bold white]\n"
        f"[bold cyan]📅 Total Días Activos:[/bold cyan] {s.total_active_days}\n"
        f"[bold magenta]⏱️ Minutos Estudiados:[/bold magenta] {s.total_study_minutes} min ({s.total_study_minutes/60:.1f} hrs)\n"
        f"[bold blue]📖 Páginas Leídas:[/bold blue] {s.total_pages_read}\n"
        f"[bold]🧠 Tarjetas Repasadas:[/bold] {s.total_fsrs_reviews}\n"
        f"[bold green]🎓 Temas Completados:[/bold green] {s.total_topics_completed}"
    )
    console.print(Panel(panel_text, title="📊 Hábitos y Consistencia de Estudio", border_style="green"))


@activity_app.command(name="heatmap")
def show_heatmap(days: int = typer.Option(30, "--days", "-d", help="Número de días a mostrar (ej. 14, 30, 60)")):
    """Muestra el resumen de actividad reciente por fecha con su score ponderado."""
    tracker = ActivityTracker(cuenta_de_la_cli().id)
    data = tracker.get_heatmap(days=days)

    table = Table(title=f"📅 Actividad de Estudio (Últimos {days} días)", border_style="cyan")
    table.add_column("Fecha", style="white")
    table.add_column("Score", justify="right", style="bold green")
    table.add_column("Nivel", justify="center")
    table.add_column("Pomodoro", justify="right", style="magenta")
    table.add_column("FSRS", justify="right", style="cyan")
    table.add_column("Páginas", justify="right", style="blue")
    table.add_column("Temas", justify="right", style="green")

    intensity_symbols = {
        0: "[dim]·[/dim]",
        1: "[green]▪[/green]",
        2: "[bold green]■[/bold green]",
        3: "[bold yellow]█[/bold yellow]",
        4: "[bold red]🔥[/bold red]",
    }

    for d in data.days:
        if d.score > 0 or days <= 14:
            table.add_row(
                d.date,
                f"{d.score:.1f}",
                intensity_symbols.get(d.level, "·"),
                f"{d.study_minutes} min",
                str(d.fsrs_reviews),
                str(d.pages_read),
                str(d.topics_completed),
            )

    console.print(table)
    console.print(f"[bold green]🔥 Racha actual:[/bold green] {data.streak.current_streak} días consecutivas | [bold yellow]Récord:[/bold yellow] {data.streak.longest_streak} días")


@activity_app.command(name="due-topics")
def show_due_topics():
    """Lista los temas completados del Roadmap que requieren repaso espaciado macro hoy."""
    engine = MacroFSRSEngine(cuenta_de_la_cli().id)
    topics = engine.repo.get_due_topics()

    if not topics:
        console.print("[green]🎉 ¡No tienes temas pendientes de repaso macro hoy! Todo tu conocimiento está al día.[/green]")
        return

    table = Table(title=f"🧠 Temas para Repaso Macro FSRS ({len(topics)} pendientes)", border_style="yellow")
    table.add_column("ID", style="dim")
    table.add_column("Tema", style="bold white")
    table.add_column("Ruta", style="cyan")
    table.add_column("Próximo Vencimiento", style="yellow")
    table.add_column("Intervalo (Días)", justify="right")
    table.add_column("Repasos", justify="right")

    for t in topics:
        due_str = str(t.due_date)[:10] if t.due_date else "Hoy"
        table.add_row(
            str(t.tema_id),
            t.tema_titulo or f"Tema #{t.tema_id}",
            t.ruta_titulo or "Ruta",
            due_str,
            str(t.scheduled_days),
            str(t.reps),
        )

    console.print(table)
    console.print("[dim]Usa la Web UI o MCP Copilot para realizar el Micro-Quiz Feynman de 3 minutos.[/dim]")
