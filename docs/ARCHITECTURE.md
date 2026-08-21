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

## Memória e agendamento

- `MemoryManager` + `Database` (`src/memory/`): memória chave/valor de longo
  prazo e histórico de conversa, em SQLite local.
- `Scheduler` (`src/core/scheduler.py`) + `reminder_parser.py`: lembretes/
  timers ("me lembra em 30 minutos", "às 18h me avisa", recorrência diária),
  persistidos na mesma base SQLite, checados por um `QTimer` periódico.

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

## Testes

Ver [TESTING.md](TESTING.md) para os padrões usados (construção "bare" do
orquestrador, reset do EventBus, thread síncrona para testes determinísticos).
