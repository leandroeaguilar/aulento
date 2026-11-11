"""Doble en memoria del almacén de vectores (PostgreSQL + pgvector) para la suite: ningún test abre un Postgres real.

Interpreta las pocas formas de SQL que usa `VectorRepository` leyendo la propia sentencia: las columnas de un
`INSERT` y las condiciones `columna = %s` (o `(columna = %s OR columna IS NULL)`) de un `WHERE`. Así, una
sentencia que olvide `user_id` o `embedding_model` se comporta como lo haría en Postgres: el `INSERT` deja la
fila sin dueño o sin modelo y el `SELECT` o el `DELETE` alcanzan filas ajenas o de otro modelo.
"""

import contextlib
import math
import re
from typing import Self

COLUMNAS_DE_ORIGEN = {"id", "source_type", "source_id", "source_title", "chunk_text", "embedding", "metadata"}
MARCADOR = re.compile(r"(?:(\w+)\s*=\s*)?%s")
# `(columna = %s OR columna IS NULL)`: la condición también la cumple una fila sin valor en esa columna
ADMITE_VACIO = re.compile(r"\(\s*(\w+)\s*=\s*%s\s+OR\s+\1\s+IS\s+NULL\s*\)", flags=re.IGNORECASE)
# Las columnas que el esquema sumó después de la tabla original, cada una con su `ALTER TABLE`
COLUMNAS_AGREGADAS = {"user_id", "embedding_model"}
# Todo texto recibe el mismo vector: cualquier fragmento es igual de cercano a cualquier consulta
VECTOR_UNICO = (1.0, 0.0, 0.0)
# El modelo con que el doble dice haber calculado ese vector
MODELO_DEL_DOBLE = "gemini-embedding-001"

_instalado: "PgvectorFalso | None" = None


class ErrorDePostgres(Exception):
    """Lo que Postgres rechazaría: una columna que no existe o un objeto que ya existe."""


class PgvectorFalso:
    """Conexión de mentira a `knowledge_embeddings`: guarda las filas en una lista y anota cada sentencia."""

    def __init__(self):
        self.filas: list[dict] = []
        self.sentencias: list[tuple[str, tuple]] = []
        self.columnas: set[str] = set()
        self.indices: set[str] = set()
        # Un Postgres encendido en el que nadie creó todavía la tabla
        self.sin_tabla = False
        self._siguiente_id = 1

    def cursor(self) -> "_Cursor":
        return _Cursor(self)

    @contextlib.contextmanager
    def transaction(self):
        yield self

    def close(self) -> None:
        """Las conexiones de mentira no se cierran: la misma sirve a todos los pedidos del test."""

    def volcado(self) -> list[tuple]:
        """Las filas tal como quedaron, para comparar el almacén antes y después de un pedido."""
        return [tuple((columna, repr(fila[columna])) for columna in sorted(fila) if columna != "embedding") for fila in self.filas]

    def de(self, user_id: int | None) -> list[dict]:
        return [fila for fila in self.filas if fila.get("user_id") == user_id]

    def sembrar_fila_sin_dueno(self, **campos) -> dict:
        """Una fila como las que dejó la versión anterior del esquema: sin la columna de dueño."""
        fila = {"id": self._siguiente_id, "metadata": "{}", "embedding": [1.0], **campos}
        self._siguiente_id += 1
        self.filas.append(fila)
        return fila

    def sembrar_fila_sin_modelo(self, user_id: int, **campos) -> dict:
        """Una fila con dueño indexada antes de que se guardara el modelo de embeddings: sin esa columna."""
        return self.sembrar_fila_sin_dueno(user_id=user_id, embedding=list(VECTOR_UNICO), **campos)


class _Cursor:
    def __init__(self, base: PgvectorFalso):
        self._base = base
        self._resultado: list[tuple] = []
        self.rowcount = -1

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def fetchone(self):
        return self._resultado[0] if self._resultado else None

    def fetchall(self) -> list[tuple]:
        return list(self._resultado)

    def execute(self, sql: str, params=()) -> None:
        base = self._base
        parametros = tuple(params)
        sentencia = " ".join(re.sub(r"--[^\n]*", "", sql).split())
        base.sentencias.append((sentencia, parametros))
        marcadores = MARCADOR.findall(sentencia)
        if len(marcadores) != len(parametros):
            raise ErrorDePostgres(f"{len(marcadores)} marcadores y {len(parametros)} parámetros: {sentencia}")
        orden = sentencia.upper()

        if orden.startswith("SELECT 1"):
            self._resultado = [(1,)]
        elif orden.startswith("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS"):
            self._resultado = [] if base.sin_tabla else [(columna,) for columna in sorted(self._columnas_conocidas())]
        elif orden.startswith("CREATE EXTENSION"):
            self._resultado = []
        elif orden.startswith("CREATE TABLE"):
            self._crear_tabla(orden)
        elif orden.startswith("ALTER TABLE"):
            self._agregar_columna(sentencia)
        elif orden.startswith("CREATE INDEX"):
            self._crear_indice(sentencia)
        elif orden.startswith("INSERT INTO KNOWLEDGE_EMBEDDINGS"):
            self._insertar(sentencia, parametros)
        elif orden.startswith("SELECT COUNT(*) FROM KNOWLEDGE_EMBEDDINGS"):
            self._resultado = [(len(self._filtradas(sentencia, marcadores, parametros)),)]
        elif orden.startswith("SELECT EMBEDDING_MODEL, COUNT(*) FROM KNOWLEDGE_EMBEDDINGS"):
            self._contar_por_modelo(sentencia, marcadores, parametros)
        elif orden.startswith("SELECT") and "FROM KNOWLEDGE_EMBEDDINGS" in orden:
            self._buscar(sentencia, marcadores, parametros)
        elif orden.startswith("DELETE FROM KNOWLEDGE_EMBEDDINGS"):
            borradas = self._filtradas(sentencia, marcadores, parametros)
            base.filas = [fila for fila in base.filas if fila not in borradas]
            self.rowcount = len(borradas)
        else:
            raise ErrorDePostgres(f"sentencia que el doble no conoce: {sentencia}")

    def _crear_tabla(self, orden: str) -> None:
        if self._base.columnas and "IF NOT EXISTS" not in orden:
            raise ErrorDePostgres('relation "knowledge_embeddings" already exists')
        self._base.columnas |= COLUMNAS_DE_ORIGEN
        self._base.sin_tabla = False

    def _agregar_columna(self, sentencia: str) -> None:
        alta = re.search(r"ADD COLUMN (IF NOT EXISTS )?(\w+)", sentencia, flags=re.IGNORECASE)
        if alta is None:
            raise ErrorDePostgres(f"ALTER que el doble no conoce: {sentencia}")
        if self._base.sin_tabla:
            raise ErrorDePostgres('relation "knowledge_embeddings" does not exist')
        columna = alta.group(2)
        conocidas = self._columnas_conocidas()
        if columna in conocidas and not alta.group(1):
            raise ErrorDePostgres(f'column "{columna}" of relation "knowledge_embeddings" already exists')
        self._base.columnas = conocidas | {columna}

    def _crear_indice(self, sentencia: str) -> None:
        alta = re.search(r"CREATE INDEX (IF NOT EXISTS )?(\w+) ON knowledge_embeddings", sentencia, flags=re.IGNORECASE)
        if alta is None:
            raise ErrorDePostgres(f"índice que el doble no conoce: {sentencia}")
        if self._base.sin_tabla:
            raise ErrorDePostgres('relation "knowledge_embeddings" does not exist')
        if alta.group(2) in self._base.indices and not alta.group(1):
            raise ErrorDePostgres(f'relation "{alta.group(2)}" already exists')
        self._base.indices.add(alta.group(2))

    def _columnas_conocidas(self) -> set[str]:
        # Una base recién creada por el doble (sin `init_postgres_db`) acepta el esquema actual completo
        return set(self._base.columnas or COLUMNAS_DE_ORIGEN | COLUMNAS_AGREGADAS)

    def _exigir_columnas(self, columnas) -> None:
        if self._base.sin_tabla:
            raise ErrorDePostgres('relation "knowledge_embeddings" does not exist')
        conocidas = self._columnas_conocidas()
        for columna in columnas:
            if columna not in conocidas:
                raise ErrorDePostgres(f'column "{columna}" does not exist')

    def _insertar(self, sentencia: str, parametros: tuple) -> None:
        columnas = [c.strip() for c in re.search(r"\((.*?)\)\s*VALUES", sentencia, flags=re.IGNORECASE).group(1).split(",")]
        self._exigir_columnas(columnas)
        fila = dict(zip(columnas, parametros, strict=True))
        fila["id"] = self._base._siguiente_id
        self._base._siguiente_id += 1
        self._base.filas.append(fila)
        self._resultado = [(fila["id"],)]

    def _filtradas(self, sentencia: str, marcadores: list[str], parametros: tuple) -> list[dict]:
        condiciones = [(columna, valor) for columna, valor in zip(marcadores, parametros, strict=True) if columna]
        self._exigir_columnas(columna for columna, _ in condiciones)
        admiten_vacio = {columna.lower() for columna in ADMITE_VACIO.findall(sentencia)}

        def cumple(fila: dict, columna: str, valor) -> bool:
            return fila.get(columna) == valor or (columna.lower() in admiten_vacio and fila.get(columna) is None)

        return [fila for fila in self._base.filas if all(cumple(fila, columna, valor) for columna, valor in condiciones)]

    def _contar_por_modelo(self, sentencia: str, marcadores: list[str], parametros: tuple) -> None:
        if "GROUP BY EMBEDDING_MODEL" not in sentencia.upper():
            raise ErrorDePostgres('column "embedding_model" must appear in the GROUP BY clause')
        self._exigir_columnas(["embedding_model"])
        cuenta: dict = {}
        for fila in self._filtradas(sentencia, marcadores, parametros):
            cuenta[fila.get("embedding_model")] = cuenta.get(fila.get("embedding_model"), 0) + 1
        self._resultado = sorted(cuenta.items(), key=lambda par: par[0] or "")

    def _buscar(self, sentencia: str, marcadores: list[str], parametros: tuple) -> None:
        consulta, limite = parametros[0], parametros[-1]
        encontradas = [
            (
                fila["id"],
                fila.get("source_type"),
                fila.get("source_id"),
                fila.get("source_title"),
                fila.get("chunk_text"),
                fila.get("metadata"),
                _coseno(consulta, fila["embedding"]),
            )
            for fila in self._filtradas(sentencia, marcadores, parametros)
        ]
        encontradas.sort(key=lambda fila: (-fila[6], fila[0]))
        self._resultado = encontradas[:limite]


def _coseno(a: list[float], b: list[float]) -> float:
    norma = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b, strict=False)) / norma if norma else 0.0


def instalar(monkeypatch) -> PgvectorFalso:
    """Deja el doble como el Postgres del test: conectado y vacío. Los embeddings no salen a la red."""
    global _instalado
    from aulento.core import extensiones
    from aulento.core.embedding_service import EmbeddingService, VectorDeTexto
    from aulento.db import postgres, vector_repository

    falso = PgvectorFalso()
    monkeypatch.setattr(postgres, "get_postgres_connection", lambda *args, **kwargs: falso)
    monkeypatch.setattr(vector_repository, "get_postgres_connection", lambda *args, **kwargs: falso)
    monkeypatch.setattr(extensiones, "_fabricas_de_almacen", [lambda uid: vector_repository.VectorRepository(uid)])
    monkeypatch.setattr(
        EmbeddingService, "embeber", lambda self, text: VectorDeTexto(vector=list(VECTOR_UNICO), modelo=MODELO_DEL_DOBLE)
    )
    # Cada test estrena proceso: las altas de las columnas de dueño y de modelo todavía no se hicieron
    monkeypatch.setattr(postgres, "_dueno_asegurado", False)
    monkeypatch.setattr(postgres, "_modelo_asegurado", False)
    _instalado = falso
    return falso


def instalado() -> PgvectorFalso:
    """El doble del test en curso."""
    assert _instalado is not None, "el test no pidió la fixture `pgvector_falso`"
    return _instalado


def desinstalar() -> None:
    global _instalado
    _instalado = None
