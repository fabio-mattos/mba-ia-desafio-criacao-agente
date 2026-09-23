"""Acesso somente-leitura aos dados fixos do condominio (dados/*.json).

Estes arquivos nunca sao alterados pelo assistente: apartamentos e areas sao
cadastro de referencia. Reservas e visitantes tem seu proprio armazenamento
(ver storage/), semeado a partir dos JSON pelo comando de restauracao.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

from .config import AREAS_JSON


@dataclass(frozen=True)
class Area:
    id: str
    nome: str
    taxa: float

    @property
    def gera_cobranca(self) -> bool:
        return self.taxa > 0


@lru_cache(maxsize=1)
def listar_areas() -> list[Area]:
    dados = json.loads(AREAS_JSON.read_text(encoding="utf-8"))
    return [Area(id=a["id"], nome=a["nome"], taxa=float(a["taxa"])) for a in dados]


def obter_area(area_id: str) -> Area | None:
    for area in listar_areas():
        if area.id == area_id:
            return area
    return None
