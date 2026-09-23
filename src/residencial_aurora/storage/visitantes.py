"""Leitura e gravacao de autorizacoes de visitantes."""

from __future__ import annotations

import time

from .db import conectar


async def listar_por_apartamento(apartamento: str) -> list[dict]:
    async with conectar() as db:
        rows = await db.execute_fetchall(
            "SELECT nome, data FROM visitantes WHERE apartamento = ? ORDER BY data",
            (apartamento,),
        )
        return [dict(row) for row in rows]


async def autorizar(apartamento: str, nome: str, data: str) -> None:
    async with conectar() as db:
        await db.execute(
            "INSERT INTO visitantes (apartamento, nome, data, criado_em) VALUES (?, ?, ?, ?)",
            (apartamento, nome, data, time.time()),
        )
        await db.commit()


async def semear(visitantes_iniciais: list[dict]) -> None:
    async with conectar() as db:
        for v in visitantes_iniciais:
            await db.execute(
                "INSERT INTO visitantes (apartamento, nome, data, criado_em) VALUES (?, ?, ?, ?)",
                (v["apartamento"], v["nome"], v["data"], time.time()),
            )
        await db.commit()
