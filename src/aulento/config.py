"""Configuración global y resolución de rutas para Aulento."""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

VARIABLE_DEL_DIRECTORIO_DE_DATOS = "AULENTO_DATA_DIR"
DEFAULT_DATA_DIR = Path.home() / ".aulento"
# La carpeta de cuando el producto se llamaba Study Engine (ADR 021): se muda una vez y, si no se puede, se sigue usando
CARPETA_ANTERIOR = Path.home() / ".study-engine"
# El nombre del archivo de la base no cambió con la marca: cambiarlo obligaría a migrar datos (ADR 021)
NOMBRE_DE_LA_BASE = "study_engine.db"
DEFAULT_DB_PATH = DEFAULT_DATA_DIR / NOMBRE_DE_LA_BASE


def _carpeta_por_defecto() -> Path:
    """La carpeta por defecto, o la anterior si todavía no se mudó. No crea, mueve ni borra nada."""
    if not DEFAULT_DATA_DIR.exists() and CARPETA_ANTERIOR.exists():
        return CARPETA_ANTERIOR
    return DEFAULT_DATA_DIR


def _resolver_directorio_de_datos() -> Path:
    """Directorio de datos configurado, sin crearlo: la variable de entorno o, si no, el valor por defecto."""
    env_dir = (os.getenv(VARIABLE_DEL_DIRECTORIO_DE_DATOS) or "").strip()
    return Path(env_dir) if env_dir else _carpeta_por_defecto()


def mudar_carpeta_anterior() -> Path | None:
    """Renombra `~/.study-engine` a `~/.aulento` si hace falta; devuelve la carpeta nueva si la mudó (070, R7).

    Solo actúa sin `AULENTO_DATA_DIR`, con la carpeta anterior presente y sin la nueva: nunca copia ni mezcla
    carpetas. Si el renombre falla (un archivo abierto en Windows, otro disco), deja todo como estaba y la app
    sigue con la carpeta anterior, que `_carpeta_por_defecto` elige mientras la nueva no exista.
    """
    if (os.getenv(VARIABLE_DEL_DIRECTORIO_DE_DATOS) or "").strip():
        return None
    if DEFAULT_DATA_DIR.exists() or not CARPETA_ANTERIOR.exists():
        return None
    try:
        CARPETA_ANTERIOR.rename(DEFAULT_DATA_DIR)
    except OSError as error:
        logger.warning(
            "No se pudo mudar %s a %s (%s): se sigue usando la carpeta anterior.",
            CARPETA_ANTERIOR, DEFAULT_DATA_DIR, error,
        )
        return None
    logger.warning("Study Engine ahora se llama Aulento: los datos se mudaron de %s a %s.", CARPETA_ANTERIOR, DEFAULT_DATA_DIR)
    return DEFAULT_DATA_DIR


def get_data_dir() -> Path:
    """Retorna el único directorio de datos del sistema, creándolo si falta.

    Prioridad:
    1. Variable de entorno AULENTO_DATA_DIR
    2. ~/.aulento (o ~/.study-engine, si todavía no se mudó)
    """
    mudar_carpeta_anterior()
    data_dir = _resolver_directorio_de_datos()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def dir_de_cuenta(user_id: int) -> Path:
    """Retorna la carpeta de una cuenta dentro del directorio de datos (`usuarios/<id>/`), creándola si falta."""
    # Se importa acá: `aulento.db` importa este módulo al cargarse
    from aulento.db.cuenta import exigir_cuenta

    carpeta = get_data_dir() / "usuarios" / str(exigir_cuenta(user_id))
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def get_db_path() -> Path:
    """Retorna la ruta de la base de datos SQLite.

    Prioridad:
    1. Variable de entorno AULENTO_DB_PATH
    2. `study_engine.db` dentro del directorio de datos (no lo crea: de eso se ocupa `ensure_data_dir`)
    """
    env_path = os.getenv("AULENTO_DB_PATH")
    if env_path:
        return Path(env_path)
    return _resolver_directorio_de_datos() / NOMBRE_DE_LA_BASE


def ensure_data_dir(db_path: Path | None = None) -> Path:
    """Asegura que el directorio que contendrá la base de datos exista."""
    if db_path is None:
        # Antes de crear la carpeta nueva vacía, que dejaría atrás los datos de la anterior (070, R7)
        mudar_carpeta_anterior()
    target = db_path or get_db_path()
    if str(target) != ":memory:":
        target.parent.mkdir(parents=True, exist_ok=True)
    return target


MODO_LOCAL = "local"
MODO_SAAS = "saas"
_MODOS = {"local": MODO_LOCAL, "saas": MODO_SAAS}


class ModoInvalido(ValueError):
    """`AULENTO_MODE` trae un valor que no es un modo conocido."""

    def __init__(self, valor: str) -> None:
        self.valor = valor
        super().__init__(
            f"AULENTO_MODE trae un valor desconocido: «{valor}». Usá «local» (una sola persona, sin login, "
            "solo en esta máquina) o «saas» (varias cuentas con login), o dejala sin definir para el modo local."
        )


def get_engine_mode() -> str:
    """Retorna el modo de operación: 'local' (monousuario, por defecto) o 'saas' (multiusuario con login).

    Sin la variable, o vacía, el modo es local (ADR 017). Un valor desconocido levanta `ModoInvalido`:
    no se adivina, porque equivocarse hacia el modo local dejaría la cuenta de administrador sin login.
    """
    valor = (os.getenv("AULENTO_MODE") or "").strip().lower()
    if not valor:
        return MODO_LOCAL
    try:
        return _MODOS[valor]
    except KeyError:
        raise ModoInvalido(valor) from None


def is_saas_mode() -> bool:
    """Indica si el motor está operando en modo SaaS multiusuario."""
    return get_engine_mode() == MODO_SAAS


def is_local_mode() -> bool:
    """Indica si el motor está operando en modo Local monousuario."""
    return get_engine_mode() == MODO_LOCAL
