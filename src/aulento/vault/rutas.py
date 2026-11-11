"""Dónde está el vault de cada cuenta y cómo se confina a él toda ruta de nota.

Cada cuenta tiene su vault dentro del directorio de datos (`usuarios/<id>/vault/`). Un administrador puede
apuntar el suyo a una carpeta de la máquina del servidor (ajuste `vault_externo`). Ningún otro módulo decide
la ubicación de un vault.
"""

import logging
import os
import re
import sqlite3
import tempfile
import zipfile
from pathlib import Path, PureWindowsPath
from typing import Any

from aulento.config import dir_de_cuenta, get_data_dir, get_db_path
from aulento.core.secretos import AJUSTE_VAULT_EXTERNO, AjustesDeCuenta
from aulento.db.connection import get_connection

logger = logging.getLogger(__name__)

CARPETA_DEL_VAULT = "vault"
MARCA_CARPETAS_DEL_TUTOR = ".carpetas-del-tutor-creadas"


def carpetas_por_defecto() -> tuple[str, ...]:
    """Carpetas por defecto del tutor, derivadas de `aulento.vault.reader.ALLOWED_FOLDERS`."""
    from aulento.vault.reader import ALLOWED_FOLDERS

    return tuple(ALLOWED_FOLDERS)


# Largo máximo de un nombre de archivo de nota, sin la extensión
LARGO_MAXIMO_DE_NOMBRE = 120

# Nombres que Windows reserva para dispositivos: no pueden ser el nombre de un archivo, con o sin extensión
NOMBRES_RESERVADOS = frozenset(
    {"con", "prn", "aux", "nul"} | {f"com{n}" for n in range(1, 10)} | {f"lpt{n}" for n in range(1, 10)}
)


# Lo que se responde por una nota que no existe o que apunta fuera del vault: el mismo texto en los dos casos
MENSAJE_NOTA_NO_ENCONTRADA = "Nota no encontrada en el vault de la cuenta."


class VaultNoDisponibleError(RuntimeError):
    """El vault externo que fijó la cuenta ya no existe o ya no se puede usar: no se lee ni se escribe en ningún otro lugar."""


class RutaFueraDelVaultError(ValueError):
    """Una ruta, identificador o nombre de nota apunta fuera del vault de la cuenta."""


class CarpetaDeVaultInvalida(ValueError):
    """La carpeta pedida como vault externo no sirve; el mensaje dice por qué."""


def vault_propio(user_id: int) -> Path:
    """Vault de la cuenta dentro del directorio de datos, creándolo si falta con las carpetas por defecto del tutor."""
    carpeta = dir_de_cuenta(user_id) / CARPETA_DEL_VAULT
    carpeta.mkdir(parents=True, exist_ok=True)
    marca = carpeta / MARCA_CARPETAS_DEL_TUTOR
    if not marca.exists():
        for nombre in carpetas_por_defecto():
            try:
                (carpeta / nombre).mkdir(parents=True, exist_ok=True)
            except OSError as e:
                logger.warning(
                    "No se pudo crear la carpeta por defecto %s en el vault propio %s: %s",
                    nombre,
                    carpeta,
                    e,
                )
        try:
            marca.touch(exist_ok=True)
        except OSError as e:
            logger.warning(
                "No se pudo crear la marca de carpetas del tutor en %s: %s",
                marca,
                e,
            )
    return carpeta


def _carpetas_del_servidor() -> list[Path]:
    """Carpetas que un vault externo no puede ser, contener ni tener adentro.

    El directorio de datos (la clave maestra, los vaults de las demás cuentas y, por defecto, la base), y la
    carpeta donde vive la base cuando está fuera de él.
    """
    carpetas = [get_data_dir().resolve()]
    base = get_db_path()
    if str(base) != ":memory:":
        carpetas.append(base.resolve().parent)
    return carpetas


def _toca_al_servidor(carpeta: Path) -> bool:
    """La carpeta, ya resuelta, es una de las del servidor, está dentro de una o contiene alguna."""
    return any(carpeta.is_relative_to(propia) or propia.is_relative_to(carpeta) for propia in _carpetas_del_servidor())


def _es_temporal_o_del_sistema(carpeta: Path) -> bool:
    """Rechaza el vault si es la carpeta temporal o un ancestro de ella; y para /proc, /sys, /dev si es, contiene o está dentro."""
    temp_dir = Path(tempfile.gettempdir()).resolve()
    if carpeta == temp_dir or temp_dir.is_relative_to(carpeta):
        return True
    try:
        p_tmp = Path("/tmp").resolve()
        if carpeta == p_tmp or p_tmp.is_relative_to(carpeta):
            return True
    except (OSError, ValueError):
        pass

    for especial in ("/proc", "/sys", "/dev"):
        p = Path(especial)
        try:
            if p.exists():
                res = p.resolve()
                if carpeta == res or carpeta.is_relative_to(res) or res.is_relative_to(carpeta):
                    return True
        except (OSError, ValueError):
            pass
        try:
            if str(carpeta).replace("\\", "/").rstrip("/").lower() == especial.lower():
                return True
        except (OSError, ValueError):
            pass
    return False


def vault_externo_fijado(conn: sqlite3.Connection, user_id: int) -> str | None:
    """Carpeta que la cuenta fijó como vault externo, exista o no; None si usa el vault propio."""
    valor = AjustesDeCuenta(conn, user_id).leer(AJUSTE_VAULT_EXTERNO)
    return valor.strip() if isinstance(valor, str) and valor.strip() else None


def vault_de_la_cuenta(conn: sqlite3.Connection, user_id: int) -> Path:
    """Vault donde la cuenta lee y escribe sus notas.

    Es la carpeta del ajuste `vault_externo` si la cuenta lo fijó o, si no, su vault propio (que se crea).
    Si la carpeta externa fijada ya no existe levanta `VaultNoDisponibleError`: no se cae al vault propio,
    porque las notas nuevas quedarían en otro lugar sin que la cuenta se entere. Lo mismo si hoy resuelve
    dentro del directorio de datos o de la carpeta de la base (o los contiene): se validó al fijarla, pero
    la carpeta pudo reemplazarse después por un enlace o una unión, o el servidor pudo cambiar de lugar.
    """
    externo = vault_externo_fijado(conn, user_id)
    if externo is None:
        return vault_propio(user_id)
    carpeta = Path(externo)
    if not carpeta.is_dir():
        raise VaultNoDisponibleError(
            f"La carpeta fijada como vault externo de la cuenta ya no existe: {externo}. "
            "Volvé a crearla, fijá otra o quitá el vault externo para usar el vault propio de la cuenta."
        )
    if _toca_al_servidor(carpeta.resolve()) or _es_temporal_o_del_sistema(carpeta.resolve()):
        raise VaultNoDisponibleError(
            f"La carpeta fijada como vault externo de la cuenta ya no se puede usar: {externo} hoy lleva al "
            "directorio de datos del servidor o a la carpeta de su base. Fijá otra o quitá el vault externo "
            "para usar el vault propio de la cuenta."
        )
    return carpeta


def vault_de_la_cuenta_con_conexion_propia(user_id: int, db_path: Path | str | None = None) -> Path:
    """Como `vault_de_la_cuenta`, para quien no tiene una conexión a mano: abre una y la cierra."""
    conn = get_connection(db_path)
    try:
        return vault_de_la_cuenta(conn, user_id)
    finally:
        conn.close()


def estado_del_vault(conn: sqlite3.Connection, user_id: int) -> dict[str, Any]:
    """Qué vault usa la cuenta: `externo`, la carpeta externa fijada (`ruta`) y si está `disponible`."""
    externo = vault_externo_fijado(conn, user_id)
    if externo is None:
        return {"externo": False, "ruta": None, "disponible": True}
    carpeta = Path(externo)
    return {
        "externo": True,
        "ruta": externo,
        "disponible": carpeta.is_dir()
        and not _toca_al_servidor(carpeta.resolve())
        and not _es_temporal_o_del_sistema(carpeta.resolve()),
    }


def fijar_vault_externo(conn: sqlite3.Connection, user_id: int, carpeta: Path | str) -> Path:
    """Apunta el vault de la cuenta a una carpeta existente de la máquina del servidor y la devuelve resuelta.

    Levanta `CarpetaDeVaultInvalida` si la ruta no es absoluta, no es una carpeta existente, o si es, contiene
    o está dentro del directorio de datos del servidor (ahí viven la clave maestra y los vaults de las demás
    cuentas) o de la carpeta donde vive la base.
    """
    texto = str(carpeta or "").strip()
    if not texto:
        raise CarpetaDeVaultInvalida("Falta la carpeta del vault externo.")
    candidata = Path(texto)
    if not candidata.is_absolute():
        raise CarpetaDeVaultInvalida("La carpeta del vault externo tiene que ser una ruta absoluta.")
    if not candidata.is_dir():
        raise CarpetaDeVaultInvalida("La carpeta del vault externo no existe en la máquina del servidor.")
    resuelta = candidata.resolve()
    if _toca_al_servidor(resuelta) or _es_temporal_o_del_sistema(resuelta):
        raise CarpetaDeVaultInvalida(
            "La carpeta del vault externo no puede estar dentro del directorio de datos del servidor ni de la "
            "carpeta donde vive su base, ni contenerlos."
        )
    AjustesDeCuenta(conn, user_id).guardar(AJUSTE_VAULT_EXTERNO, str(resuelta))
    return resuelta


def quitar_vault_externo(conn: sqlite3.Connection, user_id: int) -> bool:
    """La cuenta vuelve a su vault propio; la carpeta externa no se toca. Dice si había una fijada."""
    return AjustesDeCuenta(conn, user_id).borrar(AJUSTE_VAULT_EXTERNO)


def _sale_del_vault(referencia: str) -> bool:
    """La referencia es absoluta, trae unidad de Windows o sube con `..`."""
    normal = referencia.replace("\\", "/")
    ventana = PureWindowsPath(referencia)
    return (
        "\x00" in referencia
        or normal.startswith("/")
        or bool(ventana.drive)
        or ventana.is_absolute()
        or ".." in normal.split("/")
    )


def resolver_en_vault(vault: Path, referencia: str) -> Path:
    """Ruta de `referencia` (relativa al vault) ya resuelta, comprobando que quede dentro del vault.

    Levanta `RutaFueraDelVaultError` si es absoluta, trae unidad, usa `..` o pasa por un enlace que sale del vault.
    """
    texto = (referencia or "").strip()
    if _sale_del_vault(texto):
        raise RutaFueraDelVaultError("La ruta pedida apunta fuera del vault de la cuenta.")
    raiz = vault.resolve()
    destino = (raiz / texto.replace("\\", "/")).resolve()
    if not destino.is_relative_to(raiz):
        raise RutaFueraDelVaultError("La ruta pedida apunta fuera del vault de la cuenta.")
    return destino


def relativa_al_vault(vault: Path, ruta: Path | str) -> str:
    """Ruta de un archivo del vault tal como se le informa a la cuenta: relativa al vault y con barras `/`.

    Las respuestas no llevan rutas absolutas del disco del servidor. De un archivo que no está en el vault
    solo se informa el nombre.
    """
    try:
        return Path(ruta).resolve().relative_to(vault.resolve()).as_posix()
    except ValueError:
        return Path(ruta).name


def exigir_nombre_de_nota(nombre: str) -> str:
    """Devuelve el nombre de una nota a escribir; levanta `RutaFueraDelVaultError` si en realidad es una ruta.

    Un título puede llevar dos puntos o una barra («Redes: TCP/IP»); lo que no puede es subir con `..`,
    empezar con un separador o con una unidad de Windows seguida de separador.
    """
    texto = (nombre or "").strip()
    normal = texto.replace("\\", "/")
    if "\x00" in texto or normal.startswith("/") or ".." in normal.split("/") or re.match(r"^[A-Za-z]:/", normal):
        raise RutaFueraDelVaultError("El nombre de la nota apunta fuera del vault de la cuenta.")
    return texto


def nombre_de_archivo_seguro(nombre: str, defecto: str) -> str:
    """Nombre de archivo o carpeta de una sola línea: letras, números, espacios y guiones; nunca vacío ni reservado."""
    limpio = re.sub(r"\s+", " ", re.sub(r"[^\w\s-]", "", nombre or "")).strip()[:LARGO_MAXIMO_DE_NOMBRE].strip()
    if not limpio:
        return defecto
    return f"{limpio} (nota)" if limpio.lower() in NOMBRES_RESERVADOS else limpio


# `os.path.isjunction` existe desde Python 3.12; antes, una unión que sale del vault se descarta al resolverla
_es_union = getattr(os.path, "isjunction", lambda ruta: False)


def _es_enlace(ruta: Path) -> bool:
    """La entrada es un enlace simbólico o una unión de directorios de Windows."""
    return ruta.is_symlink() or _es_union(ruta)


def escribir_zip_del_vault(vault: Path, destino: Path) -> int:
    """Escribe en `destino` un `.zip` con todos los archivos del vault; devuelve cuántos incluyó.

    No sigue enlaces simbólicos ni uniones, y descarta toda entrada que resuelva fuera del vault.
    """
    raiz = vault.resolve()
    incluidos = 0
    with zipfile.ZipFile(destino, "w", compression=zipfile.ZIP_DEFLATED) as archivo:
        for carpeta, subcarpetas, nombres in os.walk(raiz, followlinks=False):
            actual = Path(carpeta)
            subcarpetas[:] = sorted(
                nombre
                for nombre in subcarpetas
                if not _es_enlace(actual / nombre) and (actual / nombre).resolve().is_relative_to(raiz)
            )
            for nombre in sorted(nombres):
                if nombre == MARCA_CARPETAS_DEL_TUTOR:
                    continue
                ruta = actual / nombre
                if _es_enlace(ruta) or not ruta.is_file() or not ruta.resolve().is_relative_to(raiz):
                    continue
                archivo.write(ruta, ruta.relative_to(raiz).as_posix())
                incluidos += 1
        if incluidos == 0:
            leeme = (
                "# Mis notas\n\n"
                "Todavía no tenés notas guardadas en tu cuenta.\n"
                "Podés generar apuntes desde tus materiales o pedírselos al tutor.\n"
            )
            archivo.writestr("LEEME.md", leeme.encode("utf-8"))
    return incluidos
