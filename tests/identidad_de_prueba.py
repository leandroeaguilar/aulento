"""Identidad multiusuario de prueba para los tests del core (051).

El core solo trae el modo local; el modo saas necesita una extensión que aporte la identidad. Los tests que prueban
cómo el core usa los enganches en saas (portada, validadores, 401 sin sesión) la toman de acá, sin la nube.
"""

import sqlite3
from collections.abc import Callable

import pytest
from fastapi import HTTPException

from aulento.auth.modelos import Usuario
from aulento.core.extensiones import Extension
from aulento.core.identity import IIdentityProvider


class IdentidadDePrueba(IIdentityProvider):
    """Todo pedido es de la cuenta que devuelve `cuenta(conn)`; si devuelve None, no hay sesión."""

    def __init__(self, usuario: Usuario | None) -> None:
        self.usuario = usuario

    @property
    def modo(self) -> str:
        return "saas"

    def get_usuario(self) -> Usuario:
        if self.usuario is None:
            raise HTTPException(status_code=401, detail="Sin sesión.")
        return self.usuario

    def get_usuario_opcional(self) -> Usuario | None:
        return self.usuario

    def es_admin(self) -> bool:
        return self.usuario is not None and self.usuario.es_admin

    def es_autenticado(self) -> bool:
        return self.usuario is not None


def extension_de_identidad(cuenta: Callable[[sqlite3.Connection], Usuario | None]) -> Extension:
    return Extension(nombre="identidad_de_prueba", identidad=lambda request, conn: IdentidadDePrueba(cuenta(conn)))


def sin_sesion(conn: sqlite3.Connection) -> None:
    return None


def modo_saas(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AULENTO_MODE", "saas")
