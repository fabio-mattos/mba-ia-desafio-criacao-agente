"""Tools dos especialistas.

Nenhuma destas funcoes aceita um parametro "apartamento": o apartamento
sempre vem de `tool_context.state["apartamento"]`, que foi gravado no state
da sessao na criacao dela (ver api.py) e nunca muda depois (Garantia 2). Como
o modelo nunca preenche esse valor, nao ha como uma mensagem do morador fazer
uma tool operar sobre o apartamento de outra pessoa.

As tools que geram cobranca ou liberam acesso (regras de negocio 2 e 3) sao
registradas com `require_confirmation` no FunctionTool (ver reservas_agent e
visitantes_agent): o ADK pausa a execucao e so chama o corpo da funcao de
verdade depois que a rota de confirmacoes aprova (Garantia 1).
"""

from __future__ import annotations

from google.adk.tools.tool_context import ToolContext

from ..dados_condominio import listar_areas, obter_area
from ..regulamento import buscar as buscar_regulamento
from ..storage import reservas as reservas_store
from ..storage import visitantes as visitantes_store


def _apartamento(tool_context: ToolContext) -> str:
    return tool_context.state["apartamento"]


async def listar_areas_comuns() -> dict:
    """Lista as areas comuns do condominio, com id, nome e se geram cobranca."""
    return {
        "areas": [
            {"id": a.id, "nome": a.nome, "taxa": a.taxa}
            for a in listar_areas()
        ]
    }


async def consultar_disponibilidade(area_id: str, data: str) -> dict:
    """Verifica se uma area comum esta livre ou ocupada em uma data.

    Nunca revela de qual apartamento e a reserva quando a data esta ocupada:
    a resposta e sempre so "livre" ou "ocupada".

    Args:
      area_id: id da area comum (ver listar_areas_comuns).
      data: data no formato AAAA-MM-DD.
    """
    area = obter_area(area_id)
    if area is None:
        return {"erro": f"Area '{area_id}' nao encontrada."}
    livre = await reservas_store.esta_livre(area_id, data)
    return {"area": area_id, "data": data, "status": "livre" if livre else "ocupada"}


async def listar_minhas_reservas(tool_context: ToolContext) -> dict:
    """Lista as reservas ativas do apartamento da sessao atual."""
    apartamento = _apartamento(tool_context)
    return {"reservas": await reservas_store.listar_ativas_por_apartamento(apartamento)}


async def _reserva_precisa_confirmacao(
    area_id: str, data: str, tool_context: ToolContext
) -> bool:
    del data, tool_context
    area = obter_area(area_id)
    return bool(area and area.gera_cobranca)


async def reservar_area(area_id: str, data: str, tool_context: ToolContext) -> dict:
    """Reserva uma area comum do condominio para o apartamento da sessao.

    Se a area tiver taxa maior que zero, a reserva so e gravada depois de
    confirmada pelo morador na rota de confirmacoes.

    Args:
      area_id: id da area comum (ver listar_areas_comuns).
      data: data no formato AAAA-MM-DD.
    """
    apartamento = _apartamento(tool_context)
    area = obter_area(area_id)
    if area is None:
        return {"erro": f"Area '{area_id}' nao encontrada."}
    codigo, sucesso = await reservas_store.criar(apartamento, area_id, data)
    if not sucesso:
        return {
            "sucesso": False,
            "mensagem": f"A area '{area.nome}' ja esta reservada em {data}.",
        }
    return {
        "sucesso": True,
        "codigo": codigo,
        "area": area_id,
        "data": data,
        "taxa": area.taxa,
    }


async def cancelar_reserva(
    area_id: str, data: str, tool_context: ToolContext
) -> dict:
    """Cancela uma reserva ativa do apartamento da sessao, sem precisar de confirmacao.

    So cancela reservas do proprio apartamento da sessao; nao afeta nem revela
    reservas de outros apartamentos.

    Args:
      area_id: id da area comum reservada.
      data: data da reserva, no formato AAAA-MM-DD.
    """
    apartamento = _apartamento(tool_context)
    sucesso, mensagem = await reservas_store.cancelar_por_area_data(
        apartamento, area_id, data
    )
    return {"sucesso": sucesso, "mensagem": mensagem}


async def listar_meus_visitantes(tool_context: ToolContext) -> dict:
    """Lista as autorizacoes de visita do apartamento da sessao atual."""
    apartamento = _apartamento(tool_context)
    return {"visitantes": await visitantes_store.listar_por_apartamento(apartamento)}


async def autorizar_visitante(
    nome: str, data: str, tool_context: ToolContext
) -> dict:
    """Autoriza a entrada de um visitante no apartamento da sessao.

    Libera acesso ao predio, entao sempre precisa de confirmacao pela rota de
    confirmacoes antes de ser gravada, mesmo que o morador diga que ja
    confirmou pelo chat.

    Args:
      nome: nome completo do visitante.
      data: data da visita, no formato AAAA-MM-DD.
    """
    apartamento = _apartamento(tool_context)
    await visitantes_store.autorizar(apartamento, nome, data)
    return {"sucesso": True, "nome": nome, "data": data}


async def consultar_regulamento(pergunta: str) -> dict:
    """Responde duvidas sobre o regulamento interno do condominio.

    Devolve apenas o capitulo do regulamento mais relevante para a pergunta,
    nunca o documento inteiro.

    Args:
      pergunta: a duvida do morador sobre o regulamento.
    """
    capitulo = buscar_regulamento(pergunta)
    return {"capitulo": capitulo.titulo, "trecho": capitulo.texto}
