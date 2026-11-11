"""Comandos CLI para Rutas de Aprendizaje, Prompt Maestro y Comparador de PDFs."""

from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree

from aulento.cli.contexto import cuenta_de_la_cli
from aulento.core.ia.pasarela import PasarelaDeIA
from aulento.db.roadmap_repository import RoadmapRepository
from aulento.models.roadmap import (
    AlcanceRuta,
    RoadmapCreate,
    RoadmapModuleCreate,
    RoadmapTopicCreate,
    LessonPromptRequest,
    OrigenClase,
)
from aulento.roadmap.engine import RoadmapEngine
from aulento.roadmap.prompt_builder import LessonPromptBuilder
from aulento.roadmap.lesson_studio import LessonStudio
from aulento.roadmap.pdf_comparator import RoadmapPDFComparator

roadmap_app = typer.Typer(help="Rutas de Aprendizaje Dinámicas, Prompt Maestro y Lesson Studio")
console = Console()


@roadmap_app.command(name="list")
def list_roadmaps():
    """Lista todas las rutas de aprendizaje con porcentaje de avance."""
    repo = RoadmapRepository(cuenta_de_la_cli().id)
    roadmaps = repo.get_roadmaps()

    if not roadmaps:
        console.print("[yellow]No hay rutas de aprendizaje registradas. Usa 'aulento roadmap create' para iniciar una.[/yellow]")
        return

    table = Table(title="🗺️ Rutas de Aprendizaje (Aulento)", show_header=True, header_style="bold cyan")
    table.add_column("ID", style="dim", width=5)
    table.add_column("Título", style="bold white", min_width=25)
    table.add_column("Nivel", style="magenta", width=12)
    table.add_column("Categoría", style="blue")
    table.add_column("Temas", justify="center", width=10)
    table.add_column("Progreso", justify="right", width=12)

    for r in roadmaps:
        pct_color = "green" if r.progreso_pct >= 80 else ("yellow" if r.progreso_pct >= 40 else "white")
        table.add_row(
            str(r.id),
            r.titulo,
            r.nivel_objetivo or "Senior",
            r.categoria,
            f"{r.temas_completados}/{r.total_temas}",
            f"[{pct_color}]{r.progreso_pct}%[/{pct_color}]",
        )

    console.print(table)


@roadmap_app.command(name="show")
def show_roadmap(roadmap_id: int):
    """Muestra el árbol jerárquico detallado de módulos y temas de una ruta."""
    repo = RoadmapRepository(cuenta_de_la_cli().id)
    detail = repo.get_roadmap(roadmap_id)

    if not detail:
        console.print(f"[red]Ruta con ID {roadmap_id} no encontrada.[/red]")
        return

    tree = Tree(f"[bold cyan]🗺️ {detail.titulo}[/bold cyan] ({detail.nivel_objetivo}) — [green]{detail.progreso_pct}% completado[/green]")

    for mod in detail.modulos:
        mod_branch = tree.add(f"[bold yellow]{mod.titulo}[/bold yellow]")
        for top in mod.temas:
            icon = "✔" if top.estado.value == "completado" else ("🚀" if top.estado.value == "en_progreso" else "⏳")
            color = "green" if top.estado.value == "completado" else ("cyan" if top.estado.value == "en_progreso" else "dim white")
            has_class = " [bold purple](Clase disponible)[/bold purple]" if top.clase else ""
            mod_branch.add(f"[{color}]{icon} [{top.id}] {top.titulo}[/{color}]{has_class}")

    console.print(Panel(tree, border_style="cyan"))


@roadmap_app.command(name="create")
def create_roadmap_cmd(
    title: str = typer.Option(..., "--title", "-t", help="Título o rol de la ruta"),
    level: str = typer.Option("Senior", "--level", "-l", help="Nivel objetivo (Junior, Semi-Senior, Senior, Staff)"),
    alcance: AlcanceRuta = typer.Option(
        AlcanceRuta.CURSO.value,
        "--alcance",
        "-a",
        help="Tamaño de la ruta: curso, especializacion o carrera (materias que se expanden a demanda)",
    ),
):
    """Crea una nueva ruta de aprendizaje con Gemini o, si el título coincide exacto, desde una plantilla curada."""
    repo = RoadmapRepository(cuenta_de_la_cli().id)
    engine = RoadmapEngine(repo=repo)

    console.print(f"[cyan]Diseñando ruta de aprendizaje para '[bold]{title}[/bold]' ({level})...[/cyan]")
    data = engine.generate_roadmap_with_ai(prompt=title, target_role=title, experience_level=level, alcance=alcance)
    created = repo.create_roadmap(data)

    console.print(f"[green]✔ Ruta creada con éxito: [bold]{created.titulo}[/bold] (ID: {created.id})[/green]")
    console.print(f"Total de módulos: {len(created.modulos)} | Total de temas: {created.total_temas}")

    aviso = created.metadata_json.get("aviso")
    if aviso:
        console.print(f"[bold yellow]⚠ Aviso:[/bold yellow] [yellow]{escape(str(aviso))}[/yellow]")


@roadmap_app.command(name="seed")
def seed_templates_cmd():
    """Carga todas las plantillas canónicas de la industria (4 roles clave) en la base de datos."""
    repo = RoadmapRepository(cuenta_de_la_cli().id)
    created = repo.ensure_curated_templates()
    if created:
        console.print(f"[green]✔ Se cargaron {len(created)} nuevas rutas canónicas oficiales.[/green]")
        for c in created:
            console.print(f"  - [bold]{c.titulo}[/bold] ({c.nivel_objetivo}) - ID: {c.id}")
    else:
        console.print("[yellow]✔ Todas las rutas canónicas ya se encuentran cargadas en tu base de datos.[/yellow]")


@roadmap_app.command(name="prompt")
def generate_prompt_cmd(
    topic_id: int = typer.Option(..., "--topic-id", "-i", help="ID del tema para la clase"),
    materiales: bool = typer.Option(True, "--materiales/--no-materiales", help="Instrucción de buscar en tus materiales subidos (MCP)"),
    web: bool = typer.Option(True, "--web/--no-web", help="Instrucción de investigación web y documentación oficial"),
    target_llm: str = typer.Option("notebooklm", "--target", help="Destino: notebooklm, claude, chatgpt, gemini"),
):
    """Genera el Prompt Maestro estructurado con SOPs de Sistema Maestro para copiar y pegar."""
    repo = RoadmapRepository(cuenta_de_la_cli().id)
    builder = LessonPromptBuilder(repo=repo)
    req = LessonPromptRequest(
        include_materials=materiales,
        include_web_research=web,
        sop_style=True,
        include_fsrs_cards=True,
        target_llm=target_llm,
    )
    try:
        res = builder.build_prompt(topic_id, req)
        console.print(Panel(f"[bold cyan]Prompt Maestro para: {res.topic_title}[/bold cyan]\n[dim]Entorno sugerido: {target_llm.capitalize()}[/dim]\n\n" + res.master_prompt, border_style="green"))
        console.print(f"[yellow]Instrucciones:[/yellow]\n{res.instructions}")
    except ValueError as e:
        console.print(f"[red]{e}[/red]")


@roadmap_app.command(name="import")
def import_lesson_cmd(
    topic_id: int = typer.Option(..., "--topic-id", "-i", help="ID del tema"),
    file_path: Path = typer.Option(..., "--file", "-f", help="Ruta al archivo Markdown con la clase generada"),
    export_fsrs: bool = typer.Option(True, "--fsrs/--no-fsrs", help="Inyectar flashcards automáticamente a FSRS"),
    export_vault: bool = typer.Option(True, "--vault/--no-vault", help="Guardar apunte canónico en el Vault de Obsidian"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Reemplazar sin preguntar la clase que el tema ya tenga"),
):
    """Importa una clase externa desde un archivo Markdown."""
    if not file_path.exists():
        console.print(f"[red]El archivo {file_path} no existe.[/red]")
        return

    content = file_path.read_text(encoding="utf-8")
    repo = RoadmapRepository(cuenta_de_la_cli().id)
    studio = LessonStudio(repo=repo)

    existente = repo.get_lesson_by_topic_id(topic_id)
    if existente and not overwrite:
        console.print(
            f"[yellow]El tema {topic_id} ya tiene una clase: [bold]{escape(existente.titulo)}[/bold]. "
            "Si la reemplazás, la actual queda guardada como versión anterior.[/yellow]"
        )
        if not typer.confirm("¿Reemplazarla?", default=False):
            console.print("[dim]No se modificó nada.[/dim]")
            return

    lesson = studio.import_external_lesson(topic_id, content, origen=OrigenClase.NOTEBOOKLM)
    console.print(f"[green]✔ Clase importada: [bold]{lesson.titulo}[/bold][/green]")
    console.print(f"Diagramas Mermaid: {len(lesson.diagramas_mermaid)} | Flashcards detectadas: {len(lesson.flashcards_json)}")

    if export_fsrs and lesson.flashcards_json:
        cards_count = studio.export_flashcards_to_fsrs(lesson.id)
        console.print(f"[cyan]✔ {cards_count} tarjetas inyectadas exitosamente al motor FSRS v5.[/cyan]")

    if export_vault:
        try:
            v_path = studio.export_lesson_to_vault(lesson.id)
            console.print(f"[magenta]✔ Apunte canónico guardado en el Vault: [bold]{v_path}[/bold][/magenta]")
            if studio.last_backup_path:
                console.print(
                    f"[yellow]En el vault había una nota distinta de la que escribió el sistema; se guardó una copia en: {studio.last_backup_path}[/yellow]"
                )
        except Exception as e:
            console.print(f"[yellow]Aviso al guardar en Vault: {e}[/yellow]")


@roadmap_app.command(name="versions")
def lesson_versions_cmd(
    topic_id: int = typer.Option(..., "--topic-id", "-i", help="ID del tema"),
):
    """Lista las versiones anteriores de la clase de un tema."""
    versiones = RoadmapRepository(cuenta_de_la_cli().id).get_lesson_versions(topic_id)
    if not versiones:
        console.print(f"[dim]El tema {topic_id} no tiene versiones anteriores de su clase.[/dim]")
        return
    table = Table(title=f"Versiones anteriores de la clase del tema {topic_id}")
    table.add_column("ID", justify="right")
    table.add_column("Guardada")
    table.add_column("Título")
    table.add_column("Origen")
    table.add_column("Caracteres", justify="right")
    for v in versiones:
        table.add_row(str(v.id), str(v.fecha_version), escape(v.titulo), v.origen.value, str(len(v.contenido_markdown)))
    console.print(table)
    console.print("[dim]Restaurá una con: aulento roadmap restore --version-id <ID>[/dim]")


@roadmap_app.command(name="restore")
def lesson_restore_cmd(
    version_id: int = typer.Option(..., "--version-id", "-v", help="ID de la versión a restaurar"),
):
    """Restaura una versión anterior de una clase; la vigente queda guardada como versión."""
    restaurada = RoadmapRepository(cuenta_de_la_cli().id).restore_lesson_version(version_id)
    if not restaurada:
        console.print(f"[red]No existe la versión {version_id}.[/red]")
        raise typer.Exit(code=1)
    console.print(f"[green]✔ Clase restaurada: [bold]{escape(restaurada.titulo)}[/bold] (tema {restaurada.tema_id}).[/green]")
    console.print("[dim]La clase que estaba vigente quedó guardada como versión anterior.[/dim]")


@roadmap_app.command(name="compare")
def compare_pdf_cmd(
    roadmap_id: int = typer.Option(..., "--roadmap-id", "-r", help="ID de la ruta activa"),
    pdf_path: Path = typer.Option(..., "--pdf", "-p", help="Ruta al archivo PDF con el syllabus a comparar"),
    merge: bool = typer.Option(False, "--merge", help="Incorporar de inmediato los temas faltantes detectados"),
):
    """Ejecuta un Gap Analysis entre un syllabus PDF y la ruta activa."""
    if not pdf_path.exists():
        console.print(f"[red]El archivo PDF {pdf_path} no existe.[/red]")
        return

    repo = RoadmapRepository(cuenta_de_la_cli().id)
    detail = repo.get_roadmap(roadmap_id)
    if not detail:
        console.print(f"[red]Ruta con ID {roadmap_id} no encontrada.[/red]")
        return

    console.print(f"[cyan]Analizando syllabus PDF '{pdf_path.name}' contra '{detail.titulo}'...[/cyan]")
    pdf_bytes = pdf_path.read_bytes()
    comparator = RoadmapPDFComparator(PasarelaDeIA.de_repositorio(repo))
    result = comparator.compare_syllabus(detail, pdf_bytes, filename=pdf_path.name)

    console.print(Panel(f"[bold green]Resumen del Gap Analysis:[/bold green] {result.summary}", border_style="cyan"))

    if result.matched_topics:
        console.print("\n[bold green]🟢 Temas ya cubiertos en tu ruta:[/bold green]")
        for m in result.matched_topics:
            console.print(f"  ✔ {m}")

    if result.gap_topics:
        console.print(f"\n[bold yellow]🟠 Brechas detectadas ({len(result.gap_topics)} temas faltantes):[/bold yellow]")
        for g in result.gap_topics:
            console.print(f"  + [bold]{g.titulo}[/bold]: {g.descripcion or ''}")

    if merge and result.gap_topics:
        inserted = repo.merge_gap_topics(roadmap_id, result.gap_topics)
        console.print(f"\n[bold green]✔ {inserted} temas faltantes incorporados exitosamente a la ruta.[/bold green]")
