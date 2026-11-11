"""Comandos CLI para inspección del Vault de Obsidian, generación de exámenes y evaluación Feynman."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from aulento.cli.contexto import cuenta_de_la_cli
from aulento.core.secretos import MENSAJE_SECRETO_ILEGIBLE, ClaveMaestraInvalida, SecretoIlegible
from aulento.db.connection import get_connection
from aulento.vault.carpetas import carpetas_del_tutor
from aulento.vault.reader import VaultReader, sembrar_notas_de_muestra
from aulento.vault.rutas import (
    MENSAJE_NOTA_NO_ENCONTRADA,
    CarpetaDeVaultInvalida,
    RutaFueraDelVaultError,
    VaultNoDisponibleError,
    estado_del_vault,
    fijar_vault_externo,
    quitar_vault_externo,
    vault_de_la_cuenta,
)
from aulento.exams.generator import ExamGenerator
from aulento.exams.feynman import FeynmanEvaluator
from aulento.exams.models import FeynmanSubmission, QuestionType
from aulento.vault.sop_course import CourseNoteGenerator, CourseNoteRequest
from aulento.vault.cloud_notes import MaterialNoteGenerator
from aulento.vault.weekly_digest import WeeklyDigestExporter

console = Console()

vault_cli = typer.Typer(name="vault", help="Exploración e indexación del Vault de Obsidian.")
exam_cli = typer.Typer(name="exam", help="Generador de exámenes de Active Recall sobre el Vault.")
feynman_cli = typer.Typer(name="feynman", help="Evaluador interactivo de la Técnica Feynman.")


@contextmanager
def _errores_del_vault() -> Iterator[None]:
    """Termina el comando con su explicación, sin traceback, ante un problema del vault o de un secreto.

    Un vault externo que ya no existe, una ruta o nombre de nota que sale del vault de la cuenta y un secreto
    de la cuenta que no se puede descifrar.
    """
    try:
        yield
    except VaultNoDisponibleError as error:
        console.print(f"[bold red]✖ {escape(str(error))}[/bold red]", soft_wrap=True)
        raise typer.Exit(code=1) from None
    except RutaFueraDelVaultError:
        console.print(f"[bold red]✖ {MENSAJE_NOTA_NO_ENCONTRADA}[/bold red]", soft_wrap=True)
        raise typer.Exit(code=1) from None
    except SecretoIlegible:
        console.print(f"[bold red]✖ {MENSAJE_SECRETO_ILEGIBLE}[/bold red]", soft_wrap=True)
        raise typer.Exit(code=1) from None


ERRORES_CON_EXPLICACION = (VaultNoDisponibleError, RutaFueraDelVaultError, SecretoIlegible, ClaveMaestraInvalida)


@contextmanager
def _otros_errores(titulo: str) -> Iterator[None]:
    """Muestra con ese título cualquier otro error del comando; los de `_errores_del_vault` siguen de largo."""
    try:
        yield
    except ERRORES_CON_EXPLICACION:
        raise
    except Exception as e:
        console.print(f"[bold red]{titulo}:[/bold red] {e}")


def _vault_de_la_cli() -> Path:
    """Carpeta del vault de la cuenta de la CLI."""
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        return vault_de_la_cuenta(conn, cuenta.id)
    finally:
        conn.close()


def _lector_de_la_cli() -> VaultReader:
    """Lector de las notas del vault de la cuenta de la CLI, en las carpetas que eligió para el tutor."""
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        return VaultReader(vault_de_la_cuenta(conn, cuenta.id), carpetas=carpetas_del_tutor(conn, cuenta.id))
    finally:
        conn.close()


# --- COMANDOS VAULT ---
@vault_cli.command("list")
def cmd_vault_list(
    folder: str = typer.Option(None, "--folder", "-f", help="Filtrar por carpeta ('04 Knowledge', '06 Raw', '02 MOCs')"),
    search: str = typer.Option(None, "--search", "-s", help="Buscar por término"),
):
    """Lista las notas del vault de la cuenta."""
    with _errores_del_vault():
        reader = _lector_de_la_cli()
        if search:
            notes = reader.search_notes(search)
            if folder:
                notes = [n for n in notes if n.folder == folder]
        else:
            notes = reader.list_notes(folder=folder)

    if not notes:
        console.print("[yellow]No se encontraron notas en las carpetas autorizadas del Vault.[/yellow]")
        return

    table = Table(title="Notas del Vault de Obsidian (Solo Lectura)")
    table.add_column("Carpeta", style="cyan", no_wrap=True)
    table.add_column("Título", style="bold white")
    table.add_column("Tags", style="green")
    table.add_column("Wikilinks", justify="center", style="magenta")
    table.add_column("ID / Ruta", style="dim")

    for n in notes:
        tag_str = ", ".join(n.tags[:3]) if n.tags else "-"
        table.add_row(n.folder, n.title, tag_str, str(len(n.wikilinks)), n.id)

    console.print(table)


@vault_cli.command("stats")
def cmd_vault_stats():
    """Muestra estadísticas del grafo de notas, tags y enlaces del vault de la cuenta."""
    with _errores_del_vault():
        stats = _lector_de_la_cli().get_vault_stats()

    grid = Table.grid(padding=1)
    grid.add_column(style="bold cyan")
    grid.add_column(style="white")

    grid.add_row("Total de Notas:", str(stats["total_notes"]))
    grid.add_row("Enlaces Wikilinks:", str(stats["total_wikilinks"]))
    grid.add_row("Tags Únicos:", str(stats["total_unique_tags"]))
    grid.add_row("Distribución por Carpeta:", str(stats["folder_distribution"]))

    console.print(Panel(grid, title="[bold green]Grafo del Vault de Obsidian[/bold green]", border_style="green"))


@vault_cli.command("inspect")
def cmd_vault_inspect(note_id: str = typer.Argument(..., help="ID o nombre de la nota")):
    """Inspecciona el contenido y metadatos de una nota del vault de la cuenta."""
    with _errores_del_vault():
        note = _lector_de_la_cli().get_note(note_id)

    if not note:
        console.print(f"[red]Nota '{note_id}' no encontrada en el Vault.[/red]")
        return

    wl_str = ", ".join([f"[[{w.target}]]" for w in note.wikilinks]) or "Ninguno"
    tag_str = ", ".join([f"#{t}" for t in note.tags]) or "Ninguno"

    info = (
        f"[bold cyan]ID:[/bold cyan] {note.id}\n"
        f"[bold cyan]Ruta:[/bold cyan] {note.path}\n"
        f"[bold cyan]Carpeta:[/bold cyan] {note.folder}\n"
        f"[bold cyan]Tags:[/bold cyan] {tag_str}\n"
        f"[bold cyan]Wikilinks:[/bold cyan] {wl_str}\n\n"
        f"[bold white]Resumen:[/bold white] {note.summary}\n\n"
        f"[dim]{note.clean_text[:600]}...[/dim]"
    )
    console.print(Panel(info, title=f"[bold green]{note.title}[/bold green]", border_style="cyan"))


@vault_cli.command("note-template")
def cmd_vault_note_template(
    course_id: int = typer.Argument(..., help="ID del curso registrado"),
    topic: str = typer.Argument(..., help="Tema o módulo de la nota"),
    tldr: str = typer.Option(None, "--tldr", help="Resumen ejecutivo corto (TL;DR)"),
    concepts: str = typer.Option(None, "--concepts", "-c", help="Conceptos clave separados por coma"),
    save: bool = typer.Option(False, "--save", "-s", help="Guardar archivo Markdown físicamente en el Vault (04 Knowledge/Cursos/)"),
):
    """Genera una plantilla de apunte estructurada según el SOP oficial de Obsidian."""
    key_concepts = [c.strip() for c in concepts.split(",")] if concepts else []
    req = CourseNoteRequest(course_id=course_id, topic=topic, tldr=tldr, key_concepts=key_concepts)
    generator = CourseNoteGenerator(cuenta_de_la_cli().id)

    with _errores_del_vault(), _otros_errores("Error generando apunte"):
        if save:
            target_path = generator.save_note_to_vault(req)
            console.print(f"[bold green]✔ Apunte SOP creado y guardado en:[/bold green] {target_path}")
        else:
            data = generator.generate_note_markdown(req)
            console.print(Panel(
                f"[bold cyan]Ruta Destino:[/bold cyan] {data['relative_path']}\n"
                f"[bold cyan]Curso:[/bold cyan] {data['course']} ({data['platform']})\n\n"
                f"{data['content'][:600]}...\n\n"
                f"[dim]Usa flag --save para escribir físicamente en el Vault.[/dim]",
                title=f"[bold green]Plantilla SOP: {data['title']}[/bold green]",
                border_style="green",
            ))


@vault_cli.command("list-materials")
def cmd_vault_list_materials():
    """Lista los materiales subidos por la cuenta con los que se puede generar un apunte."""
    with _errores_del_vault():
        materials = MaterialNoteGenerator(cuenta_de_la_cli().id).list_available_materials()

    if not materials:
        console.print("[yellow]Todavía no subiste materiales. Subilos desde «Mis materiales» en la web.[/yellow]")
        return

    table = Table(title="Mis materiales")
    table.add_column("ID", style="dim", no_wrap=True)
    table.add_column("Nombre del Material", style="bold white")
    table.add_column("Tipo", style="cyan", no_wrap=True)
    table.add_column("Subido", style="magenta", no_wrap=True)

    for m in materials:
        table.add_row(str(m["id"]), escape(m["name"]), m["extension"], m["creado_en"])

    console.print(table)


@vault_cli.command("note-from-material")
def cmd_vault_note_from_material(
    material_id: int = typer.Option(..., "--material-id", "-m", help="ID del material (ver vault list-materials)"),
    course_id: int = typer.Option(None, "--course-id", "-c", help="ID del curso destino (opcional, auto-detecta si se omite)"),
    topic: str = typer.Option(None, "--topic", "-t", help="Título conceptual personalizado (opcional)"),
    notes: str = typer.Option(None, "--notes", "-n", help="Notas adicionales u observaciones personales"),
    save: bool = typer.Option(False, "--save", "-s", help="Guardar archivo Markdown físicamente en el Vault (04 Knowledge/Cursos/)"),
):
    """Sintetiza un apunte SOP oficial para el Vault a partir de un material subido por la cuenta."""
    with _errores_del_vault():
        generator = MaterialNoteGenerator(cuenta_de_la_cli().id)
        with _otros_errores("Error generando apunte desde el material"):
            if save:
                target_path = generator.save_note_to_vault(
                    material_id=material_id,
                    course_id=course_id,
                    topic=topic,
                    custom_notes=notes,
                )
                console.print(f"[bold green]✔ Apunte SOP generado desde el material y guardado en:[/bold green] {target_path}")
            else:
                data = generator.generate_note(
                    material_id=material_id,
                    course_id=course_id,
                    topic=topic,
                    custom_notes=notes,
                )
                console.print(
                    Panel(
                        f"[bold cyan]Ruta Destino:[/bold cyan] {data['relative_path']}\n"
                        f"[bold cyan]Curso Asociado:[/bold cyan] {data['course']} ({data['platform']})\n"
                        f"[bold cyan]Material Origen:[/bold cyan] {escape(data['file_name'])}\n\n"
                        f"{data['content'][:750]}...\n\n"
                        f"[dim]Usa flag --save (-s) para escribir el apunte directamente en el Obsidian Vault.[/dim]",
                        title=f"[bold green]Apunte SOP: {data['title']}[/bold green]",
                        border_style="green",
                    )
                )


@vault_cli.command("export-weekly")
def cmd_vault_export_weekly(
    week: str = typer.Option(None, "--week", "-w", help="Semana ISO (ej. 2026-W39)"),
    save_vault: bool = typer.Option(False, "--save-vault", "-s", help="Guardar directamente en 02 MOCs/ del Vault"),
):
    """Compila y exporta el Weekly Digest con métricas de cursos, libros y FSRS para Obsidian."""
    exporter = WeeklyDigestExporter(cuenta_de_la_cli().id)
    with _errores_del_vault(), _otros_errores("Error exportando Weekly Digest"):
        if save_vault:
            target_path = exporter.save_digest_to_vault(week)
            console.print(f"[bold green]✔ Weekly Digest exportado y guardado en:[/bold green] {target_path}")
        else:
            digest = exporter.build_digest(week)
            m = digest["metrics"]
            summary_info = (
                f"[bold cyan]Semana:[/bold cyan] {digest['week_label']} | [bold cyan]Ruta:[/bold cyan] {digest['relative_path']}\n"
                f"[bold cyan]Métricas:[/bold cyan] {m['courses_count']} cursos, {m['books_count']} libros, {m['streak']} días racha FSRS, {m['retention']:.1f}% retención\n\n"
                f"{digest['content'][:700]}...\n\n"
                f"[dim]Usa flag --save-vault para escribir físicamente en el Vault.[/dim]"
            )
            console.print(Panel(summary_info, title=f"[bold green]{digest['title']}[/bold green]", border_style="cyan"))


@vault_cli.command("seed-samples")
def cmd_vault_seed_samples():
    """Copia al vault de la cuenta las notas de muestra que todavía no tiene."""
    with _errores_del_vault():
        creadas = sembrar_notas_de_muestra(_vault_de_la_cli())
    console.print(f"[bold green]✔ Notas de muestra copiadas al vault de la cuenta:[/bold green] {creadas}")


@vault_cli.command("location")
def cmd_vault_location(
    carpeta: str = typer.Option(None, "--set", help="Carpeta existente del servidor a usar como vault (solo administradores)"),
    quitar: bool = typer.Option(False, "--clear", help="Volver al vault propio de la cuenta (solo administradores)"),
):
    """Muestra qué vault usa la cuenta; con --set o --clear un administrador apunta el suyo a otra carpeta."""
    cuenta = cuenta_de_la_cli()
    if carpeta and quitar:
        console.print("[bold red]✖ Usá --set o --clear, no los dos.[/bold red]")
        raise typer.Exit(code=1)
    if (carpeta or quitar) and not cuenta.es_admin:
        console.print("[bold red]✖ Solo un administrador puede apuntar su vault a otra carpeta.[/bold red]", soft_wrap=True)
        raise typer.Exit(code=1)

    conn = get_connection()
    try:
        if carpeta:
            try:
                fijar_vault_externo(conn, cuenta.id, carpeta)
            except CarpetaDeVaultInvalida as error:
                console.print(f"[bold red]✖ {escape(str(error))}[/bold red]", soft_wrap=True)
                raise typer.Exit(code=1) from None
        elif quitar:
            quitar_vault_externo(conn, cuenta.id)
        estado = estado_del_vault(conn, cuenta.id)
    finally:
        conn.close()

    if not estado["externo"]:
        console.print("La cuenta usa su vault propio, dentro del directorio de datos del servidor.", soft_wrap=True)
    elif estado["disponible"]:
        console.print(f"La cuenta usa un vault externo: {escape(estado['ruta'])}", soft_wrap=True)
    else:
        console.print(
            f"[yellow]La cuenta tiene fijado un vault externo que ya no existe: {escape(estado['ruta'])}. "
            "Volvé a crear la carpeta, fijá otra con --set o quitala con --clear.[/yellow]",
            soft_wrap=True,
        )


# --- COMANDOS EXAM ---
@exam_cli.command("create")
def cmd_exam_create(
    note_id: str = typer.Argument(..., help="ID o término de la nota para evaluar"),
    q_type: str = typer.Option("all", "--type", "-t", help="Tipo: multiple_choice, cloze, open_reasoning o all"),
    num: int = typer.Option(3, "--num", "-n", help="Cantidad de preguntas"),
):
    """Genera un examen adaptativo de Active Recall sobre una nota del vault de la cuenta."""
    with _errores_del_vault():
        reader = _lector_de_la_cli()
        note = reader.get_note(note_id)
        if not note:
            matched = reader.search_notes(note_id)
            note = matched[0] if matched else None

    if not note:
        console.print(f"[red]No se encontró ninguna nota relacionada con '{note_id}'.[/red]")
        return

    types_map = {
        "multiple_choice": [QuestionType.MULTIPLE_CHOICE],
        "cloze": [QuestionType.CLOZE],
        "open": [QuestionType.OPEN_REASONING],
        "open_reasoning": [QuestionType.OPEN_REASONING],
        "all": [QuestionType.MULTIPLE_CHOICE, QuestionType.CLOZE, QuestionType.OPEN_REASONING],
    }

    selected_types = types_map.get(q_type.lower(), types_map["all"])

    generator = ExamGenerator(reader)
    exam = generator.generate_exam_for_note(note, question_types=selected_types, count=num)

    console.print(f"\n[bold green]=== {exam.title} ===[/bold green]")
    console.print(f"[dim]Total preguntas: {exam.total_questions} | Origen: {note.folder}/{note.title}[/dim]\n")

    for i, q in enumerate(exam.questions, 1):
        type_badge = f"[bold yellow][{q.question_type.upper()}][/bold yellow]"
        console.print(f"[bold cyan]Pregunta {i}:[/bold cyan] {type_badge} {q.prompt}")

        if q.options:
            for opt_idx, opt in enumerate(q.options, 1):
                marker = "•"
                console.print(f"   {marker} {opt}")

        console.print(f"   [bold green]Respuesta Correcta:[/bold green] {q.correct_answer}")
        console.print(f"   [dim]Fundamento: {q.explanation}[/dim]\n")


# --- COMANDOS FEYNMAN ---
@feynman_cli.command("evaluate")
def cmd_feynman_evaluate(
    concept: str = typer.Argument(..., help="Concepto a explicar (ej. 'Star Schema', 'Webhooks', 'Transformers')"),
    explanation: str = typer.Option(None, "--explanation", "-e", help="Tu explicación del concepto en lenguaje propio"),
    audience: str = typer.Option("principiante", "--audience", "-a", help="Audiencia objetivo"),
):
    """Evalúa tu explicación de un concepto bajo los principios de la Técnica Feynman, con las notas de tu vault."""
    if not explanation:
        console.print(f"\n[bold cyan]Técnica Feynman — Explicar como a un principiante:[/bold cyan] {concept}")
        console.print("[dim]Escribe tu explicación con tus propias palabras evitando jergas sin definir:[/dim]\n")
        explanation = typer.prompt("Tu explicación")

    sub = FeynmanSubmission(concept=concept, explanation=explanation, target_audience=audience)
    with _errores_del_vault():
        res = FeynmanEvaluator(_lector_de_la_cli()).evaluate(sub)

    # Color según score
    color = "green" if res.score >= 75 else ("yellow" if res.score >= 50 else "red")

    summary_text = (
        f"[bold]Puntaje Global:[/bold] [{color}]{res.score}/100[/{color}]  |  "
        f"[bold]Maestría:[/bold] [{color}]{res.mastery_level}[/{color}]\n"
        f"[bold]Claridad y Sencillez:[/bold] {res.clarity_score}/100  |  "
        f"[bold]Exactitud Técnica:[/bold] {res.precision_score}/100\n\n"
        f"[bold white]{res.feedback_summary}[/bold white]\n\n"
    )

    if res.strengths:
        summary_text += "[bold green]Puntos Fuertes Identificados:[/bold green]\n"
        for s in res.strengths:
            summary_text += f"  ✔ {s}\n"
        summary_text += "\n"

    if res.knowledge_gaps:
        summary_text += "[bold yellow]Lagunas Conceptuales (Knowledge Gaps):[/bold yellow]\n"
        for g in res.knowledge_gaps:
            summary_text += f"  ⚠ {g}\n"
        summary_text += "\n"

    if res.jargon_used:
        summary_text += f"[bold red]Jergas Detectadas:[/bold red] {', '.join(res.jargon_used)}\n\n"

    summary_text += f"[bold cyan]Analogía Sugerida de Feynman:[/bold cyan]\n[italic]{res.suggested_simplification}[/italic]"

    console.print(Panel(summary_text, title=f"[bold {color}]Diagnóstico Feynman: {concept}[/bold {color}]", border_style=color))
