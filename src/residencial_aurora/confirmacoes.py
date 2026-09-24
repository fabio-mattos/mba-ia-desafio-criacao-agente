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

import json

from google.adk.sessions.session import Session

CONFIRMATION_FUNCTION_CALL_NAME = "adk_request_confirmation"

_ACAO_POR_TOOL = {
    "reservar_area": "reservar_area_comum",
    "autorizar_visitante": "autorizar_visitante",
}


def _pedidos_sem_resposta(session: Session) -> list[tuple[str, dict]]:
    """Todos os pedidos de confirmacao sem resposta, em ordem: (chave, pedido)."""
    pedidos: dict[str, tuple[str, dict]] = {}
    respondidos: set[str] = set()

    for event in session.events:
        for fc in event.get_function_calls():
            if fc.name != CONFIRMATION_FUNCTION_CALL_NAME or not fc.id:
                continue
            original = (fc.args or {}).get("originalFunctionCall") or {}
            nome_tool = original.get("name", "")
            detalhes = original.get("args") or {}
            chave = json.dumps([nome_tool, detalhes], sort_keys=True)
            pedidos[fc.id] = (
                chave,
                {
                    "id": fc.id,
                    "acao": _ACAO_POR_TOOL.get(nome_tool, nome_tool),
                    "detalhes": detalhes,
                },
            )
        for fr in event.get_function_responses():
            if fr.name == CONFIRMATION_FUNCTION_CALL_NAME and fr.id:
                respondidos.add(fr.id)
                # Respondeu um pedido: os pedidos identicos anteriores
                # (mesma acao e mesmos argumentos) ficam resolvidos junto.
                if fr.id in pedidos:
                    chave = pedidos[fr.id][0]
                    respondidos.update(
                        i for i, (c, _) in pedidos.items() if c == chave
                    )

    return [(c, p) for i, (c, p) in pedidos.items() if i not in respondidos]


def listar_pendentes(session: Session) -> list[dict]:
    """Pendencias para mostrar ao morador, sem repetir a mesma acao.

    O modelo as vezes chama a mesma tool de novo (por exemplo, quando o
    morador escreve "ja confirmei"), gerando um segundo pedido identico. So o
    mais recente de cada acao+argumentos aparece; o id de um pedido anterior
    identico continua aceito pela rota (ver `esta_pendente`).
    """
    por_chave: dict[str, dict] = {}
    for chave, pedido in _pedidos_sem_resposta(session):
        por_chave.pop(chave, None)
        por_chave[chave] = pedido
    return list(por_chave.values())


def esta_pendente(session: Session, confirmacao_id: str) -> bool:
    return any(p["id"] == confirmacao_id for _, p in _pedidos_sem_resposta(session))
