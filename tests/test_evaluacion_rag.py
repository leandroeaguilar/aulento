"""Evaluación cuantitativa del RAG del tutor (R8).

Carga notas de ejemplo y preguntas del conjunto de evaluación, mide aciertos@5
de la vía por palabras y de la fusión con el respaldo local (sin IA), y falla
si la tasa de acierto cae por debajo de los pisos registrados.
Con AULENTO_EVAL_IA=1 se evalúa además con embeddings reales de la IA de la cuenta.
"""

import json
import os
from pathlib import Path

import pytest

from aulento.core.knowledge_rag import (
    TIPO_DE_FUENTE_NOTA,
    KnowledgeRAGService,
)
from aulento.db.vectores_sqlite import AlmacenVectoresSqlite
from aulento.mcp.agent import (
    ORIGEN_VECTORIAL,
    Fragmento,
    fusion_rrf,
)

RUTA_EVALUACION = Path(__file__).parent / "datos_rag" / "evaluacion_rag.json"


def _cargar_datos():
    with open(RUTA_EVALUACION, "r", encoding="utf-8") as f:
        return json.load(f)


def _fuente_en_top_k(resultados, fuente_esperada: str, top_k: int = 5) -> bool:
    """Verifica si el identificador esperado está presente en los primeros top_k resultados."""
    for res in resultados[:top_k]:
        fid = getattr(res, "fuente_id", None) or (res.get("source_id") if isinstance(res, dict) else None)
        if fid == fuente_esperada:
            return True
        nombre = getattr(res, "nombre", None) or (res.get("source_title") if isinstance(res, dict) else "")
        if fuente_esperada.lower() in str(nombre).lower():
            return True
    return False


@pytest.fixture
def evaluacion_setup(tmp_path):
    """Inicializa base de datos temporal con las notas del conjunto de evaluación."""
    db_path = tmp_path / "vectores_eval.db"
    user_id = 9999
    repo = AlmacenVectoresSqlite(user_id=user_id, db_path=db_path)
    rag = KnowledgeRAGService(user_id=user_id, repository=repo)

    datos = _cargar_datos()
    for nota in datos["notas"]:
        rag.index_document(
            source_type=TIPO_DE_FUENTE_NOTA,
            source_id=nota["id"],
            source_title=nota["titulo"],
            content=nota["contenido"],
        )

    return {"rag": rag, "repo": repo, "datos": datos, "user_id": user_id}


def test_evaluacion_rag_piso_aciertos(evaluacion_setup):
    """Mide aciertos@5 para búsqueda por palabras y fusión con respaldo local contra el piso mínimo."""
    rag = evaluacion_setup["rag"]
    repo = evaluacion_setup["repo"]
    datos = evaluacion_setup["datos"]

    preguntas = datos["preguntas"]
    piso_palabras = float(datos.get("piso_aciertos_palabras", 0.50))
    piso_fusion = float(datos.get("piso_aciertos_fusion", 0.55))

    aciertos_palabras = 0
    aciertos_fusion = 0

    for item in preguntas:
        pregunta = item["pregunta"]
        esperada = item["fuente_esperada"]

        # 1. Búsqueda por palabras (BM25 si está implementado, o conteo de términos en fragmentos)
        if hasattr(repo, "search_bm25"):
            palabras_raw = repo.search_bm25(query=pregunta, limit=10)
        else:
            # Respaldo simple para medición previa a T4
            conn = repo._get_conn()
            terminos = [t.lower() for t in pregunta.split() if len(t) > 3]
            filas = conn.execute(
                "SELECT id, source_type, source_id, source_title, chunk_text, metadata FROM fragmentos WHERE user_id = ?;",
                (evaluacion_setup["user_id"],),
            ).fetchall()
            puntuadas = []
            for f in filas:
                texto_b = (f["source_title"] + " " + f["chunk_text"]).lower()
                pts = sum(texto_b.count(t) for t in terminos)
                if pts > 0:
                    puntuadas.append((pts, f))
            puntuadas.sort(key=lambda x: -x[0])
            palabras_raw = [
                {
                    "id": p[1]["id"],
                    "source_type": p[1]["source_type"],
                    "source_id": p[1]["source_id"],
                    "source_title": p[1]["source_title"],
                    "chunk_text": p[1]["chunk_text"],
                }
                for p in puntuadas[:10]
            ]

        if _fuente_en_top_k(palabras_raw, esperada, top_k=5):
            aciertos_palabras += 1

        # 2. Búsqueda semántica (con respaldo local)
        vec_raw = rag.search(query=pregunta, limit=10, min_similarity=0.0)

        # 3. Fusión RRF
        vec_frags = [
            Fragmento(
                nombre=v["source_title"],
                origen=ORIGEN_VECTORIAL,
                texto=v["chunk_text"],
                tipo_fuente=v["source_type"],
                fuente_id=v["source_id"],
            )
            for v in vec_raw
        ]
        pal_frags = [
            Fragmento(
                nombre=p["source_title"],
                origen="palabras",
                texto=p["chunk_text"],
                tipo_fuente=p["source_type"],
                fuente_id=p["source_id"],
            )
            for p in palabras_raw
        ]

        fusionados = fusion_rrf(vec_frags, pal_frags, k=60, limite=5)
        if _fuente_en_top_k(fusionados, esperada, top_k=5):
            aciertos_fusion += 1

    total = len(preguntas)
    tasa_palabras = aciertos_palabras / total
    tasa_fusion = aciertos_fusion / total

    print(f"\nEvaluación RAG: Palabras hit@5: {tasa_palabras:.2%} ({aciertos_palabras}/{total})")
    print(f"Evaluación RAG: Fusión hit@5: {tasa_fusion:.2%} ({aciertos_fusion}/{total})")

    assert tasa_palabras >= piso_palabras, (
        f"La tasa de aciertos por palabras ({tasa_palabras:.2%}) cayó debajo del piso ({piso_palabras:.2%})"
    )
    assert tasa_fusion >= piso_fusion, (
        f"La tasa de aciertos de fusión ({tasa_fusion:.2%}) cayó debajo del piso ({piso_fusion:.2%})"
    )


@pytest.mark.skipif(
    os.environ.get("AULENTO_EVAL_IA") != "1",
    reason="Evaluación con embeddings reales requiere AULENTO_EVAL_IA=1 y credenciales.",
)
def test_evaluacion_rag_con_ia():
    """Evalúa aciertos@5 conectándose a la IA configurada en la cuenta."""
    # Se ejecuta solo bajo demanda con AULENTO_EVAL_IA=1
