"""Nombre anterior de Aulento (ADR 021): reenvía `python -m study_engine` y el comando `study-engine` a `aulento`.

Existe para no romper las configuraciones MCP locales que ya arrancan `python -m study_engine … mcp serve`.
Se retira en una feature posterior a la 069.
"""

import sys

AVISO = "Study Engine ahora se llama Aulento: usá `aulento` o `python -m aulento`. Este nombre dejará de funcionar."


def main() -> None:
    """Avisa por stderr (stdout es el transporte de MCP por stdio) y corre la CLI de Aulento."""
    from aulento.__main__ import (
        cli,  # en Windows deja stdout y stderr en UTF-8 antes del aviso
    )

    print(AVISO, file=sys.stderr)

    cli(prog_name="aulento")
