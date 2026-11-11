"""Archivo de registro del modo local (051, R9): `<data_dir>/aulento.log`, rotativo, que lee el diagnóstico.

En local no hay un servidor que junte los registros: lo que se avisa (advertencias y errores de `aulento.*`) queda
en este archivo, para que el diagnóstico lo muestre y se pueda adjuntar a un reporte. En la nube, los registros van a la
salida del contenedor.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from aulento.config import get_data_dir

NOMBRE_DEL_ARCHIVO = "aulento.log"
TAMANO_MAXIMO = 1024 * 1024  # 1 MB por archivo
RESPALDOS = 3  # aulento.log.1 .. .3
FORMATO = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def ruta_del_registro() -> Path:
    return get_data_dir() / NOMBRE_DEL_ARCHIVO


def abrir_registro_local() -> RotatingFileHandler:
    """Suma al logger `aulento` un archivo rotativo y lo devuelve para cerrarlo con `cerrar_registro_local`."""
    manejador = RotatingFileHandler(ruta_del_registro(), maxBytes=TAMANO_MAXIMO, backupCount=RESPALDOS, encoding="utf-8")
    manejador.setFormatter(logging.Formatter(FORMATO))
    logging.getLogger("aulento").addHandler(manejador)
    return manejador


def cerrar_registro_local(manejador: RotatingFileHandler) -> None:
    logging.getLogger("aulento").removeHandler(manejador)
    manejador.close()
