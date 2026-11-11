"""Bus de eventos del dominio: el core avisa lo que pasa y las extensiones escuchan (ADR 017).

El core no sabe quién escucha ni para qué. Un suscriptor que falla se anota en el registro y no
interrumpe ni a los demás suscriptores ni a quien emitió el evento.
"""

import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

IA_CONSUMO = "ia.consumo"
"""Una llamada a un proveedor de IA terminó. Datos: user_id, proveedor, modelo, endpoint_tipo, tokens_entrada,
tokens_salida, tokens_totales, estado."""

IA_ANTES = "ia.antes"
"""Una llamada a un proveedor de IA está por hacerse. Datos: user_id, proveedor, endpoint_tipo. Se verifica con
`bus.verificar`: un suscriptor que levanta una excepción frena la llamada (por ejemplo, sin saldo)."""

Suscriptor = Callable[..., Any]


class BusDeEventos:
    """Registro de suscriptores por nombre de evento."""

    def __init__(self) -> None:
        self._suscriptores: dict[str, list[Suscriptor]] = defaultdict(list)

    def suscribir(self, nombre: str, funcion: Suscriptor) -> None:
        """Agrega `funcion` a los suscriptores de `nombre`.

        Se puede suscribir la misma función más de una vez (por ejemplo, dos apps del mismo proceso con la misma
        extensión): cada registro cuenta para desuscribir, pero `emitir` la llama una sola vez.
        """
        self._suscriptores[nombre].append(funcion)

    def desuscribir(self, nombre: str, funcion: Suscriptor) -> None:
        """Quita un registro de `funcion` en `nombre`; si no estaba, no hace nada."""
        lista = self._suscriptores.get(nombre, [])
        if funcion in lista:
            lista.remove(funcion)

    def emitir(self, nombre: str, **datos: Any) -> None:
        """Llama a cada suscriptor de `nombre` con `datos`; las excepciones se anotan y se siguen."""
        # Una vez por función: un registro repetido no repite el efecto (por ejemplo, un débito)
        for funcion in dict.fromkeys(self._suscriptores.get(nombre, [])):
            try:
                funcion(**datos)
            except Exception:
                logger.exception("Un suscriptor del evento %s falló; se sigue con los demás.", nombre)

    def verificar(self, nombre: str, **datos: Any) -> None:
        """Como `emitir`, pero la primera excepción de un suscriptor sube a quien verifica y frena lo que iba a hacer."""
        for funcion in dict.fromkeys(self._suscriptores.get(nombre, [])):
            funcion(**datos)

    def limpiar(self) -> None:
        """Quita todos los suscriptores."""
        self._suscriptores.clear()


bus = BusDeEventos()
"""Bus del proceso: lo usa el core para emitir y `create_app` para registrar las suscripciones de sus extensiones."""
