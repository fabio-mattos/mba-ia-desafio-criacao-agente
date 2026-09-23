"""Garantia 4: a busca devolve um unico capitulo, nunca o documento inteiro."""

from __future__ import annotations

import pytest

from residencial_aurora.agents.tools import consultar_regulamento
from residencial_aurora.config import REGULAMENTO_MD
from residencial_aurora.regulamento import buscar


@pytest.mark.parametrize(
    ("pergunta", "capitulo"),
    [
        ("Posso ter cachorro no apartamento?", "Animais de estimação"),
        ("Qual o horario da piscina?", "Piscina"),
        ("Posso fazer obra de reforma no sabado?", "Obras e reformas"),
        ("Como funciona a mudanca?", "Mudanças"),
    ],
)
def test_busca_acha_capitulo_certo(pergunta, capitulo):
    assert capitulo in buscar(pergunta).titulo


async def test_tool_devolve_so_um_capitulo():
    resultado = await consultar_regulamento("Posso ter cachorro?")
    completo = REGULAMENTO_MD.read_text(encoding="utf-8")
    assert len(resultado["trecho"]) < len(completo) / 3
    assert resultado["trecho"].count("## Capítulo") == 1
