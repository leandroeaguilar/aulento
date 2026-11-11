"""Comandos CLI para inspeccionar, configurar y probar los proveedores de IA de la cuenta."""


import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from aulento.cli.contexto import cuenta_de_la_cli
from aulento.core.ia.pasarela import PasarelaDeIA, exigir_proveedor
from aulento.core.ia.tipos import NOMBRE_VISIBLE, PROVEEDORES, IANoDisponibleError
from aulento.db.connection import get_connection

ia_app = typer.Typer(help="Configuración, selección y prueba de proveedores de IA (Gemini, Anthropic y OpenAI)")
console = Console()


def _validar_proveedor(proveedor: str) -> str:
    try:
        return exigir_proveedor((proveedor or "").strip().lower())
    except ValueError as e:
        console.print(f"[bold red]✖ {escape(str(e))}[/bold red]")
        raise typer.Exit(code=1) from None


@ia_app.command("status")
def cmd_ia_status():
    """Muestra el estado de cada proveedor de IA para la cuenta (proveedor activo, claves, modelos y capacidades)."""
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        pasarela = PasarelaDeIA(conn, cuenta.id)
        estado = pasarela.estado()
    finally:
        conn.close()

    activo = estado["proveedor_activo"]
    console.print(
        f"\n[bold]Cuenta:[/bold] [cyan]{escape(cuenta.nombre_usuario)}[/cyan] · "
        f"[bold]Proveedor activo:[/bold] [bold green]{escape(NOMBRE_VISIBLE.get(activo, activo))}[/bold green]"
    )

    table = Table(title="🤖 Proveedores de IA Configurados", show_header=True, header_style="bold cyan")
    table.add_column("Proveedor", style="bold white", width=18)
    table.add_column("Estado", justify="center", width=10)
    table.add_column("Clave Guardada", width=22)
    table.add_column("Modelo Activo", width=24)
    table.add_column("Capacidades", style="dim")

    for prov in PROVEEDORES:
        info = estado["proveedores"].get(prov, {})
        es_activo = "[bold green]✔ Activo[/bold green]" if prov == activo else "[dim]Inactivo[/dim]"
        nombre = escape(NOMBRE_VISIBLE.get(prov, prov))

        if info.get("error_de_clave"):
            clave_str = f"[bold red]✖ {escape(info['error_de_clave'])}[/bold red]"
        elif info.get("tiene_clave"):
            pista = info.get("clave") or ""
            clave_str = f"[green]✔ Configurada ({escape(pista)})[/green]"
        else:
            clave_str = "[dim]Sin clave[/dim]"

        modelo = escape(str(info.get("modelo") or "(ninguno)"))
        capacidades = ", ".join(info.get("capacidades", []))

        table.add_row(nombre, es_activo, clave_str, modelo, capacidades)

    console.print(table)
    console.print(
        "[dim]Para cambiar de proveedor: [bold]aulento ia set-provider <gemini|anthropic|openai>[/bold]\n"
        "Para guardar una clave:    [bold]aulento ia set-key <proveedor> [--nivel free|paid][/bold]\n"
        "Para probar la conexión:   [bold]aulento ia test <proveedor>[/bold][/dim]\n"
    )


@ia_app.command("set-provider")
def cmd_ia_set_provider(
    proveedor: str = typer.Argument(..., help="gemini, anthropic u openai"),
):
    """Elige el proveedor de IA activo para la cuenta."""
    prov = _validar_proveedor(proveedor)
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        pasarela = PasarelaDeIA(conn, cuenta.id)
        pasarela.fijar_proveedor(prov)
    finally:
        conn.close()

    console.print(
        f"[bold green]✔ Proveedor activo de la cuenta {escape(cuenta.nombre_usuario)} "
        f"fijado en [bold]{escape(NOMBRE_VISIBLE[prov])}[/bold].[/bold green]"
    )


@ia_app.command("set-key")
def cmd_ia_set_key(
    proveedor: str = typer.Argument(..., help="gemini, anthropic u openai"),
    key: str | None = typer.Option(
        None,
        "--key",
        "-k",
        help="Clave de API del proveedor (si no se especifica, se solicita oculta)",
    ),
    nivel: str = typer.Option("free", "--nivel", "-n", help="Nivel de Gemini: 'free' o 'paid' (por defecto 'free')"),
):
    """Guarda cifrada la clave de API para un proveedor. La clave nunca se muestra en claro."""
    prov = _validar_proveedor(proveedor)
    if not key:
        key = typer.prompt(f"Clave de API para {NOMBRE_VISIBLE[prov]}", hide_input=True)

    if not key or not key.strip():
        console.print("[bold red]✖ La clave no puede estar vacía.[/bold red]")
        raise typer.Exit(code=1)

    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        pasarela = PasarelaDeIA(conn, cuenta.id)
        pasarela.guardar_clave(prov, key.strip(), nivel=nivel.strip().lower())
    except ValueError as e:
        console.print(f"[bold red]✖ {escape(str(e))}[/bold red]")
        raise typer.Exit(code=1) from None
    finally:
        conn.close()

    console.print(
        f"[bold green]✔ Clave de {escape(NOMBRE_VISIBLE[prov])} guardada exitosamente "
        f"(cifrada, para la cuenta {escape(cuenta.nombre_usuario)}).[/bold green]"
    )


@ia_app.command("remove-key")
def cmd_ia_remove_key(
    proveedor: str = typer.Argument(..., help="gemini, anthropic u openai"),
    nivel: str | None = typer.Option(
        None, "--nivel", "-n", help="En Gemini, nivel a borrar ('free' o 'paid'); si se omite, borra ambas"
    ),
):
    """Elimina la clave guardada de un proveedor para la cuenta."""
    prov = _validar_proveedor(proveedor)
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        pasarela = PasarelaDeIA(conn, cuenta.id)
        borrada = pasarela.quitar_clave(prov, nivel=nivel.strip().lower() if nivel else None)
    except ValueError as e:
        console.print(f"[bold red]✖ {escape(str(e))}[/bold red]")
        raise typer.Exit(code=1) from None
    finally:
        conn.close()

    if borrada:
        console.print(
            f"[bold green]✔ Clave de {escape(NOMBRE_VISIBLE[prov])} eliminada para la cuenta {escape(cuenta.nombre_usuario)}.[/bold green]"
        )
    else:
        console.print(f"[yellow]No había clave registrada de {escape(NOMBRE_VISIBLE[prov])} para eliminar.[/yellow]")


@ia_app.command("set-model")
def cmd_ia_set_model(
    proveedor: str = typer.Argument(..., help="gemini, anthropic u openai"),
    modelo: str = typer.Argument(..., help="Nombre del modelo (ej. claude-sonnet-5-5, gpt-4o, gemini-2.5-flash)"),
):
    """Guarda el modelo preferido que usará la cuenta con ese proveedor."""
    prov = _validar_proveedor(proveedor)
    if not modelo or not modelo.strip():
        console.print("[bold red]✖ El modelo no puede estar vacío.[/bold red]")
        raise typer.Exit(code=1)

    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        pasarela = PasarelaDeIA(conn, cuenta.id)
        pasarela.fijar_modelo(prov, modelo.strip())
    finally:
        conn.close()

    console.print(
        f"[bold green]✔ Modelo de {escape(NOMBRE_VISIBLE[prov])} fijado en "
        f"[bold]{escape(modelo.strip())}[/bold] para la cuenta {escape(cuenta.nombre_usuario)}.[/bold green]"
    )


@ia_app.command("models")
def cmd_ia_models(
    proveedor: str = typer.Argument(..., help="gemini, anthropic u openai"),
):
    """Consulta en vivo al proveedor la lista de modelos disponibles para la clave de la cuenta."""
    prov = _validar_proveedor(proveedor)
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        pasarela = PasarelaDeIA(conn, cuenta.id)
        modelos = pasarela.modelos(prov)
    except IANoDisponibleError as e:
        console.print(f"[bold red]✖ {escape(str(e))}[/bold red]")
        raise typer.Exit(code=1) from None
    finally:
        conn.close()

    table = Table(title=f"📋 Modelos Disponibles en {NOMBRE_VISIBLE[prov]}", show_header=True)
    table.add_column("#", justify="right", style="dim", width=4)
    table.add_column("Modelo", style="bold white")

    for i, mod in enumerate(modelos, 1):
        table.add_row(str(i), mod)

    console.print(table)


@ia_app.command("test")
def cmd_ia_test(
    proveedor: str = typer.Argument(..., help="gemini, anthropic u openai"),
):
    """Prueba la conexión y credenciales de la cuenta con un pedido mínimo hacia el proveedor."""
    prov = _validar_proveedor(proveedor)
    cuenta = cuenta_de_la_cli()
    conn = get_connection()
    try:
        pasarela = PasarelaDeIA(conn, cuenta.id)
        resultado = pasarela.probar(prov)
    finally:
        conn.close()

    ok = resultado.get("ok", False)
    modelo = escape(str(resultado.get("modelo") or ""))
    mensaje = escape(str(resultado.get("mensaje") or ""))
    latencia = resultado.get("latencia_ms")
    lat_str = f" · Latencia: {latencia} ms" if latencia is not None else ""

    if ok:
        console.print(
            Panel(
                f"[bold green]✔ Conexión exitosa[/bold green]\n"
                f"Proveedor: {escape(NOMBRE_VISIBLE[prov])}\n"
                f"Modelo: {modelo}{lat_str}\n\n"
                f"[dim]{mensaje}[/dim]",
                title="Prueba de Conexión IA",
                border_style="green",
            )
        )
    else:
        console.print(
            Panel(
                f"[bold red]✖ Conexión fallida[/bold red]\n"
                f"Proveedor: {escape(NOMBRE_VISIBLE[prov])}\n"
                f"Modelo: {modelo}\n\n"
                f"[bold red]{mensaje}[/bold red]",
                title="Prueba de Conexión IA",
                border_style="red",
            )
        )
        raise typer.Exit(code=1)
