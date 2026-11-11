"""Carpetas del vault de una cuenta: cuáles hay, cuáles lee el tutor y cómo se crean desde la web.

En un servidor desplegado nadie entra al disco a crear carpetas: la cuenta las ve, las crea y elige las del
tutor desde la interfaz. Todo queda confinado al vault de la cuenta (`resolver_en_vault`).
"""

import os
import sqlite3
from pathlib import Path
from typing import Any

from aulento.core.secretos import AJUSTE_CARPETAS_DEL_TUTOR, AjustesDeCuenta
from aulento.vault.reader import ALLOWED_FOLDERS
from aulento.vault.rutas import (
    NOMBRES_RESERVADOS,
    RutaFueraDelVaultError,
    _es_enlace,
    _sale_del_vault,
    nombre_de_archivo_seguro,
    resolver_en_vault,
)

# Hasta dónde se baja al listar y al crear: un vault de Obsidian no anida más que esto en la práctica
PROFUNDIDAD_MAXIMA = 4
# Cuántas carpetas se listan como mucho: con miles, el listado se corta (las notas se cuentan igual en todo el árbol)
MAXIMO_DE_CARPETAS = 500
MAXIMO_DE_CARPETAS_DEL_TUTOR = 50

DESCRIPCION_DE_CARPETAS: dict[str, str] = {
    "04 Knowledge": "Tus apuntes y conceptos.",
    "06 Raw": "Material en bruto, recortes y transcripciones.",
    "02 MOCs": "Índices que conectan temas.",
}


class CarpetaInvalida(ValueError):
    """La carpeta pedida no se puede crear ni elegir; el mensaje dice por qué."""


def _segmentos(ruta: str) -> list[str]:
    return [parte.strip() for parte in (ruta or "").replace("\\", "/").split("/") if parte.strip()]


def listar_carpetas(vault: Path) -> list[dict[str, Any]]:
    """Carpetas del vault (relativas, con `/`) y cuántas notas `.md` tiene cada una contando sus subcarpetas.

    Lista hasta `PROFUNDIDAD_MAXIMA` niveles y `MAXIMO_DE_CARPETAS` carpetas, pero cuenta las notas de todo el
    árbol, como las lee el tutor. No sigue enlaces ni uniones y saltea las carpetas ocultas (`.obsidian`, `.trash`).
    """
    raiz = vault.resolve()
    if not raiz.is_dir():
        return []
    notas: dict[str, int] = {}
    for carpeta, subcarpetas, nombres in os.walk(raiz, followlinks=False):
        actual = Path(carpeta)
        # Sin `os.path.isjunction` (Python 3.11) una unión no se reconoce como enlace: la descarta el resolve
        subcarpetas[:] = sorted(
            nombre
            for nombre in subcarpetas
            if not nombre.startswith(".")
            and not _es_enlace(actual / nombre)
            and (actual / nombre).resolve().is_relative_to(raiz)
        )
        partes = actual.relative_to(raiz).parts
        visibles = partes[:PROFUNDIDAD_MAXIMA]
        if len(partes) == len(visibles) and partes and len(notas) < MAXIMO_DE_CARPETAS:
            notas.setdefault("/".join(partes), 0)
        # Las notas de esta carpeta suman en ella y en cada carpeta listada que la contiene
        directas = sum(1 for nombre in nombres if nombre.lower().endswith(".md"))
        for nivel in range(1, len(visibles) + 1):
            ancestro = "/".join(visibles[:nivel])
            if ancestro in notas:
                notas[ancestro] += directas
    return [{"ruta": ruta, "notas": notas[ruta]} for ruta in sorted(notas, key=str.lower)]


def normalizar_carpeta_nueva(ruta: str) -> str:
    """Ruta relativa de una carpeta a crear; levanta `CarpetaInvalida` si un nombre no sirve.

    Cada nivel admite letras (con acentos), números, espacios, guiones y guiones bajos.
    """
    segmentos = _segmentos(ruta)
    if not segmentos:
        raise CarpetaInvalida("Escribí el nombre de la carpeta.")
    if _sale_del_vault((ruta or "").strip()):
        raise CarpetaInvalida("La carpeta se escribe relativa a tu vault, por ejemplo «04 Knowledge/Cursos».")
    if len(segmentos) > PROFUNDIDAD_MAXIMA:
        raise CarpetaInvalida(f"Una carpeta puede tener hasta {PROFUNDIDAD_MAXIMA} niveles.")
    for segmento in segmentos:
        if segmento.lower() in NOMBRES_RESERVADOS:
            raise CarpetaInvalida(f"«{segmento}» es un nombre reservado del sistema: elegí otro.")
        if segmento in (".", "..") or nombre_de_archivo_seguro(segmento, "") != segmento:
            raise CarpetaInvalida(
                f"«{segmento}» no sirve como nombre de carpeta: usá letras, números, espacios y guiones."
            )
    return "/".join(segmentos)


def crear_carpeta(vault: Path, ruta: str) -> str:
    """Crea la carpeta (y las que falten arriba) dentro del vault y devuelve su ruta relativa.

    Levanta `CarpetaInvalida` si el nombre no sirve o ya hay un archivo con ese nombre, y
    `RutaFueraDelVaultError` si la ruta sale del vault.
    """
    relativa = normalizar_carpeta_nueva(ruta)
    destino = resolver_en_vault(vault, relativa)
    segmentos = relativa.split("/")
    try:
        for nivel in range(1, len(segmentos) + 1):
            tramo = vault / "/".join(segmentos[:nivel])
            if tramo.exists() and not tramo.is_dir():
                raise CarpetaInvalida(f"Ya hay un archivo llamado «{'/'.join(segmentos[:nivel])}» en tu vault.")
        destino.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Nombre demasiado largo para el disco, vault de solo lectura...: sin rutas del servidor en el mensaje
        raise CarpetaInvalida(f"No se pudo crear la carpeta «{relativa}» en tu vault.") from None
    return relativa


def _carpeta_existente(vault: Path, ruta: str) -> str:
    """Ruta relativa normalizada de una carpeta que ya existe en el vault; si no, `CarpetaInvalida`."""
    segmentos = _segmentos(ruta)
    if not segmentos:
        raise CarpetaInvalida("Hay una carpeta sin nombre en la selección.")
    if _sale_del_vault((ruta or "").strip()):
        raise RutaFueraDelVaultError("La carpeta pedida apunta fuera del vault de la cuenta.")
    if any(segmento.startswith(".") for segmento in segmentos):
        raise CarpetaInvalida("Las carpetas ocultas del vault no se pueden elegir para el tutor.")
    destino = resolver_en_vault(vault, "/".join(segmentos))
    try:
        existe = destino.is_dir()
    except OSError:
        existe = False
    if not existe:
        raise CarpetaInvalida(f"La carpeta «{'/'.join(segmentos)}» no existe en tu vault: creala primero.")
    return destino.relative_to(vault.resolve()).as_posix()


def carpetas_del_tutor(conn: sqlite3.Connection, user_id: int) -> list[str]:
    """Carpetas que el tutor lee de la cuenta; sin elección guardada, las de siempre del vault."""
    valor = AjustesDeCuenta(conn, user_id).leer(AJUSTE_CARPETAS_DEL_TUTOR)
    if isinstance(valor, list):
        elegidas = [carpeta for carpeta in valor if isinstance(carpeta, str) and carpeta.strip()]
        if elegidas:
            return elegidas
    return list(ALLOWED_FOLDERS)


def fijar_carpetas_del_tutor(conn: sqlite3.Connection, user_id: int, vault: Path, carpetas: list[str]) -> list[str]:
    """Guarda qué carpetas del vault lee el tutor y las devuelve normalizadas, sin repetir.

    Cada una tiene que existir en el vault; levanta `CarpetaInvalida` si alguna no, si no hay ninguna o si
    son demasiadas, y `RutaFueraDelVaultError` si alguna sale del vault. Un pedido inválido no guarda nada.
    """
    if len(carpetas) > MAXIMO_DE_CARPETAS_DEL_TUTOR:
        raise CarpetaInvalida(f"El tutor puede leer hasta {MAXIMO_DE_CARPETAS_DEL_TUTOR} carpetas.")
    elegidas: list[str] = []
    for carpeta in carpetas:
        relativa = _carpeta_existente(vault, carpeta)
        if relativa not in elegidas:
            elegidas.append(relativa)
    if not elegidas:
        raise CarpetaInvalida("Elegí al menos una carpeta para el tutor.")
    AjustesDeCuenta(conn, user_id).guardar(AJUSTE_CARPETAS_DEL_TUTOR, elegidas)
    return elegidas


def carpetas_del_vault(conn: sqlite3.Connection, user_id: int, vault: Path) -> dict[str, Any]:
    """Lo que muestra la interfaz: las carpetas del vault y cuáles lee el tutor, con las que todavía no existen."""
    del_tutor = carpetas_del_tutor(conn, user_id)
    return {
        "carpetas": [
            {
                **carpeta,
                "del_tutor": carpeta["ruta"] in del_tutor,
                "descripcion": DESCRIPCION_DE_CARPETAS.get(carpeta["ruta"]),
            }
            for carpeta in listar_carpetas(vault)
        ],
        "del_tutor": del_tutor,
        "faltan": [carpeta for carpeta in del_tutor if not _existe(vault, carpeta)],
        "recomendadas": list(ALLOWED_FOLDERS),
        "descripciones": dict(DESCRIPCION_DE_CARPETAS),
    }


def crear_carpetas_faltantes(conn: sqlite3.Connection, user_id: int, vault: Path) -> list[str]:
    """Crea en el vault las carpetas del tutor que todavía no existen; devuelve cuáles creó.

    Acepta tanto vault propio como externo. Si alguna no se puede crear, levanta CarpetaInvalida.
    """
    del_tutor = carpetas_del_tutor(conn, user_id)
    creadas: list[str] = []
    for carpeta in del_tutor:
        if not _existe(vault, carpeta):
            crear_carpeta(vault, carpeta)
            creadas.append(carpeta)
    return creadas


def _existe(vault: Path, carpeta: str) -> bool:
    try:
        return resolver_en_vault(vault, carpeta).is_dir()
    except (RutaFueraDelVaultError, OSError):
        return False
