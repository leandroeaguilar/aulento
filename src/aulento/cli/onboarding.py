"""Módulo interactivo de Onboarding para nuevos usuarios de Aulento."""

import sqlite3
import webbrowser

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from aulento.auth import servicio
from aulento.auth.modelos import Usuario
from aulento.auth.repositorio import RepositorioAuth
from aulento.cli.contexto import CuentaNoResuelta, resolver_cuenta_de_la_cli
from aulento.cli.user_commands import mostrar_importacion
from aulento.config import ensure_data_dir, get_db_path
from aulento.core.gemini_gateway import GeminiGateway
from aulento.core.importacion import Informe
from aulento.db.connection import get_connection
from aulento.db.migrations import ErrorDeMigracion
from aulento.db.schema import init_db, seed_plataformas
from aulento.fsrs.deck_seed import seed_fsrs_deck

console = Console()
onboarding_app = typer.Typer(help="Asistente interactivo de bienvenida y configuración inicial")


def _cuenta_del_asistente(conn: sqlite3.Connection) -> Usuario | None:
    """Cuenta cuyos datos prepara el asistente: la de la CLI o, si todavía no existe ninguna, una nueva administradora."""
    try:
        return resolver_cuenta_de_la_cli()
    except CuentaNoResuelta as error:
        if RepositorioAuth(conn).contar_usuarios() > 0:
            console.print(f"[yellow]⚠ No se modificaron datos: {escape(str(error))}[/yellow]", soft_wrap=True)
            return None

    # El core es de una sola persona: la cuenta local, sin contraseña, como la crea la web en modo local (051)
    importaciones: list[Informe | None] = []
    usuario = servicio.crear_cuenta_local(conn, al_importar=importaciones.append)
    console.print(f"[green]✔ Cuenta local lista: [bold]{escape(usuario.nombre_usuario)}[/bold].[/green]")
    for informe in importaciones:
        mostrar_importacion(informe)
    return usuario


def _preparar_datos_de_la_cuenta(conn: sqlite3.Connection, con_mazo: bool) -> int | None:
    """Siembra las plataformas de la cuenta y deja su mazo sembrado o vacío; retorna sus tarjetas, o None sin cuenta."""
    cuenta = _cuenta_del_asistente(conn)
    if cuenta is None:
        return None
    seed_plataformas(conn, cuenta.id)
    if con_mazo:
        return seed_fsrs_deck(conn, cuenta.id)
    conn.execute("DELETE FROM fsrs_items WHERE user_id = ?;", (cuenta.id,))
    conn.commit()
    return 0


def _configurar_clave_de_ia(conn: sqlite3.Connection) -> None:
    """Ofrece cargar la clave de Gemini de la cuenta de la CLI; se guarda cifrada y nunca se muestra."""
    try:
        cuenta: Usuario | None = resolver_cuenta_de_la_cli()
        motivo = ""
    except (CuentaNoResuelta, ErrorDeMigracion) as error:
        cuenta, motivo = None, str(error)

    if cuenta is not None:
        estado = GeminiGateway(conn, cuenta.id).get_status()
        if estado.has_free_key or estado.has_paid_key:
            console.print("[green]✔ Clave Gemini ya configurada.[/green]")
            return

    api_key = typer.prompt(
        "Ingresa tu clave de API de Gemini (o presiona Enter para omitir)",
        default="",
        show_default=False,
        hide_input=True,
    ).strip()
    if not api_key:
        console.print("[dim]Omitido. Puedes configurarla más tarde desde la Web o con 'aulento fsrs gemini-config'.[/dim]")
    elif cuenta is None:
        console.print(f"[yellow]⚠ No se guardó la clave: {escape(motivo)}[/yellow]", soft_wrap=True)
    else:
        GeminiGateway(conn, cuenta.id).save_keys_config(free_key=api_key)
        console.print("[green]✔ Clave de Gemini guardada cifrada para tu cuenta.[/green]")


@onboarding_app.callback(invoke_without_command=True)
def run_onboarding_wizard():
    """Ejecuta el asistente interactivo paso a paso para configurar Aulento."""
    console.print("")
    console.print(
        Panel.fit(
            "[bold cyan]🎓 ¡Bienvenido a Aulento (Local-First)![/bold cyan]\n"
            "[dim]Tu centro operativo personal para plataformas académicas, libros técnicos y FSRS v5.[/dim]",
            border_style="cyan",
        )
    )
    console.print("")

    db_path = get_db_path()
    ensure_data_dir()

    # Paso 1: Configuración de la Base de Datos
    console.print("[bold yellow]Paso 1: Inicialización de la Base de Datos[/bold yellow]")
    console.print(f"[dim]Ubicación física local:[/dim] [cyan]{db_path}[/cyan]\n")

    if db_path.exists():
        console.print("[green]✔ Ya existe una base de datos en esta máquina.[/green]")
        reset_choice = Confirm.ask("¿Deseas conservarla sin modificar?", default=True)
        if not reset_choice:
            init_mode = Prompt.ask(
                "¿Cómo deseas reinicializarla?",
                choices=["limpia", "recomendado"],
                default="limpia",
            )
            conn = get_connection(db_path)
            try:
                init_db(conn)
                total = _preparar_datos_de_la_cuenta(conn, con_mazo=init_mode == "recomendado")
                if total:
                    console.print(f"[green]✔ Base inicializada con {total} tarjetas de inglés técnico.[/green]")
                elif total == 0:
                    console.print("[green]✔ Base inicializada en cero absoluto (0 tarjetas, 0 rutas).[/green]")
            finally:
                conn.close()
    else:
        console.print("Elige cómo deseas comenzar:")
        console.print("  [bold]1[/bold] - [bold green]Cero absoluto[/bold green] (Base limpia para crear tu propio contenido desde cero)")
        console.print("  [bold]2[/bold] - [bold cyan]Recomendado[/bold cyan] (Con mazo inicial de 159 colocaciones de inglés técnico)")
        
        choice = Prompt.ask("Selecciona una opción", choices=["1", "2"], default="1")
        conn = get_connection(db_path)
        try:
            init_db(conn)
            total = _preparar_datos_de_la_cuenta(conn, con_mazo=choice == "2")
            if total:
                console.print(f"[green]✔ Mazo de inglés sembrado con {total} tarjetas profesionales.[/green]")
            elif total == 0:
                console.print("[green]✔ Base de datos lista en blanco (0 tarjetas, 0 rutas).[/green]")
        finally:
            conn.close()

    console.print("")

    # Paso 2: Configuración de Gemini AI (Opcional)
    console.print("[bold yellow]Paso 2: Asistente de IA (Google Gemini 1.5 Flash)[/bold yellow]")
    console.print("[dim]Permite generar clases magistrales y evaluar pronunciación de inglés. (Opcional)[/dim]")
    conn = get_connection(db_path)
    try:
        _configurar_clave_de_ia(conn)
    finally:
        conn.close()

    console.print("")

    # Paso 3: Lanzar Dashboard Web
    console.print("[bold yellow]Paso 3: ¡Todo Listo![/bold yellow]")
    console.print("[dim]Aulento está completamente configurado y listo para estudiar.[/dim]\n")

    launch_web = Confirm.ask("¿Deseas iniciar el servidor y abrir el Dashboard Web en tu navegador?", default=True)
    if launch_web:
        console.print("\n[bold green]🚀 Iniciando Aulento en http://localhost:8000 ...[/bold green]")
        console.print("[dim]Presiona Ctrl + C en la terminal cuando desees detener el servidor.[/dim]\n")
        try:
            webbrowser.open("http://localhost:8000")
        except Exception:
            pass
        from aulento.cli.web_commands import run_web_server
        run_web_server(host="127.0.0.1", port=8000, reload=False)
    else:
        console.print("\n[cyan]Puedes iniciar el servidor web en cualquier momento ejecutando:[/cyan]")
        console.print("  [bold]python -m aulento serve[/bold]  o haciendo doble clic en  [bold]start.bat[/bold]\n")
