"""Garantia 1: pendencias derivadas dos eventos, sem duplicar a mesma acao."""

from __future__ import annotations

from google.adk.events.event import Event
from google.adk.sessions.session import Session
from google.genai import types

from residencial_aurora.confirmacoes import (
    CONFIRMATION_FUNCTION_CALL_NAME,
    esta_pendente,
    listar_pendentes,
)

RESERVA = {"name": "reservar_area", "args": {"area_id": "salao-de-festas", "data": "2030-07-10"}}


def _pedido(fc_id, original=RESERVA):
    return Event(
        author="especialista_reservas",
        content=types.Content(
            role="model",
            parts=[
                types.Part(
                    function_call=types.FunctionCall(
                        id=fc_id,
                        name=CONFIRMATION_FUNCTION_CALL_NAME,
                        args={"originalFunctionCall": original},
                    )
                )
            ],
        ),
    )


def _resposta(fc_id):
    return Event(
        author="user",
        content=types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        id=fc_id,
                        name=CONFIRMATION_FUNCTION_CALL_NAME,
                        response={"confirmed": True},
                    )
                )
            ],
        ),
    )


def _sessao(*eventos):
    return Session(id="s", app_name="a", user_id="101", events=list(eventos))


def test_pedido_sem_resposta_fica_pendente():
    pendentes = listar_pendentes(_sessao(_pedido("c1")))
    assert pendentes == [
        {"id": "c1", "acao": "reservar_area_comum", "detalhes": RESERVA["args"]}
    ]


def test_pedidos_identicos_aparecem_uma_vez_e_ambos_ids_valem():
    sessao = _sessao(_pedido("c1"), _pedido("c2"))
    assert [p["id"] for p in listar_pendentes(sessao)] == ["c2"]
    assert esta_pendente(sessao, "c1") and esta_pendente(sessao, "c2")


def test_responder_um_resolve_os_identicos():
    sessao = _sessao(_pedido("c1"), _pedido("c2"), _resposta("c1"))
    assert listar_pendentes(sessao) == []
    assert not esta_pendente(sessao, "c2")


def test_acoes_diferentes_continuam_separadas():
    visitante = {"name": "autorizar_visitante", "args": {"nome": "Ana", "data": "2030-07-12"}}
    sessao = _sessao(_pedido("c1"), _pedido("c2", visitante), _resposta("c1"))
    assert [p["acao"] for p in listar_pendentes(sessao)] == ["autorizar_visitante"]


def test_mesmo_pedido_depois_de_respondido_fica_pendente_de_novo():
    sessao = _sessao(_pedido("c1"), _resposta("c1"), _pedido("c3"))
    assert [p["id"] for p in listar_pendentes(sessao)] == ["c3"]
