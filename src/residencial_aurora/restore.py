"""Restaura reservas, visitantes e sessoes para o estado inicial de dados/.

Uso: uv run python -m residencial_aurora.restore

Apaga tambem as sessoes (data/sessoes.db): restaurar o condominio para o
estado inicial dos arquivos em dados/ so faz sentido comecando as conversas
do zero tambem, e assim cada rodada de testes parte de um estado limpo e
previsivel.
"""

from __future__ import annotations

import asyncio
import json

from .config import RESERVAS_JSON, SESSOES_DB_PATH, VISITANTES_JSON
from .storage import reservas as reservas_store
from .storage import visitantes as visitantes_store
from .storage.db import resetar_banco


async def _restaurar() -> None:
    resetar_banco()
    for suffix in ("", "-wal", "-shm"):
        path = SESSOES_DB_PATH.parent / (SESSOES_DB_PATH.name + suffix)
        path.unlink(missing_ok=True)

    reservas_iniciais = json.loads(RESERVAS_JSON.read_text(encoding="utf-8"))
    visitantes_iniciais = json.loads(VISITANTES_JSON.read_text(encoding="utf-8"))
    await reservas_store.semear(reservas_iniciais)
    await visitantes_store.semear(visitantes_iniciais)

    print(
        f"Restaurado: {len(reservas_iniciais)} reservas,"
        f" {len(visitantes_iniciais)} visitantes, sessoes limpas."
    )


def main() -> None:
    asyncio.run(_restaurar())


if __name__ == "__main__":
    main()
