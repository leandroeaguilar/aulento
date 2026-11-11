"""Comandos CLI de la cuenta: listarla e importar los archivos de una instalación anterior.

Crear, invitar, restablecer, activar y desactivar cuentas es multiusuario: vive en la nube (051).
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from aulento.auth.modelos import ROL_ADMIN
from aulento.auth.repositorio import RepositorioAuth
from aulento.core.importacion import (
    ERRORES_DE_IMPORTACION,
    Informe,
    importar_archivos_anteriores,
)
from aulento.core.secretos import ClaveMaestraInvalida
from aulento.db.connection import get_connection
from aulento.db.migrations import migrar
from aulento.vault.rutas import CarpetaDeVaultInvalida, fijar_vault_externo

user_app = typer.Typer(
    help="Cuenta de usuario: listar e importar archivos de una instalación anterior"
)
console = Console()

AVISO_CLAVE_SOLO_EN_EL_ENTORNO = (
    "Aviso: la cuenta quedó sin clave de Gemini, porque no había ninguna en los archivos. Una clave que vivía "
    "solo en una variable de entorno no se importa: cargala desde Configuración en la web."
)


@contextmanager
def _base() -> Iterator[sqlite3.Connection]:
    """Abre la base con el esquema al día y la cierra al terminar."""
    conn = get_connection()
    try:
        migrar(conn)
        yield conn
    finally:
        conn.close()


def _fallar(mensaje: str) -> typer.Exit:
    console.print(f"[bold red]Error:[/bold red] {escape(mensaje)}")
    return typer.Exit(code=1)


def _cuenta_por_nombre(conn: sqlite3.Connection, nombre: str) -> sqlite3.Row:
    fila = RepositorioAuth(conn).usuario_por_nombre(nombre.lower())
    if fila is None:
        raise _fallar(f"No existe una cuenta llamada '{nombre}'.")
    return fila


def mostrar_importacion(informe: Informe | None) -> None:
    """Muestra el informe de una importación de archivos anteriores; el informe no lleva secretos.

    Con None avisa que la importación no pudo correr; si no había nada que importar no muestra nada.
    """
    if informe is None:
        console.print(
            "[yellow]⚠ No se pudieron importar los archivos anteriores de la instalación. "
            "Probá de nuevo con 'aulento user import-files <usuario>'.[/yellow]",
            soft_wrap=True,
        )
        return
    if not informe.encontro_algo:
        return
    for linea in informe.lineas():
        console.print(linea, markup=False, highlight=False, soft_wrap=True)


@user_app.command("list")
def cmd_user_list():
    """Lista las cuentas con su rol, estado y último ingreso."""
    with _base() as conn:
        cuentas = RepositorioAuth(conn).listar_usuarios()
    if not cuentas:
        console.print("[dim]Todavía no hay cuentas. Creá la cuenta local con 'aulento onboarding' (o abriendo la web).[/dim]")
        return
    tabla = Table(title="Cuentas de Aulento")
    tabla.add_column("ID", style="dim", width=4)
    tabla.add_column("Usuario", style="bold white")
    tabla.add_column("Rol", style="cyan")
    tabla.add_column("Estado")
    tabla.add_column("Creada", style="dim")
    tabla.add_column("Último ingreso", style="dim")
    for cuenta in cuentas:
        tabla.add_row(
            str(cuenta["id"]),
            escape(cuenta["nombre_usuario"]),
            cuenta["rol"],
            "[green]activa[/green]" if cuenta["activo"] else "[red]desactivada[/red]",
            cuenta["creado_en"][:10],
            (cuenta["ultimo_ingreso"] or "-")[:16],
        )
    console.print(tabla)


@user_app.command("import-files")
def cmd_user_import_files(
    nombre: str = typer.Argument(..., help="Nombre de usuario de la cuenta que recibe los archivos"),
    vault: str | None = typer.Option(
        None,
        "--vault",
        help="Carpeta existente de esta máquina que pasa a ser el vault de la cuenta (solo administradores)",
    ),
    origen: str | None = typer.Option(
        None,
        "--from",
        help="Carpeta existente donde están los archivos anteriores, si no es el directorio de datos del servidor; "
        "el respaldo queda dentro de ella",
    ),
):
    """Importa a una cuenta los archivos anteriores del directorio de datos: claves, prompts, Duolingo y vault.

    Solo carga lo que la cuenta no tiene y se puede repetir. Los archivos ya importados se mueven a una carpeta
    de respaldo dentro del directorio recorrido; nunca se borran.
    """
    if origen is not None and not Path(origen).is_dir():
        raise _fallar("La carpeta indicada con --from no existe en esta máquina.")
    with _base() as conn:
        fila = _cuenta_por_nombre(conn, nombre)
        if vault is not None:
            if fila["rol"] != ROL_ADMIN:
                raise _fallar("Solo una cuenta administradora puede usar como vault una carpeta de esta máquina.")
            try:
                carpeta = fijar_vault_externo(conn, fila["id"], vault)
            except CarpetaDeVaultInvalida as error:
                raise _fallar(str(error)) from None
            console.print(f"[bold green]✔[/bold green] Vault externo de [bold]{escape(nombre.lower())}[/bold]:")
            console.print(str(carpeta), markup=False, highlight=False, soft_wrap=True)
        try:
            informe = importar_archivos_anteriores(conn, fila["id"], origen=origen)
        except ClaveMaestraInvalida:
            raise
        except ERRORES_DE_IMPORTACION as error:
            raise _fallar(f"No se pudieron importar los archivos anteriores ({type(error).__name__}).") from None
    if informe.encontro_algo:
        mostrar_importacion(informe)
    else:
        console.print("[dim]No hay archivos anteriores para importar.[/dim]")
    if informe.sin_clave_de_ia:
        console.print(AVISO_CLAVE_SOLO_EN_EL_ENTORNO, markup=False, highlight=False, soft_wrap=True)
