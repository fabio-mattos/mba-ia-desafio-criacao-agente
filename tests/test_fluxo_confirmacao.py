"""Fluxo de confirmacao completo pela API, com um modelo roteirizado no lugar do Gemini.

Os agentes, o Runner, a sessao em SQLite e as tools sao os de verdade; so o
modelo e trocado por `ModeloRoteirizado`, que sempre transfere para o
especialista de reservas e pede `reservar_area` com a data da mensagem. Assim
da para conferir sem cota do Gemini a parte que o modelo nao decide: pedido
de confirmacao, negar, aprovar, 409, retomada depois de "reiniciar" a API e
duas aprovacoes simultaneas (passos 7, 8, 13 e 14 do enunciado).
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncGenerator

import httpx
import pytest
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from residencial_aurora import runtime
from residencial_aurora.agents import especialistas
from residencial_aurora.api import app

DATA = re.compile(r"\d{4}-\d{2}-\d{2}")


class ModeloRoteirizado(BaseLlm):
    papel: str

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        del stream
        if self.papel == "orquestrador":
            parte = types.Part(
                function_call=types.FunctionCall(
                    name="transfer_to_agent",
                    args={"agent_name": "especialista_reservas"},
                )
            )
        elif any(p.function_response for p in llm_request.contents[-1].parts or []):
            parte = types.Part(text="Pronto.")
        else:
            texto = next(
                p.text
                for c in reversed(llm_request.contents)
                for p in c.parts or []
                if p.text and "Reserve" in p.text
            )
            parte = types.Part(
                function_call=types.FunctionCall(
                    name="reservar_area",
                    args={"area_id": "salao-de-festas", "data": DATA.search(texto)[0]},
                )
            )
        yield LlmResponse(content=types.Content(role="model", parts=[parte]))


@pytest.fixture(autouse=True)
def modelo_roteirizado(monkeypatch):
    monkeypatch.setattr(
        especialistas.orquestrador_principal, "model", ModeloRoteirizado(model="fake", papel="orquestrador")
    )
    monkeypatch.setattr(
        especialistas.especialista_reservas, "model", ModeloRoteirizado(model="fake", papel="reservas")
    )


@pytest.fixture
async def cliente():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _sessao_com_pedido(client: httpx.AsyncClient, apartamento: str, data: str):
    session_id = (await client.post("/sessoes", json={"apartamento": apartamento})).json()[
        "session_id"
    ]
    resposta = await client.post(
        f"/sessoes/{session_id}/mensagens",
        json={"texto": f"Reserve o salão de festas para {data}."},
    )
    assert resposta.status_code == 200
    pendentes = resposta.json()["confirmacoes_pendentes"]
    assert len(pendentes) == 1
    assert pendentes[0]["detalhes"] == {"area_id": "salao-de-festas", "data": data}
    return session_id, pendentes[0]["id"]


async def _salao(client: httpx.AsyncClient, apartamento: str, data: str) -> list[dict]:
    reservas = (await client.get(f"/apartamentos/{apartamento}/reservas")).json()
    return [r for r in reservas if r["area"] == "salao-de-festas" and r["data"] == data]


async def test_negar_nao_grava_e_aprovar_grava_uma_vez(cliente):
    sessao, pedido = await _sessao_com_pedido(cliente, "101", "2030-04-20")
    assert await _salao(cliente, "101", "2030-04-20") == []

    resposta = await cliente.post(
        f"/sessoes/{sessao}/confirmacoes", json={"id": pedido, "confirmado": False}
    )
    assert resposta.status_code == 200
    assert resposta.json()["confirmacoes_pendentes"] == []
    assert await _salao(cliente, "101", "2030-04-20") == []

    sessao, pedido = await _sessao_com_pedido(cliente, "101", "2030-04-20")
    resposta = await cliente.post(
        f"/sessoes/{sessao}/confirmacoes", json={"id": pedido, "confirmado": True}
    )
    assert resposta.status_code == 200
    assert len(await _salao(cliente, "101", "2030-04-20")) == 1

    repetida = await cliente.post(
        f"/sessoes/{sessao}/confirmacoes", json={"id": pedido, "confirmado": True}
    )
    assert repetida.status_code == 409
    assert len(await _salao(cliente, "101", "2030-04-20")) == 1


async def test_aprovar_depois_de_reiniciar_executa_a_acao(cliente):
    sessao, pedido = await _sessao_com_pedido(cliente, "101", "2030-04-27")
    eventos_antes = (await cliente.get(f"/sessoes/{sessao}/eventos")).json()

    # "Reinicio": descarta o Runner e o servico de sessao em memoria; so o
    # que esta em disco (data/sessoes.db e data/condominio.db) sobrevive.
    runtime.obter_session_service.cache_clear()
    runtime.obter_runner.cache_clear()

    assert (await cliente.get(f"/sessoes/{sessao}/eventos")).json() == eventos_antes
    resposta = await cliente.post(
        f"/sessoes/{sessao}/confirmacoes", json={"id": pedido, "confirmado": True}
    )
    assert resposta.status_code == 200
    assert len(await _salao(cliente, "101", "2030-04-27")) == 1


async def test_duas_aprovacoes_simultaneas_uma_reserva(cliente):
    s3, pedido3 = await _sessao_com_pedido(cliente, "101", "2030-05-11")
    s4, pedido4 = await _sessao_com_pedido(cliente, "201", "2030-05-11")

    r3, r4 = await asyncio.gather(
        cliente.post(f"/sessoes/{s3}/confirmacoes", json={"id": pedido3, "confirmado": True}),
        cliente.post(f"/sessoes/{s4}/confirmacoes", json={"id": pedido4, "confirmado": True}),
    )

    assert r3.status_code == 200 and r4.status_code == 200
    total = await _salao(cliente, "101", "2030-05-11") + await _salao(cliente, "201", "2030-05-11")
    assert len(total) == 1
