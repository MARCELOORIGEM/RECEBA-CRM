"""Ponto de entrada da API — mantido para `uvicorn server:app`.

A implementação está em `app/`, dividida por domínio. A versão anterior era um
único arquivo de 612 linhas com models, rotas, seed e config misturados.
"""
from app.main import app

__all__ = ["app"]
