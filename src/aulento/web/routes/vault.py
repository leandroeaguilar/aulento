"""Router FastAPI del vault de la cuenta: notas, descarga completa, ubicación y generación de apuntes."""

import os
import tempfile
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from aulento.auth.dependencias import requiere_admin
from aulento.auth.modelos import Usuario
from aulento.config import dir_de_cuenta
from aulento.vault.carpetas import (
    MAXIMO_DE_CARPETAS_DEL_TUTOR,
    CarpetaInvalida,
    carpetas_del_vault,
    crear_carpeta,
    crear_carpetas_faltantes,
    fijar_carpetas_del_tutor,
)
from aulento.vault.cloud_notes import MaterialNoteRequest
from aulento.vault.models import VaultNote
from aulento.vault.reader import sembrar_notas_de_muestra
from aulento.vault.rutas import (
    MENSAJE_NOTA_NO_ENCONTRADA,
    CarpetaDeVaultInvalida,
    RutaFueraDelVaultError,
    escribir_zip_del_vault,
    estado_del_vault,
    fijar_vault_externo,
    quitar_vault_externo,
    relativa_al_vault,
    resolver_en_vault,
)
from aulento.vault.sop_course import CourseNoteRequest
from aulento.web.dependencies import (
    ApuntesDeCurso,
    ApuntesDeMateriales,
    Conexion,
    Cuenta,
    LectorDelVault,
    RepoCursos,
    ResumenSemanal,
    SinCuentaCompartida,
    VaultDeLaSesion,
    no_encontrado,
)

router = APIRouter(prefix="/api/vault", tags=["Vault"])


class UbicacionDelVault(BaseModel):
    """Qué vault usa la cuenta. `ruta` es la carpeta externa fijada; el vault propio no informa su ruta."""

    externo: bool
    ruta: str | None = None
    disponible: bool


class FijarUbicacionDelVault(BaseModel):
    ruta: str | None = Field(
        None, description="Carpeta existente de la máquina del servidor; null o vacío vuelve al vault propio"
    )


class CarpetaDelVault(BaseModel):
    ruta: str = Field(..., description="Ruta relativa al vault, con '/'")
    notas: int = Field(..., description="Notas .md que tiene, contando sus subcarpetas")
    del_tutor: bool = Field(..., description="El tutor lee esta carpeta")
    descripcion: str | None = Field(None, description="Para qué sirve la carpeta si es una de las recomendadas por defecto")


class CarpetasDelVault(BaseModel):
    """Carpetas del vault de la cuenta y cuáles lee el tutor; `faltan` son las del tutor que todavía no existen."""

    carpetas: list[CarpetaDelVault]
    del_tutor: list[str]
    faltan: list[str]
    recomendadas: list[str]
    descripciones: dict[str, str] = Field(
        default_factory=dict, description="Para qué sirve cada carpeta recomendada por defecto"
    )


class CrearCarpeta(BaseModel):
    ruta: str = Field(..., max_length=200, description="Carpeta a crear, relativa al vault (ej. '04 Knowledge/Redes')")


class ElegirCarpetasDelTutor(BaseModel):
    carpetas: list[Annotated[str, Field(max_length=200)]] = Field(
        ..., max_length=MAXIMO_DE_CARPETAS_DEL_TUTOR, description="Carpetas existentes del vault que lee el tutor"
    )


@router.get("/notes", response_model=list[VaultNote])
def list_vault_notes(
    reader: LectorDelVault,
    folder: str | None = Query(None, description="Filtro por carpeta: '04 Knowledge', '06 Raw', '02 MOCs'"),
    search: str | None = Query(None, description="Término de búsqueda"),
):
    """Retorna las notas del vault de la cuenta (solo lectura); una carpeta fuera del vault responde 404."""
    if search:
        notes = reader.search_notes(search)
        if folder:
            notes = [n for n in notes if n.folder == folder]
        return notes
    return reader.list_notes(folder=folder)


@router.get("/stats", response_model=dict[str, Any])
def get_vault_statistics(reader: LectorDelVault):
    """Retorna métricas del grafo de conocimiento del vault de la cuenta (conteo de notas, wikilinks, tags)."""
    return reader.get_vault_stats()


@router.get("/export.zip")
def export_vault_as_zip(vault: VaultDeLaSesion, usuario: Cuenta):
    """Descarga el vault completo de la cuenta como `.zip`; no incluye enlaces ni nada que resuelva fuera de él."""
    carpeta_cuenta = dir_de_cuenta(usuario.id)
    carpeta_cuenta.mkdir(parents=True, exist_ok=True)
    descriptor, nombre = tempfile.mkstemp(prefix="vault-", suffix=".zip", dir=carpeta_cuenta)
    os.close(descriptor)
    temporal = Path(nombre)
    try:
        escribir_zip_del_vault(vault, temporal)
    except BaseException:
        temporal.unlink(missing_ok=True)
        raise
    return FileResponse(
        temporal,
        media_type="application/zip",
        filename="vault.zip",
        background=BackgroundTask(temporal.unlink, missing_ok=True),
    )


@router.get("/location", response_model=UbicacionDelVault)
def get_vault_location(usuario: Cuenta, conn: Conexion):
    """Dice si la cuenta usa su vault propio o una carpeta externa, y si esa carpeta sigue existiendo."""
    return estado_del_vault(conn, usuario.id)


@router.put("/location", response_model=UbicacionDelVault, dependencies=[SinCuentaCompartida])
def set_vault_location(
    data: FijarUbicacionDelVault, administrador: Annotated[Usuario, Depends(requiere_admin)], conn: Conexion
):
    """Apunta el vault del administrador de la sesión a una carpeta existente del servidor, o lo devuelve al propio.

    Solo cambia el vault de quien lo pide; una cuenta común recibe 403 y una carpeta que no sirve, 400.
    """
    if data.ruta and data.ruta.strip():
        try:
            fijar_vault_externo(conn, administrador.id, data.ruta)
        except CarpetaDeVaultInvalida as e:
            raise HTTPException(status_code=400, detail=str(e)) from None
    else:
        quitar_vault_externo(conn, administrador.id)
    return estado_del_vault(conn, administrador.id)


@router.get("/folders", response_model=CarpetasDelVault)
def list_vault_folders(usuario: Cuenta, conn: Conexion, vault: VaultDeLaSesion):
    """Lista las carpetas del vault de la cuenta y marca las que lee el tutor."""
    return carpetas_del_vault(conn, usuario.id, vault)


@router.post("/folders", response_model=CarpetasDelVault, status_code=201, dependencies=[SinCuentaCompartida])
def create_vault_folder(data: CrearCarpeta, usuario: Cuenta, conn: Conexion, vault: VaultDeLaSesion):
    """Crea una carpeta (y las que falten arriba) dentro del vault de la cuenta; sirve también en un servidor."""
    try:
        crear_carpeta(vault, data.ruta)
    except (CarpetaInvalida, RutaFueraDelVaultError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    return carpetas_del_vault(conn, usuario.id, vault)


@router.post("/folders/create-missing", response_model=CarpetasDelVault, dependencies=[SinCuentaCompartida])
def create_missing_vault_folders(usuario: Cuenta, conn: Conexion, vault: VaultDeLaSesion):
    """Crea en el vault de la cuenta las carpetas del tutor que todavía no existen (propio o externo)."""
    try:
        crear_carpetas_faltantes(conn, usuario.id, vault)
    except (CarpetaInvalida, RutaFueraDelVaultError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    return carpetas_del_vault(conn, usuario.id, vault)


@router.put("/tutor-folders", response_model=CarpetasDelVault, dependencies=[SinCuentaCompartida])
def set_tutor_folders(data: ElegirCarpetasDelTutor, usuario: Cuenta, conn: Conexion, vault: VaultDeLaSesion):
    """Elige qué carpetas del vault leen el tutor, los exámenes y la cosecha; tienen que existir."""
    try:
        fijar_carpetas_del_tutor(conn, usuario.id, vault, data.carpetas)
    except (CarpetaInvalida, RutaFueraDelVaultError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    return carpetas_del_vault(conn, usuario.id, vault)


@router.post("/sample-notes", dependencies=[SinCuentaCompartida])
def seed_sample_notes(vault: VaultDeLaSesion):
    """Copia al vault de la cuenta las notas de muestra que todavía no tiene; solo ocurre cuando la cuenta lo pide."""
    return {"status": "ok", "created": sembrar_notas_de_muestra(vault)}


@router.get("/notes/materials")
def list_materials_for_notes(generator: ApuntesDeMateriales):
    """Lista los materiales subidos por la cuenta con los que se puede generar un apunte."""
    return generator.list_available_materials()


@router.get("/notes/{note_id:path}/download")
def download_vault_note(
    note_id: str,
    vault: VaultDeLaSesion,
    reader: LectorDelVault,
):
    """Descarga una nota individual del vault de la cuenta como archivo .md tal cual está guardado."""
    ruta = None
    candidata = resolver_en_vault(vault, note_id)
    if candidata.is_file():
        ruta = candidata
    elif candidata.with_suffix(".md").is_file():
        ruta = candidata.with_suffix(".md")

    if ruta is None:
        note = reader.get_note(note_id)
        if note:
            ruta = resolver_en_vault(vault, note.path)

    if not ruta or not ruta.is_file() or ruta.suffix.lower() != ".md":
        raise HTTPException(status_code=404, detail=MENSAJE_NOTA_NO_ENCONTRADA)

    return FileResponse(
        ruta,
        media_type="text/markdown; charset=utf-8",
        filename=ruta.name,
    )


@router.get("/notes/{note_id:path}", response_model=VaultNote)
def get_single_vault_note(note_id: str, reader: LectorDelVault):
    """Retorna una nota del vault de la cuenta; una que no existe o que apunta fuera del vault responde 404."""
    note = reader.get_note(note_id)
    if not note:
        raise HTTPException(status_code=404, detail=MENSAJE_NOTA_NO_ENCONTRADA)
    return note


@router.post("/notes/from-material", dependencies=[SinCuentaCompartida])
def generate_note_from_material(
    req: MaterialNoteRequest,
    generator: ApuntesDeMateriales,
    cursos: RepoCursos,
    save_to_vault: bool | None = Query(None, description="Si es True, escribe el archivo en el Vault (anula req.save_to_vault)"),
):
    """Sintetiza un apunte canónico a partir de un material de la cuenta y, si se pide, lo guarda en su vault.

    Un material o un curso de otra cuenta responde 404, igual que uno inexistente.
    """
    if req.course_id is not None and not cursos.get_by_id(req.course_id):
        raise no_encontrado("Curso", req.course_id)
    try:
        note_data = generator.generate_note(
            material_id=req.material_id,
            course_id=req.course_id,
            topic=req.topic,
            custom_notes=req.custom_notes,
        )
        should_save = save_to_vault if save_to_vault is not None else req.save_to_vault
        if should_save:
            path = generator.save_note_to_vault(
                material_id=req.material_id,
                course_id=req.course_id,
                topic=req.topic,
                custom_notes=req.custom_notes,
            )
            note_data["saved_path"] = relativa_al_vault(generator.vault_path, path)
            note_data["status"] = "saved"
        else:
            note_data["status"] = "preview"
        return note_data
    except RutaFueraDelVaultError:
        raise
    except ValueError as e:
        status_code = 404 if ("no existe" in str(e).lower() or "no se encontró" in str(e).lower()) else 400
        raise HTTPException(status_code=status_code, detail=str(e))


@router.post("/notes/course-template")
def generate_course_note_template(
    req: CourseNoteRequest,
    generator: ApuntesDeCurso,
    cursos: RepoCursos,
    save_to_vault: bool = Query(False, description="Si es True, escribe el archivo en el Vault"),
):
    """Genera la plantilla oficial Markdown de apunte y, si se pide, la guarda en 04 Knowledge/Cursos/ del vault de la cuenta."""
    if not cursos.get_by_id(req.course_id):
        raise no_encontrado("Curso", req.course_id)
    try:
        note_data = generator.generate_note_markdown(req)
        if save_to_vault:
            path = generator.save_note_to_vault(req)
            note_data["saved_path"] = relativa_al_vault(generator.vault_path, path)
        return note_data
    except RutaFueraDelVaultError:
        raise
    except ValueError as e:
        status_code = 404 if "no existe" in str(e).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(e))


@router.get("/digest/weekly")
def get_weekly_digest(
    exporter: ResumenSemanal,
    week_label: str | None = Query(None, description="Semana ISO, ej. 2026-W39"),
):
    """Compila las métricas de estudio de la cuenta y genera el Weekly Digest en Markdown para Obsidian."""
    return exporter.build_digest(week_label)


@router.post("/digest/weekly/save")
def save_weekly_digest(
    exporter: ResumenSemanal,
    week_label: str | None = Query(None, description="Semana ISO, ej. 2026-W39"),
):
    """Guarda el Weekly Digest de la cuenta en 02 MOCs/ de su vault."""
    try:
        saved_file = exporter.save_digest_to_vault(week_label)
        relativa = relativa_al_vault(exporter.vault_path, saved_file)
        return {
            "status": "saved",
            "file_path": relativa,
            "saved_path": relativa,
            "filename": saved_file.name,
        }
    except RutaFueraDelVaultError:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
