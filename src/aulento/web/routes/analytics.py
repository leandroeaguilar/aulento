"""Router FastAPI para analítica de tokens, costos estimados y gestión de doble API Key de Gemini."""

from fastapi import APIRouter, Query

from aulento.web.dependencies import SinCuentaCompartida, ClavesDeGemini, RepoRutas
from aulento.models.roadmap import (
    DualKeyConfig,
    DualKeyStatus,
    TokenLogItem,
    TokenUsageSummary,
)

router = APIRouter(tags=["Analytics & Config"])


@router.get("/api/analytics/tokens", response_model=TokenUsageSummary)
def get_token_usage_summary(
    repo: RepoRutas,
    days: int = Query(30, ge=1, le=365, description="Ventana de tiempo en días"),
):
    """Retorna las métricas de consumo de tokens y costos estimados en USD de la cuenta."""
    return repo.get_token_usage_summary(days=days)


@router.get("/api/analytics/logs", response_model=list[TokenLogItem])
def get_recent_api_logs(
    repo: RepoRutas,
    limit: int = Query(50, ge=1, le=500, description="Cantidad máxima de registros recientes"),
):
    """Retorna las transacciones recientes de API de la cuenta, con latencia y tokens."""
    return repo.get_recent_api_logs(limit=limit)


@router.get("/api/config/gemini-keys", response_model=DualKeyStatus)
def get_gemini_keys_status(pasarela: ClavesDeGemini):
    """Retorna si la cuenta cargó cada clave (con sus últimos cuatro caracteres), el tier activo y el modelo."""
    return pasarela.get_keys_status()


@router.post("/api/config/gemini-keys", response_model=DualKeyStatus, dependencies=[SinCuentaCompartida])
def update_gemini_keys_config(config: DualKeyConfig, pasarela: ClavesDeGemini):
    """Guarda para la cuenta la clave gratuita y la de pago (cifradas), el tier activo y el modelo preferido."""
    pasarela.save_keys_config(
        free_key=config.get_free_key(),
        paid_key=config.get_paid_key(),
        tier=config.active_tier,
    )
    if config.preferred_model and config.preferred_model.strip():
        pasarela.save_model(config.preferred_model)
    return pasarela.get_status()
