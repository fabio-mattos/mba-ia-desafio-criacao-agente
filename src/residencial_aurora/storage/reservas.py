"""Leitura e gravacao de reservas.

A exclusividade de "uma reserva por area/data" (regra de negocio 1 e
Garantia 5) e garantida pelo indice unico parcial `idx_reservas_area_data_ativa`
(ver db.py), verificado pelo proprio SQLite no instante do INSERT: duas
gravacoes concorrentes para a mesma area e data nunca coexistem, porque a
segunda sempre esbarra no indice, mesmo que ambas tenham conferido a agenda
livre antes.
"""

from __future__ import annotations

import time
import uuid

import aiosqlite

from .db import conectar


def _gerar_codigo() -> str:
    return f"RSV-{uuid.uuid4().hex[:8].upper()}"


async def esta_livre(area_id: str, data: str) -> bool:
    async with conectar() as db:
        async with db.execute(
            "SELECT 1 FROM reservas WHERE area = ? AND data = ? AND status = 'ativa'",
            (area_id, data),
        ) as cursor:
            row = await cursor.fetchone()
            return row is None


async def listar_ativas_por_apartamento(apartamento: str) -> list[dict]:
    async with conectar() as db:
        rows = await db.execute_fetchall(
            "SELECT codigo, area, data FROM reservas"
            " WHERE apartamento = ? AND status = 'ativa'"
            " ORDER BY data",
            (apartamento,),
        )
        return [dict(row) for row in rows]


async def criar(apartamento: str, area_id: str, data: str) -> tuple[str | None, bool]:
    """Tenta gravar uma nova reserva. Retorna (codigo, sucesso)."""
    codigo = _gerar_codigo()
    try:
        async with conectar() as db:
            await db.execute(
                "INSERT INTO reservas (codigo, apartamento, area, data, status, criada_em)"
                " VALUES (?, ?, ?, ?, 'ativa', ?)",
                (codigo, apartamento, area_id, data, time.time()),
            )
            await db.commit()
        return codigo, True
    except aiosqlite.IntegrityError:
        return None, False


async def cancelar_por_area_data(
    apartamento: str, area_id: str, data: str
) -> tuple[bool, str]:
    async with conectar() as db:
        async with db.execute(
            "SELECT apartamento FROM reservas"
            " WHERE area = ? AND data = ? AND status = 'ativa'",
            (area_id, data),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None or row["apartamento"] != apartamento:
            return False, "Nao ha reserva ativa dessa area nessa data para o seu apartamento."
        await db.execute(
            "UPDATE reservas SET status = 'cancelada'"
            " WHERE area = ? AND data = ? AND status = 'ativa'",
            (area_id, data),
        )
        await db.commit()
        return True, "Reserva cancelada."


async def cancelar_por_codigo(apartamento: str, codigo: str) -> tuple[bool, str]:
    async with conectar() as db:
        async with db.execute(
            "SELECT apartamento FROM reservas WHERE codigo = ? AND status = 'ativa'",
            (codigo,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None or row["apartamento"] != apartamento:
            return False, "Nao ha reserva ativa com esse codigo para o seu apartamento."
        await db.execute(
            "UPDATE reservas SET status = 'cancelada' WHERE codigo = ?", (codigo,)
        )
        await db.commit()
        return True, "Reserva cancelada."


async def semear(reservas_iniciais: list[dict]) -> None:
    async with conectar() as db:
        for r in reservas_iniciais:
            await db.execute(
                "INSERT INTO reservas (codigo, apartamento, area, data, status, criada_em)"
                " VALUES (?, ?, ?, ?, 'ativa', ?)",
                (r["codigo"], r["apartamento"], r["area"], r["data"], time.time()),
            )
        await db.commit()
