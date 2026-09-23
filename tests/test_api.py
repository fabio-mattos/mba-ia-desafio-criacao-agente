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
