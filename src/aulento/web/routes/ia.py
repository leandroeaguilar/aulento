"""Router FastAPI para la configuración de los proveedores de IA de cada cuenta.

Permite ver el estado de cada proveedor (Gemini, Anthropic y OpenAI), elegir el proveedor activo,
guardar o quitar claves cifradas sin exponerlas completas, elegir modelos y probar la conexión.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from aulento.core.ia.tipos import PROVEEDORES
from aulento.web.dependencies import IADeLaCuenta, SinCuentaCompartida

router = APIRouter(prefix="/api/config/ia", tags=["IA & Providers"])


class ConfigIAPut(BaseModel):
    proveedor_activo: str | None = Field(None, description="Proveedor activo: gemini, anthropic o openai")
    proveedor: str | None = Field(None, description="Alias de proveedor_activo o destino del modelo")
    modelo: str | None = Field(None, description="Modelo a fijar para el proveedor indicado o activo")
    modelos: dict[str, str] | None = Field(None, description="Diccionario proveedor -> modelo a fijar")


class ClaveIAPut(BaseModel):
    clave: str | None = Field(None, description="Clave de API del proveedor")
    key: str | None = Field(None, description="Alias de clave")
    nivel: str | None = Field("free", description="Nivel para Gemini ('free' o 'paid')")


def _exigir_proveedor_valido(proveedor: str) -> str:
    prov = (proveedor or "").strip().lower()
    if prov not in PROVEEDORES:
        raise HTTPException(
            status_code=400,
            detail=f"Proveedor de IA inválido ({proveedor!r}): los disponibles son {', '.join(PROVEEDORES)}.",
        )
    return prov


@router.get("", response_model=dict[str, Any])
def get_ia_config(pasarela: IADeLaCuenta):
    """Retorna el estado de los tres proveedores para la cuenta (proveedor activo, pistas de claves y modelos)."""
    return pasarela.estado()


@router.put("", response_model=dict[str, Any], dependencies=[SinCuentaCompartida])
def update_ia_config(body: ConfigIAPut, pasarela: IADeLaCuenta):
    """Actualiza el proveedor activo y/o los modelos preferidos de la cuenta."""
    prov_activo = body.proveedor_activo or body.proveedor
    if prov_activo is not None and body.modelo is None:
        prov = _exigir_proveedor_valido(prov_activo)
        pasarela.fijar_proveedor(prov)

    if body.modelos is not None:
        for prov_nom, mod_nom in body.modelos.items():
            prov = _exigir_proveedor_valido(prov_nom)
            if not isinstance(mod_nom, str) or not mod_nom.strip():
                raise HTTPException(status_code=400, detail="El modelo no puede estar vacío.")
            pasarela.fijar_modelo(prov, mod_nom.strip())

    if body.modelo is not None:
        if not isinstance(body.modelo, str) or not body.modelo.strip():
            raise HTTPException(status_code=400, detail="El modelo no puede estar vacío.")
        dest_prov = _exigir_proveedor_valido(body.proveedor or pasarela.proveedor_activo())
        pasarela.fijar_modelo(dest_prov, body.modelo.strip())
        if body.proveedor_activo is not None:
            pasarela.fijar_proveedor(_exigir_proveedor_valido(body.proveedor_activo))

    return pasarela.estado()


@router.put("/{proveedor}/key", response_model=dict[str, Any], dependencies=[SinCuentaCompartida])
def save_provider_key(proveedor: str, body: ClaveIAPut, pasarela: IADeLaCuenta):
    """Guarda cifrada la clave de la cuenta para ese proveedor. En Gemini admite nivel 'free' o 'paid'."""
    prov = _exigir_proveedor_valido(proveedor)
    clave = body.clave or body.key
    if not clave or not isinstance(clave, str) or not clave.strip():
        raise HTTPException(status_code=400, detail="La clave no puede estar vacía.")

    nivel = (body.nivel or "free").strip().lower()
    if prov == "gemini" and nivel not in ("free", "paid"):
        raise HTTPException(status_code=400, detail="El nivel de clave de Gemini debe ser 'free' o 'paid'.")

    try:
        pasarela.guardar_clave(prov, clave.strip(), nivel=nivel)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return pasarela.estado()


@router.delete("/{proveedor}/key", response_model=dict[str, Any], dependencies=[SinCuentaCompartida])
def remove_provider_key(proveedor: str, pasarela: IADeLaCuenta, nivel: str | None = Query(None)):
    """Elimina la clave guardada para ese proveedor. En Gemini puede indicarse ?nivel=free o ?nivel=paid."""
    prov = _exigir_proveedor_valido(proveedor)
    if prov == "gemini" and nivel is not None and nivel not in ("free", "paid"):
        raise HTTPException(status_code=400, detail="El nivel de clave de Gemini debe ser 'free' o 'paid'.")

    try:
        pasarela.quitar_clave(prov, nivel=nivel)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return pasarela.estado()


@router.get("/{proveedor}/models", response_model=dict[str, Any])
def get_provider_models(proveedor: str, pasarela: IADeLaCuenta):
    """Consulta la lista viva de modelos disponibles para la clave de la cuenta con ese proveedor."""
    prov = _exigir_proveedor_valido(proveedor)
    modelos = pasarela.modelos(prov)
    return {"proveedor": prov, "modelos": modelos}


@router.post("/{proveedor}/test", response_model=dict[str, Any])
def test_provider_connection(proveedor: str, pasarela: IADeLaCuenta):
    """Prueba la conexión y credenciales de la cuenta con un pedido mínimo hacia el proveedor."""
    prov = _exigir_proveedor_valido(proveedor)
    return pasarela.probar(prov)
