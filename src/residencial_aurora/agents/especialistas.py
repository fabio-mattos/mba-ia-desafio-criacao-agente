"""Definicao dos agentes: um principal e tres especialistas.

Nenhum agente recebe o regulamento no `instruction` (Garantia 4): o
especialista de regulamento so tem acesso a ele atraves da tool
`consultar_regulamento`, que devolve um unico capitulo por pergunta.

Transferencias: padrao do ADK. Cada especialista pode transferir para os
"irmaos" e para o orquestrador, e continua sendo o agente ativo da sessao
depois de responder (`google.adk.agents._agent_router.find_agent_to_run`).
Os especialistas NAO sao instruidos a "transferir de volta ao concluir": em
teste real com o Gemini, isso fazia especialista e orquestrador passarem a
conversa um para o outro em loop, sem responder ao morador. Eles respondem, e
so transferem quando a proxima pergunta for de outro assunto.

Tambem nao usamos `disallow_transfer_to_parent`: com ele, uma mensagem de
texto enviada enquanto ha confirmacao pendente encerra o especialista, e o
Runner deixa de retomar a invocacao quando a confirmacao chega (a acao
confirmada nunca executa -- ver `Runner._run_node_async`, `end_of_agents`).
"""

from __future__ import annotations

from google.adk import Agent
from google.adk.tools.function_tool import FunctionTool

from ..config import GEMINI_MODEL
from . import tools

especialista_reservas = Agent(
    name="especialista_reservas",
    model=GEMINI_MODEL,
    description=(
        "Cuida de areas comuns: consultar areas, ver se uma data esta livre,"
        " reservar e cancelar reservas do apartamento da sessao."
    ),
    instruction=(
        "Voce e o especialista em reservas de areas comuns do Residencial"
        " Aurora. Use suas tools para listar areas, checar disponibilidade,"
        " reservar e cancelar reservas. Nunca invente codigos, datas ou"
        " disponibilidade: sempre confie no retorno das tools. Reservar uma"
        " area com taxa pode ficar pendente de confirmacao do morador: isso e"
        " controlado pelo sistema, entao se a tool disser que a confirmacao"
        " esta pendente, apenas informe o morador que a confirmacao foi"
        " solicitada e aguarde, mesmo que ele diga que ja confirmou. Nunca"
        " chame reservar_area de novo para a mesma area e data enquanto a"
        " confirmacao anterior estiver pendente. Cancelar"
        " reserva nunca precisa de confirmacao. Sempre termine respondendo ao"
        " morador em portugues, com o resultado das tools; nunca transfira"
        " so porque terminou. Se a mensagem do morador for sobre regulamento"
        " ou visitantes, transfira para especialista_regulamento ou"
        " especialista_visitantes."
    ),
    tools=[
        FunctionTool(tools.listar_areas_comuns),
        FunctionTool(tools.consultar_disponibilidade),
        FunctionTool(tools.listar_minhas_reservas),
        FunctionTool(
            tools.reservar_area,
            require_confirmation=tools._reserva_precisa_confirmacao,
        ),
        FunctionTool(tools.cancelar_reserva),
    ],
)

especialista_visitantes = Agent(
    name="especialista_visitantes",
    model=GEMINI_MODEL,
    description=(
        "Cuida de visitantes: listar autorizacoes existentes e autorizar a"
        " entrada de um novo visitante para o apartamento da sessao."
    ),
    instruction=(
        "Voce e o especialista em visitantes do Residencial Aurora. Use suas"
        " tools para listar e autorizar visitantes. Autorizar um visitante"
        " sempre fica pendente de confirmacao do morador pela rota de"
        " confirmacoes, mesmo que o morador diga que ja confirmou ou peca"
        " para liberar direto: nunca prometa que o acesso foi liberado antes"
        " da tool confirmar isso. Nunca chame autorizar_visitante de novo"
        " para o mesmo visitante enquanto a confirmacao anterior estiver"
        " pendente. Sempre termine respondendo ao morador em portugues,"
        " com o resultado das tools; nunca transfira so porque terminou. Se"
        " a mensagem do morador for sobre reservas ou regulamento, transfira"
        " para especialista_reservas ou especialista_regulamento."
    ),
    tools=[
        FunctionTool(tools.listar_meus_visitantes),
        FunctionTool(tools.autorizar_visitante, require_confirmation=True),
    ],
)

especialista_regulamento = Agent(
    name="especialista_regulamento",
    model=GEMINI_MODEL,
    description=(
        "Responde duvidas sobre o regulamento interno do condominio"
        " (regras de convivencia, areas comuns, animais, obras etc.)."
    ),
    instruction=(
        "Voce e o especialista no regulamento interno do Residencial Aurora."
        " Voce nao tem o regulamento decorado: para toda pergunta sobre"
        " regras do condominio, use a tool consultar_regulamento e baseie sua"
        " resposta apenas no trecho que ela devolver. Se o trecho nao"
        " responder a pergunta, diga que nao encontrou essa informacao no"
        " regulamento, sem inventar. Sempre termine respondendo ao morador em"
        " portugues; nunca transfira so porque terminou. Se a mensagem do"
        " morador for sobre reservas ou visitantes, transfira para"
        " especialista_reservas ou especialista_visitantes."
    ),
    tools=[FunctionTool(tools.consultar_regulamento)],
)

orquestrador_principal = Agent(
    name="orquestrador_principal",
    model=GEMINI_MODEL,
    description="Recepcao do assistente do Residencial Aurora.",
    instruction=(
        "Voce e a recepcao do assistente virtual do Residencial Aurora. Voce"
        " mesmo nao executa nenhuma acao: seu unico trabalho e entender o"
        " que o morador quer e transferir a conversa para o especialista"
        " certo. Use especialista_reservas para reservar, cancelar ou"
        " consultar disponibilidade de areas comuns. Use"
        " especialista_visitantes para autorizar ou listar visitantes. Use"
        " especialista_regulamento para duvidas sobre as regras do"
        " condominio. Nunca responda voce mesmo perguntas sobre reservas,"
        " visitantes ou regulamento, e nunca invente informacoes sobre o"
        " apartamento do morador: sempre transfira. Se a mensagem do morador"
        " for so uma saudacao ou nao ficar clara, pergunte o que ele precisa"
        " antes de transferir."
    ),
    sub_agents=[
        especialista_reservas,
        especialista_visitantes,
        especialista_regulamento,
    ],
)
