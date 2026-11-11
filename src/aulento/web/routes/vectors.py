"""Router para endpoints de Búsqueda Semántica Vectorial."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field

from aulento.auth.dependencias import requiere_admin
from aulento.auth.modelos import Usuario
from aulento.core.knowledge_rag import FuenteNoEncontrada
from aulento.core.secretos import ERRORES_AL_LEER_UN_SECRETO
from aulento.web.dependencies import (
    BusquedaSemantica,
    Conexion,
    SinCuentaCompartida,
    no_encontrado,
)

router = APIRouter(prefix="/api/vectors", tags=["Vectors / Semantic Search"])


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="Consulta en lenguaje natural para búsqueda semántica")
    limit: int = Field(default=5, ge=1, le=50, description="Cantidad máxima de resultados")
    source_type: str | None = Field(default=None, max_length=50, description="Filtrar por tipo: 'obsidian_note', 'book_chunk', etc.")
    min_similarity: float = Field(default=0.4, ge=0.0, le=1.0, description="Umbral mínimo de similitud coseno")


class IndexRequest(BaseModel):
    source_type: str = Field(..., description="Tipo de fuente: 'obsidian_note', 'book_chunk', etc.")
    source_id: str = Field(..., description="Identificador único del recurso")
    source_title: str = Field(..., description="Título visible del recurso")
    content: str = Field(..., min_length=10, description="Contenido de texto a vectorizar")
    metadata: dict[str, Any] | None = None


@router.get("/status")
def get_vector_status(service: BusquedaSemantica):
    """Retorna el estado del almacén de vectores, cuántos fragmentos tiene indexados la cuenta y con qué modelos."""
    return service.get_stats()


@router.post("/init")
def initialize_vector_database(
    admin: Annotated[Usuario, Depends(requiere_admin)],
    service: BusquedaSemantica,
):
    """Inicializa el esquema y las tablas del índice de búsqueda; en local no hace falta y responde sin error."""
    try:
        return service.repo.inicializar()
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Error al inicializar el índice de búsqueda: {e!s}")


@router.post("/search")
def semantic_search(request: SearchRequest, service: BusquedaSemantica):
    """Ejecuta una búsqueda semántica por similitud de coseno sobre los fragmentos de la cuenta.

    Solo considera los indexados con el modelo de embeddings de la consulta, que la respuesta informa.
    """
    if not service.is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El índice de búsqueda no está disponible en este momento.",
        )
    results = service.search(
        query=request.query,
        limit=request.limit,
        source_type=request.source_type,
        min_similarity=request.min_similarity,
    )
    return {"query": request.query, "total_results": len(results), "matches": results, **service.detalle_del_embedding()}


@router.post("/index", status_code=status.HTTP_201_CREATED, dependencies=[SinCuentaCompartida])
def index_document(request: IndexRequest, service: BusquedaSemantica):
    """Genera embeddings para un documento y lo almacena a nombre de la cuenta."""
    if not service.is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El índice de búsqueda no está disponible en este momento.",
        )
    try:
        chunks_indexed = service.index_document(
            source_type=request.source_type,
            source_id=request.source_id,
            source_title=request.source_title,
            content=request.content,
            metadata=request.metadata,
        )
        return {
            "ok": True,
            "source_id": request.source_id,
            "source_title": request.source_title,
            "chunks_indexed": chunks_indexed,
            **service.detalle_del_embedding(),
        }
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Error durante la vectorización: {e!s}")


@router.post("/sync-catalog", dependencies=[SinCuentaCompartida])
def sync_catalog_to_vectors(db: Conexion, service: BusquedaSemantica):
    """Sincroniza e indexa los materiales y notas de la cuenta hacia el almacén de vectores."""
    if not service.is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El índice de búsqueda no está disponible en este momento.",
        )
    try:
        res = service.sync_catalog(db)
        msg = f"Indexación completada: {res['indexados']} indexados, {res['salteados']} salteados, {res['fallidos']} fallidos."
        return {
            "ok": True,
            "message": msg,
            **res,
        }
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Error al sincronizar catálogo: {e!s}")


class SelectionIndexItem(BaseModel):
    type: str = Field(..., description="Tipo de item: 'course', 'book' o 'material'")
    id: str = Field(..., description="Identificador numérico del curso, el libro o el material")


class SelectionIndexRequest(BaseModel):
    items: list[SelectionIndexItem] = Field(..., min_length=1, max_length=100, description="Lista de items seleccionados para indexar (1 a 100)")


@router.post("/index-book/{book_id}", dependencies=[SinCuentaCompartida])
def index_single_book(
    db: Conexion,
    service: BusquedaSemantica,
    book_id: int = Path(..., ge=1, description="ID numérico del libro"),
):
    """Indexa un libro de la cuenta hacia el almacén de vectores; uno ajeno responde 404 como uno inexistente."""
    if not service.is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El índice de búsqueda no está disponible en este momento.",
        )
    try:
        res = service.index_single_book(db, book_id)
        return {"ok": True, "message": f"Libro '{res['title']}' indexado con éxito.", **res}
    except FuenteNoEncontrada as e:
        raise no_encontrado(e.que, e.identificador) from None
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Error al indexar libro: {e!s}")


@router.post("/index-course/{course_id}", dependencies=[SinCuentaCompartida])
def index_single_course(
    db: Conexion,
    service: BusquedaSemantica,
    course_id: int = Path(..., ge=1, description="ID numérico del curso"),
):
    """Indexa un curso de la cuenta hacia el almacén de vectores; uno ajeno responde 404 como uno inexistente."""
    if not service.is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El índice de búsqueda no está disponible en este momento.",
        )
    try:
        res = service.index_single_course(db, course_id)
        return {"ok": True, "message": f"Curso '{res['title']}' indexado con éxito.", **res}
    except FuenteNoEncontrada as e:
        raise no_encontrado(e.que, e.identificador) from None
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Error al indexar curso: {e!s}")


@router.post("/index-selection", dependencies=[SinCuentaCompartida])
def index_selection(req: SelectionIndexRequest, db: Conexion, service: BusquedaSemantica):
    """Indexa un lote de cursos, libros y materiales de la cuenta; con uno ajeno no indexa nada y responde 404."""
    if not service.is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El índice de búsqueda no está disponible en este momento.",
        )
    try:
        items_dict = [it.model_dump() for it in req.items]
        res = service.index_selection(db, items_dict)
        return {"ok": True, "message": f"Se indexaron {res['total_indexed']} ítems con éxito ({res['total_chunks']} chunks).", **res}
    except FuenteNoEncontrada as e:
        raise no_encontrado(e.que, e.identificador) from None
    except ERRORES_AL_LEER_UN_SECRETO:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Error al indexar selección: {e!s}")

