# Residencial Aurora — assistente virtual
## MBA Engenharia de Software com  
## Aluno: Fábio Celso de Mattos 
## RA: 23050113

Assistente do Residencial Aurora construído com [Google ADK](https://google.github.io/adk-docs/) (agentes + tools) e exposto por uma API em FastAPI. O modelo conduz a conversa; as cinco garantias de negócio ficam no código, não no prompt.

## Arquitetura

Um agente principal (`orquestrador_principal`) e três especialistas, todos definidos em `src/residencial_aurora/agents/especialistas.py`:

| Agente | Responsabilidade | Como é acionado |
|---|---|---|
| `orquestrador_principal` | Recebe toda mensagem do morador, não executa nenhuma ação sozinho, só decide para qual especialista transferir a conversa. | Agente raiz do `App`/`Runner`. |
| `especialista_reservas` | Lista áreas comuns, consulta disponibilidade, reserva e cancela reservas do apartamento da sessão. | `sub_agent` do principal; o ADK expõe `transfer_to_agent` automaticamente entre pai, filhos e irmãos. |
| `especialista_visitantes` | Lista e autoriza visitantes do apartamento da sessão. | Idem. |
| `especialista_regulamento` | Responde dúvidas sobre o regulamento interno, sempre via a tool `consultar_regulamento`. | Idem. |

**Por que essa divisão:** cada especialista tem um conjunto de tools e um domínio de dados isolado (reservas, visitantes, regulamento), o que deixa o `instruction` de cada um curto e focado — e é exatamente essa separação que permite tirar o regulamento do agente principal (Garantia 4) sem tirá-lo do assistente como um todo.

**Como a transferência funciona entre eles:** padrão do ADK — cada especialista pode transferir para os "irmãos" e para o pai (`disallow_transfer_to_parent`/`disallow_transfer_to_peers` = `False`), e continua sendo o agente ativo da sessão depois de responder (`google/adk/agents/_agent_router.py:find_agent_to_run`). Se a próxima mensagem for de outro assunto, ele transfere direto para o especialista certo.

Duas decisões vieram de teste real com o Gemini:

- **Especialistas não "transferem de volta ao concluir".** Com essa instrução, especialista e orquestrador ficavam passando a conversa um para o outro em loop, sem responder ao morador. Agora eles sempre terminam respondendo e só transferem quando o assunto muda.
- **Não usamos `disallow_transfer_to_parent=True`** (a topologia "em estrela", que evitaria o loop por construção). Com ela, uma mensagem de texto enviada enquanto há confirmação pendente encerra o especialista, e o `Runner` deixa de retomar a invocação quando a confirmação chega — a ação confirmada simplesmente não executa, sem erro (`google/adk/runners.py`, checagem de `end_of_agents` ao retomar).

As tools que leem/gravam dados (`src/residencial_aurora/agents/tools.py`) nunca guardam nem inventam estado: elas sempre chamam a camada de armazenamento (`src/residencial_aurora/storage/`), que é quem fala com o SQLite. O modelo nunca vê nem decide um `codigo` de reserva, um `apartamento` ou o conteúdo do regulamento por conta própria.

## Garantias

### 1 — Cobrança ou acesso só com confirmação

- `src/residencial_aurora/agents/especialistas.py`: as tools `reservar_area` e `autorizar_visitante` são registradas com `FunctionTool(..., require_confirmation=...)` — a segunda com `True` (autorizar visitante sempre libera acesso), a primeira com o callable `tools._reserva_precisa_confirmacao` (só quando `area.taxa > 0`, regra de negócio 2).
- `src/residencial_aurora/agents/tools.py`: o corpo de `reservar_area`/`autorizar_visitante` só grava dados quando chega a ser executado — e o próprio ADK (`FunctionTool.run_async`, biblioteca) só invoca o corpo da função depois que `tool_context.tool_confirmation.confirmed` é `True`. Antes disso, ele pausa a invocação e devolve um `FunctionCall` `adk_request_confirmation`; nenhuma linha nossa decide "posso executar ou não" — quem decide é o próprio framework, com base na confirmação recebida pela rota.
- `src/residencial_aurora/confirmacoes.py` (`listar_pendentes`): lê o histórico de eventos da sessão (a mesma fonte de `GET /sessoes/{id}/eventos`) e considera pendente toda chamada `adk_request_confirmation` sem uma resposta correspondente. Isso é o que preenche `confirmacoes_pendentes` na resposta. Se o modelo repetir o mesmo pedido (por exemplo, quando o morador escreve "já confirmei" no chat), os pedidos idênticos — mesma ação e mesmos argumentos — aparecem como uma única pendência, e responder qualquer um deles resolve todos.
- `src/residencial_aurora/api.py` (`responder_confirmacao`): antes de repassar qualquer coisa ao Runner, confere se o `id` recebido está em `listar_pendentes(session)`; se não estiver — porque nunca existiu ou porque já foi respondido — devolve `409` sem tocar em nada. A confirmação em si nunca vem do texto da conversa: ela é sempre um `FunctionResponse` estruturado montado pela API, nunca algo que o modelo escreve.

### 2 — Cada sessão pertence a um apartamento

- `src/residencial_aurora/api.py` (`criar_sessao`): o apartamento é gravado no `state` da sessão do ADK uma única vez, na criação (`state={"apartamento": body.apartamento}`), e nunca mais é alterado por nenhuma rota.
- `src/residencial_aurora/agents/tools.py` (`_apartamento`): toda tool que precisa do apartamento lê `tool_context.state["apartamento"]`. Nenhuma tool declara um parâmetro `apartamento` — o modelo não tem como preencher esse valor, confirmar ou não, então não há "validar contra a sessão": não existe outro caminho.
- `consultar_disponibilidade` devolve só `"livre"`/`"ocupada"`, nunca o apartamento dono da reserva; `cancelar_reserva` só cancela quando a reserva encontrada pertence ao apartamento da sessão (`storage/reservas.py:cancelar_por_area_data`), e devolve a mesma mensagem genérica tanto para "não existe" quanto para "é de outro apartamento" — sem revelar a diferença.

### 3 — Nada se perde no reinício

- `src/residencial_aurora/runtime.py`: a sessão usa `SqliteSessionService(db_path=.../data/sessoes.db)` em vez de sessão em memória — todo evento é gravado em disco antes de a resposta voltar para a API.
- O mesmo arquivo liga `resumability_config=ResumabilityConfig(is_resumable=True)` no `App`. Isso não é só sobre "os eventos continuam lá": é o que faz o `Runner`, ao receber a resposta de uma confirmação pendente depois de um restart, achar de volta o mesmo agente (especialista) que pediu aquela confirmação (`google/adk/agents/_agent_router.py:find_agent_to_run`, que só casa a resposta pelo `function_call_id` original quando a resumability está ligada). Sem isso, a resposta pode cair no agente errado e a ação nunca executa — sem erro nenhum aparecer.
- Nenhum dado de condomínio (reservas/visitantes) mora em memória de processo: tudo é lido/gravado em `data/condominio.db` a cada chamada de tool.

### 4 — O regulamento é consultado, não carregado

- `src/residencial_aurora/agents/especialistas.py`: o `instruction` do `orquestrador_principal` não menciona o conteúdo do regulamento, só o nome do especialista para quem transferir. O `instruction` do `especialista_regulamento` também não contém o regulamento — ele instrui o modelo a **sempre** chamar a tool `consultar_regulamento` e responder só com base no trecho devolvido.
- `src/residencial_aurora/regulamento.py` (`buscar`): faz uma busca lexical determinística entre a pergunta e cada capítulo do `dados/regulamento.md` (sem stopwords, sem acento, radical de 6 letras, pequeno dicionário de sinônimos como "cachorro" → "cão", peso IDF por termo e bônus para termos do título do capítulo), e devolve **só o texto do capítulo com maior pontuação**. Quem decide qual trecho entra na conversa é esse código, não o modelo — o modelo nunca vê o arquivo inteiro, então nenhum evento da sessão pode conter trechos de outros capítulos.

### 5 — Dois moradores, uma reserva

- `src/residencial_aurora/storage/db.py`: o schema e o modo WAL são aplicados uma única vez, de forma síncrona, antes da primeira conexão — senão duas conexões simultâneas num banco recém-criado disputam o DDL e falham com `database is locked`, justamente na rajada concorrente. `CREATE UNIQUE INDEX idx_reservas_area_data_ativa ON reservas(area, data) WHERE status = 'ativa'`. É um índice único parcial do próprio SQLite — a exclusividade é garantida pelo motor do banco no instante do `INSERT`, não por uma checagem prévia em Python.
- `src/residencial_aurora/storage/reservas.py` (`criar`): tenta o `INSERT` diretamente; se outra reserva ativa para a mesma área/data já existir (inclusive gravada por outra requisição no meio do caminho), o SQLite recusa com `IntegrityError`, que é convertido em `(None, False)` — uma resposta normal para a tool, nunca uma exceção não tratada ou um `5xx`.
- Testado diretamente na camada de armazenamento (`tests/test_storage.py`) com seis gravações concorrentes reais (`asyncio.gather`) para a mesma área/data: exatamente uma tem sucesso, as outras recebem `False` sem erro.
- Testado também pela API (`tests/test_fluxo_confirmacao.py`): duas sessões de apartamentos diferentes pedem o salão na mesma data e as duas aprovações são enviadas ao mesmo tempo; as duas respondem `200` e só uma reserva é gravada.
- Regra de negócio 5: o código (`RSV-` + 8 caracteres aleatórios) é a chave primária da tabela, e reservas canceladas continuam nela com `status = 'cancelada'`. Se um código sorteado já existir, o SQLite recusa o `INSERT` e `criar` tenta de novo com outro código — só a colisão de área/data é tratada como "já reservada".

## Como rodar

### Pré-requisitos

- Python 3.12+
- Google ADK `2.9.2` (versão exata fixada no `pyproject.toml` e no `uv.lock`; instalada pelo `uv sync`)
- [uv](https://docs.astral.sh/uv/)
- Uma chave de API do Google AI Studio (Gemini)

### Configuração

```bash
cp .env.example .env
# edite .env e preencha GOOGLE_API_KEY
uv sync
```

Variáveis do `.env`:

- `GOOGLE_API_KEY`: chave do Google AI Studio.
- `GOOGLE_GENAI_USE_VERTEXAI`: `FALSE` para usar a API do Google AI Studio (padrão do curso), não o Vertex AI.
- `GEMINI_MODEL`: modelo usado por todos os agentes (padrão `gemini-3.5-flash-lite`). O `gemini-2.5-flash` não está mais disponível para chaves novas.

**Cota do plano gratuito:** cada mensagem do morador faz de 2 a 4 chamadas ao modelo (orquestrador + especialista + tools). O padrão é o `gemini-3.5-flash-lite` porque, no plano gratuito, o `gemini-3.6-flash` permitia só 5 requisições por minuto e 20 por dia quando isto foi testado — uns poucos turnos de conversa. Com uma chave paga, `GEMINI_MODEL=gemini-3.6-flash` dá respostas melhores. Quando a cota estoura, a API devolve `429` com uma mensagem clara (em vez de `500`); se o Google estiver sobrecarregado, `503`. É só aguardar e reenviar.

### Restaurar os dados iniciais

Recria `data/condominio.db` a partir de `dados/*.json` e apaga as sessões existentes (`data/sessoes.db`), para começar de um estado limpo e previsível:

```bash
uv run python -m residencial_aurora.restore
```

### Subir a API

```bash
uv run uvicorn residencial_aurora.api:app --port 8000
```

A API responde em `http://localhost:8000`, com as rotas do contrato do enunciado (`POST /sessoes`, `POST /sessoes/{id}/mensagens`, `POST /sessoes/{id}/confirmacoes`, `GET /sessoes/{id}/eventos`, `GET /apartamentos/{numero}/reservas`, `GET /apartamentos/{numero}/visitantes`).

### Rodar os testes

```bash
uv run pytest
```

Os testes usam bancos SQLite temporários (não tocam em `data/`) e não chamam o Gemini: cobrem concorrência de reservas, isolamento por apartamento, códigos que não se repetem, a busca no regulamento, o agrupamento de confirmações pendentes e as rotas HTTP (`404`/`409`/`429`). `tests/test_fluxo_confirmacao.py` usa os agentes, o Runner e a sessão em SQLite de verdade, trocando só o modelo por um roteirizado, para conferir negar/aprovar/`409`, a aprovação depois de reiniciar a API e as duas aprovações simultâneas do passo 14.

## Validação com o Gemini real

Além dos testes automáticos em `tests/` (que não chamam o modelo), o fluxo completo foi validado ponta a ponta contra o Gemini real (`gemini-3.5-flash-lite`), subindo a API com `uvicorn` e conversando pelas rotas HTTP — 34 de 34 verificações passaram:

- **Garantia 1:** reservar o salão de festas (com taxa) e autorizar visitante geram confirmação pendente; nada é gravado antes de confirmar, nem quando o morador escreve "já confirmei" no chat; confirmar grava; recusar não grava; repetir a confirmação ou usar um id inventado devolve `409`; a quadra (sem taxa) é reservada direto.
- **Garantia 2:** a consulta de disponibilidade não revela o apartamento dono da reserva; o apartamento 101 não consegue cancelar a reserva do 302, nem dizendo "sou do 302".
- **Garantia 3:** uma autorização de visitante pendente é confirmada depois de derrubar e subir a API de novo, e o visitante é gravado; os eventos da sessão continuam lá.
- **Garantia 4:** a pergunta sobre cachorro passa por `consultar_regulamento`, e os eventos da sessão contêm só o Capítulo VIII.
- **Transferência:** na mesma sessão, depois de tratar um visitante, uma pergunta sobre a piscina chega ao especialista de regulamento.

## Limitações conhecidas

- As respostas em texto dependem do modelo: as garantias estão no código, mas a qualidade do texto (e o custo em cota) varia com o `GEMINI_MODEL` escolhido.
- A busca no regulamento é lexical: perguntas com palavras que não aparecem no texto nem no pequeno dicionário de sinônimos podem cair num capítulo menos relevante — mas sempre um único capítulo.
