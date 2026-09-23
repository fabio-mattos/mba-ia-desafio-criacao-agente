"""Conexao com o banco de dados do condominio (reservas, visitantes, sessoes).

Cada operacao abre e fecha sua propria conexao aiosqlite, com busy_timeout
generoso: isso permite que duas requisicoes concorrentes (ver Garantia 5)
serializem no proprio SQLite em vez de falhar com "database is locked".

O schema e o modo WAL sao aplicados uma unica vez por arquivo, de forma
sincrona, antes da primeira conexao assincrona: trocar o journal_mode ou
rodar o DDL em duas conexoes ao mesmo tempo nao respeita o busy_timeout e
falha com "database is locked" justamente na primeira rajada concorrente.
"""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

from ..config import CONDOMINIO_DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS reservas (
    codigo TEXT PRIMARY KEY,
    apartamento TEXT NOT NULL,
    area TEXT NOT NULL,
    data TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ativa',
    criada_em REAL NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_reservas_area_data_ativa
    ON reservas(area, data)
    WHERE status = 'ativa';

CREATE TABLE IF NOT EXISTS visitantes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    apartamento TEXT NOT NULL,
    nome TEXT NOT NULL,
    data TEXT NOT NULL,
    criado_em REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sessao_apartamento (
    session_id TEXT PRIMARY KEY,
    apartamento TEXT NOT NULL,
    criada_em REAL NOT NULL
);
"""


_inicializados: set[Path] = set()


def _inicializar(path: Path) -> None:
    # Sincrono e sem await: nenhuma outra corrotina roda no meio.
    if path in _inicializados and path.exists():
        return
    with sqlite3.connect(path, timeout=5.0) as db:
        db.execute("PRAGMA journal_mode = WAL")
        db.executescript(SCHEMA)
    _inicializados.add(path)


@asynccontextmanager
async def conectar() -> AsyncIterator[aiosqlite.Connection]:
    _inicializar(CONDOMINIO_DB_PATH)
    async with aiosqlite.connect(CONDOMINIO_DB_PATH, timeout=5.0) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA busy_timeout = 5000")
        yield db


def resetar_banco() -> None:
    """Apaga o arquivo do banco. Usado apenas pelo comando de restauracao."""
    for suffix in ("", "-wal", "-shm"):
        path = CONDOMINIO_DB_PATH.parent / (CONDOMINIO_DB_PATH.name + suffix)
        path.unlink(missing_ok=True)
    _inicializados.discard(CONDOMINIO_DB_PATH)
    _inicializar(CONDOMINIO_DB_PATH)
