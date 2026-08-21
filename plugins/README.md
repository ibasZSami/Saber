# Plugins do Silva

Um plugin é um arquivo `.py` nesta pasta que expõe uma função `register(context)`.
Ela roda uma vez, quando a Silva inicia (só se **Configurações → Agente → Permitir
plugins** estiver ligado — desligado por padrão).

```python
from src.core.tool_registry import ToolSpec, PermissionTier

def register(context):
    context.register_tool(ToolSpec(
        name="minha_ferramenta",
        tier=PermissionTier.SAFE,  # ou CONFIRM se a ação tiver efeito real
        description="O que essa ferramenta faz — a IA lê isso pra saber quando usar.",
        dispatch=lambda action_param: True,  # sua lógica aqui; retorna True/False (sucesso)
        parameters={"algum_campo": "string"},  # opcional
    ))
```

`context` também dá acesso a:
- `context.event_bus` — pra emitir/assinar eventos (`src/core/event_bus.py`).
- `context.settings` — leitura/escrita de configuração (`Settings.get`/`Settings.set`).

## Segurança — leia antes de instalar um plugin de terceiros

Um plugin é código Python de verdade, rodando dentro do processo da Silva — **não é
uma sandbox**. A função `dispatch` de um plugin pode fazer qualquer coisa que
código Python normal faz, sem passar pelas mesmas travas que `run_terminal_tool`
ou `browser_navigate` têm (allowlist, sem shell, etc.) a menos que o próprio autor
do plugin escolha construir isso. Só instale plugins de fontes em que você confia,
do mesmo jeito que só instalaria qualquer outro programa. Tier `CONFIRM` numa
ferramenta de plugin ainda pede confirmação real antes de rodar (mesmo fluxo de
`AgentCore`), então prefira isso pra qualquer ação com efeito real no sistema.

Um plugin quebrado (erro de sintaxe, exceção no `register`, sem função `register`)
nunca derruba o app inteiro — só aquele plugin específico fica de fora, com o erro
registrado no log.

Veja `example_dice.py` nesta pasta pra um exemplo funcional completo.
