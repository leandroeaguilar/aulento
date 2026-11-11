"""Compatibilidad con el nombre anterior, Study Engine (ADR 021). Se retira en una feature posterior a la 069."""

import logging
import os
from collections.abc import MutableMapping

PREFIJO_ANTERIOR = "STUDY_ENGINE_"
PREFIJO = "AULENTO_"

logger = logging.getLogger("aulento")


def adoptar_variables_viejas(environ: MutableMapping[str, str] = os.environ) -> list[str]:
    """Copia cada `STUDY_ENGINE_<X>` a `AULENTO_<X>` cuando esta falta; devuelve los nombres nuevos copiados.

    Si están las dos, gana la nueva. Solo se copian nombres y valores: el aviso nombra las variables, nunca
    muestra un valor, porque varias son secretos (la clave maestra, clientes OAuth).
    """
    copiadas = []
    for nombre in sorted(n for n in environ if n.startswith(PREFIJO_ANTERIOR)):
        nueva = PREFIJO + nombre[len(PREFIJO_ANTERIOR):]
        if nueva not in environ:
            environ[nueva] = environ[nombre]
            copiadas.append(nueva)
    if copiadas:
        logger.warning(
            "Study Engine ahora se llama Aulento: se tomaron %s de sus nombres anteriores (%s). "
            "Renombralas, que los nombres viejos dejarán de leerse.",
            ", ".join(copiadas),
            ", ".join(PREFIJO_ANTERIOR + n[len(PREFIJO):] for n in copiadas),
        )
    return copiadas
