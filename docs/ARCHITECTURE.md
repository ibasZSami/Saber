# Arquitetura do Silva

Visão geral de como as peças do Silva se encaixam. Para o que o app faz (features,
atalhos), ver o [README](../README.md); para o modelo de permissões e segurança,
ver [SECURITY.md](SECURITY.md).

## Camadas

```
src/
├── core/        Orquestração, agente de ferramentas, eventos, estado, scheduler
├── ai/          Providers de IA, prompts, parsing de resposta, contexto de prompt
├── character/   Sprites, animação, estado funcional/emoção do personagem
├── desktop/     Ações no sistema (abrir app, volume, allowlist, permissões)
├── vision/      Captura de tela, diff, OCR, tradução, modos de visão contínua
├── voice/       Entrada de voz (mic + áudio do sistema), TTS
├── memory/      SQLite: memória de longo prazo, histórico, lembretes
├── ui/          Janelas Qt (pet, chat, configurações, diálogo de confirmação)
└── config/      Settings (config.json + .env)
```

## `CompanionOrchestrator` — o centro

`src/core/orchestrator.py` constrói e conecta todo o resto no `__init__` e expõe
`handle_user_message()` como o ponto de entrada de qualquer input (chat, voz,
comando de texto). Não é um "god object" cego — a lógica de decisão real
(permissão, ferramentas, estado) já foi extraída para as classes abaixo; o
orquestrador principalmente fia (wires) essas peças e coordena o fluxo de uma
mensagem.

### Fluxo de uma mensagem (`handle_user_message`)

1. Roda numa thread de fundo (nunca bloqueia a UI).
2. Comandos determinísticos primeiro (Modo Nerd, lembrete, visão, áudio do
   sistema) — respondem sem chamar a IA quando reconhecidos.
3. Monta o contexto do prompt (`ContextManager`): janela ativa, contexto de
   tela estruturado com timestamp de recência, memórias salvas.
4. Decide se anexa uma captura de tela real (`_should_attach_vision`) e qual
   provider usar (`_select_provider` — rápido, complexo, ou visão).
5. Chama a IA, faz parse da resposta JSON (`speech`, `emotion`, `action`,
   `action_param`).
6. Despacha a ação via `AgentCore.execute()` (ver [SECURITY.md](SECURITY.md)).
7. Atualiza estado funcional + emoção, fala a resposta, grava na memória.
8. Qualquer exceção no meio do caminho é capturada — nunca trava em
   "pensando" para sempre.

## `EventBus` — pub/sub thread-safe

`src/core/event_bus.py` é um singleton por processo. Internamente usa um
`QObject` com um único `Signal` genérico (`Qt.AutoConnection`): emitir da
própria thread da GUI entrega na hora (síncrono); emitir de uma thread de
fundo enfileira automaticamente na thread da GUI. Isso torna qualquer
subscriber seguro de escrever sem se preocupar em qual thread o emit
aconteceu — sem precisar de `QueuedConnection` manual espalhado pelo código.

Todo evento relevante do app passa por aqui (mudança de tela, ação executada,
lembrete disparado, modo alternado, etc.) — ver a lista completa de
constantes no topo do arquivo.

## Agente de ferramentas (`AgentCore` + `ToolRegistry`)

- **`ToolRegistry`** (`src/core/tool_registry.py`): tabela nome → `ToolSpec`
  (tier de permissão, descrição, parâmetros, função de despacho). É a fonte
  única de verdade tanto para o que a IA pode chamar quanto para o que
  realmente executa — sem duas listas desalinhadas.
- **`AgentCore`** (`src/core/agent_core.py`): recebe `(action, action_param)`
  já parseado da resposta da IA e decide se executa, pede confirmação, ou
  recusa, conforme o tier e as políticas salvas. Ver
  [SECURITY.md](SECURITY.md#fluxo-de-permissão) para o fluxo completo.

Ferramentas hoje: `open_application`, `close_application`, `open_url`,
`search_web`, `remember`, `forget_memory`, `set_app_volume`,
`research_topic`, `create_reminder`, além de `observe_screen`/
`translate_screen` (descritivas — disparadas por palavra-chave, não por
despacho de ferramenta).

## Agent Engine — execução de objetivos em múltiplos passos

`src/core/agent_engine.py` + `src/core/task_manager.py` (em construção,
FASE 2 do plano de evolução — mouse/teclado/terminal/browser ainda não
existem como ferramentas, isso é FASE 3) implementam um loop real:

```
OBSERVAR (histórico de passos) → DECIDIR (1 chamada à IA) → AGIR (AgentCore)
→ VERIFICAR (observação) → REPETIR, até done=true ou um limite estourar
```

- **`TaskManager`**: dono do ciclo de vida de uma `Task` (PENDING → RUNNING →
  COMPLETED/FAILED/CANCELLED, com PAUSED opcional no meio) — histórico de
  passos, e três limites de segurança checados a cada passo: número máximo
  de passos, timeout, e detecção de repetição (a mesma ação+parâmetro N
  vezes seguidas corta o loop). Não executa nada sozinho.
- **`AgentEngine`**: o loop em si, rodando numa thread de fundo. Usa um
  prompt de sistema **separado** do conversacional
  (`build_agent_system_prompt`, em `src/ai/prompts.py`) e um parser próprio
  (`src/ai/agent_response.py`) — o schema de cada passo não tem `"speech"`,
  só `thought`/`done`/`result`/`action`/`action_param`. Despacha a ação
  escolhida através do **mesmo** `AgentCore` do chat normal — uma ferramenta
  CONFIRM dentro de uma tarefa multi-passo ainda pede confirmação de
  verdade, sem atalho.

**FASE 10 — gatilho de chat**: a própria IA decide quando usar a ação
`start_task` no lugar de uma ação direta — regra explícita no
`SYSTEM_PROMPT` (só para pedidos que genuinamente precisam de vários
passos dependentes, nunca pra pergunta simples ou ação única).
`handle_user_message` intercepta essa ação antes de chegar no
`AgentCore`/`ToolRegistry` (não é uma tool registrada) e chama
`orchestrator._start_agent_task(goal)`, que dispara
`agent_engine.run(goal, on_finish=self._on_agent_task_finished)`. O
resultado final é anunciado na voz da Silva quando o loop termina —
mesmo padrão já usado por `_on_reminder_fired`/`_announce_task_outcome`
(o callback roda na thread do Agent Engine, não na thread da GUI, mas é
seguro porque `state_manager`/`EventBus` já propagam entre threads via
Qt Signal). `orchestrator._active_task_id` rastreia a tarefa mais
recente para o comando determinístico "cancela a tarefa" ter o que
cancelar. As ferramentas abaixo (FASE 3) já funcionavam também no chat
normal de um passo só, via `AgentCore` diretamente, antes mesmo desse
gatilho existir.

**FASE 8 — resultado rico das ferramentas**: `AgentCore.execute()` sempre
devolveu só um bool (sucesso/falha) — suficiente pro chat normal, mas
insuficiente pro loop do agente: uma ferramenta como `observe_screen` (OCR
da tela, dispatch real agora, além do caminho por palavra-chave do chat) ou
`run_terminal_tool` só vale a pena chamar dentro de um loop se o PRÓXIMO
passo conseguir ver o que ela realmente retornou (o texto lido, a saída do
comando). `AgentCore.execute_with_detail()` resolve isso de forma aditiva:
uma função de dispatch pode devolver `(bool, str)` em vez de só `bool`
quando tem algo de real pra dizer; `execute()` continua devolvendo só o
bool, inalterado, pra quem já usa esse contrato. `AgentEngine` usa
`execute_with_detail()` — a observação de cada passo já é o resultado de
verdade quando existe, não só "executou com sucesso".

## Ferramentas de maior risco: mouse/teclado, terminal e navegador

Três categorias, cada uma atrás do próprio interruptor mestre em
Configurações → Agente (`input_control_enabled` / `terminal_tool_enabled` /
`browser_control_enabled`), **desligadas por padrão**. Enquanto desligadas,
`build_default_registry` nem registra um dispatch pra elas — a IA não só
não consegue executar, ela não é sequer informada de que a ferramenta
existe (ver `ToolRegistry.as_tools_schema(dispatchable_only=True)`, usado
pelo Agent Engine).

- **`src/desktop/input_control.py`** (`InputController`, via `pynput`):
  `click`/`move`/`type_text`/`press_key`. Tier **CONFIRM** — cada uso pede
  confirmação real (ou usa uma política ALWAYS/SESSION já salva), igual
  abrir um aplicativo.
- **`src/desktop/terminal_tool.py`** (`TerminalToolManager`): roda só
  binários de uma allowlist própria (Configurações → Agente, **vazia por
  padrão**), sem shell (`subprocess.run(..., shell=False)`, argumentos como
  lista de verdade), timeout de 30s, saída capada em 4000 caracteres,
  caracteres de metasintaxe de shell rejeitados nos argumentos mesmo sem
  shell interpretá-los. Emite `TERMINAL_TOOL_EXECUTED` com a saída
  completa — separado do `ACTION_EXECUTED` genérico (que continua só bool)
  porque um simples sucesso/fracasso perderia o resultado real de rodar
  algo como Nmap.
- **`src/desktop/browser_control.py`** (`BrowserController`, Playwright +
  Chromium): `navigate`/`click`/`type_text`/`read_text` — diferente de
  `open_url`, controla um navegador de verdade que fica aberto entre
  chamadas, permitindo clicar/ler/preencher dentro de uma página
  específica. A API síncrona do Playwright é presa à thread que a criou, e
  as ferramentas do Silva são despachadas de threads variadas (worker do
  chat, loop do Agent Engine) — por isso `BrowserController` roda numa
  **thread dedicada própria** com uma fila de comandos: cada chamada é
  entregue a essa thread e quem chamou espera o resultado, nunca toca o
  objeto do Playwright direto de fora dela. `click`/`type_text` recebem um
  `target` que só é tratado como seletor CSS se *parecer* um (`#id`,
  `.classe`, `tag`); caso contrário é tratado como texto visível
  (`page.get_by_text`), porque a IA só enxerga texto renderizado
  (`read_text`), nunca o HTML — não tem como fornecer um seletor de
  verdade. `browser_read` devolve o texto como `detail` via
  `execute_with_detail` (FASE 8), igual `observe_screen`/terminal.

## Visão (`src/vision/`)

- `ScreenCapture`: uma instância `mss.mss()` **por thread** (`threading.local`)
  — mss não é thread-safe, e captura acontece tanto na thread da GUI (timer
  periódico) quanto em threads de fundo (mensagem de chat pedindo a tela).
- `ScreenChangeDetector`: diff de pixels em baixa resolução — decide "a tela
  mudou?" sem nunca precisar enviar a imagem em si.
- `continuous_vision.py` (`VisionMode`, `ContinuousVisionBuffer`): modos
  explícitos OFF/CONTEXT/AWARENESS/ACTIVE e um buffer com TTL — nada é
  tratado como "tela atual" além do prazo de validade.
- `translation.py` + `ocr.py`: tradução sob demanda via Tesseract OCR.

`ContextManager.build_prompt_context` (`src/ai/context.py`) usa o timestamp
do contexto de tela para rotular a informação como recente ou dizer
explicitamente que não há leitura atual — nunca apresenta uma leitura velha
como se fosse agora.

## Personagem: estado funcional vs. emoção

`src/character/state_manager.py` mantém dois eixos independentes:

- **Estado funcional** (`set_state`) — o que Silva está literalmente fazendo
  (IDLE, THINKING, TALKING, GAMING, WORKING, SLEEP...), controlado só por
  lógica de sistema (orquestrador, detecção de janela/jogo, comandos
  determinísticos). A IA nunca escolhe isso.
- **Emoção** (`set_emotion`) — como Silva está se sentindo (HAPPY, SAD,
  ANGRY, EXCITED...), escolhida pela IA no campo `"emotion"` da resposta.
  Só aparece visualmente quando o estado funcional é neutro (IDLE/TALKING);
  em estados "ocupados" o sprite funcional tem prioridade e a emoção fica
  guardada, reaplicada automaticamente ao voltar pro neutro.

Antes da FASE 13 os dois compartilhavam um único campo (`"animation"`), o que
causava um funcional ser sobrescrito por uma reação emocional da IA (ou
vice-versa) sem aviso.

## Memória em camadas

Três camadas conceituais, cada uma já existente mas agora nomeadas
explicitamente:

- **Working** (`ContextManager`, `src/ai/context.py`): a mensagem atual +
  contexto de janela/tela — vive só durante a montagem daquele prompt,
  nunca persiste.
- **Short-term** (`MemoryManager.get_history()`): as últimas N trocas da
  conversa (SQLite, `conversation_history`) — dá continuidade sem exigir
  que o usuário peça pra guardar algo explicitamente.
- **Long-term** (`MemoryManager.get_memories()`, tabela `long_term_memory`):
  fatos que o usuário pediu pra guardar de verdade ("Guarde isso",
  "Esqueça isso") — sobrevive indefinidamente, entre sessões.

**Filtro de relevância** (`src/memory/relevance.py`): antes desta mudança,
toda memória de longo prazo entrava em **todo** prompt, sem exceção — com
poucas memórias isso não pesa, mas cresce sem limite. Agora
`select_relevant_memories()` só deixa passar memórias cujo texto realmente
se relaciona com a mensagem atual (sobreposição de palavras + menção direta
da chave), ordenadas por relevância, com um teto (`DEFAULT_MAX_MEMORIES =
8`). Sem embeddings/vector store — decisão deliberada: isso é uma
dependência real (qual store, como manter sincronizado com
`remember`/`forget`) que merece sua própria etapa, não uma adição rápida
aqui. Só se aplica ao caminho de mensagem real (`handle_user_message`) — o
comentário espontâneo continua usando o conjunto completo, já que não tem
uma mensagem específica pra comparar relevância.

RAG local (documentos/código) acabou ganhando seu próprio design — ver seção
"RAG local" mais abaixo — em vez de reusar esse mesmo filtro de relevância:
memórias são um punhado de fatos curtos, documentos/código são texto longo
que precisa de chunking e uma estratégia de busca diferente.

- `Scheduler` (`src/core/scheduler.py`) + `reminder_parser.py`: lembretes/
  timers ("me lembra em 30 minutos", "às 18h me avisa", recorrência diária),
  persistidos na mesma base SQLite, checados por um `QTimer` periódico.

## Modos do Silva

`src/core/silva_modes.py` define seis presets (`SILVA_MODES`, um dict de
nome → subconjunto de settings) e `CompanionOrchestrator.apply_silva_mode()`
os aplica — nenhuma capacidade nova, só um jeito de um clique (ou comando
"modo trabalho"/"modo jogo"/etc, mesmo padrão determinístico dos outros
toggles) alcançar uma combinação de coisas que já existem: visão
(`set_full_vision`, que já cobre `private_mode` + o QTimer ao vivo),
microfone (só grava em Settings — sem chave liga/desliga ao vivo hoje,
precisa reiniciar), fala espontânea e Modo Nerd. Cada preset só lista as
chaves que de fato importa — uma ausente fica exatamente como estava, não
volta a um padrão.

**Privacidade** é o único com efeito extra: além do preset, ele também para
qualquer captura já em andamento agora (Modo Tradução, áudio do sistema) —
os outros presets só mudam o que vai acontecer daqui pra frente.

## Attention Budget

`_maybe_speak_spontaneously` decidia se comentava sozinha com um relógio
fixo: "já se passaram N segundos desde o último comentário?" — mesmo N
jogando, ocioso, ou no meio de qualquer coisa. `AttentionBudget`
(`src/core/attention_budget.py`) troca isso por um orçamento que se
regenera com o tempo (token bucket, não relógio): a taxa de regeneração
varia com o contexto — mais devagar durante `GAMING` (não quer interromper
a partida), mais rápido quando ocioso há um tempo (`idle_seconds >
ATTENTION_IDLE_THRESHOLD_S`, nada mais competindo pela atenção), normal
nos outros casos. `can_speak()` só consulta se há orçamento suficiente;
`spend()` é chamado separadamente só quando o comentário de fato acontece
— assim uma decisão de não falar (ex: a IA não teve nada a dizer) não
gasta orçamento à toa. O teto (`MAX_BUDGET`) evita que um silêncio longo
vire uma rajada de comentários assim que termina. O `idle_gap` (nunca
falar logo depois de uma interação real) continua existindo como uma
checagem separada, antes do orçamento — são preocupações diferentes.

## Barge-in (interromper a fala)

Toda ferramenta de TTS (`src/voice/tts.py`) ganhou `stop()` — antes só
existia `speak()`, sem nenhum jeito de cancelar uma fala em andamento:
`EdgeTTSProvider.stop()` chama `pygame.mixer.music.stop()` (seguro entre
threads — o loop de espera de `speak()` sai sozinho no próximo poll,
até ~100ms depois); `Pyttsx3Provider.stop()` chama `engine.stop()`
(comportamento documentado do pyttsx3, funciona bem no driver SAPI5 do
Windows que este projeto já assume); `FallbackTTSProvider.stop()` chama
os dois de baixo (só um estará de fato tocando).

`CompanionOrchestrator._speak_async` agora rastreia `_is_speaking` e emite
`TTS_STARTED`/`TTS_FINISHED` em volta da chamada — `voice.speaking` no
`SilvaState` vem daqui. `stop_speaking()` é o método público
(`self.tts.stop()`, seguro chamar mesmo sem nada tocando) — conectado
automaticamente a `voice_input.listening_started`: apertar Push-to-Talk ou
disparar o modo mãos-livres enquanto ela está falando a interrompe na
hora, mesmo padrão de barge-in de uma conversa real. Só entrada de voz
DIRETA faz isso (não o áudio do sistema overheard, mesmo princípio de
autoridade do `is_direct_input`). "para de falar"/"cala a boca"/"fica
quieta"/"silêncio" fazem o mesmo por texto — útil principalmente na janela
de chat, que não tem áudio pra interromper naturalmente.

## Plugins

`src/core/plugin_system.py` (`PluginManager`) — mecanismo de extensão
mínimo, **desligado por padrão** (`plugins_enabled`). Um plugin é um único
arquivo `.py` em `plugins/` com uma função `register(context)`; `context`
dá acesso a `register_tool` (registra um `ToolSpec` de verdade no mesmo
`ToolRegistry` que toda ferramenta nativa usa — passa pelo mesmo
CONFIRM/allowlist/política, sem atalho), `event_bus` e `settings`.

**Não é sandbox** — a função `dispatch` de um plugin é código Python comum
rodando no mesmo processo, sem as travas que `run_terminal_tool`/
`browser_navigate` constroem por conta própria (sem shell, allowlist
própria, etc.), a menos que o autor do plugin escolha replicar isso. A
única fronteira de segurança real é o interruptor mestre — nada em
`plugins/` roda até o usuário ligar explicitamente. Um plugin quebrado
(erro de sintaxe, exceção no `register`, sem a função) nunca derruba o
resto — só aquele arquivo fica de fora, log do erro.

**Limitação conhecida**: uma ferramenta de plugin é automaticamente vista
pelo Agent Engine (que monta seu prompt dinamicamente a partir do
`ToolRegistry` via `as_tools_schema(dispatchable_only=True)`), mas **não**
pelo chat de um passo só — o `SYSTEM_PROMPT` conversacional é um texto
estático (ver `src/ai/prompts.py`) que precisa listar cada ação
manualmente, e não tem como saber de antemão o nome de uma ferramenta que
um plugin de terceiros vai criar. Corrigir isso exigiria montar o
`SYSTEM_PROMPT` dinamicamente a partir do registry — mudança maior,
deixada de fora desta passada.

Exemplo funcional em `plugins/example_dice.py` (ferramenta `roll_dice`);
guia completo em `plugins/README.md`.

## Empacotamento

`packaging/silva.spec` (PyInstaller) + `packaging/silva.iss` (Inno Setup) —
transforma o código-fonte num `Silva-Setup.exe` real. Passo a passo completo
em `packaging/README.md`; aqui só as decisões que afetam o resto do código.

**Layout onedir achatado** (`contents_directory="."` no `.spec`): PyInstaller
6+ por padrão joga tudo exceto o `.exe` numa subpasta `_internal`. Isso quebra
a premissa deste projeto de que dados do usuário (`config.json`, `data/`)
vivem *ao lado* do executável — por isso o `.spec` força de volta o layout
plano de antes da 6.0, tudo direto em `dist/Silva/`.

**Resolução de caminho frozen-aware** (`src/config/settings.py`): `PROJECT_ROOT`
normalmente sobe três níveis a partir de `__file__` (`src/config/` → raiz do
repo) — não funciona num build congelado, onde não existe árvore `src/`.
Detecta via `sys.frozen` e, nesse caso, usa `Path(sys.executable).resolve().parent`
(a pasta onde `Silva.exe` está) como raiz. `Database` (`src/memory/database.py`)
e o `plugins_dir` do orchestrator importam esse mesmo `PROJECT_ROOT` em vez de
recalcular `__file__`-based paths por conta própria, pra não duplicar (e
divergir) essa lógica.

**Autostart num build congelado** (`src/core/autostart.py`): a Scheduled
Task/Run-key que a própria Silva gerencia (aba Configurações) originalmente
montava o comando de lançamento como `"python.exe" "main.py"` — não existe
`main.py` nem `python.exe` separado num build congelado, só `Silva.exe`.
`_launch_paths()` detecta `sys.frozen` e usa `sys.executable` sozinho, sem
argumento. Por isso o instalador Inno Setup **não** oferece sua própria opção
de autostart — duplicaria o mecanismo que a Silva já gerencia por conta
própria e podia registrar os dois, lançando duas instâncias no logon.

**O que fica fora do instalador**: `config.json` e `data/` não são
empacotados — a Silva já cria os dois sozinha na primeira execução, então
cada instalação parte de config limpo em vez de herdar caminhos absolutos da
máquina onde o build foi gerado. Tesseract-OCR e o Chromium do Playwright
continuam instalados à parte (não são pacotes pip, entram centenas de MB
para uma minoria dos usuários) — mesmo tradeoff que `install.bat` já fazia.

## RAG local

`src/memory/rag_index.py` (`RAGIndex`) — busca offline em documentos/código
de uma pasta, **desligada por padrão** (`rag_enabled`), mesmo padrão de
gating "sem instância real, sem dispatch" das outras ferramentas de maior
risco: `RAGIndex()` só é construída no `__init__` do orchestrator se o
switch estiver ligado, e `index_folder`/`search_documents` ficam com
`dispatch=None` (genuinely ausentes do que a IA sabe que existe) até lá.

**BM25, não embeddings**: escolha deliberada — nada de baixar um modelo de
embeddings, sem GPU, sem custo por chamada de API, sem falar com a rede.
`rank-bm25` é uma dependência pura-Python de ~10KB. O preço é semântico:
busca por palavra-chave (com stemming/sinônimo nenhum), não por significado
— "onde fica a autenticação" não acha um trecho que só fala em "login" se
nenhuma das duas palavras aparecer literalmente. Suficiente pra "achar o
arquivo/trecho que menciona X" numa pasta pessoal ou repositório
pequeno/médio; não é um motor de busca semântica.

**Gate de relevância é overlap de token, não `score > 0`**: a fórmula
clássica de idf do BM25 (`log((N-freq+0.5)/(freq+0.5))`) dá exatamente zero
sempre que um termo aparece em cerca de metade dos chunks indexados — comum
em índices pequenos (poucos arquivos), o caso de uso real esperado aqui.
Filtrar por `score > 0` descartaria silenciosamente o único trecho relevante
nesse caso. `RAGIndex.search()` em vez disso só exige que pelo menos um
token da busca apareça literalmente no chunk, e usa o score do BM25 só pra
ordenar entre os que já passaram nesse filtro.

**Sem persistência**: o índice vive só em memória, reconstruído do zero a
cada `index_folder` — sem cache em disco, sem re-indexação incremental, sem
observar mudanças de arquivo. Se o conteúdo muda, o usuário reindexa.
Simplificação deliberada pra uma primeira versão; um índice persistente
precisaria de estratégia própria de invalidação (o arquivo mudou desde a
última vez? foi apagado?) — não vale a complexidade ainda.

**Limites de segurança embutidos** (`src/memory/rag_index.py`): só
extensões de texto/código reconhecidas são lidas (nunca binários,
imagens, ou `.env`); pastas conhecidas por serem ruído/gigantes
(`.git`, `node_modules`, `venv`, `dist`, `build`, ...) nunca são
percorridas; um arquivo maior que 2MB é pulado; e um teto de 2000 arquivos
por chamada de `index_folder` evita que indexar uma árvore gigante trave o
app. `index_folder` é `CONFIRM` (lê arquivos de verdade do disco que o
usuário não escolheu individualmente); `search_documents` é `SAFE`
(read-only sobre um índice que já exigiu confirmação pra existir).

## Observabilidade local

- `ActivityLog` (`src/core/activity_log.py`): histórico amigável de ações
  (abriu app, guardou memória, lembrete disparado...), só em memória, aba
  "Atividade" em Configurações.
- `diagnostics.py`: checagem local offline de saúde (Python, Qt, áudio,
  Whisper, Tesseract, API, assets, configuração, allowlist, autostart), aba
  "Diagnóstico".
- `SilvaState` (`src/core/silva_state.py`): fachada somente-leitura que
  computa um snapshot de "o que está acontecendo agora" a partir dos dados
  já mantidos por cada subsistema — não é um segundo armazenamento de
  estado, só uma consulta unificada.
- **Privacy Center** (`src/core/privacy_summary.py`, aba "Privacidade"):
  `format_privacy_summary()` transforma o snapshot do `SilvaState` num texto
  legível — visão, Modo Tradução, microfone, áudio do sistema, memórias
  salvas — reaproveitando o facade acima em vez de rastrear esse estado de
  novo. A aba também deixa esquecer uma memória direto ali
  (`memory_manager.forget()`), não é só leitura.

## Testes

Ver [TESTING.md](TESTING.md) para os padrões usados (construção "bare" do
orquestrador, reset do EventBus, thread síncrona para testes determinísticos).
