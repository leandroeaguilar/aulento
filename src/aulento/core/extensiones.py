"""Puntos de extensión del core: lo que un paquete externo puede sumarle a la aplicación (ADR 017).

Son genéricos a propósito: no nombran nada comercial. Una extensión aporta rutas, tablas propias (con su
numeración, sin tocar el `user_version` del core), archivos estáticos con sus etiquetas en la página y
suscripciones a los eventos del dominio (`core/eventos.py`).
"""

import re
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter

from aulento.db.migrations import ErrorDeMigracion

if TYPE_CHECKING:
    from fastapi import Request

    from aulento.auth.modelos import Usuario
    from aulento.core.identity import IIdentityProvider
    from aulento.db.vector_repository import AlmacenDeVectores
else:
    Usuario = object
    Request = object
    IIdentityProvider = object
    AlmacenDeVectores = object

PATRON_DE_NOMBRE = re.compile(r"^[a-z][a-z0-9_]*$")
PREFIJO_DE_ESTATICOS = "/static/ext"

DDL_MIGRACIONES_DE_EXTENSION = """
CREATE TABLE IF NOT EXISTS migraciones_de_extension (
    extension TEXT NOT NULL,
    version INTEGER NOT NULL,
    nombre TEXT NOT NULL,
    aplicada_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (extension, version)
);
"""


class ExtensionInvalida(ValueError):
    """Una extensión está mal declarada: nombre inválido o repetido, migraciones desordenadas o recursos ajenos."""


@dataclass(frozen=True)
class MigracionDeExtension:
    """Un paso del esquema propio de una extensión. `funcion` recibe la conexión dentro de una transacción."""

    version: int
    nombre: str
    funcion: Callable[[sqlite3.Connection], None]


@dataclass(frozen=True)
class Extension:
    """Lo que un paquete le suma al core. Solo `nombre` es obligatorio.

    - `routers`: se incluyen detrás de la exigencia de usuario del core (sin sesión, en saas, responden 401).
    - `routers_publicos`: se incluyen en la web sin exigir usuario (públicos).
    - `migraciones`: versiones crecientes desde 1, anotadas en `migraciones_de_extension`.
    - `estaticos`: carpeta servida en `/static/ext/<nombre>/`.
    - `portada`: archivo HTML servido en `/` en saas a quien llega sin sesión.
    - `hojas_de_estilo` y `scripts`: archivos de esa carpeta (rutas relativas) que se insertan en la página.
    - `suscripciones`: nombre de evento → funciones que lo escuchan.
    - `validadores_de_cuenta`: funciones que comprueban la cuenta y levantan HTTPException si no debe pasar.
    - `etiquetas_openapi`: descripción de las etiquetas que usan sus rutas, para la documentación de la API.
    - `manejadores_de_excepciones`: tipo de excepción → manejador de FastAPI (por ejemplo, `Exception` para los
      errores no previstos).
    - `capacidades`: callable o diccionario con mapa de capacidades (`nombre -> bool`) que la extensión suma o modifica.
    - `textos`: callable o diccionario con mapa de textos (`clave -> texto`) que la extensión reemplaza en la interfaz.
    - `identidad`: fábrica `(request, conn) -> IIdentityProvider` que resuelve quién pide en el modo multiusuario
      (`saas`). A lo sumo una extensión la aporta; en modo local manda siempre la cuenta local.
    - `al_arrancar`: funciones que reciben la conexión al arrancar el servidor, después de las migraciones.
    - `descripcion_openapi`: reemplaza la descripción de la API en la documentación (por ejemplo, cómo se ingresa).
    - `cuenta_compartida`: dice si una cuenta es compartida por varias personas (por ejemplo, una de demostración).
      Las rutas que guardan claves, conexiones o tokens la frenan con 403 (`SinCuentaCompartida`).
    """

    nombre: str
    routers: Sequence[APIRouter] = ()
    routers_publicos: Sequence[APIRouter] = ()
    migraciones: Sequence[MigracionDeExtension] = ()
    estaticos: Path | None = None
    portada: Path | None = None
    hojas_de_estilo: Sequence[str] = ()
    scripts: Sequence[str] = ()
    suscripciones: Mapping[str, Sequence[Callable[..., object]]] = field(default_factory=dict)
    validadores_de_cuenta: Sequence[Callable[[Usuario, sqlite3.Connection], None]] = ()
    etiquetas_openapi: Sequence[Mapping[str, str]] = ()
    manejadores_de_excepciones: Mapping[type[BaseException], Callable[..., object]] = field(default_factory=dict)
    capacidades: Callable[[Usuario | None], Mapping[str, bool]] | Mapping[str, bool] | None = None
    textos: Mapping[str, str] | Callable[[Usuario | None], Mapping[str, str]] = field(default_factory=dict)
    identidad: Callable[[Request, sqlite3.Connection], IIdentityProvider] | None = None
    cuenta_compartida: Callable[[Usuario], bool] | None = None
    al_arrancar: Sequence[Callable[[sqlite3.Connection], None]] = ()
    descripcion_openapi: str | None = None
    # Reglas de `core/permisos.py`: si la cuenta puede crear un curso, una ruta o un material más (062)
    permisos: Sequence[Callable[..., object]] = ()
    almacen_de_vectores: Callable[[int], AlmacenDeVectores] | None = None
    salud: Callable[[], Mapping[str, Any]] | None = None

    @property
    def prefijo_de_estaticos(self) -> str:
        return f"{PREFIJO_DE_ESTATICOS}/{self.nombre}"


def _validar_recurso(extension: Extension, recurso: str) -> None:
    """Un recurso de página es un archivo propio: relativo, sin `..` y sin esquema ni host."""
    if extension.estaticos is None:
        raise ExtensionInvalida(f"La extensión {extension.nombre} declara «{recurso}» pero no tiene carpeta de estáticos.")
    partes = recurso.replace("\\", "/").split("/")
    if (
        not recurso
        or recurso.startswith(("/", "\\"))
        or ":" in recurso
        or any(parte in ("", ".", "..") for parte in partes)
    ):
        raise ExtensionInvalida(
            f"La extensión {extension.nombre} declara «{recurso}»: tiene que ser un archivo de su carpeta de estáticos."
        )


def validar_extensiones(extensiones: Sequence[Extension]) -> None:
    """Comprueba nombres válidos y únicos, migraciones ordenadas sin huecos y recursos propios."""
    vistos: set[str] = set()
    for extension in extensiones:
        if not isinstance(extension, Extension):
            raise ExtensionInvalida(f"Se esperaba una Extension y llegó {type(extension).__name__}.")
        if not PATRON_DE_NOMBRE.match(extension.nombre):
            raise ExtensionInvalida(
                f"Nombre de extensión inválido: «{extension.nombre}». Usá minúsculas, dígitos y guiones bajos, "
                "empezando por una letra."
            )
        if extension.nombre in vistos:
            raise ExtensionInvalida(f"Hay dos extensiones con el nombre «{extension.nombre}».")
        vistos.add(extension.nombre)
        versiones = [m.version for m in extension.migraciones]
        if versiones != list(range(1, len(versiones) + 1)):
            raise ExtensionInvalida(
                f"Las migraciones de {extension.nombre} tienen que numerarse 1, 2, 3… en orden; llegaron {versiones}."
            )
        if extension.portada is not None and not isinstance(extension.portada, Path):
            raise ExtensionInvalida(f"La portada de {extension.nombre} debe ser un Path o None.")
        for recurso in (*extension.hojas_de_estilo, *extension.scripts):
            _validar_recurso(extension, recurso)
    con_identidad = [extension.nombre for extension in extensiones if extension.identidad is not None]
    if len(con_identidad) > 1:
        raise ExtensionInvalida(
            f"Solo una extensión puede aportar la identidad y la aportan {len(con_identidad)}: {', '.join(con_identidad)}."
        )
    con_almacen = [extension.nombre for extension in extensiones if extension.almacen_de_vectores is not None]
    if len(con_almacen) > 1:
        raise ExtensionInvalida(
            f"Solo una extensión puede aportar el almacén de vectores y lo aportan {len(con_almacen)}: {', '.join(con_almacen)}."
        )


def versiones_aplicadas(conn: sqlite3.Connection, extension: str) -> set[int]:
    """Versiones de `extension` ya anotadas; vacío si la tabla todavía no existe."""
    existe = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'migraciones_de_extension';"
    ).fetchone()
    if not existe:
        return set()
    filas = conn.execute("SELECT version FROM migraciones_de_extension WHERE extension = ?;", (extension,)).fetchall()
    return {int(fila[0]) for fila in filas}


def aplicar_migraciones_de_extension(conn: sqlite3.Connection, extension: Extension) -> list[int]:
    """Aplica en orden las migraciones pendientes de `extension`; devuelve las versiones aplicadas.

    Cada una corre en su propia transacción: si falla se revierte entera y se levanta `ErrorDeMigracion`.
    No toca el `user_version` del core.
    """
    if conn.in_transaction:
        conn.commit()
    conn.execute(DDL_MIGRACIONES_DE_EXTENSION)
    conn.commit()
    aplicadas: list[int] = []
    for migracion in extension.migraciones:
        if migracion.version in versiones_aplicadas(conn, extension.nombre):
            continue
        try:
            conn.execute("BEGIN IMMEDIATE;")
            # Otro proceso pudo aplicarla mientras se esperaba el turno de escritura
            if migracion.version not in versiones_aplicadas(conn, extension.nombre):
                migracion.funcion(conn)
                conn.execute(
                    "INSERT INTO migraciones_de_extension (extension, version, nombre) VALUES (?, ?, ?);",
                    (extension.nombre, migracion.version, migracion.nombre),
                )
                aplicadas.append(migracion.version)
            conn.commit()
        except Exception as error:
            if conn.in_transaction:
                conn.rollback()
            raise ErrorDeMigracion(migracion.version, f"{extension.nombre}.{migracion.nombre}") from error
    return aplicadas


def etiquetas_de_estilo(extensiones: Sequence[Extension]) -> str:
    """Etiquetas `<link>` de las hojas de estilo de las extensiones, para insertar antes de `</head>`."""
    return "\n".join(
        f'<link rel="stylesheet" href="{escape(extension.prefijo_de_estaticos)}/{escape(hoja)}">'
        for extension in extensiones
        for hoja in extension.hojas_de_estilo
    )


def etiquetas_de_script(extensiones: Sequence[Extension]) -> str:
    """Etiquetas `<script defer>` de las extensiones, para insertar antes de `</body>`."""
    return "\n".join(
        f'<script src="{escape(extension.prefijo_de_estaticos)}/{escape(script)}" defer></script>'
        for extension in extensiones
        for script in extension.scripts
    )


def insertar_etiquetas(pagina: str, extensiones: Sequence[Extension]) -> str:
    """Pone los estilos antes del primer `</head>` y los scripts antes del último `</body>`.

    Si la página no tiene esos cierres, las etiquetas van al final.
    """
    estilos = etiquetas_de_estilo(extensiones)
    scripts = etiquetas_de_script(extensiones)
    if estilos:
        antes, cierre, despues = pagina.partition("</head>")
        pagina = f"{antes}{estilos}\n{cierre}{despues}" if cierre else f"{pagina}\n{estilos}"
    if scripts:
        # El último </body>: uno dentro de un script de la página no es el cierre real
        antes, cierre, despues = pagina.rpartition("</body>")
        pagina = f"{antes}{scripts}\n{cierre}{despues}" if cierre else f"{pagina}\n{scripts}"
    return pagina


_validadores_registrados: list[Callable[[Usuario, sqlite3.Connection], None]] = []


def registrar_validadores(validadores: Sequence[Callable[[Usuario, sqlite3.Connection], None]]) -> None:
    """Registra validadores de cuenta en el proceso (los usa quien no pasa por FastAPI, como el servidor MCP).

    Cada registro cuenta: dos apps del mismo proceso con la misma extensión lo registran dos veces, y cerrar
    una quita solo su registro. `validar_cuenta` igual corre cada validador una sola vez.
    """
    _validadores_registrados.extend(validadores)


def desregistrar_validadores(validadores: Sequence[Callable[[Usuario, sqlite3.Connection], None]]) -> None:
    """Quita un registro de cada validador indicado; si no estaba, no hace nada."""
    for validador in validadores:
        if validador in _validadores_registrados:
            _validadores_registrados.remove(validador)


def limpiar_validadores() -> None:
    """Limpia todos los validadores de cuenta registrados en el proceso."""
    _validadores_registrados.clear()


def validar_cuenta(usuario: Usuario, conn: sqlite3.Connection) -> None:
    """Ejecuta los validadores de cuenta registrados en el proceso (no en modo local)."""
    from aulento.config import is_local_mode

    if is_local_mode():
        return
    for validador in dict.fromkeys(_validadores_registrados):
        validador(usuario, conn)

_fabricas_de_almacen: list[Callable[[int], Any]] = []


def registrar_almacenes_de_vectores(fabricas: Sequence[Callable[[int], Any]]) -> None:
    """Registra fábricas de almacén de vectores en el proceso (ej. aportadas por extensiones)."""
    _fabricas_de_almacen.extend(fabricas)


def desregistrar_almacenes_de_vectores(fabricas: Sequence[Callable[[int], Any]]) -> None:
    """Quita una aparición de cada fábrica registrada."""
    for fabrica in fabricas:
        if fabrica in _fabricas_de_almacen:
            _fabricas_de_almacen.remove(fabrica)


def limpiar_almacenes_de_vectores() -> None:
    """Limpia las fábricas de almacén de vectores registradas en el proceso."""
    _fabricas_de_almacen.clear()


def obtener_almacen_de_vectores(user_id: int):
    """Retorna el almacén de vectores para la cuenta: el de una extensión registrada, o SQLite local por defecto."""
    if _fabricas_de_almacen:
        return _fabricas_de_almacen[-1](user_id)
    from aulento.config import is_local_mode

    if not is_local_mode():
        from aulento.db.vector_repository import AlmacenNoConfigurado

        return AlmacenNoConfigurado(user_id)
    from aulento.db.vectores_sqlite import AlmacenVectoresSqlite

    return AlmacenVectoresSqlite(user_id)


def registrar_extensiones(extensiones: Sequence[Extension]) -> Callable[[], None]:
    """Registra en el proceso los ganchos de las extensiones (suscripciones, validadores, permisos y vectores).

    Retorna una función que los desregistra al terminar (para lifespans o tests).
    """
    from aulento.core import eventos, permisos

    suscritas = [
        (evento, funcion)
        for extension in extensiones
        for evento, funciones in extension.suscripciones.items()
        for funcion in funciones
    ]
    for evento, funcion in suscritas:
        eventos.bus.suscribir(evento, funcion)
    validadores = [
        validador
        for extension in extensiones
        for validador in extension.validadores_de_cuenta
    ]
    registrar_validadores(validadores)
    permisos_lista = [permiso for extension in extensiones for permiso in extension.permisos]
    permisos.registrar_permisos(permisos_lista)
    almacenes = [
        extension.almacen_de_vectores
        for extension in extensiones
        if extension.almacen_de_vectores is not None
    ]
    registrar_almacenes_de_vectores(almacenes)

    def desregistrar() -> None:
        for evento, funcion in suscritas:
            eventos.bus.desuscribir(evento, funcion)
        desregistrar_validadores(validadores)
        permisos.desregistrar_permisos(permisos_lista)
        desregistrar_almacenes_de_vectores(almacenes)

    return desregistrar


def cargar_extensiones_del_entorno() -> list[Extension]:
    """Carga las extensiones configuradas para el entorno.

    Lee la variable genérica AULENTO_EXTENSIONS (formato "modulo:funcion,modulo:funcion,...").
    Cada elemento se importa con importlib y se resuelve como objeto Extension o fábrica que lo devuelve.
    """
    import importlib
    import os

    declaradas = os.getenv("AULENTO_EXTENSIONS")
    if not declaradas:
        return []

    res: list[Extension] = []
    for parte in declaradas.split(","):
        parte = parte.strip()
        if not parte:
            continue
        if ":" in parte:
            mod_name, func_name = parte.split(":", 1)
            mod = importlib.import_module(mod_name)
            ext_or_factory = getattr(mod, func_name)
            ext = ext_or_factory() if callable(ext_or_factory) else ext_or_factory
            res.append(ext)
        else:
            mod = importlib.import_module(parte)
            ext_val = getattr(mod, "extension", None)
            if callable(ext_val):
                ext_val = ext_val()
            if ext_val is not None:
                res.append(ext_val)
    return res

