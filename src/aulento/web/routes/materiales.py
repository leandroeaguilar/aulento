"""Router de los materiales que cada cuenta sube desde la PC (048): subir, listar, leer y borrar."""

import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from aulento.core.knowledge_rag import TIPO_DE_FUENTE_MATERIAL, KnowledgeRAGService
from aulento.core.materiales import (
    AlmacenDeMateriales,
    ErrorDeMaterial,
    MaterialNoEncontrado,
    MaterialRepetido,
)
from aulento.web.dependencies import (
    BusquedaSemantica,
    Materiales,
    SinCuentaCompartida,
    no_encontrado,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/materiales", tags=["Materiales"])

CAMPO_DEL_ARCHIVO = "archivo"
# Lo que suma el formulario alrededor del archivo: separadores y cabeceras de la parte
MARGEN_DEL_FORMULARIO = 64 * 1024
BYTES_POR_LECTURA = 64 * 1024
MAX_CARACTERES_PARA_MOSTRAR = 200_000


class Material(BaseModel):
    id: int
    nombre: str
    extension: str
    tipo_mime: str
    bytes: int
    caracteres: int
    creado_en: str


class MaterialSubido(Material):
    indexado: bool


class MaterialConTexto(Material):
    texto: str
    texto_cortado: bool


class UsoDelEspacio(BaseModel):
    usado: int
    tope: int
    libre: int


class ListaDeMateriales(BaseModel):
    materiales: list[Material]
    uso: UsoDelEspacio


class _CuerpoDemasiadoGrande(Exception):
    """El pedido pasó el tope antes de terminar de llegar."""


async def _cuerpo_acotado(request: Request, tope: int) -> AsyncIterator[bytes]:
    """El cuerpo del pedido por bloques; corta apenas pasa `tope` bytes, sin leer el resto."""
    leidos = 0
    async for bloque in request.stream():
        leidos += len(bloque)
        if leidos > tope:
            raise _CuerpoDemasiadoGrande
        yield bloque


def _rechazo(error: ErrorDeMaterial) -> HTTPException:
    return HTTPException(status_code=error.codigo, detail=str(error))


async def _leer_archivo(request: Request, almacen: AlmacenDeMateriales) -> tuple[str | None, bytes]:
    """Nombre y contenido del archivo del formulario, sin aceptar más de lo que le entra a la cuenta."""
    limite = await run_in_threadpool(almacen.limite_de_subida)
    tope_del_cuerpo = limite + MARGEN_DEL_FORMULARIO
    declarado = request.headers.get("content-length", "")
    if declarado.isdigit() and int(declarado) > tope_del_cuerpo:
        raise _rechazo(await run_in_threadpool(almacen.error_de_tope))
    if not request.headers.get("content-type", "").startswith("multipart/form-data"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"El archivo se manda en el campo «{CAMPO_DEL_ARCHIVO}» de un formulario multipart/form-data.",
        )

    lector = MultiPartParser(request.headers, _cuerpo_acotado(request, tope_del_cuerpo), max_files=1, max_fields=1)
    try:
        formulario = await lector.parse()
    except _CuerpoDemasiadoGrande:
        raise _rechazo(await run_in_threadpool(almacen.error_de_tope)) from None
    except MultiPartException as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Formulario inválido: {error.message}") from None

    try:
        archivo = formulario.get(CAMPO_DEL_ARCHIVO)
        if not isinstance(archivo, UploadFile):
            raise HTTPException(
                status_code=422,
                detail=f"Falta el archivo en el campo «{CAMPO_DEL_ARCHIVO}».",
            )
        datos = bytearray()
        while bloque := await archivo.read(BYTES_POR_LECTURA):
            datos += bloque
            if len(datos) > limite:
                raise _rechazo(await run_in_threadpool(almacen.error_de_tope))
        return archivo.filename, bytes(datos)
    finally:
        await formulario.close()


def _indexar(busqueda: KnowledgeRAGService, almacen: AlmacenDeMateriales, material: dict[str, Any]) -> bool:
    """Indexa el texto completo en pgvector si está disponible; un fallo queda en el log y no rompe la subida."""
    try:
        if not busqueda.is_ready():
            return False
        busqueda.index_single_material(material["id"], almacen)
        return True
    except Exception:
        logger.warning("No se pudo indexar el material %s en pgvector.", material["id"], exc_info=True)
        return False


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=MaterialSubido,
    dependencies=[SinCuentaCompartida],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": [CAMPO_DEL_ARCHIVO],
                        "properties": {
                            CAMPO_DEL_ARCHIVO: {
                                "type": "string",
                                "format": "binary",
                                "description": "Archivo .pdf, .md, .markdown o .txt de hasta 25 MB.",
                            }
                        },
                    }
                }
            },
        }
    },
    responses={
        409: {"description": "La cuenta ya tiene un material con el mismo contenido; se devuelve en `material`."},
        413: {"description": "El archivo pasa los 25 MB o no entra en los 200 MB de la cuenta."},
        415: {"description": "El archivo no es un PDF, Markdown o texto."},
        422: {"description": "El archivo está vacío, o es un PDF sin texto, cifrado o dañado."},
    },
)
async def subir_material(request: Request, almacen: Materiales, busqueda: BusquedaSemantica):
    """Guarda un material de la cuenta con su texto completo y, si pgvector está disponible, lo indexa.

    Deja de leer el cuerpo apenas pasa el tope del archivo o el espacio libre de la cuenta.
    """
    nombre, datos = await _leer_archivo(request, almacen)
    try:
        material = await run_in_threadpool(almacen.guardar, nombre, datos)
    except MaterialRepetido as error:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT, content={"detail": str(error), "material": error.material}
        )
    except ErrorDeMaterial as error:
        raise _rechazo(error) from None
    indexado = await run_in_threadpool(_indexar, busqueda, almacen, material)
    return {**material, "indexado": indexado}


@router.get("", response_model=ListaDeMateriales)
def listar_materiales(almacen: Materiales):
    """Los materiales de la cuenta, del más nuevo al más viejo, con el espacio usado y el tope."""
    return {"materiales": almacen.listar(), "uso": almacen.uso()}


@router.get("/{material_id}", response_model=MaterialConTexto)
def leer_material(material_id: int, almacen: Materiales):
    """Los datos y el texto de un material de la cuenta, cortado para mostrar si es muy largo."""
    try:
        material = almacen.obtener(material_id)
    except MaterialNoEncontrado:
        raise no_encontrado("Material", material_id) from None
    texto = material["texto"]
    return {
        **material,
        "texto": texto[:MAX_CARACTERES_PARA_MOSTRAR],
        "texto_cortado": len(texto) > MAX_CARACTERES_PARA_MOSTRAR,
    }


@router.delete("/{material_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[SinCuentaCompartida])
def borrar_material(material_id: int, almacen: Materiales, busqueda: BusquedaSemantica):
    """Borra un material de la cuenta: su archivo, su texto y sus fragmentos en pgvector."""
    try:
        almacen.obtener(material_id, con_texto=False)
    except MaterialNoEncontrado:
        raise no_encontrado("Material", material_id) from None
    # Primero los fragmentos: si pgvector falla, el material sigue ahí y se puede volver a intentar
    try:
        if busqueda.is_ready():
            busqueda.repo.delete_by_source(TIPO_DE_FUENTE_MATERIAL, str(material_id))
    except Exception:
        logger.warning("No se pudieron borrar los fragmentos del material %s.", material_id, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudieron borrar los fragmentos del material en la base vectorial. Probá de nuevo en un rato.",
        ) from None
    try:
        almacen.borrar(material_id)
    except MaterialNoEncontrado:
        raise no_encontrado("Material", material_id) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
