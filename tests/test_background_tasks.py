import threading
import time

from src.core.background_tasks import BackgroundTaskManager, STATUS_COMPLETED, STATUS_FAILED
from src.core.event_bus import EventBus


class _SyncThread:
    """Stand-in for threading.Thread that runs its target immediately and
    synchronously on .start(), so background-task effects can be asserted on
    directly instead of racing a real thread."""

    def __init__(self, target=None, args=(), kwargs=None, **_ignored):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        self._target(*self._args, **self._kwargs)


def _capture(event_bus, event_type):
    received = []
    event_bus.subscribe(event_type, lambda **kwargs: received.append(kwargs))
    return received


class TestCreateTaskSync:
    """Uses _SyncThread so the task's work_fn runs synchronously, making the
    final state directly assertable without waiting/polling."""

    def test_successful_task_completes_with_result(self, monkeypatch):
        monkeypatch.setattr(threading, "Thread", _SyncThread)
        manager = BackgroundTaskManager(EventBus())

        task_id = manager.create_task("research", "pesquisa X", lambda: "resultado final")

        task = manager.get_task(task_id)
        assert task["status"] == STATUS_COMPLETED
        assert task["result"] == "resultado final"
        assert task["error"] is None
        assert task["finished_at"] is not None

    def test_failed_task_records_error(self, monkeypatch):
        monkeypatch.setattr(threading, "Thread", _SyncThread)
        manager = BackgroundTaskManager(EventBus())

        def _boom():
            raise RuntimeError("network down")

        task_id = manager.create_task("research", "pesquisa Y", _boom)

        task = manager.get_task(task_id)
        assert task["status"] == STATUS_FAILED
        assert task["error"] == "network down"
        assert task["result"] is None

    def test_emits_started_then_completed(self, monkeypatch):
        monkeypatch.setattr(threading, "Thread", _SyncThread)
        event_bus = EventBus()
        started = _capture(event_bus, "TASK_STARTED")
        completed = _capture(event_bus, "TASK_COMPLETED")
        manager = BackgroundTaskManager(event_bus)

        task_id = manager.create_task("research", "pesquisa Z", lambda: "ok")

        assert len(started) == 1 and started[0]["task_id"] == task_id
        assert len(completed) == 1 and completed[0]["result"] == "ok"

    def test_emits_failed_not_completed_on_exception(self, monkeypatch):
        monkeypatch.setattr(threading, "Thread", _SyncThread)
        event_bus = EventBus()
        completed = _capture(event_bus, "TASK_COMPLETED")
        failed = _capture(event_bus, "TASK_FAILED")
        manager = BackgroundTaskManager(event_bus)

        manager.create_task("research", "pesquisa W", lambda: (_ for _ in ()).throw(ValueError("bad")))

        assert completed == []
        assert len(failed) == 1
        assert failed[0]["error"] == "bad"


class TestTaskLookup:
    def test_get_unknown_task_returns_none(self):
        manager = BackgroundTaskManager(EventBus())
        assert manager.get_task("does-not-exist") is None

    def test_list_tasks_returns_all_created(self, monkeypatch):
        monkeypatch.setattr(threading, "Thread", _SyncThread)
        manager = BackgroundTaskManager(EventBus())

        id1 = manager.create_task("research", "a", lambda: 1)
        id2 = manager.create_task("research", "b", lambda: 2)

        ids = {t["id"] for t in manager.list_tasks()}
        assert ids == {id1, id2}

    def test_get_task_returns_a_copy_not_the_live_dict(self, monkeypatch):
        """Callers shouldn't be able to mutate internal task state by editing
        the dict they got back from get_task()."""
        monkeypatch.setattr(threading, "Thread", _SyncThread)
        manager = BackgroundTaskManager(EventBus())
        task_id = manager.create_task("research", "a", lambda: 1)

        snapshot = manager.get_task(task_id)
        snapshot["status"] = "TAMPERED"

        assert manager.get_task(task_id)["status"] != "TAMPERED"


class TestRealThreading:
    """One real (non-mocked) threaded run, to confirm create_task() doesn't
    block the caller and the app stays responsive while work runs."""

    def test_create_task_returns_before_work_finishes(self):
        manager = BackgroundTaskManager(EventBus())
        release = threading.Event()

        def _slow_work():
            release.wait(timeout=2)
            return "done"

        start = time.monotonic()
        task_id = manager.create_task("research", "slow", _slow_work)
        elapsed = time.monotonic() - start

        assert elapsed < 0.5  # returned immediately, didn't wait for _slow_work
        assert manager.get_task(task_id)["status"] in ("PENDING", "RUNNING")

        release.set()  # let the background thread finish and clean up
        for _ in range(50):
            if manager.get_task(task_id)["status"] == STATUS_COMPLETED:
                break
            time.sleep(0.05)
        assert manager.get_task(task_id)["status"] == STATUS_COMPLETED
