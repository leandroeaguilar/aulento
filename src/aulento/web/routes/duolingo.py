"""Router para la integración y sincronización de métricas de Duolingo, con el usuario de cada cuenta."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from aulento.connectors.duolingo import (
    DuolingoProfile,
    DuolingoSinConfigurar,
    DuolingoSyncResult,
)
from aulento.web.dependencies import DuolingoDeLaCuenta, SinCuentaCompartida

router = APIRouter(prefix="/api/duolingo", tags=["Duolingo"])


class DuolingoSyncRequest(BaseModel):
    username: str | None = Field(None, max_length=100, description="Si se indica, pasa a ser el usuario de la cuenta")


class DuolingoConfig(BaseModel):
    username: str | None = Field(None, max_length=100, description="Usuario público en Duolingo; vacío lo quita")


@router.get("/config", response_model=DuolingoConfig)
def get_duolingo_config(client: DuolingoDeLaCuenta):
    """Retorna el usuario de Duolingo configurado para la cuenta, o null si no hay ninguno."""
    return DuolingoConfig(username=client.usuario_configurado())


@router.put("/config", response_model=DuolingoConfig, dependencies=[SinCuentaCompartida])
def set_duolingo_config(config: DuolingoConfig, client: DuolingoDeLaCuenta):
    """Fija el usuario de Duolingo de la cuenta; vacío o null lo quita junto con su caché."""
    return DuolingoConfig(username=client.fijar_usuario(config.username))


@router.get("/profile", response_model=DuolingoProfile)
def get_duolingo_profile(
    client: DuolingoDeLaCuenta,
    username: str | None = Query(None, max_length=100, description="Usuario a consultar; por defecto, el de la cuenta"),
):
    """Obtiene el perfil de Duolingo (racha, XP, curso actual) desde la API o la caché de la cuenta."""
    try:
        return client.get_profile(username=username)
    except DuolingoSinConfigurar as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/sync", response_model=DuolingoSyncResult, dependencies=[SinCuentaCompartida])
def sync_duolingo(client: DuolingoDeLaCuenta, request: DuolingoSyncRequest = DuolingoSyncRequest()):
    """Fuerza la sincronización en vivo con Duolingo y actualiza la caché de la cuenta."""
    return client.sync(username=request.username)
