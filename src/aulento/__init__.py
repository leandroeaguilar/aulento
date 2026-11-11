"""Aulento - Sistema Maestro de Estudio Inteligente (Local First)."""

# Primero que nada: las variables con el nombre anterior del producto se adoptan antes de que otro módulo lea
# el entorno (ADR 021)
from aulento._compat import adoptar_variables_viejas

adoptar_variables_viejas()

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

__version__ = "0.1.0"
