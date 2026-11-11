"""Capa única de proveedores de IA (ADR 009): pedido neutral, un adaptador por proveedor y la pasarela por cuenta.

Los llamadores arman un `Pedido` (`tipos.py`) y lo entregan a `PasarelaDeIA` (`pasarela.py`). Solo los
adaptadores (`gemini.py`, `anthropic.py`, `openai.py`) nombran la dirección de una API.
"""
