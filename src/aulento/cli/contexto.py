"""Cuenta con la que opera la CLI: la indicada con `--user` o `AULENTO_USER`, o la única activa."""

import os

import typer
from rich.console import Console
from rich.markup import escape

from aulento.auth.modelos import Usuario
from aulento.auth.repositorio import RepositorioAuth
from aulento.db.connection import get_connection
from aulento.db.migrations import ErrorDeMigracion, migrar

VARIABLE_DE_CUENTA = "AULENTO_USER"

COMO_INDICARLA = (
    f"Indicá la cuenta con la opción global --user <nombre> (antes del comando) o con la variable {VARIABLE_DE_CUENTA}."
)
COMO_CREARLA = "Creá la cuenta local con 'aulento onboarding' (o abriendo la web)."

console = Console()

_cuenta_indicada: str | None = None
_cuenta_resuelta: Usuario | None = None


class CuentaNoResuelta(Exception):
    """No se pudo saber como qué cuenta opera la CLI; el mensaje dice cómo indicarla."""


def indicar_cuenta(nombre: str | None) -> None:
    """Guarda el valor de la opción global `--user` sin resolverlo y descarta la cuenta ya resuelta."""
    global _cuenta_indicada
    _cuenta_indicada = nombre
    reiniciar_cuenta_de_la_cli()


def reiniciar_cuenta_de_la_cli() -> None:
    """Olvida la cuenta resuelta: la próxima consulta vuelve a leer la base."""
    global _cuenta_resuelta
    _cuenta_resuelta = None


def _nombre_indicado() -> str | None:
    """La opción global gana a la variable de entorno; un valor vacío cuenta como no indicado."""
    for valor in (_cuenta_indicada, os.environ.get(VARIABLE_DE_CUENTA)):
        if valor and valor.strip():
            return valor.strip().lower()
    return None


def hay_cuenta_indicada() -> bool:
    """Dice si la cuenta se pidió de forma explícita, con `--user` o con la variable de entorno."""
    return _nombre_indicado() is not None


def _buscar_cuenta(migrar_la_base: bool) -> Usuario:
    conn = get_connection()
    try:
        if migrar_la_base:
            migrar(conn)
        cuentas = RepositorioAuth(conn).listar_usuarios()
    finally:
        conn.close()

    nombre = _nombre_indicado()
    if nombre is not None:
        fila = next((c for c in cuentas if c["nombre_usuario"] == nombre), None)
        if fila is None:
            raise CuentaNoResuelta(f"No existe una cuenta llamada '{nombre}'. {COMO_INDICARLA}")
        if not fila["activo"]:
            raise CuentaNoResuelta(f"La cuenta '{nombre}' está desactivada. {COMO_INDICARLA}")
    else:
        activas = [c for c in cuentas if c["activo"]]
        if not activas:
            raise CuentaNoResuelta(f"No hay ninguna cuenta activa. {COMO_CREARLA} {COMO_INDICARLA}")
        if len(activas) > 1:
            nombres = ", ".join(c["nombre_usuario"] for c in activas)
            raise CuentaNoResuelta(f"Hay {len(activas)} cuentas activas ({nombres}). {COMO_INDICARLA}")
        fila = activas[0]

    return Usuario(id=fila["id"], nombre_usuario=fila["nombre_usuario"], rol=fila["rol"], activo=True)


def resolver_cuenta_de_la_cli(migrar_la_base: bool = True) -> Usuario:
    """Cuenta como la que opera este proceso; levanta `CuentaNoResuelta` si no se puede determinar.

    Antes de leer las cuentas lleva la base a la última versión; con `migrar_la_base=False` no la toca
    (para los comandos de solo lectura, que solo la llaman con la base ya al día).
    """
    global _cuenta_resuelta
    if _cuenta_resuelta is None:
        _cuenta_resuelta = _buscar_cuenta(migrar_la_base)
    return _cuenta_resuelta


def terminar_por_migracion_fallida(error: ErrorDeMigracion, consola: Console | None = None) -> typer.Exit:
    """Explica una migración fallida sin traceback y devuelve la salida con error que el comando tiene que levantar."""
    consola = consola or console
    consola.print(f"[bold red]Error:[/bold red] {escape(str(error))}", soft_wrap=True)
    causa = error.__cause__
    if causa is not None:
        consola.print(f"[dim]Causa: {escape(str(causa))}[/dim]", soft_wrap=True)
    return typer.Exit(code=1)


def cuenta_de_la_cli() -> Usuario:
    """Cuenta de un comando de datos; si no se puede determinar, explica cómo indicarla y termina con error."""
    try:
        return resolver_cuenta_de_la_cli()
    except CuentaNoResuelta as error:
        console.print(f"[bold red]Error:[/bold red] {escape(str(error))}", soft_wrap=True)
        raise typer.Exit(code=1) from None
    except ErrorDeMigracion as error:
        raise terminar_por_migracion_fallida(error) from None
