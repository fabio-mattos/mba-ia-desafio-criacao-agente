"""Rotas HTTP que nao dependem do modelo."""

from __future__ import annotations

from fastapi.testclient import TestClient

from residencial_aurora.api import app
from residencial_aurora.storage import reservas


def test_confirmacao_inexistente_devolve_409():
    with TestClient(app) as client:
        session_id = client.post("/sessoes", json={"apartamento": "101"}).json()[
            "session_id"
        ]
        resposta = client.post(
            f"/sessoes/{session_id}/confirmacoes",
            json={"id": "nao-existe", "confirmado": True},
        )
        assert resposta.status_code == 409
        assert client.get(f"/sessoes/{session_id}/eventos").json() == []


def test_sessao_desconhecida_devolve_404():
    with TestClient(app) as client:
        assert client.get("/sessoes/xyz/eventos").status_code == 404
        resposta = client.post("/sessoes/xyz/mensagens", json={"texto": "oi"})
        assert resposta.status_code == 404


async def test_rota_de_reservas_do_apartamento():
    await reservas.criar("101", "quadra", "2030-06-01")
    with TestClient(app) as client:
        assert client.get("/apartamentos/101/reservas").json()[0]["area"] == "quadra"
        assert client.get("/apartamentos/202/reservas").json() == []


def test_cota_do_modelo_estourada_vira_429(monkeypatch):
    from google.genai import errors

    from residencial_aurora import api

    async def estoura(*args, **kwargs):
        raise errors.ClientError(429, {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}})

    monkeypatch.setattr(api, "_executar_turno", estoura)
    with TestClient(app) as client:
        session_id = client.post("/sessoes", json={"apartamento": "101"}).json()["session_id"]
        resposta = client.post(f"/sessoes/{session_id}/mensagens", json={"texto": "oi"})
        assert resposta.status_code == 429
