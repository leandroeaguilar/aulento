"""Modelos de dominio para Bloques Horarios de Estudio."""

import re
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


class TipoBloque(str, Enum):
    CURSO = "curso"
    LECTURA = "lectura"
    INGLES = "ingles"
    REPASO = "repaso"
    OTRO = "otro"


TIME_REGEX = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class BloqueHorarioBase(BaseModel):
    dia_semana: int = Field(..., ge=1, le=7, description="Día de la semana: 1=Lunes a 7=Domingo")
    hora_inicio: str = Field(..., description="Hora de inicio en formato HH:MM (24h)")
    hora_fin: str = Field(..., description="Hora de fin en formato HH:MM (24h)")
    tipo: TipoBloque = Field(default=TipoBloque.CURSO, description="Tipo de actividad")
    descripcion: str = Field(..., min_length=1, max_length=255, description="Descripción de la actividad")
    url_acceso: str | None = Field(default=None, description="URL de acceso directo opcional")

    @field_validator("hora_inicio", "hora_fin")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        if not TIME_REGEX.match(v.strip()):
            raise ValueError(f"Hora '{v}' no tiene formato válido HH:MM (00:00 a 23:59)")
        return v.strip()

    @field_validator("url_acceso")
    @classmethod
    def validate_url_acceso(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v_clean = v.strip()
        if not v_clean:
            return None
        if not v_clean.startswith(("http://", "https://")):
            raise ValueError("El enlace debe comenzar con 'http://' o 'https://'")
        return v_clean

    @model_validator(mode="after")
    def validate_time_order(self) -> "BloqueHorarioBase":
        if self.hora_inicio >= self.hora_fin:
            raise ValueError(f"hora_inicio ({self.hora_inicio}) debe ser menor que hora_fin ({self.hora_fin})")
        return self


class BloqueHorarioCreate(BloqueHorarioBase):
    pass


class BloqueHorarioUpdate(BaseModel):
    dia_semana: int | None = Field(default=None, ge=1, le=7, description="Día de la semana: 1=Lunes a 7=Domingo")
    hora_inicio: str | None = Field(default=None, description="Hora de inicio en formato HH:MM (24h)")
    hora_fin: str | None = Field(default=None, description="Hora de fin en formato HH:MM (24h)")
    tipo: TipoBloque | None = Field(default=None, description="Tipo de actividad")
    descripcion: str | None = Field(default=None, min_length=1, max_length=255, description="Descripción de la actividad")
    url_acceso: str | None = Field(default=None, description="URL de acceso directo opcional")

    @field_validator("hora_inicio", "hora_fin")
    @classmethod
    def validate_time_format(cls, v: str | None) -> str | None:
        if v is not None:
            if not TIME_REGEX.match(v.strip()):
                raise ValueError(f"Hora '{v}' no tiene formato válido HH:MM (00:00 a 23:59)")
            return v.strip()
        return None

    @field_validator("url_acceso")
    @classmethod
    def validate_url_acceso(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v_clean = v.strip()
        if not v_clean:
            return None
        if not v_clean.startswith(("http://", "https://")):
            raise ValueError("El enlace debe comenzar con 'http://' o 'https://'")
        return v_clean

    @model_validator(mode="after")
    def validate_time_order(self) -> "BloqueHorarioUpdate":
        if self.hora_inicio is not None and self.hora_fin is not None and self.hora_inicio >= self.hora_fin:
            raise ValueError(f"hora_inicio ({self.hora_inicio}) debe ser menor que hora_fin ({self.hora_fin})")
        return self


class BloqueHorario(BloqueHorarioBase):
    id: int

