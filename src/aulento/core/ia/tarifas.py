"""Tarifas conocidas de los modelos, en USD por millón de tokens. Un modelo que no figura no tiene costo estimado."""

from aulento.core.ia.tipos import ANTHROPIC, GEMINI, OPENAI, IANoDisponibleError

TARIFAS_POR_MILLON: dict[str, dict[str, dict[str, float]]] = {
    GEMINI: {
        "gemini-flash-lite-latest": {"input": 0.10, "output": 0.40},
        "gemini-3.5-flash-lite": {"input": 0.10, "output": 0.40},
        "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
        "gemini-flash-latest": {"input": 0.30, "output": 2.50},
        "gemini-3.8-flash": {"input": 0.75, "output": 3.75},
        "gemini-3.5-flash": {"input": 1.50, "output": 9.00},
        "gemini-pro-latest": {"input": 1.25, "output": 10.00},
        "gemini-3.1-pro": {"input": 2.00, "output": 12.00},
    },
    ANTHROPIC: {
        "claude-opus-5-5": {"input": 4.00, "output": 20.00},
        "claude-sonnet-5-5": {"input": 2.00, "output": 10.00},
        "claude-haiku-5-5": {"input": 0.10, "output": 0.50},
    },
    # Los precios de OpenAI no están verificados: su costo queda vacío
    OPENAI: {},
}


def costo_estimado(proveedor: str, modelo: str, tokens_entrada: int, tokens_salida: int) -> float | None:
    """Costo en USD de una llamada, o `None` si no se conoce la tarifa de ese modelo."""
    tarifa = TARIFAS_POR_MILLON.get(proveedor, {}).get(modelo)
    if tarifa is None:
        return None
    costo = tokens_entrada / 1_000_000.0 * tarifa["input"] + tokens_salida / 1_000_000.0 * tarifa["output"]
    return round(costo, 6)


def costo_de_un_error(error: IANoDisponibleError) -> float | None:
    """Costo de un pedido que terminó en error: cero si no consumió tokens; si consumió, el de la tarifa del modelo."""
    if not (error.tokens_entrada or error.tokens_salida):
        return 0.0
    return costo_estimado(error.proveedor or "", error.modelo or "", error.tokens_entrada, error.tokens_salida)
