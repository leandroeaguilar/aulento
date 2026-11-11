"""Punto de entrada para ejecución directa: python -m aulento."""

import sys

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from aulento.cli.app import cli

if __name__ == "__main__":
    cli()
