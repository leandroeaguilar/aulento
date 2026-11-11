"""Modelos de dominio para Cursos Externos asociados a Plataformas."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


def _validar_ruta_segura(campo: str, v: str | None) -> str | None:
    if v is None:
        return None
    v_str = str(v).strip()
    if not v_str:
        return None
    for ch in v_str:
        if ch in ('"', "'", "<", ">") or ord(ch) < 32 or ord(ch) == 127:
            raise ValueError(f"{campo} no puede contener comillas, '<', '>' ni caracteres de control")
    return v_str


class EstadoCurso(str, Enum):
    EN_CURSO = "en_curso"
    PAUSADO = "pausado"
    COMPLETADO = "completado"


class PrioridadCurso(str, Enum):
    ALTA = "alta"
    MEDIA = "media"
    BAJA = "baja"


class CursoBase(BaseModel):
    plataforma_id: int = Field(..., gt=0, description="ID de la plataforma dueña del curso")
    nombre_curso: str = Field(..., min_length=1, max_length=200, description="Nombre del curso")
    url_aula: str = Field(..., description="Enlace directo al aula virtual o material")
    progreso_pct: float = Field(default=0.0, ge=0.0, le=100.0, description="Porcentaje de avance (0.0 - 100.0)")
    estado: EstadoCurso = Field(default=EstadoCurso.EN_CURSO, description="Estado actual de la cursada")
    prioridad: PrioridadCurso = Field(default=PrioridadCurso.ALTA, description="Nivel de prioridad")
    url_drive: str | None = Field(default=None, description="Enlace a carpeta de Google Drive / Nube")
    ruta_local: str | None = Field(default=None, description="Ruta local en el disco con material o código")
    url_notion: str | None = Field(default=None, description="Enlace a la página o base de datos en Notion")
    ruta_obsidian: str | None = Field(default=None, description="Ruta relativa o URI de la nota en Obsidian")
    external_id: str | None = Field(default=None, description="Identificador o slug externo del curso")
    fuente_sincronizacion: str | None = Field(default="manual", description="Fuente de sincronización externa o manual")
    ultima_sincronizacion: datetime | str | None = Field(default=None, description="Fecha y hora ISO de la última sincronización")
    sync_config_json: str | None = Field(default="{}", description="Configuración JSON para adaptadores de sincronización")

    @field_validator("url_aula")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v_str = str(v).strip()
        if not v_str.startswith(("http://", "https://")):
            raise ValueError("url_aula debe comenzar con http:// o https://")
        return v_str

    @field_validator("url_drive", "url_notion", mode="before")
    @classmethod
    def validate_optional_urls(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v_str = str(v).strip()
        if not v_str:
            return None
        if not v_str.startswith(("http://", "https://")):
            raise ValueError("La URL debe comenzar con http:// o https://")
        return v_str

    @field_validator("ruta_local", mode="before")
    @classmethod
    def validate_ruta_local(cls, v: str | None) -> str | None:
        return _validar_ruta_segura("ruta_local", v)

    @field_validator("ruta_obsidian", mode="before")
    @classmethod
    def validate_ruta_obsidian(cls, v: str | None) -> str | None:
        return _validar_ruta_segura("ruta_obsidian", v)


class CursoCreate(CursoBase):
    pass


class CursoUpdate(BaseModel):
    nombre_curso: str | None = Field(default=None, min_length=1, max_length=200)
    url_aula: str | None = None
    progreso_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    estado: EstadoCurso | None = None
    prioridad: PrioridadCurso | None = None
    url_drive: str | None = None
    ruta_local: str | None = None
    url_notion: str | None = None
    ruta_obsidian: str | None = None
    external_id: str | None = None
    fuente_sincronizacion: str | None = None
    ultima_sincronizacion: datetime | str | None = None
    sync_config_json: str | None = None

    @field_validator("url_aula")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v_str = str(v).strip()
        if not v_str.startswith(("http://", "https://")):
            raise ValueError("url_aula debe comenzar con http:// o https://")
        return v_str

    @field_validator("url_drive", "url_notion", mode="before")
    @classmethod
    def validate_optional_urls(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v_str = str(v).strip()
        if not v_str:
            return None
        if not v_str.startswith(("http://", "https://")):
            raise ValueError("La URL debe comenzar con http:// o https://")
        return v_str

    @field_validator("ruta_local", mode="before")
    @classmethod
    def validate_ruta_local(cls, v: str | None) -> str | None:
        return _validar_ruta_segura("ruta_local", v)

    @field_validator("ruta_obsidian", mode="before")
    @classmethod
    def validate_ruta_obsidian(cls, v: str | None) -> str | None:
        return _validar_ruta_segura("ruta_obsidian", v)


class Curso(CursoBase):
    id: int
    fecha_creacion: datetime | str | None = None
    fecha_actualizacion: datetime | str | None = None
    nombre_plataforma: str | None = None  # Campo enriquecido para joins
