# Segurança e permissões

Modelo de permissão do Silva: nenhuma ação de sistema é "shell livre" — tudo
passa por um `ToolRegistry` estruturado com tier de risco explícito. Este
documento descreve as camadas de defesa em ordem, da menos para a mais
sensível.

## Tiers de ferramenta

`PermissionTier` (`src/core/tool_registry.py`):

- **SAFE** — executa direto, sem confirmação: pesquisar na web, guardar/
  esquecer memória, agendar um lembrete, iniciar uma pesquisa em segundo
  plano, observar/traduzir a tela.
- **CONFIRM** — pede confirmação do usuário (ou usa uma política já salva):
  abrir/fechar aplicativo, abrir URL, ajustar volume de um app, controle de
  mouse/teclado, rodar ferramenta de terminal.
- **DANGEROUS** — reservado, nenhuma ferramenta usa ainda. Qualquer coisa
  marcada assim seria recusada por padrão (fail-safe) até ganhar uso real.

## Fluxo de permissão

`AgentCore.execute()` (`src/core/agent_core.py`) é o único ponto de despacho:

1. **SAFE** → executa direto.
2. **CONFIRM** → verifica `PermissionPolicyManager`:
   - política `BLOCKED` salva → recusa sem perguntar.
   - política `ALWAYS`/`SESSION` salva → executa sem novo diálogo.
   - senão, chama `confirm_fn` (o diálogo real, `ConfirmationBridge`) e
     espera a decisão do usuário: `ONCE`, `SESSION`, `ALWAYS`, `BLOCKED` ou
     `DECLINED` (cancelar). `SESSION`/`ALWAYS`/`BLOCKED` são persistidas via
     `PermissionPolicyManager.set_policy()`; `ONCE`/`DECLINED` não.
3. **DANGEROUS** → recusado sempre (nenhuma ferramenta usa este tier hoje).

`ConfirmationBridge` (`src/ui/confirmation_dialog.py`) roda a caixa de
diálogo (`QMessageBox`) na thread da GUI via
`Qt.BlockingQueuedConnection` e devolve o resultado por um atributo de
instância protegido por lock — não por argumento de signal, porque o Qt
**copia** argumentos mutáveis ao cruzar threads (uma lista/objeto passado
como argumento de signal não preserva identidade do outro lado).

## Allowlist de aplicativos

Abrir/fechar aplicativos por nome só funciona para apps na allowlist
(`Settings → Aplicativos`), gerenciável pela UI sem editar `config.json` na
mão. `resolve_app_path()` (`src/desktop/app_resolver.py`) também tenta
resolver um app fora da allowlist via busca no Menu Iniciar/`shutil.which`
— mas **rejeita** qualquer nome contendo `\`, `/` ou `:` antes disso, porque
`shutil.which` trata um caminho absoluto como válido diretamente, o que
seria um bypass completo da allowlist (ex.: pedir para "abrir"
`C:\Windows\System32\cmd.exe` literal).

## Conteúdo observado nunca é instrução

Regra central (reforçada tanto no prompt de sistema quanto no código):
texto que o Silva **ouviu** ou **viu** (áudio do jogo/PC transcrito, OCR da
tela, resultado de busca na web) é informação para comentar, nunca um
comando para obedecer — mesmo que esteja escrito como uma ordem direta.

- **Nível de prompt** (`src/ai/prompts.py`, `src/core/research.py`): instrui
  o modelo explicitamente a tratar conteúdo observado como dado, não comando.
- **Nível de código** (`is_direct_input` em `handle_user_message`): todo
  gatilho determinístico por palavra-chave (Modo Nerd, lembrete, visão,
  tradução) só dispara para input que o usuário realmente digitou/falou —
  nunca para áudio do sistema meramente transcrito. Sem isso, um vídeo
  tocando "Silva, vira nerd" mudaria configurações de verdade.
- **Última linha de defesa**: o próprio fluxo CONFIRM acima, para qualquer
  ação de maior risco que a IA tente executar de qualquer forma.

## Validação de parâmetros vindos da IA

Toda função de despacho em `tool_registry.py` valida o **tipo**, não só a
truthiness, do `action_param` — a IA pode alucinar qualquer shape JSON
decodificável (dict, lista, número, bool) em vez do que a ferramenta espera.
Um `action_param` do tipo errado vira um "não executou" limpo, nunca uma
exceção não tratada vazando (ex.: `_forget_memory` exige `isinstance(key,
str)`; antes disso um dict vazio resolvia `key=None` e ainda reportava
sucesso).

## Segredos

- Chave de API fica em `.env` ao lado de `config.json`, nunca no
  `config.json` versionado.
- `_redact_secret()` (`src/ai/provider.py`) remove a chave de qualquer
  mensagem de erro antes de logar **ou** de devolver como fala — uma
  exceção de rede que ecoasse a chave de volta não vaza nem no log nem na
  voz do Silva.
- `diagnostics.py` reporta só presença/ausência de chave configurada, nunca
  o valor.

## Mouse/teclado e terminal (FASE 3) — a camada extra de opt-in

Estas duas categorias somam uma proteção que nenhuma outra ferramenta tem:
um **interruptor mestre** em Configurações → Agente
(`input_control_enabled` / `terminal_tool_enabled`), **desligado por
padrão**. Enquanto desligado, o objeto que faria o trabalho
(`InputController`/`TerminalToolManager`) nem é construído no
`CompanionOrchestrator.__init__` — a ferramenta correspondente fica sem
`dispatch` no `ToolRegistry`, então mesmo que a IA "decida" chamá-la, nada
acontece (mesmo caminho seguro de "ação desconhecida" que qualquer nome de
ferramenta inválido já usa). Isso é mais forte que só recusar no diálogo:
a capacidade genuinamente não existe até o usuário optar por ela.

Com o interruptor ligado, tier CONFIRM ainda se aplica normalmente — cada
clique/tecla/execução de terminal passa pelo fluxo de confirmação descrito
acima, podendo virar política ALWAYS/SESSION salva como qualquer outra ação
CONFIRM.

O terminal, além disso, tem sua própria allowlist (Configurações → Agente,
**vazia por padrão** — nenhum binário roda até ser adicionado manualmente),
nunca usa `shell=True`, valida argumentos contra caracteres de metasintaxe
de shell, limita tempo de execução (30s) e tamanho de saída (4000
caracteres), e cada execução é logada via `TERMINAL_TOOL_EXECUTED`.

## Testes de segurança dedicados

`tests/test_security_*.py` cobre especificamente: argumentos inválidos/
malformados vindos da IA, bypass de permissão, ferramentas malformadas, e
vazamento de segredos — não são testes de feature, são testes de que um
input adversarial (intencional ou alucinado) não consegue contornar as
camadas acima.
