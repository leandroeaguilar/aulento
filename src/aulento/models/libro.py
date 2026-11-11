"""Modelos de dominio para el seguimiento de lectura de libros técnicos."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, computed_field, model_validator


class EstadoLibro(str, Enum):
    LEYENDO = "leyendo"
    PAUSADO = "pausado"
    COMPLETADO = "completado"


class LibroBase(BaseModel):
    titulo: str = Field(..., min_length=1, max_length=200, description="Título del libro")
    capitulo_actual: int = Field(default=1, ge=0, description="Capítulo o sección actual")
    total_capitulos: int = Field(default=1, gt=0, description="Total de capítulos o secciones")
    pagina_actual: int = Field(default=0, ge=0, description="Página actual leída")
    total_paginas: int | None = Field(default=None, gt=0, description="Total de páginas del libro (opcional)")
    ruta_vault: str | None = Field(default=None, description="Ruta relativa o nombre del libro en el vault")
    estado: EstadoLibro = Field(default=EstadoLibro.LEYENDO, description="Estado de lectura")
    google_books_id: str | None = Field(default=None, description="Identificador del volumen en Google Books")
    fuente_sincronizacion: str | None = Field(default="manual", description="Fuente de lectura o sincronización (manual, google_books, apple_books)")
    ultima_sincronizacion: datetime | str | None = Field(default=None, description="Fecha de última sincronización externa")

    @model_validator(mode="after")
    def validate_capitulos(self) -> "LibroBase":
        if self.capitulo_actual > self.total_capitulos:
            raise ValueError(f"capitulo_actual ({self.capitulo_actual}) no puede ser mayor a total_capitulos ({self.total_capitulos})")
        if self.total_paginas is not None and self.pagina_actual > self.total_paginas:
            raise ValueError(f"pagina_actual ({self.pagina_actual}) no puede ser mayor a total_paginas ({self.total_paginas})")
        return self


class LibroCreate(LibroBase):
    pass


class LibroUpdate(BaseModel):
    titulo: str | None = Field(default=None, min_length=1, max_length=200)
    capitulo_actual: int | None = Field(default=None, ge=0)
    total_capitulos: int | None = Field(default=None, gt=0)
    pagina_actual: int | None = Field(default=None, ge=0)
    total_paginas: int | None = Field(default=None, gt=0)
    ruta_vault: str | None = None
    estado: EstadoLibro | None = None
    google_books_id: str | None = None
    fuente_sincronizacion: str | None = None
    ultima_sincronizacion: datetime | str | None = None


class Libro(LibroBase):
    id: int
    fecha_creacion: datetime | str | None = None
    fecha_actualizacion: datetime | str | None = None

    @computed_field
    @property
    def porcentaje_leido(self) -> float:
        if self.total_paginas and self.total_paginas > 0:
            return round(min(100.0, (self.pagina_actual / self.total_paginas) * 100.0), 1)
        if self.total_capitulos > 0:
            return round(min(100.0, (self.capitulo_actual / self.total_capitulos) * 100.0), 1)
        return 0.0
