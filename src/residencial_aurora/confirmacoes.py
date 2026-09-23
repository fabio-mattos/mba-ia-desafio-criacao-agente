"""Deriva as confirmacoes pendentes de uma sessao a partir dos proprios eventos do ADK.

Garantia 1: a pendencia nao e um estado que o codigo da API inventa e guarda
em paralelo -- ela e lida direto do historico de eventos que o ADK ja
persiste (a mesma fonte usada por GET /sessoes/{id}/eventos). Uma
confirmacao esta pendente quando existe, no historico, uma chamada de funcao
"adk_request_confirmation" cujo id ainda nao tem uma resposta de funcao
correspondente. Isso e o que garante o 409 do enunciado: um id que nao esta
nesta lista -- por nao existir ou por ja ter sido respondido -- nunca chega a
executar nada.
"""

from __future__ import annotations

from google.adk.sessions.session import Session

CONFIRMATION_FUNCTION_CALL_NAME = "adk_request_confirmation"

_ACAO_POR_TOOL = {
    "reservar_area": "reservar_area_comum",
    "autorizar_visitante": "autorizar_visitante",
}


def listar_pendentes(session: Session) -> list[dict]:
    pedidos: dict[str, dict] = {}
    respondidos: set[str] = set()

    for event in session.events:
        for fc in event.get_function_calls():
            if fc.name != CONFIRMATION_FUNCTION_CALL_NAME or not fc.id:
                continue
            original = (fc.args or {}).get("originalFunctionCall") or {}
            nome_tool = original.get("name", "")
            pedidos[fc.id] = {
                "id": fc.id,
                "acao": _ACAO_POR_TOOL.get(nome_tool, nome_tool),
                "detalhes": original.get("args") or {},
            }
        for fr in event.get_function_responses():
            if fr.name == CONFIRMATION_FUNCTION_CALL_NAME and fr.id:
                respondidos.add(fr.id)

    return [p for fc_id, p in pedidos.items() if fc_id not in respondidos]


def esta_pendente(session: Session, confirmacao_id: str) -> bool:
    return any(p["id"] == confirmacao_id for p in listar_pendentes(session))
