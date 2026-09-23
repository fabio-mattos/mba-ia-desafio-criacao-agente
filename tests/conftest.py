"""Isola cada teste em bancos SQLite temporarios, sem tocar em data/."""

from __future__ import annotations

import pytest

from residencial_aurora import runtime
from residencial_aurora.storage import db


@pytest.fixture(autouse=True)
def bancos_temporarios(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "CONDOMINIO_DB_PATH", tmp_path / "condominio.db")
    monkeypatch.setattr(runtime, "SESSOES_DB_PATH", tmp_path / "sessoes.db")
    runtime.obter_session_service.cache_clear()
    runtime.obter_runner.cache_clear()
    yield
    runtime.obter_session_service.cache_clear()
    runtime.obter_runner.cache_clear()
