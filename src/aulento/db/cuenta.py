"""Validación de la cuenta dueña que exigen los repositorios y servicios de datos de estudio."""


def exigir_cuenta(user_id: int) -> int:
    """Devuelve `user_id` si es el id de una cuenta (entero positivo); si no, levanta `ValueError`.

    Sin esta comprobación un `None` llegaría al SQL como `user_id = NULL` y un olvido pasaría por
    "la cuenta no tiene datos" en vez de fallar.
    """
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise ValueError(f"Se necesita la cuenta dueña de los datos (id entero positivo); se recibió {user_id!r}.")
    return user_id


def exigir_repositorio_de_cuenta(repo: object) -> int:
    """Devuelve la cuenta de un repositorio; levanta `ValueError` si falta el repositorio o no está atado a una."""
    return exigir_cuenta(getattr(repo, "user_id", None))
