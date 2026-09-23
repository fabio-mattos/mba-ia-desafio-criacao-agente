"""Monta o App e o Runner do ADK, com sessao persistida em SQLite.

Garantia 3 (nada se perde no reinicio): a sessao usa `SqliteSessionService`
gravando em `data/sessoes.db`, entao os eventos sobrevivem ao restart do
processo. `resumability_config=ResumabilityConfig(is_resumable=True)` e o
que faz o Runner, ao receber a resposta de uma confirmacao pendente, achar de
volta o mesmo agente (especialista) que pediu a confirmacao original -- veja
`google.adk.agents._agent_router.find_agent_to_run`, que so usa esse
casamento por function-call-id quando a resumability esta ligada; sem ela, a
resposta pode cair no agente errado e a acao nunca executa (o "trap"
silencioso descrito no enunciado).
"""

from __future__ import annotations

from functools import lru_cache

from google.adk.apps import App, ResumabilityConfig
from google.adk.runners import Runner
from google.adk.sessions.sqlite_session_service import SqliteSessionService

from .agents.especialistas import orquestrador_principal
from .config import APP_NAME, SESSOES_DB_PATH


@lru_cache(maxsize=1)
def obter_session_service() -> SqliteSessionService:
    return SqliteSessionService(db_path=str(SESSOES_DB_PATH))


@lru_cache(maxsize=1)
def obter_runner() -> Runner:
    app = App(
        name=APP_NAME,
        root_agent=orquestrador_principal,
        resumability_config=ResumabilityConfig(is_resumable=True),
    )
    return Runner(app=app, session_service=obter_session_service())
