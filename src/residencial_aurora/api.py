"""API HTTP do assistente do Residencial Aurora.

Rotas de conversa (`/sessoes/...`) passam pelo Runner do ADK. Rotas de
verificacao (`/apartamentos/...`) leem o banco de dados direto, sem passar
pelo modelo -- existem so para o avaliador conferir o efeito das conversas.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel

from .confirmacoes import (
    CONFIRMATION_FUNCTION_CALL_NAME,
    esta_pendente,
    listar_pendentes,
)
from .config import APP_NAME
from .events_json import evento_para_json
from .runtime import obter_runner, obter_session_service
from .storage import reservas as reservas_store
from .storage import sessoes as sessoes_store
from .storage import visitantes as visitantes_store

app = FastAPI(title="Residencial Aurora")


@app.exception_handler(genai_errors.APIError)
async def _erro_do_modelo(request: Request, exc: genai_errors.APIError) -> JSONResponse:
    # Cota estourada (comum no plano gratuito) ou modelo sobrecarregado nao sao
    # erros da API: devolve 429/503 para o cliente tentar de novo, em vez de 500.
    if exc.code == 429:
        return JSONResponse(
            status_code=429,
            content={"detail": "Limite de requisicoes do modelo atingido. Tente novamente em instantes."},
        )
    if exc.code == 503:
        return JSONResponse(
            status_code=503,
            content={"detail": "O modelo esta sobrecarregado no momento. Tente novamente em instantes."},
        )
    return JSONResponse(
        status_code=502,
        content={"detail": f"Erro ao chamar o modelo: {exc.status or exc.code}."},
    )


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
    pediu_confirmacao = any(
        fc.name == CONFIRMATION_FUNCTION_CALL_NAME
        for evento in eventos
        for fc in evento.get_function_calls()
    )
    if not resposta and pediu_confirmacao:
        # O ADK pausa o turno no pedido de confirmacao, as vezes sem texto do modelo.
        resposta = (
            "Essa acao precisa da sua confirmacao antes de ser concluida."
            " Veja as confirmacoes pendentes."
        )
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

    if not esta_pendente(session, body.id):
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
