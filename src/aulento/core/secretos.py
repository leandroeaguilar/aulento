"""Clave maestra, almacén cifrado de secretos y ajustes no secretos, los dos por cuenta (ADR 008)."""

import json
import logging
import os
import re
import secrets
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from aulento.config import get_data_dir
from aulento.db.cuenta import exigir_cuenta

logger = logging.getLogger(__name__)

VARIABLE_DE_LA_CLAVE_MAESTRA = "AULENTO_SECRET_KEY"
ARCHIVO_DE_LA_CLAVE_MAESTRA = "clave_maestra.key"

SECRETO_GEMINI_CLAVE_GRATUITA = "gemini_clave_gratuita"
SECRETO_GEMINI_CLAVE_PAGA = "gemini_clave_paga"
SECRETO_ANTHROPIC_CLAVE = "anthropic_clave"
SECRETO_OPENAI_CLAVE = "openai_clave"
NOMBRES_DE_SECRETOS = (
    SECRETO_GEMINI_CLAVE_GRATUITA,
    SECRETO_GEMINI_CLAVE_PAGA,
    SECRETO_ANTHROPIC_CLAVE,
    SECRETO_OPENAI_CLAVE,
)

AJUSTE_GEMINI_NIVEL_ACTIVO = "gemini_nivel_activo"
AJUSTE_GEMINI_MODELO = "gemini_modelo"
AJUSTE_PROMPT_RUTA = "prompt_ruta"
AJUSTE_PROMPT_CLASE = "prompt_clase"
AJUSTE_DUOLINGO_USUARIO = "duolingo_usuario"
AJUSTE_DUOLINGO_CACHE = "duolingo_cache"
AJUSTE_VAULT_EXTERNO = "vault_externo"
AJUSTE_CARPETAS_DEL_TUTOR = "carpetas_del_tutor"
AJUSTE_IA_PROVEEDOR_ACTIVO = "ia_proveedor_activo"
AJUSTE_ANTHROPIC_MODELO = "anthropic_modelo"
AJUSTE_OPENAI_MODELO = "openai_modelo"
AJUSTE_ONBOARDING_COMPLETADO = "onboarding_completado"
CLAVES_DE_AJUSTES = (
    AJUSTE_GEMINI_NIVEL_ACTIVO,
    AJUSTE_GEMINI_MODELO,
    AJUSTE_PROMPT_RUTA,
    AJUSTE_PROMPT_CLASE,
    AJUSTE_DUOLINGO_USUARIO,
    AJUSTE_DUOLINGO_CACHE,
    AJUSTE_VAULT_EXTERNO,
    AJUSTE_CARPETAS_DEL_TUTOR,
    AJUSTE_IA_PROVEEDOR_ACTIVO,
    AJUSTE_ANTHROPIC_MODELO,
    AJUSTE_OPENAI_MODELO,
    AJUSTE_ONBOARDING_COMPLETADO,
)

# Sin `:`: el texto que se cifra es `<cuenta>:<nombre>:<valor>` y el prefijo no puede ser ambiguo
_NOMBRE_VALIDO = re.compile(r"[a-z][a-z0-9_]{0,63}")
# Un valor de este largo o menos no da pista: mostrar cuatro caracteres sería mostrar la mitad o más
LARGO_SIN_PISTA = 8
CARACTERES_DE_LA_PISTA = 4

_archivos_avisados: set[str] = set()
_permisos_avisados: set[str] = set()

# Lo que tarda, como mucho, cada herramienta de Windows con la que se restringe el archivo de la clave
SEGUNDOS_PARA_RESTRINGIR = 15


class ClaveMaestraInvalida(RuntimeError):
    """La clave maestra configurada no es una clave Fernet: no se genera otra ni se toca la que está."""


# Lo que se le dice a una cuenta cuando la clave maestra está mal formada: sin la clave ni rutas del servidor
MENSAJE_CLAVE_MAESTRA_INVALIDA = (
    "La clave maestra del servidor no es válida, así que los secretos guardados no se pueden leer ni guardar. "
    f"Quien administra el servidor tiene que corregir {VARIABLE_DE_LA_CLAVE_MAESTRA} o restaurar el archivo de la "
    "clave maestra desde su respaldo."
)


class SecretoIlegible(RuntimeError):
    """Un secreto guardado no se pudo descifrar con la clave maestra actual, o no es de esta cuenta y nombre."""

    def __init__(self, user_id: int, nombre: str) -> None:
        self.user_id = user_id
        self.nombre = nombre
        super().__init__(
            f"No se pudo descifrar el secreto «{nombre}» de la cuenta {user_id} con la clave maestra actual. "
            "El secreto guardado no se modificó: restaurá la clave maestra con la que se cifró o volvé a cargarlo."
        )


# Lo que se le dice a una cuenta cuando uno de sus secretos guardados no se pudo descifrar
MENSAJE_SECRETO_ILEGIBLE = "No se pudo leer un dato cifrado guardado de tu cuenta; volvé a cargarlo."

# Lo que puede levantar la lectura de un secreto guardado: quien degrada o deja pasar uno, hace lo mismo con el otro
ERRORES_AL_LEER_UN_SECRETO = (SecretoIlegible, ClaveMaestraInvalida)


def _validar_clave(clave: bytes, origen: str) -> bytes:
    """Devuelve la clave si sirve para Fernet; si no, levanta `ClaveMaestraInvalida` sin mostrarla."""
    try:
        Fernet(clave)
    except (ValueError, TypeError):
        raise ClaveMaestraInvalida(
            f"La clave maestra de {origen} no es una clave Fernet válida (32 bytes en base64 seguro para URL). "
            "Corregila o restaurala desde tu respaldo: no se generó otra ni se modificó la existente, porque "
            "con una clave distinta los secretos ya guardados quedarían ilegibles."
        ) from None
    return clave


def _herramienta_de_windows(nombre: str) -> str:
    """Ruta completa de una herramienta del sistema: no se busca en el PATH, que otro podría haber cambiado."""
    return str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / nombre)


def _restringir_acl_de_windows(archivo: Path) -> bool:
    """Deja como única entrada de la ACL el control total de quien corre el proceso, sin nada heredado.

    En Windows `chmod` solo cambia el atributo de solo lectura: el archivo nace con los permisos heredados de
    su carpeta, que pueden incluir a otros usuarios de la máquina. Devuelve si se pudo.
    """
    try:
        quien = subprocess.run(
            [_herramienta_de_windows("whoami.exe"), "/user", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            timeout=SEGUNDOS_PARA_RESTRINGIR,
            check=True,
        )
        # `"dominio\usuario","S-1-5-21-…"`: el identificador no depende del idioma del sistema
        identificador = quien.stdout.strip().rsplit(",", 1)[-1].strip().strip('"')
        if not identificador.startswith("S-1-"):
            return False
        subprocess.run(
            [_herramienta_de_windows("icacls.exe"), str(archivo), "/inheritance:r", "/grant:r", f"*{identificador}:F"],
            capture_output=True,
            timeout=SEGUNDOS_PARA_RESTRINGIR,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def _restringir_permisos(archivo: Path) -> bool:
    """Deja el archivo accesible solo para quien corre el proceso; devuelve si se pudo."""
    if sys.platform == "win32":
        return _restringir_acl_de_windows(archivo)
    try:
        os.chmod(archivo, 0o600)
    except OSError:
        return False
    return True


def _avisar_permisos_sin_restringir(archivo: Path) -> None:
    """Avisa, una vez por proceso y por archivo, que la clave maestra quedó con los permisos de su carpeta."""
    if str(archivo) in _permisos_avisados:
        return
    _permisos_avisados.add(str(archivo))
    aviso = (
        f"No se pudieron restringir los permisos de {archivo}, que guarda la clave maestra: quedó con los de su "
        "carpeta y otros usuarios de esta máquina podrían leerlo. Restringilo a mano a tu usuario (en Windows: "
        f"icacls <archivo> /inheritance:r /grant:r <usuario>:F) o definí {VARIABLE_DE_LA_CLAVE_MAESTRA}."
    )
    logger.warning(aviso)
    print(aviso, file=sys.stderr)


def _escribir_si_no_existe(archivo: Path, contenido: bytes) -> bool:
    """Crea el archivo con ese contenido solo si no existía; devuelve si lo creó.

    Los permisos se restringen con el archivo todavía vacío: el contenido nunca está en un archivo abierto a otros.
    """
    try:
        descriptor = os.open(archivo, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(descriptor, "wb") as salida:
        _restringir_permisos(archivo)
        salida.write(contenido)
    return True


def _crear_archivo_de_clave(archivo: Path) -> bool:
    """Genera una clave y la deja en `archivo` de forma atómica; devuelve False si otro proceso ya lo había creado.

    La clave se escribe completa en un archivo temporal vecino y recién entonces se enlaza con el nombre
    definitivo: nadie llega a leer un archivo a medio escribir, y un archivo existente nunca se pisa.
    """
    clave = Fernet.generate_key()
    temporal = archivo.with_name(f"{archivo.name}.{os.getpid()}-{secrets.token_hex(4)}.tmp")
    _escribir_si_no_existe(temporal, clave)
    try:
        os.link(temporal, archivo)
    except FileExistsError:
        return False
    except OSError:
        # Sistema de archivos sin enlaces duros: creación exclusiva directa, que tampoco pisa
        if not _escribir_si_no_existe(archivo, clave):
            return False
    finally:
        temporal.unlink(missing_ok=True)
    # El enlace comparte los permisos del temporal, ya restringidos: acá se confirma sobre el nombre definitivo
    if not _restringir_permisos(archivo):
        _avisar_permisos_sin_restringir(archivo)
    return True


def _avisar_clave_generada(archivo: Path) -> None:
    """Avisa, una vez por proceso y por archivo, que la clave maestra se generó junto a los datos."""
    if str(archivo) in _archivos_avisados:
        return
    _archivos_avisados.add(str(archivo))
    aviso = (
        f"Se generó una clave maestra para cifrar los secretos en {archivo}. Respaldala junto con la base: "
        "sin ella los secretos guardados no se pueden leer. Para no dejarla junto a los datos, definí "
        f"{VARIABLE_DE_LA_CLAVE_MAESTRA}."
    )
    logger.warning(aviso)
    print(aviso, file=sys.stderr)


def clave_maestra() -> bytes:
    """Devuelve la clave Fernet con la que se cifran los secretos de todas las cuentas.

    Sale de `AULENTO_SECRET_KEY`; si la variable no está, de `clave_maestra.key` en el directorio de datos,
    que se genera la primera vez. Una clave mal formada levanta `ClaveMaestraInvalida`.
    """
    de_la_variable = (os.getenv(VARIABLE_DE_LA_CLAVE_MAESTRA) or "").strip()
    if de_la_variable:
        return _validar_clave(de_la_variable.encode("utf-8"), f"la variable {VARIABLE_DE_LA_CLAVE_MAESTRA}")

    archivo = get_data_dir() / ARCHIVO_DE_LA_CLAVE_MAESTRA
    if not archivo.exists() and _crear_archivo_de_clave(archivo):
        _avisar_clave_generada(archivo)
    return _validar_clave(archivo.read_bytes().strip(), f"el archivo {archivo}")


def _exigir_nombre(nombre: str, de_que: str) -> str:
    if not isinstance(nombre, str) or _NOMBRE_VALIDO.fullmatch(nombre) is None:
        raise ValueError(
            f"Nombre de {de_que} inválido ({nombre!r}): minúsculas, dígitos y guion bajo, empezando por una letra."
        )
    return nombre


def _ahora() -> str:
    return datetime.now(UTC).isoformat()


class AlmacenDeSecretos:
    """Secretos de una cuenta, cifrados en `secretos_usuario` con la clave maestra.

    Se cifra `<cuenta>:<nombre>:<valor>` y al leer se comprueba ese prefijo: una fila copiada a otra cuenta
    o a otro nombre no se lee como propia.
    """

    def __init__(self, conn: sqlite3.Connection, user_id: int) -> None:
        self.conn = conn
        self.user_id = exigir_cuenta(user_id)

    def __repr__(self) -> str:
        return f"AlmacenDeSecretos(user_id={self.user_id})"

    def _prefijo(self, nombre: str) -> str:
        return f"{self.user_id}:{nombre}:"

    def guardar(self, nombre: str, valor: str) -> None:
        """Cifra y guarda el secreto, reemplazando el que hubiera con ese nombre."""
        _exigir_nombre(nombre, "secreto")
        if not isinstance(valor, str):
            raise TypeError(f"El secreto «{nombre}» tiene que ser texto; se recibió {type(valor).__name__}.")
        if not valor.strip():
            raise ValueError(f"El secreto «{nombre}» no puede estar vacío.")
        cifrado = Fernet(clave_maestra()).encrypt((self._prefijo(nombre) + valor).encode("utf-8"))
        self.conn.execute(
            "INSERT INTO secretos_usuario (user_id, nombre, valor_cifrado, actualizado_en) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id, nombre) DO UPDATE SET "
            "valor_cifrado = excluded.valor_cifrado, actualizado_en = excluded.actualizado_en;",
            (self.user_id, nombre, cifrado, _ahora()),
        )
        self.conn.commit()

    def leer(self, nombre: str) -> str | None:
        """Devuelve el secreto en claro, o None si la cuenta no lo tiene. No modifica la fila aunque no descifre."""
        _exigir_nombre(nombre, "secreto")
        fila = self.conn.execute(
            "SELECT valor_cifrado FROM secretos_usuario WHERE user_id = ? AND nombre = ?;", (self.user_id, nombre)
        ).fetchone()
        if fila is None:
            return None
        cifrado = fila[0].encode("utf-8") if isinstance(fila[0], str) else bytes(fila[0])
        try:
            claro = Fernet(clave_maestra()).decrypt(cifrado).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError):
            raise SecretoIlegible(self.user_id, nombre) from None
        prefijo = self._prefijo(nombre)
        if not claro.startswith(prefijo):
            raise SecretoIlegible(self.user_id, nombre)
        return claro[len(prefijo):]

    def borrar(self, nombre: str) -> bool:
        """Borra el secreto; devuelve si existía."""
        _exigir_nombre(nombre, "secreto")
        cursor = self.conn.execute(
            "DELETE FROM secretos_usuario WHERE user_id = ? AND nombre = ?;", (self.user_id, nombre)
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def tiene(self, nombre: str) -> bool:
        """Indica si la cuenta tiene cargado ese secreto, sin descifrarlo."""
        _exigir_nombre(nombre, "secreto")
        fila = self.conn.execute(
            "SELECT 1 FROM secretos_usuario WHERE user_id = ? AND nombre = ?;", (self.user_id, nombre)
        ).fetchone()
        return fila is not None

    def pista(self, nombre: str) -> str | None:
        """Últimos cuatro caracteres del secreto; cadena vacía si es demasiado corto y None si no está cargado."""
        valor = self.leer(nombre)
        if valor is None:
            return None
        return valor[-CARACTERES_DE_LA_PISTA:] if len(valor) > LARGO_SIN_PISTA else ""

    def nombres(self) -> list[str]:
        """Nombres de los secretos que la cuenta tiene cargados, en orden alfabético."""
        filas = self.conn.execute(
            "SELECT nombre FROM secretos_usuario WHERE user_id = ? ORDER BY nombre;", (self.user_id,)
        ).fetchall()
        return [fila[0] for fila in filas]


class AjustesDeCuenta:
    """Ajustes no secretos de una cuenta, guardados como JSON en `ajustes_usuario`."""

    def __init__(self, conn: sqlite3.Connection, user_id: int) -> None:
        self.conn = conn
        self.user_id = exigir_cuenta(user_id)

    def __repr__(self) -> str:
        return f"AjustesDeCuenta(user_id={self.user_id})"

    def leer(self, clave: str, defecto: Any = None) -> Any:
        """Devuelve el valor guardado, o `defecto` si la cuenta no tiene ese ajuste."""
        _exigir_nombre(clave, "ajuste")
        fila = self.conn.execute(
            "SELECT valor FROM ajustes_usuario WHERE user_id = ? AND clave = ?;", (self.user_id, clave)
        ).fetchone()
        return defecto if fila is None else json.loads(fila[0])

    def guardar(self, clave: str, valor: Any) -> None:
        """Guarda el valor (cualquier cosa que entre en JSON), reemplazando el que hubiera."""
        _exigir_nombre(clave, "ajuste")
        self.conn.execute(
            "INSERT INTO ajustes_usuario (user_id, clave, valor, actualizado_en) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id, clave) DO UPDATE SET valor = excluded.valor, actualizado_en = excluded.actualizado_en;",
            (self.user_id, clave, json.dumps(valor, ensure_ascii=False), _ahora()),
        )
        self.conn.commit()

    def borrar(self, clave: str) -> bool:
        """Borra el ajuste; devuelve si existía."""
        _exigir_nombre(clave, "ajuste")
        cursor = self.conn.execute(
            "DELETE FROM ajustes_usuario WHERE user_id = ? AND clave = ?;", (self.user_id, clave)
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def claves(self) -> list[str]:
        """Claves de los ajustes que la cuenta tiene guardados, en orden alfabético."""
        filas = self.conn.execute(
            "SELECT clave FROM ajustes_usuario WHERE user_id = ? ORDER BY clave;", (self.user_id,)
        ).fetchall()
        return [fila[0] for fila in filas]


def quitar_de_la_cuenta_sin_confirmar(
    conn: sqlite3.Connection, user_id: int, secretos: tuple[str, ...], ajustes: tuple[str, ...]
) -> None:
    """Borra esos secretos y ajustes de la cuenta sin confirmar la transacción: la confirma quien llama (una migración)."""
    cuenta = exigir_cuenta(user_id)
    for nombre in secretos:
        conn.execute(
            "DELETE FROM secretos_usuario WHERE user_id = ? AND nombre = ?;", (cuenta, _exigir_nombre(nombre, "secreto"))
        )
    for clave in ajustes:
        conn.execute("DELETE FROM ajustes_usuario WHERE user_id = ? AND clave = ?;", (cuenta, _exigir_nombre(clave, "ajuste")))
