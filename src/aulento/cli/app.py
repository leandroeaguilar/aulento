"""Aplicación CLI principal para Aulento construida con Typer y Rich."""

import sqlite3
import sys

# Ensure UTF-8 stdout/stderr on Windows to avoid charmap encoding errors
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import click
import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from typer.core import TyperGroup

from aulento.cli.activity_commands import activity_app
from aulento.cli.contexto import (
    CuentaNoResuelta,
    cuenta_de_la_cli,
    hay_cuenta_indicada,
    indicar_cuenta,
    resolver_cuenta_de_la_cli,
    terminar_por_migracion_fallida,
)
from aulento.cli.duolingo_commands import duolingo_app
from aulento.cli.focus_commands import focus_app
from aulento.cli.fsrs_commands import fsrs_app
from aulento.cli.ia_commands import ia_app
from aulento.cli.mcp_commands import mcp_app
from aulento.cli.onboarding import onboarding_app
from aulento.cli.roadmap_commands import roadmap_app
from aulento.cli.user_commands import user_app
from aulento.cli.vault_commands import exam_cli, feynman_cli, vault_cli
from aulento.cli.web_commands import web_app
from aulento.config import ensure_data_dir, get_db_path, mudar_carpeta_anterior
from aulento.core.study_planner import StudyPlannerEngine
from aulento.models.study_planner import AdaptivePlanRequest, ApplyPlanRequest
from aulento.connectors.course_sync import CourseSyncManager
from aulento.core.ia.tipos import IANoDisponibleError
from aulento.core.secretos import ClaveMaestraInvalida
from aulento.db.connection import get_connection
from aulento.db.migrations import ErrorDeMigracion, ultima_version, version_actual
from aulento.db.repository import (
    BloqueHorarioRepository,
    CursoRepository,
    LibroRepository,
    PlataformaRepository,
)
from aulento.db.schema import init_db, seed_plataformas
from aulento.fsrs.deck_seed import seed_fsrs_deck
from aulento.models.curso import CursoCreate, PrioridadCurso
from aulento.models.horario import BloqueHorarioCreate, TipoBloque
from aulento.models.libro import EstadoLibro, LibroCreate
from aulento.models.plataforma import PlataformaCreate


class GrupoPrincipal(TyperGroup):
    """Grupo raíz de la CLI: una clave maestra mal formada o un comando que exige IA y no la tuvo terminan con su
    explicación y salida 1, sin traceback."""

    def invoke(self, ctx: click.Context):
        try:
            return super().invoke(ctx)
        except (ClaveMaestraInvalida, IANoDisponibleError) as error:
            console.print(f"[bold red]Error:[/bold red] {escape(str(error))}", soft_wrap=True)
            raise typer.Exit(code=1) from None


cli = typer.Typer(
    name="aulento",
    help="Sistema Maestro de Estudio Inteligente (Local First)",
    no_args_is_help=True,
    cls=GrupoPrincipal,
)
console = Console()

db_app = typer.Typer(help="Comandos de gestión y estado de la base de datos SQLite")
hub_app = typer.Typer(help="Hub de plataformas académicas y cursos")
books_app = typer.Typer(help="Gestor y seguimiento de lectura de libros técnicos")
schedule_app = typer.Typer(help="Cronograma semanal de bloques horarios de estudio")
planner_app = typer.Typer(help="Motor de recomendación y planificación adaptativa de estudio")

cli.add_typer(onboarding_app, name="onboarding")
cli.add_typer(db_app, name="db")
cli.add_typer(hub_app, name="hub")
cli.add_typer(books_app, name="books")
cli.add_typer(schedule_app, name="schedule")
cli.add_typer(planner_app, name="planner")
cli.add_typer(fsrs_app, name="fsrs")
cli.add_typer(mcp_app, name="mcp")
cli.add_typer(web_app, name="web")
cli.add_typer(web_app, name="serve")
cli.add_typer(vault_cli, name="vault")
cli.add_typer(exam_cli, name="exam")
cli.add_typer(feynman_cli, name="feynman")
cli.add_typer(duolingo_app, name="duolingo")
cli.add_typer(focus_app, name="focus")
cli.add_typer(roadmap_app, name="roadmap")
cli.add_typer(activity_app, name="activity")
cli.add_typer(user_app, name="user")
cli.add_typer(ia_app, name="ia")


@cli.callback()
def opciones_globales(
    user: str = typer.Option(
        None,
        "--user",
        help="Cuenta como la que operan los comandos de datos (también AULENTO_USER); "
        "si hay una sola cuenta activa no hace falta.",
    ),
):
    """Guarda la cuenta indicada; se resuelve recién cuando un comando de datos la necesita."""
    mudar_carpeta_anterior()
    indicar_cuenta(user)


DIAS_SEMANA = {
    1: "Lunes",
    2: "Martes",
    3: "Miércoles",
    4: "Jueves",
    5: "Viernes",
    6: "Sábado",
    7: "Domingo",
}


# ─── DB COMMANDS ─────────────────────────────────────────────────────────────

# Totales del sistema, sin filtrar por cuenta: solo cantidades, nunca contenido
TABLAS_DEL_ESTADO = (
    ("Plataformas Académicas", "plataformas"),
    ("Cursos Externos", "cursos_externos"),
    ("Libros de Lectura", "libros_lectura"),
    ("Bloques Horarios", "bloques_horarios"),
)


@db_app.command("init")
def cmd_db_init(
    seed: bool = typer.Option(
        True, "--seed/--no-seed", help="Sembrar las 5 plataformas y el mazo iniciales para la cuenta, si hay una"
    ),
):
    """Inicializa la base de datos SQLite local y crea las tablas relacionales."""
    db_path = get_db_path()
    ensure_data_dir()
    conn = get_connection(db_path)
    try:
        try:
            init_db(conn)
        except ErrorDeMigracion as error:
            raise terminar_por_migracion_fallida(error) from None
        console.print(f"[bold green]✔[/bold green] Base de datos inicializada en: [cyan]{db_path}[/cyan]")
        if not seed:
            return
        if hay_cuenta_indicada():
            # Pedida de forma explícita, la cuenta tiene que existir y estar activa: si no, es un error
            cuenta = cuenta_de_la_cli()
        else:
            try:
                cuenta = resolver_cuenta_de_la_cli()
            except CuentaNoResuelta as error:
                console.print(f"[yellow]⚠ No se sembraron datos iniciales: {escape(str(error))}[/yellow]", soft_wrap=True)
                return
        seed_plataformas(conn, cuenta.id)
        console.print("[green]✔ Plataformas iniciales sembradas (Digital House, Google Skills, Humai, Coursera, Anthropic).[/green]")
        total_cards = seed_fsrs_deck(conn, cuenta.id)
        console.print(f"[green]✔ Mazo FSRS sembrado: [bold]{total_cards}[/bold] colocaciones de inglés técnico profesional.[/green]")
    finally:
        conn.close()


@db_app.command("status")
def cmd_db_status():
    """Muestra el estado de la base de datos SQLite y conteo de registros."""
    db_path = get_db_path()
    if not db_path.exists():
        console.print(f"[bold yellow]⚠[/bold yellow] La base de datos no existe en [cyan]{db_path}[/cyan]. Ejecutá: [bold]aulento db init[/bold]")
        raise typer.Exit(code=1)

    conn = get_connection(db_path)
    try:
        version = version_actual(conn)
        al_dia = version >= ultima_version()
        totales = []
        for entidad, tabla in TABLAS_DEL_ESTADO:
            try:
                totales.append((entidad, str(conn.execute(f"SELECT count(*) FROM {tabla};").fetchone()[0])))
            except sqlite3.OperationalError:
                # En una base de una versión anterior la tabla puede no existir todavía
                totales.append((entidad, "—"))
        table = Table(title="Estado de SQLite Local (study_engine.db): todas las cuentas")
        table.add_column("Entidad", style="cyan", no_wrap=True)
        table.add_column("Registros", style="magenta")
        for entidad, total in totales:
            table.add_row(entidad, total)

        console.print(Panel(f"Ruta: [bold green]{db_path}[/bold green]", title="Base de Datos SQLite"))
        console.print(table)

        if not al_dia:
            # Solo lectura: este comando no migra ni respalda; los registros por cuenta dependen del esquema nuevo
            console.print(
                f"[bold yellow]⚠[/bold yellow] Hay migraciones pendientes: la base está en la versión {version} "
                f"y este programa espera la {ultima_version()}. Ejecutá [bold]aulento db init[/bold] para aplicarlas.",
                soft_wrap=True,
            )
            return

        motivo = ""
        try:
            cuenta = resolver_cuenta_de_la_cli(migrar_la_base=False)
        except CuentaNoResuelta as error:
            cuenta = None
            motivo = str(error)

        if cuenta is None:
            console.print(f"[dim]No se muestran los registros por cuenta: {escape(motivo)}[/dim]", soft_wrap=True)
            return
        propios = Table(title=f"Registros de la cuenta {escape(cuenta.nombre_usuario)}")
        propios.add_column("Entidad", style="cyan", no_wrap=True)
        propios.add_column("Registros", style="magenta")
        propios.add_row("Plataformas Académicas", str(len(PlataformaRepository(conn, cuenta.id).list_all())))
        propios.add_row("Cursos Externos", str(len(CursoRepository(conn, cuenta.id).list_all())))
        propios.add_row("Libros de Lectura", str(len(LibroRepository(conn, cuenta.id).list_all())))
        propios.add_row("Bloques Horarios", str(len(BloqueHorarioRepository(conn, cuenta.id).list_all())))
        console.print(propios)
    finally:
        conn.close()


# ─── HUB & CURSOS COMMANDS ───────────────────────────────────────────────────

@hub_app.command("list")
def cmd_hub_list():
    """Lista todas las plataformas académicas y los cursos en curso."""
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        plat_repo = PlataformaRepository(conn, cuenta.id)
        curso_repo = CursoRepository(conn, cuenta.id)

        plataformas = plat_repo.list_all()
        cursos = curso_repo.list_all()

        # Tabla de Plataformas
        p_table = Table(title="🏛 Plataformas Académicas Registradas")
        p_table.add_column("ID", style="dim", width=4)
        p_table.add_column("Plataforma", style="bold white")
        p_table.add_column("URL Portal", style="blue")
        p_table.add_column("Distintivo", style="yellow")

        for p in plataformas:
            p_table.add_row(str(p.id), p.nombre, p.url_acceso, f"[{p.icono_color}]●[/{p.icono_color}] {p.icono_color}")

        console.print(p_table)
        console.print("")

        # Tabla de Cursos
        c_table = Table(title="📚 Cursos y Cursadas Actuales")
        c_table.add_column("ID", style="dim", width=4)
        c_table.add_column("Plataforma", style="cyan")
        c_table.add_column("Curso", style="bold white")
        c_table.add_column("Progreso", justify="right")
        c_table.add_column("Estado", style="yellow")
        c_table.add_column("Prioridad", style="magenta")
        c_table.add_column("Aula Virtual (1-Clic)", style="blue")

        for c in cursos:
            color_prog = "green" if c.progreso_pct >= 100.0 else ("yellow" if c.progreso_pct > 0 else "red")
            prog_text = f"[{color_prog}]{c.progreso_pct:.1f}%[/{color_prog}]"
            c_table.add_row(
                str(c.id),
                c.nombre_plataforma or str(c.plataforma_id),
                c.nombre_curso,
                prog_text,
                c.estado.value,
                c.prioridad.value,
                c.url_aula,
            )

        if not cursos:
            console.print("[dim]No hay cursos registrados aún. Usá 'aulento hub add-course' para cargar uno.[/dim]")
        else:
            console.print(c_table)
    finally:
        conn.close()


@hub_app.command("add-platform")
def cmd_hub_add_platform(
    nombre: str = typer.Argument(..., help="Nombre de la plataforma académica (ej. Platzi, Udemy, edX)"),
    url: str = typer.Option(..., "--url", "-u", help="URL del portal o aula virtual"),
    color: str = typer.Option("sky", "--color", "-c", help="Color distintivo (blue, purple, green, orange, cyan, sky, etc.)"),
):
    """Registra una nueva plataforma académica en el Hub."""
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        repo = PlataformaRepository(conn, cuenta.id)
        plat = repo.create(PlataformaCreate(nombre=nombre, url_acceso=url, icono_color=color))
        console.print(f"[bold green]✔[/bold green] Plataforma registrada con ID [bold cyan]{plat.id}[/bold cyan]: [bold]{plat.nombre}[/bold] ([cyan]{plat.url_acceso}[/cyan]).")
    finally:
        conn.close()


@hub_app.command("add-course")
def cmd_hub_add_course(
    plataforma_id: int = typer.Option(..., "--plataforma", "-p", help="ID de la plataforma"),
    nombre: str = typer.Option(..., "--nombre", "-n", help="Nombre del curso"),
    url_aula: str = typer.Option(..., "--url", "-u", help="URL del aula virtual"),
    progreso: float = typer.Option(0.0, "--progreso", help="Progreso inicial (0 a 100)"),
    prioridad: str = typer.Option("alta", "--prioridad", help="alta | media | baja"),
):
    """Registra un nuevo curso asociado a una plataforma académica."""
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        plat_repo = PlataformaRepository(conn, cuenta.id)
        curso_repo = CursoRepository(conn, cuenta.id)

        plat = plat_repo.get_by_id(plataforma_id)
        if not plat:
            console.print(f"[bold red]Error:[/bold red] Plataforma ID {plataforma_id} no encontrada.")
            raise typer.Exit(code=1)

        curso = curso_repo.create(
            CursoCreate(
                plataforma_id=plataforma_id,
                nombre_curso=nombre,
                url_aula=url_aula,
                progreso_pct=progreso,
                prioridad=PrioridadCurso(prioridad.lower()),
            )
        )
        console.print(f"[bold green]✔[/bold green] Curso registrado con ID [bold cyan]{curso.id}[/bold cyan] en [bold]{plat.nombre}[/bold].")
    finally:
        conn.close()


@hub_app.command("update-progress")
def cmd_hub_update_progress(
    curso_id: int = typer.Argument(..., help="ID del curso"),
    progreso: float = typer.Argument(..., help="Nuevo porcentaje de avance (0.0 a 100.0)"),
):
    """Actualiza el porcentaje de avance de un curso."""
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        curso_repo = CursoRepository(conn, cuenta.id)
        updated = curso_repo.update_progress(curso_id, progreso)
        if not updated:
            console.print(f"[bold red]Error:[/bold red] Curso ID {curso_id} no encontrado.")
            raise typer.Exit(code=1)
        console.print(f"[bold green]✔[/bold green] Curso [bold]{updated.nombre_curso}[/bold] actualizado al [cyan]{updated.progreso_pct:.1f}%[/cyan] (Estado: [yellow]{updated.estado.value}[/yellow]).")
    finally:
        conn.close()


@hub_app.command("sync")
def cmd_hub_sync(
    curso_id: int = typer.Argument(..., help="ID del curso a sincronizar"),
    progreso: float | None = typer.Option(None, "--progreso", "-p", help="Progreso porcentual opcional (0-100)"),
    labs_completados: int | None = typer.Option(None, "--labs-ok", help="Labs completados"),
    total_labs: int | None = typer.Option(None, "--labs-total", help="Total de labs"),
    modulos_completados: int | None = typer.Option(None, "--modulos-ok", help="Módulos completados"),
    total_modulos: int | None = typer.Option(None, "--modulos-total", help="Total de módulos"),
    fuente: str = typer.Option("cli", "--fuente", "-f", help="Nombre de la fuente"),
):
    """Sincroniza el avance de un curso registrado en el Hub Académico."""
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        manager = CourseSyncManager(conn, cuenta.id)
        payload = {"fuente": fuente}
        if progreso is not None:
            payload["progreso_pct"] = progreso
        if labs_completados is not None and total_labs is not None:
            payload["completed_labs"] = labs_completados
            payload["total_labs"] = total_labs
        if modulos_completados is not None and total_modulos is not None:
            payload["completed_modules"] = modulos_completados
            payload["total_modules"] = total_modulos

        res = manager.sync_course(curso_id, payload=payload)
        console.print(f"[green]✔[/green] Curso [bold]{res.nombre_curso}[/bold] sincronizado.")
        console.print(f"  • Progreso: [cyan]{res.progreso_anterior:.1f}% ➔ {res.progreso_pct:.1f}%[/cyan] ({res.estado})")
        console.print(f"  • Fuente: {res.fuente} | Mensaje: {res.mensaje}")
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]Error al sincronizar curso: {e}[/red]")
        raise typer.Exit(1)
    finally:
        conn.close()


@hub_app.command("sync-google-skills")
def cmd_hub_sync_google_skills(
    profile_url_or_id: str = typer.Argument(..., help="URL o ID de perfil público de Google Cloud Skills Boost"),
    auto_import: bool = typer.Option(False, "--auto-import", help="Importar automáticamente insignias como cursos"),
):
    """Sincroniza cursos asociados a Google Cloud Skills Boost con un perfil público."""
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        manager = CourseSyncManager(conn, cuenta.id)
        results = manager.sync_google_skills_profile(profile_url_or_id, auto_import=auto_import)
        console.print(f"[green]✔[/green] Se procesaron {len(results)} insignias/cursos de Skills Boost:")
        for r in results:
            console.print(f"  • [bold]{r.nombre_curso}[/bold]: {r.progreso_pct:.1f}% ({r.estado}) - {r.mensaje}")
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]Error al sincronizar Skills Boost: {e}[/red]")
        raise typer.Exit(1)
    finally:
        conn.close()


@hub_app.command("webhook-info")
def cmd_hub_webhook_info():
    """Muestra la configuración y URL del webhook universal de cursos para la cuenta activa."""
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM mcp_tokens WHERE usuario_id = ? ORDER BY id DESC LIMIT 1;", (cuenta.id,))
        token_str = "<mcp_token_de_tu_cuenta>"
        console.print(Panel.fit(
            "[bold cyan]Webhook Universal de Cursos - Aulento[/bold cyan]\n\n"
            "• [bold]Endpoint:[/bold] POST http://localhost:8000/api/hub/sync/webhook\n"
            f"• [bold]Autenticación:[/bold] Bearer {token_str} (o sesión web activa)\n\n"
            "[bold yellow]Ejemplo cURL:[/bold yellow]\n"
            f"curl -X POST http://localhost:8000/api/hub/sync/webhook \\\n"
            f"  -H 'Authorization: Bearer {token_str}' \\\n"
            f"  -H 'Content-Type: application/json' \\\n"
            f"  -d '{{\"curso\": \"Data Engineering\", \"progreso_pct\": 75.0, \"plataforma\": \"Humai\"}}'\n\n"
            "Compatible con Tampermonkey, Atajos de Apple o scripts automáticos.",
            title="📡 Webhook de Progreso",
        ))
    finally:
        conn.close()


@hub_app.command("sync-status")
def cmd_hub_sync_status():
    """Muestra el estado general de sincronización de cursos."""
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        repo = CursoRepository(conn, cuenta.id)
        status = repo.get_sync_status()
        table = Table(title="🔄 Estado de Sincronización de Cursos", show_header=True)
        table.add_column("Métrica", style="cyan")
        table.add_column("Valor", style="green")
        table.add_row("Total de cursos", str(status["total_cursos"]))
        table.add_row("Cursos sincronizados", str(status["cursos_sincronizados"]))
        table.add_row("Última sincronización", str(status["ultima_sincronizacion"] or "Nunca"))
        console.print(table)
    finally:
        conn.close()


# ─── BOOKS COMMANDS ──────────────────────────────────────────────────────────

@books_app.command("list")
def cmd_books_list(
    estado: str = typer.Option(None, "--estado", "-e", help="Filtrar por: leyendo | pausado | completado"),
):
    """Lista los libros técnicos en lectura y su progreso."""
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        repo = LibroRepository(conn, cuenta.id)
        filtro_estado = EstadoLibro(estado.lower()) if estado else None
        libros = repo.list_all(estado=filtro_estado)

        table = Table(title="📖 Libros Técnicos en Seguimiento (Reading Tracker)")
        table.add_column("ID", style="dim", width=4)
        table.add_column("Título", style="bold white")
        table.add_column("Capítulo", justify="center")
        table.add_column("Avance", justify="right")
        table.add_column("Estado", style="yellow")
        table.add_column("Ruta Vault", style="dim")

        for l in libros:
            color = "green" if l.porcentaje_leido >= 100.0 else ("cyan" if l.porcentaje_leido > 0 else "red")
            table.add_row(
                str(l.id),
                l.titulo,
                f"{l.capitulo_actual} / {l.total_capitulos}",
                f"[{color}]{l.porcentaje_leido:.1f}%[/{color}]",
                l.estado.value,
                l.ruta_vault or "-",
            )

        if not libros:
            console.print("[dim]No hay libros registrados. Usá 'aulento books add' para comenzar uno.[/dim]")
        else:
            console.print(table)
    finally:
        conn.close()


@books_app.command("add")
def cmd_books_add(
    titulo: str = typer.Option(..., "--titulo", "-t", help="Título de la obra"),
    total_capitulos: int = typer.Option(..., "--total", "-c", help="Total de capítulos o secciones"),
    capitulo_actual: int = typer.Option(1, "--actual", "-a", help="Capítulo actual de inicio"),
    ruta_vault: str = typer.Option(None, "--vault", "-v", help="Ruta de notas en el vault"),
):
    """Registra un nuevo libro técnico para seguimiento de lectura."""
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        repo = LibroRepository(conn, cuenta.id)
        libro = repo.create(
            LibroCreate(
                titulo=titulo,
                capitulo_actual=capitulo_actual,
                total_capitulos=total_capitulos,
                ruta_vault=ruta_vault,
            )
        )
        console.print(f"[bold green]✔[/bold green] Libro registrado con ID [cyan]{libro.id}[/cyan]: [bold]{libro.titulo}[/bold] ({libro.porcentaje_leido:.1f}% leído).")
    finally:
        conn.close()


@books_app.command("advance")
def cmd_books_advance(
    libro_id: int = typer.Argument(..., help="ID del libro a avanzar"),
    capitulos: int = typer.Option(1, "--capitulos", "-n", help="Cantidad de capítulos leídos a sumar"),
):
    """Avanza rápidamente el capítulo actual de un libro."""
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        repo = LibroRepository(conn, cuenta.id)
        updated = repo.advance_chapter(libro_id, chapters=capitulos)
        if not updated:
            console.print(f"[bold red]Error:[/bold red] Libro ID {libro_id} no encontrado.")
            raise typer.Exit(code=1)
        console.print(
            f"[bold green]✔[/bold green] [bold]{updated.titulo}[/bold] avanzado a capítulo "
            f"[cyan]{updated.capitulo_actual}/{updated.total_capitulos}[/cyan] "
            f"([bold green]{updated.porcentaje_leido:.1f}%[/bold green], Estado: [yellow]{updated.estado.value}[/yellow])."
        )
    finally:
        conn.close()


@books_app.command("sync-google")
def cmd_books_sync_google():
    """Sincroniza estanterías y avance de lectura con Google Play Libros."""
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        from aulento.connectors.google_books import (
            AutorizacionGoogleBooksInvalida,
            GoogleBooksConnector,
            GoogleBooksError,
        )
        connector = GoogleBooksConnector(conn, cuenta.id)
        if not connector.esta_autorizado():
            console.print("[bold yellow]⚠[/bold yellow] Google Play Libros no está vinculado a esta cuenta.")
            console.print("Ingresá a la interfaz web para iniciar la vinculación OAuth.")
            raise typer.Exit(code=1)
        res = connector.sincronizar()
        console.print(
            f"[bold green]✔[/bold green] Sincronización completada: [cyan]{res['sincronizados']}[/cyan] libros procesados "
            f"([green]+{res['creados']}[/green] creados, [yellow]{res['actualizados']}[/yellow] actualizados)."
        )
        for d in res.get("detalles", []):
            console.print(f"  • {d['titulo']} ({d['accion']}) -> pág. {d['pagina']}")
    except (AutorizacionGoogleBooksInvalida, GoogleBooksError) as e:
        console.print(f"[bold red]Error al sincronizar:[/bold red] {e}")
        raise typer.Exit(code=1)
    finally:
        conn.close()


@books_app.command("google-status")
def cmd_books_google_status():
    """Muestra el estado de la conexión con Google Play Libros."""
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        from aulento.connectors.google_books import GoogleBooksConnector
        connector = GoogleBooksConnector(conn, cuenta.id)
        conectado = connector.esta_autorizado()
        cliente = connector.obtener_cliente_oauth() is not None
        estado_str = "[bold green]Conectado[/bold green]" if conectado else "[bold yellow]No conectado[/bold yellow]"
        cliente_str = "[bold green]Configurado[/bold green]" if cliente else "[bold red]Falta configurar[/bold red]"
        console.print(f"Google Play Libros: {estado_str} (Cliente OAuth: {cliente_str})")
    finally:
        conn.close()


@books_app.command("webhook-info")
def cmd_books_webhook_info():
    """Muestra la configuración y formato para el webhook de Apple Libros (Atajos)."""
    console.print("[bold cyan]Webhook de Sincronización de Lectura (Apple Libros / Atajos)[/bold cyan]")
    console.print("  • [bold]Endpoint:[/bold] POST /api/books/sync/webhook")
    console.print("  • [bold]Autenticación:[/bold] Cabecera Authorization: Bearer <mcp_token> o ?token=<mcp_token>")
    console.print("  • [bold]Cuerpo JSON:[/bold]")
    console.print('    {"titulo": "Título de la obra", "pagina_actual": 42, "total_paginas": 400, "fuente": "apple_books"}')
    console.print("  • [bold]Atajos de Apple:[/bold] Creá una automatización al cerrar Libros que ejecute 'Obtener contenido de URL'.")


@books_app.command("quiz")
def cmd_books_quiz(
    book_id: int = typer.Argument(..., help="ID del libro a evaluar"),
    cantidad: int = typer.Option(3, "--cantidad", "-n", help="Cantidad de preguntas (1 a 5)"),
    capitulo: int = typer.Option(None, "--capitulo", "-c", help="Capítulo a evaluar (opcional)"),
    pagina: int = typer.Option(None, "--pagina", "-p", help="Página de referencia (opcional)"),
):
    """Genera e interactúa con un cuestionario de Active Recall sobre el libro con feedback de IA."""
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        from aulento.core.book_active_recall import BookActiveRecallService
        from aulento.models.book_active_recall import (
            ActiveRecallEvaluateRequest,
            ActiveRecallGenerateRequest,
            UserAnswerItem,
        )
        service = BookActiveRecallService(conn, cuenta.id)
        console.print("[bold cyan]🧠 Generando cuestionario de Active Recall con IA...[/bold cyan]")
        req = ActiveRecallGenerateRequest(
            capitulo_desde=capitulo,
            capitulo_hasta=capitulo,
            pagina_desde=pagina,
            pagina_hasta=pagina,
            cantidad=cantidad,
        )
        try:
            preguntas_resp = service.generar_preguntas(book_id, req)
        except ValueError as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            raise typer.Exit(1)

        console.print(f"\n[bold green]📚 {preguntas_resp.titulo}[/bold green] ({preguntas_resp.tramo_evaluado})")
        respuestas_usuario = []
        for p in preguntas_resp.preguntas:
            console.print(f"\n[bold yellow]Pregunta {p.id}:[/bold yellow] {p.pregunta}")
            console.print(f"[dim]Objetivo: {p.objetivo_conceptual}[/dim]")
            ans = typer.prompt("Tu respuesta")
            respuestas_usuario.append(
                UserAnswerItem(
                    question_id=p.id,
                    pregunta=p.pregunta,
                    respuesta_usuario=ans,
                )
            )

        console.print("\n[bold cyan]Evaluando respuestas con IA...[/bold cyan]")
        eval_resp = service.evaluar_respuestas(
            book_id,
            ActiveRecallEvaluateRequest(
                tramo_evaluado=preguntas_resp.tramo_evaluado,
                respuestas=respuestas_usuario,
            ),
        )

        color_score = "green" if eval_resp.score_global >= 80 else ("yellow" if eval_resp.score_global >= 60 else "red")
        console.print(f"\n[bold]Calificación:[/bold] [{color_score}]{eval_resp.score_global}% ({eval_resp.veredicto})[/{color_score}]")
        console.print(f"[italic]{eval_resp.resumen_pedagogico}[/italic]\n")

        for ev in eval_resp.evaluaciones:
            console.print(f"[bold]P{ev.question_id} (Puntaje: {ev.puntaje}/100):[/bold]")
            if ev.aciertos:
                console.print(f"  [green]✓ Aciertos:[/green] {ev.aciertos}")
            if ev.mejoras:
                console.print(f"  [yellow]⚠ A profundizar:[/yellow] {ev.mejoras}")
            if ev.explicacion_optima:
                console.print(f"  [cyan]ℹ Explicación de referencia:[/cyan] {ev.explicacion_optima}")
    finally:
        conn.close()


@books_app.command("harvest")
def cmd_books_harvest(
    book_id: int = typer.Argument(..., help="ID del libro del cual cosechar tarjetas"),
    cantidad: int = typer.Option(5, "--cantidad", "-n", help="Cantidad de tarjetas a generar"),
    capitulo: int = typer.Option(None, "--capitulo", "-c", help="Capítulo específico"),
    auto_commit: bool = typer.Option(False, "--commit", "-y", help="Guardar automáticamente sin pedir confirmación"),
):
    """Cosecha tarjetas FSRS de vocabulario y conceptos técnicos desde el libro."""
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        from aulento.core.book_active_recall import BookActiveRecallService
        from aulento.models.book_active_recall import (
            BookHarvestCommitRequest,
            BookHarvestPreviewRequest,
        )
        service = BookActiveRecallService(conn, cuenta.id)
        console.print("[bold cyan]🃏 Extrayendo términos técnicos y conceptos con IA...[/bold cyan]")
        try:
            prev = service.previsualizar_cosecha(
                book_id,
                BookHarvestPreviewRequest(capitulo=capitulo, cantidad=cantidad),
            )
        except ValueError as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            raise typer.Exit(1)

        table = Table(title=f"🃏 Tarjetas FSRS Cosechadas: {prev.titulo} ({prev.tramo})")
        table.add_column("#", style="dim", width=3)
        table.add_column("Pregunta / Término", style="bold cyan")
        table.add_column("Respuesta Esperada", style="green")
        table.add_column("Contexto de Uso", style="yellow")

        for idx, card in enumerate(prev.cards, 1):
            table.add_row(str(idx), card.item_pregunta, card.respuesta_esperada, card.contexto_uso or "-")

        console.print(table)

        if not auto_commit:
            confirmar = typer.confirm(f"¿Guardar {len(prev.cards)} tarjetas en tu mazo FSRS?", default=True)
            if not confirmar:
                console.print("[yellow]Operación cancelada. No se guardaron tarjetas.[/yellow]")
                return

        com = service.confirmar_cosecha(book_id, BookHarvestCommitRequest(cards=prev.cards))
        console.print(f"[bold green]✓ {com.guardadas} tarjetas añadidas al mazo FSRS[/bold green] (Omitidas duplicadas: {com.omitidas_duplicadas})")
    finally:
        conn.close()



# ─── SCHEDULE COMMANDS ───────────────────────────────────────────────────────

@schedule_app.command("list")
def cmd_schedule_list(
    dia: int = typer.Option(None, "--dia", "-d", help="Filtrar por día de la semana (1=Lunes .. 7=Domingo)"),
):
    """Lista los bloques horarios semanales del SOP Cronogramas de Estudio."""
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        repo = BloqueHorarioRepository(conn, cuenta.id)
        bloques = repo.list_all(dia_semana=dia)

        table = Table(title="🗓 Cronograma Semanal de Estudio (Bloques Horarios)")
        table.add_column("ID", style="dim", width=4)
        table.add_column("Día", style="bold cyan")
        table.add_column("Horario", justify="center", style="yellow")
        table.add_column("Tipo", style="magenta")
        table.add_column("Descripción", style="white")
        table.add_column("Acceso Directo", style="blue")

        for b in bloques:
            nombre_dia = DIAS_SEMANA.get(b.dia_semana, f"Día {b.dia_semana}")
            table.add_row(
                str(b.id),
                nombre_dia,
                f"{b.hora_inicio} - {b.hora_fin}",
                b.tipo.value,
                b.descripcion,
                b.url_acceso or "-",
            )

        if not bloques:
            console.print("[dim]No hay bloques horarios cargados aún. Usá 'aulento schedule add'.[/dim]")
        else:
            console.print(table)
    finally:
        conn.close()


@schedule_app.command("add")
def cmd_schedule_add(
    dia: int = typer.Option(..., "--dia", "-d", help="1=Lunes a 7=Domingo"),
    inicio: str = typer.Option(..., "--inicio", "-i", help="Hora inicio (ej. 10:30)"),
    fin: str = typer.Option(..., "--fin", "-f", help="Hora fin (ej. 12:30)"),
    tipo: str = typer.Option("curso", "--tipo", "-t", help="curso | lectura | ingles | repaso | otro"),
    descripcion: str = typer.Option(..., "--desc", help="Descripción de la actividad"),
    url: str = typer.Option(None, "--url", help="URL opcional de acceso directo"),
):
    """Agrega un bloque horario al cronograma semanal."""
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        repo = BloqueHorarioRepository(conn, cuenta.id)
        bloque = repo.create(
            BloqueHorarioCreate(
                dia_semana=dia,
                hora_inicio=inicio,
                hora_fin=fin,
                tipo=TipoBloque(tipo.lower()),
                descripcion=descripcion,
                url_acceso=url,
            )
        )
        dia_nom = DIAS_SEMANA.get(bloque.dia_semana, str(bloque.dia_semana))
        console.print(f"[bold green]✔[/bold green] Bloque agendado: [bold]{dia_nom} {bloque.hora_inicio}-{bloque.hora_fin}[/bold] ({bloque.descripcion}).")
    finally:
        conn.close()


# ─── PLANNER COMMANDS ─────────────────────────────────────────────────────────

@planner_app.command("briefing")
def cmd_planner_briefing():
    """Muestra el resumen ejecutivo matutino y estado de urgencia pedagógica."""
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        engine = StudyPlannerEngine(conn, cuenta.id)
        b = engine.obtener_daily_briefing()

        grid = Table.grid(expand=True)
        grid.add_column(justify="left")
        grid.add_row(f"[bold cyan]📅 Fecha:[/bold cyan] {b.fecha}")
        grid.add_row(f"[bold yellow]🔥 Racha:[/bold yellow] {b.racha_dias} días (Récord: {b.record_racha})")
        grid.add_row(f"[bold green]⏱ Estudiado hoy:[/bold green] {'Sí' if b.estudiado_hoy else 'No'} ({b.minutos_hoy} min)")
        grid.add_row(f"[bold magenta]🎴 FSRS Due:[/bold magenta] {b.fsrs_due_count} tarjetas vencidas")
        grid.add_row(f"[bold magenta]🧠 Macro-FSRS Due:[/bold magenta] {b.macro_fsrs_due_count} temas")

        if b.curso_sugerido:
            grid.add_row(f"[bold blue]🎓 Curso Sugerido:[/bold blue] {b.curso_sugerido['nombre_curso']} ({b.curso_sugerido['progreso_pct']:.0f}%) [{b.curso_sugerido['prioridad'].upper()}]")
        if b.libro_sugerido:
            grid.add_row(f"[bold white]📖 Libro Sugerido:[/bold white] {b.libro_sugerido['titulo']} (Pág {b.libro_sugerido['pagina_actual']}/{b.libro_sugerido['total_paginas']})")

        urgency_color = "red" if b.urgency_score > 60 else ("yellow" if b.urgency_score > 30 else "green")
        grid.add_row(f"[bold]⚡ Urgencia Pedagógica:[/bold] [{urgency_color}]{b.urgency_score}/100[/{urgency_color}]")
        grid.add_row("")
        grid.add_row(f"[italic]{b.mensaje_enfoque}[/italic]")

        console.print(Panel(grid, title="🎯 Daily Briefing Ejecutivo", border_style="cyan"))
    finally:
        conn.close()


@planner_app.command("plan")
def cmd_planner_plan(
    minutes: int = typer.Option(60, "-m", "--minutes", help="Minutos disponibles para estudiar"),
    start: str | None = typer.Option(None, "-s", "--start", help="Hora de inicio en formato HH:MM"),
    apply: bool = typer.Option(False, "-a", "--apply", help="Aplica el plan insertando los bloques en la agenda"),
):
    """Calcula un plan de estudio adaptativo estructurado en fases y permite aplicarlo a la agenda."""
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        engine = StudyPlannerEngine(conn, cuenta.id)
        req = AdaptivePlanRequest(available_minutes=minutes, start_time=start)
        plan = engine.generar_plan_adaptativo(req)

        table = Table(title=f"🎯 Plan Adaptativo ({plan.total_minutos} min - Urgencia: {plan.score_urgencia}/100)")
        table.add_column("#", style="dim", width=3)
        table.add_column("Horario", style="cyan", width=13)
        table.add_column("Fase", style="bold yellow", width=18)
        table.add_column("Actividad", style="white")
        table.add_column("Min", justify="right", width=5)
        table.add_column("Meta", style="green")

        for i, b in enumerate(plan.bloques, 1):
            horario = f"{b.hora_inicio or '--'} - {b.hora_fin or '--'}"
            table.add_row(
                str(i),
                horario,
                b.fase.value.replace("_", " ").title(),
                f"[bold]{b.titulo}[/bold]\n[dim]{b.descripcion}[/dim]",
                str(b.duracion_minutos),
                b.meta_especifica or "-",
            )

        console.print(table)
        console.print(f"[dim]{plan.resumen_pedagogico}[/dim]\n")

        if apply:
            app_req = ApplyPlanRequest(bloques=plan.bloques, reemplazar_existentes=False)
            res = engine.aplicar_plan_a_agenda(app_req)
            console.print(f"[bold green]✔ {res.mensaje}[/bold green] (Bloques creados: {res.bloque_ids})")
    finally:
        conn.close()
