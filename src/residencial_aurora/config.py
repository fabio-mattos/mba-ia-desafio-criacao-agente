"""Configuracao central do assistente: nomes fixos, caminhos e variaveis de ambiente."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

APP_NAME = "residencial-aurora"

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DADOS_DIR = BASE_DIR / "dados"
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

CONDOMINIO_DB_PATH = DATA_DIR / "condominio.db"
SESSOES_DB_PATH = DATA_DIR / "sessoes.db"

APARTAMENTOS_JSON = DADOS_DIR / "apartamentos.json"
AREAS_JSON = DADOS_DIR / "areas.json"
RESERVAS_JSON = DADOS_DIR / "reservas.json"
VISITANTES_JSON = DADOS_DIR / "visitantes.json"
REGULAMENTO_MD = DADOS_DIR / "regulamento.md"

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
