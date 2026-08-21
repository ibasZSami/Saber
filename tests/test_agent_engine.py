from unittest.mock import MagicMock

from src.core.agent_core import AgentCore
from src.core.agent_engine import AgentEngine
from src.core.event_bus import EventBus
from src.core.task_manager import TaskManager, TaskStatus
from src.core.tool_registry import build_default_registry


class _SyncThread:
    """Stand-in for threading.Thread that runs its target immediately and
    synchronously on .start() — see tests/test_orchestrator_actions.py for
    the original of this pattern."""

    def __init__(self, target=None, args=(), kwargs=None, **_ignored):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        self._target(*self._args, **self._kwargs)


def _bus():
    bus = EventBus()
    bus.reset()
    return bus


def _engine(ai_provider=None, action_manager=None, memory_manager=None):
    bus = _bus()
    action_manager = action_manager or MagicMock()
    memory_manager = memory_manager or MagicMock()
    registry = build_default_registry(action_manager, memory_manager)
    agent_core = AgentCore(registry, bus)
    task_manager = TaskManager(bus)
    ai_provider = ai_provider or MagicMock()
    engine = AgentEngine(ai_provider, agent_core, task_manager, bus)
    return engine, task_manager, action_manager, bus


class TestSingleStepCompletion:
    def test_immediately_done_completes_the_task(self, monkeypatch):
        import threading
        engine, task_manager, _, _ = _engine()
        engine.ai_provider.chat.return_value = (
            '{"thought": "sei a resposta", "done": true, "result": "42", '
            '"action": "Nenhuma", "action_param": ""}'
        )
        monkeypatch.setattr(threading, "Thread", _SyncThread)
        finished = []

        task_id = engine.run("qual a resposta?", on_finish=lambda r, ok: finished.append((r, ok)))

        assert task_manager.get_task(task_id).status == TaskStatus.COMPLETED
        assert task_manager.get_task(task_id).result == "42"
        assert finished == [("42", True)]

    def test_malformed_ai_output_ends_the_task_as_completed_with_an_explanation(self, monkeypatch):
        import threading
        engine, task_manager, _, _ = _engine()
        engine.ai_provider.chat.return_value = "isso não é JSON"
        monkeypatch.setattr(threading, "Thread", _SyncThread)
        finished = []

        task_id = engine.run("x", on_finish=lambda r, ok: finished.append((r, ok)))

        assert task_manager.get_task(task_id).status == TaskStatus.COMPLETED
        assert finished[0][1] is True
        assert "consegui" in finished[0][0] or "interpretar" in finished[0][0]


class TestMultiStepExecution:
    def test_executes_a_tool_then_completes(self, monkeypatch):
        import threading
        action_manager = MagicMock()
        action_manager.search_web.return_value = True
        engine, task_manager, action_manager, _ = _engine(action_manager=action_manager)
        engine.ai_provider.chat.side_effect = [
            '{"done": false, "action": "search_web", "action_param": "preço do produto X"}',
            '{"done": true, "result": "o preço é R$50", "action": "Nenhuma", "action_param": ""}',
        ]
        monkeypatch.setattr(threading, "Thread", _SyncThread)

        task_id = engine.run("descobrir o preço do produto X")

        task = task_manager.get_task(task_id)
        assert task.status == TaskStatus.COMPLETED
        assert task.step_count == 1
        assert task.steps[0].action == "search_web"
        action_manager.search_web.assert_called_once_with("preço do produto X")

    def test_failed_tool_call_is_recorded_and_loop_continues(self, monkeypatch):
        import threading
        action_manager = MagicMock()
        action_manager.search_web.return_value = False  # tool reports failure
        engine, task_manager, action_manager, _ = _engine(action_manager=action_manager)
        engine.ai_provider.chat.side_effect = [
            '{"done": false, "action": "search_web", "action_param": "notepad"}',
            '{"done": true, "result": "desisti", "action": "Nenhuma", "action_param": ""}',
        ]
        monkeypatch.setattr(threading, "Thread", _SyncThread)

        task_id = engine.run("x")

        task = task_manager.get_task(task_id)
        assert "falhou" in task.steps[0].observation or "recusada" in task.steps[0].observation
        assert task.status == TaskStatus.COMPLETED


class TestRichObservation:
    """FASE 8 — a tool with real output (observe_screen's OCR text, a
    terminal command's stdout) must surface it as the step's observation,
    not just a generic success/failure line — see AgentCore.execute_with_detail."""

    def test_tuple_dispatch_detail_becomes_the_observation_on_success(self, monkeypatch):
        import threading
        from src.core.tool_registry import ToolRegistry, ToolSpec, PermissionTier
        registry = ToolRegistry()
        registry.register(ToolSpec(
            name="observe_screen", tier=PermissionTier.SAFE, description="test",
            dispatch=lambda p: (True, "Inventário: 64/64 madeira"),
        ))
        bus = EventBus()
        bus.reset()
        agent_core = AgentCore(registry, bus)
        task_manager = TaskManager(bus)
        engine = AgentEngine(MagicMock(), agent_core, task_manager, bus)
        engine.ai_provider.chat.side_effect = [
            '{"done": false, "action": "observe_screen", "action_param": ""}',
            '{"done": true, "result": "inventário cheio", "action": "Nenhuma", "action_param": ""}',
        ]
        monkeypatch.setattr(threading, "Thread", _SyncThread)

        task_id = engine.run("verificar inventário")

        task = task_manager.get_task(task_id)
        assert task.steps[0].observation == "Inventário: 64/64 madeira"

    def test_tuple_dispatch_detail_is_prefixed_on_failure(self, monkeypatch):
        import threading
        from src.core.tool_registry import ToolRegistry, ToolSpec, PermissionTier
        registry = ToolRegistry()
        registry.register(ToolSpec(
            name="run_terminal_tool", tier=PermissionTier.CONFIRM, description="test",
            dispatch=lambda p: (False, "não está na allowlist"),
        ))
        bus = EventBus()
        bus.reset()
        agent_core = AgentCore(registry, bus)
        task_manager = TaskManager(bus)
        engine = AgentEngine(MagicMock(), agent_core, task_manager, bus)
        engine.ai_provider.chat.side_effect = [
            '{"done": false, "action": "run_terminal_tool", "action_param": {"name": "nmap"}}',
            '{"done": true, "result": "não deu", "action": "Nenhuma", "action_param": ""}',
        ]
        monkeypatch.setattr(threading, "Thread", _SyncThread)

        task_id = engine.run("rodar nmap")

        task = task_manager.get_task(task_id)
        assert task.steps[0].observation == "Falhou: não está na allowlist"


class TestSafetyLimits:
    def test_stops_at_max_steps(self, monkeypatch):
        import threading
        action_manager = MagicMock()
        action_manager.search_web.return_value = True
        engine, task_manager, _, _ = _engine(action_manager=action_manager)
        # Always a different query, so this never trips repetition detection —
        # isolates the max_steps limit specifically.
        counter = {"n": 0}

        def _fake_chat(prompt, system_prompt, history, image_base64=None):
            counter["n"] += 1
            return f'{{"done": false, "action": "search_web", "action_param": "query {counter["n"]}"}}'

        engine.ai_provider.chat.side_effect = _fake_chat
        monkeypatch.setattr(threading, "Thread", _SyncThread)
        finished = []

        task_id = engine.run("x", on_finish=lambda r, ok: finished.append((r, ok)), max_steps=3)

        task = task_manager.get_task(task_id)
        assert task.status == TaskStatus.FAILED
        assert task.step_count == 3
        assert "passos" in task.error
        assert finished[0][1] is False

    def test_stops_on_repetition(self, monkeypatch):
        import threading
        action_manager = MagicMock()
        action_manager.open_application.return_value = False
        engine, task_manager, _, _ = _engine(action_manager=action_manager)
        engine.ai_provider.chat.return_value = (
            '{"done": false, "action": "open_application", "action_param": "chrome"}'
        )
        monkeypatch.setattr(threading, "Thread", _SyncThread)
        finished = []

        task_id = engine.run("x", on_finish=lambda r, ok: finished.append((r, ok)), max_steps=100)

        task = task_manager.get_task(task_id)
        assert task.status == TaskStatus.FAILED
        assert "repetiu" in task.error
        assert finished[0][1] is False

    def test_provider_exception_fails_the_task_instead_of_crashing_the_thread(self, monkeypatch):
        import threading
        engine, task_manager, _, _ = _engine()
        engine.ai_provider.chat.side_effect = RuntimeError("network down")
        monkeypatch.setattr(threading, "Thread", _SyncThread)
        finished = []

        task_id = engine.run("x", on_finish=lambda r, ok: finished.append((r, ok)))

        task = task_manager.get_task(task_id)
        assert task.status == TaskStatus.FAILED
        assert "network down" in task.error
        assert finished == [("network down", False)]


class TestCancellation:
    def test_task_cancelled_before_the_loop_starts_is_never_resurrected_to_running(self):
        engine, task_manager, _, _ = _engine()
        task = task_manager.create_task("x")
        task_manager.cancel(task.id)
        finished = []

        engine._run_loop(task.id, lambda r, ok: finished.append((r, ok)))

        assert task_manager.get_task(task.id).status == TaskStatus.CANCELLED
        assert finished == []

    def test_cancel_signaled_mid_loop_stops_before_the_next_step(self, monkeypatch):
        import threading
        action_manager = MagicMock()
        action_manager.search_web.return_value = True
        engine, task_manager, _, _ = _engine(action_manager=action_manager)

        def _fake_chat(prompt, system_prompt, history, image_base64=None):
            task = task_manager.list_tasks()[-1]
            if task.step_count == 0:
                task_manager.cancel(task.id)
            return '{"done": false, "action": "search_web", "action_param": "gatos"}'

        engine.ai_provider.chat.side_effect = _fake_chat
        monkeypatch.setattr(threading, "Thread", _SyncThread)
        finished = []

        task_id = engine.run("x", on_finish=lambda r, ok: finished.append((r, ok)))

        task = task_manager.get_task(task_id)
        assert task.status == TaskStatus.CANCELLED
        assert task.step_count == 1  # the in-flight step still completed
        assert finished == []  # cancellation never calls on_finish
