"""Garantias 2 e 5 na camada de armazenamento."""

from __future__ import annotations

import asyncio

from residencial_aurora.storage import reservas, visitantes


async def test_duas_reservas_concorrentes_mesma_area_data():
    apartamentos = ["101", "102", "201", "202", "301", "302"]
    resultados = await asyncio.gather(
        *(reservas.criar(ap, "salao-de-festas", "2030-05-01") for ap in apartamentos)
    )
    sucessos = [ok for _, ok in resultados]
    assert sucessos.count(True) == 1
    assert not await reservas.esta_livre("salao-de-festas", "2030-05-01")


async def test_reserva_cancelada_libera_a_data():
    await reservas.criar("101", "quadra", "2030-05-02")
    ok, _ = await reservas.cancelar_por_area_data("101", "quadra", "2030-05-02")
    assert ok
    _, ok = await reservas.criar("202", "quadra", "2030-05-02")
    assert ok


async def test_cancelar_reserva_de_outro_apartamento_nao_revela_nada():
    await reservas.criar("302", "churrasqueira", "2030-05-03")
    ok_outro, msg_outro = await reservas.cancelar_por_area_data(
        "101", "churrasqueira", "2030-05-03"
    )
    ok_vazio, msg_vazio = await reservas.cancelar_por_area_data(
        "101", "churrasqueira", "2030-05-04"
    )
    assert not ok_outro and not ok_vazio
    assert msg_outro == msg_vazio
    assert not await reservas.esta_livre("churrasqueira", "2030-05-03")


async def test_visitantes_isolados_por_apartamento():
    await visitantes.autorizar("101", "Ana", "2030-05-05")
    await visitantes.autorizar("202", "Beto", "2030-05-05")
    assert await visitantes.listar_por_apartamento("101") == [
        {"nome": "Ana", "data": "2030-05-05"}
    ]
