"""Embeddings de una cuenta: los calcula su pasarela de IA; sin IA utilizable, un vector determinista local."""

import hashlib
import logging
import math
from dataclasses import dataclass

from aulento.core.ia.pasarela import PasarelaDeIA
from aulento.core.ia.tipos import (
    DIMENSIONES_DE_EMBEDDING,
    IANoDisponibleError,
    motivo_sin_ia,
)

logger = logging.getLogger(__name__)

EMBEDDING_DIMENSIONS = DIMENSIONES_DE_EMBEDDING
# Con qué nombre de modelo se guardan los vectores del respaldo local: nunca se comparan con los de un proveedor
MODELO_LOCAL_DE_EMBEDDINGS = "local-sha256"


@dataclass(frozen=True)
class VectorDeTexto:
    """El embedding de un texto y con qué se calculó.

    `proveedor` es `None` cuando el vector es el del respaldo local; `por_capacidad`, que lo calculó un proveedor
    de la cuenta que no es el activo. `motivo_sin_ia` dice por qué se usó el respaldo local cuando la causa no es
    que falte cargar una clave.
    """

    vector: list[float]
    modelo: str
    proveedor: str | None = None
    por_capacidad: bool = False
    motivo_sin_ia: str | None = None


class EmbeddingService:
    """Representaciones vectoriales de 768 dimensiones con la IA de una cuenta, con respaldo determinista local."""

    def __init__(self, pasarela: PasarelaDeIA | None = None):
        """`pasarela` es la de la cuenta que pide los embeddings; sin ella el vector es el local."""
        if pasarela is not None and not isinstance(pasarela, PasarelaDeIA):
            raise TypeError("El servicio de embeddings necesita la pasarela de IA de la cuenta que los pide.")
        self._pasarela = pasarela

    def embeber(self, text: str, tarea: str = "documento") -> VectorDeTexto:
        """El embedding del texto con el modelo que lo calculó.

        Lo calcula el proveedor de la cuenta que ofrece embeddings (el activo o, si no los ofrece, otro con clave).
        Sin clave, sin ningún proveedor que los ofrezca o ante una falla del proveedor, devuelve el vector
        determinista local, que lleva su propio nombre de modelo.
        """
        cleaned = text.strip()
        if not cleaned:
            return VectorDeTexto(vector=[0.0] * EMBEDDING_DIMENSIONS, modelo=MODELO_LOCAL_DE_EMBEDDINGS)
        if self._pasarela is None:
            return VectorDeTexto(vector=self._generate_fallback_vector(cleaned), modelo=MODELO_LOCAL_DE_EMBEDDINGS)
        try:
            embedding = self._pasarela.embeber(cleaned, tarea=tarea)
        except IANoDisponibleError as error:
            logger.warning(
                "Sin embeddings de IA para la cuenta %s (%s): se usa el vector determinista local.",
                self._pasarela.user_id,
                type(error).__name__,
            )
            return VectorDeTexto(
                vector=self._generate_fallback_vector(cleaned),
                modelo=MODELO_LOCAL_DE_EMBEDDINGS,
                motivo_sin_ia=motivo_sin_ia(error),
            )
        return VectorDeTexto(
            vector=embedding.vector,
            modelo=embedding.modelo,
            proveedor=embedding.proveedor,
            por_capacidad=embedding.por_capacidad,
        )

    def modelo_actual(self) -> str:
        """El modelo con el que hoy se calcularía un embedding de la cuenta, sin calcular ninguno."""
        de_la_cuenta = self._pasarela.embeddings_de_la_cuenta() if self._pasarela is not None else None
        return de_la_cuenta[1] if de_la_cuenta else MODELO_LOCAL_DE_EMBEDDINGS

    def generate_embedding(self, text: str, tarea: str = "documento") -> list[float]:
        """Solo el vector de 768 dimensiones del texto (ver `embeber`)."""
        return self.embeber(text, tarea=tarea).vector

    def generate_batch(self, texts: list[str], tarea: str = "documento") -> list[list[float]]:
        """Genera embeddings para una lista de textos secuencialmente."""
        return [self.generate_embedding(t, tarea=tarea) for t in texts]

    @staticmethod
    def _generate_fallback_vector(text: str) -> list[float]:
        """Genera un vector pseudo-semántico unitario basado en hashing para entornos offline/tests."""
        h = hashlib.sha256(text.encode("utf-8")).digest()
        vec = []
        for i in range(EMBEDDING_DIMENSIONS):
            byte_val = h[i % len(h)]
            # Normalizar entre -1.0 y 1.0 con variación sinusoidal
            val = math.sin((byte_val + i) * 0.1)
            vec.append(val)

        # Normalizar a norma L2 = 1.0
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]
