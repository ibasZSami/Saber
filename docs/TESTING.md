# Testes

```
pytest tests/ --cov=src --cov-report=term-missing
```

Roda automaticamente a cada push/PR via GitHub Actions (`windows-latest`,
já que o app depende de bibliotecas Windows-only — pycaw, winreg,
`keyboard`, comtypes). Para lint (erros reais, não estilo):

```
ruff check --select E9,F src/ tests/ main.py
```

## Padrões usados neste projeto

### Construção "bare" do orquestrador

`CompanionOrchestrator.__new__(CompanionOrchestrator)` constrói a instância
**sem** rodar `__init__` (que exige sprites, chaves de API, dispositivos de
áudio reais). O teste então atribui só os atributos que o método sob teste
de fato usa:

```python
orch = CompanionOrchestrator.__new__(CompanionOrchestrator)
orch.settings = FakeSettings(screen_monitoring_enabled=True, private_mode=False)
orch.event_bus = EventBus()
...
```

Isso mantém os testes de lógica de orquestração rápidos e isolados de Qt/
hardware real, sem precisar mockar o `__init__` inteiro.

### Reset do EventBus entre testes

`EventBus` é um singleton por processo. `tests/conftest.py` tem uma fixture
`autouse` que chama `EventBus().reset()` antes e depois de cada teste — sem
isso, subscribers registrados por um teste vazariam para os seguintes
(especialmente relevante desde que o dispatch passou a rodar por um sinal
Qt real, que pode entregar de forma enfileirada).

### `_capture` para asserções em eventos

Helper comum nos arquivos de teste:

```python
def _capture(event_bus, event_type):
    received = []
    event_bus.subscribe(event_type, lambda **kwargs: received.append(kwargs))
    return received
```

### Thread síncrona para caminhos determinísticos

Vários métodos do orquestrador (`handle_user_message`, `_trigger_spontaneous_comment`)
disparam uma `threading.Thread` de verdade. Para testar o resultado de forma
síncrona sem sleep/polling, os testes fazem `monkeypatch.setattr(threading,
"Thread", _SyncThread)`, onde `_SyncThread` roda o `target` imediatamente em
vez de agendar numa thread real.

### Cross-thread real quando o mecanismo em si é o que está sob teste

Quando o teste é sobre thread-safety de verdade (ex.: `EventBus` entregando
de uma thread de fundo para a GUI), usar uma thread real + bombear
`QApplication.processEvents()` num loop limitado por timeout — mockar a
Thread aqui esconderia exatamente o bug que o teste existe para pegar.

### Isolamento de arquivo (Settings, Database)

Testes que tocam `Settings` ou `Database` usam a fixture `tmp_path` do
pytest para apontar `config_path`/`db_path` para um arquivo temporário —
nunca para o `config.json`/`memory.db` reais do projeto.
