"""Lectura tolerante del JSON que devuelve un modelo: no todos los proveedores lo entregan limpio."""

import json
import re
from typing import Any

from aulento.core.ia.tipos import NOMBRE_VISIBLE, IANoDisponibleError, Respuesta

_BLOQUE_DE_CODIGO = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def leer_json(texto: str | None) -> Any:
    """El valor JSON de una respuesta, aunque venga en un bloque de código o con texto alrededor.

    Levanta `ValueError` si el texto no contiene un objeto ni una lista JSON.
    """
    limpio = (texto or "").strip()
    candidatos = [limpio, *(bloque.strip() for bloque in _BLOQUE_DE_CODIGO.findall(limpio))]
    for candidato in candidatos:
        try:
            return json.loads(candidato)
        except ValueError:
            continue
    comienzos = [posicion for posicion in (limpio.find("{"), limpio.find("[")) if posicion >= 0]
    if comienzos:
        try:
            return json.JSONDecoder().raw_decode(limpio[min(comienzos) :])[0]
        except ValueError:
            pass
    raise ValueError("La respuesta no contiene JSON válido.")


def leer_json_de(respuesta: Respuesta, consecuencia: str = "") -> Any:
    """El JSON de la respuesta de un modelo; si no lo trae levanta `IANoDisponibleError` nombrando al proveedor.

    `consecuencia` se agrega al mensaje: qué pasó con la operación («No se agregaron temas.»).
    """
    try:
        return leer_json(respuesta.texto)
    except ValueError:
        raise respuesta_inutil(respuesta, "devolvió una respuesta que no es JSON válido", consecuencia) from None


def respuesta_inutil(respuesta: Respuesta, que_paso: str, consecuencia: str = "") -> IANoDisponibleError:
    """El error de una respuesta que llegó pero no sirve: «<Proveedor> <qué pasó>. <consecuencia>»."""
    cortada = " (la respuesta llegó cortada por el tope de tokens)" if respuesta.truncada else ""
    mensaje = f"{NOMBRE_VISIBLE[respuesta.proveedor]} {que_paso}{cortada}. {consecuencia}".strip()
    return IANoDisponibleError(mensaje, proveedor=respuesta.proveedor, modelo=respuesta.modelo)
