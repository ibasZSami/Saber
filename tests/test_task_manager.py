from src.core.event_bus import EventBus
from src.core.task_manager import REPETITION_LIMIT, TaskManager, TaskStatus


def _manager():
    bus = EventBus()
    bus.reset()
    return TaskManager(bus), bus


class TestCreateTask:
    def test_creates_a_pending_task_with_the_given_goal(self):
        manager, _ = _manager()
        task = manager.create_task("abrir o navegador e pesquisar gatos")
        assert task.status == TaskStatus.PENDING
        assert task.goal == "abrir o navegador e pesquisar gatos"
        assert task.step_count == 0

    def test_uses_default_limits_when_not_given(self):
        manager, _ = _manager()
        task = manager.create_task("x")
        assert task.max_steps > 0
        assert task.timeout_seconds > 0

    def test_custom_limits_are_respected(self):
        manager, _ = _manager()
        task = manager.create_task("x", max_steps=3, timeout_seconds=10.0)
        assert task.max_steps == 3
        assert task.timeout_seconds == 10.0

    def test_list_tasks_includes_created_tasks(self):
        manager, _ = _manager()
        task = manager.create_task("x")
        assert task in manager.list_tasks()


class TestLifecycle:
    def test_start_sets_running_and_emits_event(self):
        manager, bus = _manager()
        received = []
        bus.subscribe("TASK_LOOP_STARTED", lambda **kw: received.append(kw))
        task = manager.create_task("x")

        manager.start(task.id)

        assert manager.get_task(task.id).status == TaskStatus.RUNNING
        assert received == [{"task_id": task.id, "goal": "x"}]

    def test_pause_only_takes_effect_while_running(self):
        manager, bus = _manager()
        received = []
        bus.subscribe("TASK_LOOP_PAUSED", lambda **kw: received.append(kw))
        task = manager.create_task("x")

        manager.pause(task.id)  # still PENDING — no-op

        assert manager.get_task(task.id).status == TaskStatus.PENDING
        assert received == []

        manager.start(task.id)
        manager.pause(task.id)

        assert manager.get_task(task.id).status == TaskStatus.PAUSED
        assert len(received) == 1

    def test_resume_only_takes_effect_while_paused(self):
        manager, bus = _manager()
        received = []
        bus.subscribe("TASK_LOOP_RESUMED", lambda **kw: received.append(kw))
        task = manager.create_task("x")
        manager.start(task.id)

        manager.resume(task.id)  # was RUNNING, not PAUSED — no-op
        assert received == []

        manager.pause(task.id)
        manager.resume(task.id)
        assert manager.get_task(task.id).status == TaskStatus.RUNNING
        assert len(received) == 1

    def test_cancel_from_running(self):
        manager, bus = _manager()
        received = []
        bus.subscribe("TASK_LOOP_CANCELLED", lambda **kw: received.append(kw))
        task = manager.create_task("x")
        manager.start(task.id)

        manager.cancel(task.id)

        assert manager.get_task(task.id).status == TaskStatus.CANCELLED
        assert received == [{"task_id": task.id}]

    def test_cancel_from_pending_and_paused_too(self):
        manager, _ = _manager()
        pending_task = manager.create_task("x")
        manager.cancel(pending_task.id)
        assert manager.get_task(pending_task.id).status == TaskStatus.CANCELLED

        paused_task = manager.create_task("y")
        manager.start(paused_task.id)
        manager.pause(paused_task.id)
        manager.cancel(paused_task.id)
        assert manager.get_task(paused_task.id).status == TaskStatus.CANCELLED

    def test_cancel_a_finished_task_does_nothing(self):
        manager, bus = _manager()
        received = []
        bus.subscribe("TASK_LOOP_CANCELLED", lambda **kw: received.append(kw))
        task = manager.create_task("x")
        manager.start(task.id)
        manager.complete(task.id, "ok")

        manager.cancel(task.id)

        assert manager.get_task(task.id).status == TaskStatus.COMPLETED
        assert received == []

    def test_complete_sets_result(self):
        manager, bus = _manager()
        received = []
        bus.subscribe("TASK_LOOP_COMPLETED", lambda **kw: received.append(kw))
        task = manager.create_task("x")

        manager.complete(task.id, "preço é R$50")

        assert manager.get_task(task.id).status == TaskStatus.COMPLETED
        assert manager.get_task(task.id).result == "preço é R$50"
        assert received == [{"task_id": task.id, "result": "preço é R$50"}]

    def test_fail_sets_error(self):
        manager, bus = _manager()
        received = []
        bus.subscribe("TASK_LOOP_FAILED", lambda **kw: received.append(kw))
        task = manager.create_task("x")

        manager.fail(task.id, "deu ruim")

        assert manager.get_task(task.id).status == TaskStatus.FAILED
        assert manager.get_task(task.id).error == "deu ruim"
        assert received == [{"task_id": task.id, "error": "deu ruim"}]


class TestRecordStep:
    def test_appends_a_step_and_emits_event(self):
        manager, bus = _manager()
        received = []
        bus.subscribe("TASK_LOOP_STEP", lambda **kw: received.append(kw))
        task = manager.create_task("x")

        manager.record_step(task.id, "search_web", "gatos", "Ação executada com sucesso.")

        assert manager.get_task(task.id).step_count == 1
        step = manager.get_task(task.id).steps[0]
        assert step.action == "search_web"
        assert step.action_param == "gatos"
        assert step.observation == "Ação executada com sucesso."
        assert received == [{
            "task_id": task.id, "action": "search_web", "action_param": "gatos",
            "observation": "Ação executada com sucesso.", "step_number": 1,
        }]


class TestExceededLimits:
    def test_within_limits_returns_none(self):
        manager, _ = _manager()
        task = manager.create_task("x", max_steps=5, timeout_seconds=100.0)
        assert manager.exceeded_limits(task.id) is None

    def test_max_steps_reached(self):
        manager, _ = _manager()
        task = manager.create_task("x", max_steps=2, timeout_seconds=100.0)
        manager.record_step(task.id, "a", "1", "ok")
        manager.record_step(task.id, "a", "2", "ok")
        assert "passos" in manager.exceeded_limits(task.id)

    def test_timeout_reached(self):
        manager, _ = _manager()
        task = manager.create_task("x", max_steps=100, timeout_seconds=0.0)
        assert "Tempo limite" in manager.exceeded_limits(task.id)

    def test_repetition_detected(self):
        manager, _ = _manager()
        task = manager.create_task("x", max_steps=100, timeout_seconds=100.0)
        for _ in range(REPETITION_LIMIT):
            manager.record_step(task.id, "open_application", "chrome", "falhou")
        assert "repetiu" in manager.exceeded_limits(task.id)

    def test_alternating_actions_do_not_count_as_repetition(self):
        manager, _ = _manager()
        task = manager.create_task("x", max_steps=100, timeout_seconds=100.0)
        for i in range(REPETITION_LIMIT):
            manager.record_step(task.id, "search_web", f"query {i}", "ok")
        assert manager.exceeded_limits(task.id) is None

    def test_fewer_than_limit_repeats_do_not_trigger(self):
        manager, _ = _manager()
        task = manager.create_task("x", max_steps=100, timeout_seconds=100.0)
        for _ in range(REPETITION_LIMIT - 1):
            manager.record_step(task.id, "open_application", "chrome", "falhou")
        assert manager.exceeded_limits(task.id) is None
