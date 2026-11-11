"""Modelos de dominio para Plataformas Académicas."""

from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl, field_validator


class PlataformaBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100, description="Nombre de la plataforma académica")
    url_acceso: str = Field(..., description="URL de acceso al portal")
    icono_color: str = Field(default="blue", max_length=30, description="Color distintivo para la UI")

    @field_validator("url_acceso")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v_str = str(v).strip()
        if not (v_str.startswith("http://") or v_str.startswith("https://")):
            raise ValueError("url_acceso debe comenzar con http:// o https://")
        return v_str


class PlataformaCreate(PlataformaBase):
    pass


class PlataformaUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=100)
    url_acceso: str | None = None
    icono_color: str | None = None

    @field_validator("url_acceso")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v_str = str(v).strip()
        if not (v_str.startswith("http://") or v_str.startswith("https://")):
            raise ValueError("url_acceso debe comenzar con http:// o https://")
        return v_str


class Plataforma(PlataformaBase):
    id: int
    fecha_creacion: datetime | str | None = None
