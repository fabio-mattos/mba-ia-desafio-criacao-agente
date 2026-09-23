"""API HTTP do assistente do Residencial Aurora.

Rotas de conversa (`/sessoes/...`) passam pelo Runner do ADK. Rotas de
verificacao (`/apartamentos/...`) leem o banco de dados direto, sem passar
pelo modelo -- existem so para o avaliador conferir o efeito das conversas.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI, HTTPException
from google.genai import types
from pydantic import BaseModel

from .confirmacoes import CONFIRMATION_FUNCTION_CALL_NAME, listar_pendentes
from .config import APP_NAME
from .events_json import evento_para_json
from .runtime import obter_runner, obter_session_service
from .storage import reservas as reservas_store
from .storage import sessoes as sessoes_store
from .storage import visitantes as visitantes_store

app = FastAPI(title="Residencial Aurora")


class CriarSessaoRequest(BaseModel):
    apartamento: str


class CriarSessaoResponse(BaseModel):
    session_id: str


class MensagemRequest(BaseModel):
    texto: str


class ConfirmacaoRequest(BaseModel):
    id: str
    confirmado: bool


class RespostaConversa(BaseModel):
    resposta: str
    confirmacoes_pendentes: list[dict]


async def _apartamento_da_sessao(session_id: str) -> str:
    apartamento = await sessoes_store.obter_apartamento(session_id)
    if apartamento is None:
        raise HTTPException(status_code=404, detail="Sessao nao encontrada.")
    return apartamento


def _extrair_resposta(eventos: list) -> str:
    textos = []
    for evento in eventos:
        if evento.partial or not evento.content or not evento.content.parts:
            continue
        for part in evento.content.parts:
            if part.text:
                textos.append(part.text.strip())
    return " ".join(t for t in textos if t)


async def _executar_turno(session_id: str, apartamento: str, mensagem: types.Content) -> RespostaConversa:
    runner = obter_runner()
    eventos = [
        evento
        async for evento in runner.run_async(
            user_id=apartamento, session_id=session_id, new_message=mensagem
        )
    ]
    resposta = _extrair_resposta(eventos)
    session = await obter_session_service().get_session(
        app_name=APP_NAME, user_id=apartamento, session_id=session_id
    )
    pendentes = listar_pendentes(session)
    return RespostaConversa(resposta=resposta, confirmacoes_pendentes=pendentes)


@app.post("/sessoes", status_code=201, response_model=CriarSessaoResponse)
async def criar_sessao(body: CriarSessaoRequest) -> CriarSessaoResponse:
    session_id = uuid.uuid4().hex
    await obter_session_service().create_session(
        app_name=APP_NAME,
        user_id=body.apartamento,
        session_id=session_id,
        state={"apartamento": body.apartamento},
    )
    await sessoes_store.registrar(session_id, body.apartamento)
    return CriarSessaoResponse(session_id=session_id)


@app.post("/sessoes/{session_id}/mensagens", response_model=RespostaConversa)
async def enviar_mensagem(session_id: str, body: MensagemRequest) -> RespostaConversa:
    apartamento = await _apartamento_da_sessao(session_id)
    mensagem = types.Content(role="user", parts=[types.Part(text=body.texto)])
    return await _executar_turno(session_id, apartamento, mensagem)


@app.post("/sessoes/{session_id}/confirmacoes")
async def responder_confirmacao(session_id: str, body: ConfirmacaoRequest) -> Any:
    apartamento = await _apartamento_da_sessao(session_id)
    session = await obter_session_service().get_session(
        app_name=APP_NAME, user_id=apartamento, session_id=session_id
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Sessao nao encontrada.")

    pendentes_ids = {p["id"] for p in listar_pendentes(session)}
    if body.id not in pendentes_ids:
        raise HTTPException(
            status_code=409,
            detail="Nao ha confirmacao pendente com esse id nesta sessao.",
        )

    mensagem = types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    id=body.id,
                    name=CONFIRMATION_FUNCTION_CALL_NAME,
                    response={"confirmed": body.confirmado},
                )
            )
        ],
    )
    resultado = await _executar_turno(session_id, apartamento, mensagem)
    return resultado


@app.get("/sessoes/{session_id}/eventos")
async def listar_eventos(session_id: str) -> list[dict]:
    apartamento = await _apartamento_da_sessao(session_id)
    session = await obter_session_service().get_session(
        app_name=APP_NAME, user_id=apartamento, session_id=session_id
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Sessao nao encontrada.")
    return [evento_para_json(evento) for evento in session.events]


@app.get("/apartamentos/{numero}/reservas")
async def reservas_do_apartamento(numero: str) -> list[dict]:
    return await reservas_store.listar_ativas_por_apartamento(numero)


@app.get("/apartamentos/{numero}/visitantes")
async def visitantes_do_apartamento(numero: str) -> list[dict]:
    return await visitantes_store.listar_por_apartamento(numero)
