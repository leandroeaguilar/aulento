"""Módulo de la interfaz web local de Aulento con FastAPI y Uvicorn."""

from aulento.web.app import create_app

__all__ = ["create_app"]
