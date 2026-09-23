"""Mapeia session_id -> apartamento, para as rotas que so recebem o session_id.

O apartamento e definido uma unica vez, na criacao da sessao (Garantia 2), e
gravado aqui junto com o registro da sessao no ADK. As tools nunca leem esta
tabela: elas leem o apartamento do state da sessao do ADK (ver agents/tools.py).
Esta tabela existe so para a camada HTTP resolver qual `user_id` do ADK
corresponde a um `session_id`, sem depender do schema interno do ADK.
"""

from __future__ import annotations

import time

from .db import conectar


async def registrar(session_id: str, apartamento: str) -> None:
    async with conectar() as db:
        await db.execute(
            "INSERT INTO sessao_apartamento (session_id, apartamento, criada_em)"
            " VALUES (?, ?, ?)",
            (session_id, apartamento, time.time()),
        )
        await db.commit()


async def obter_apartamento(session_id: str) -> str | None:
    async with conectar() as db:
        async with db.execute(
            "SELECT apartamento FROM sessao_apartamento WHERE session_id = ?",
            (session_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return row["apartamento"] if row else None
