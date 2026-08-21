import threading
import time

from PySide6.QtWidgets import QApplication

from src.core.event_bus import EventBus

_PUMP_TIMEOUT_S = 5.0


def _capture(event_bus, event_type):
    received = []
    event_bus.subscribe(event_type, lambda **kwargs: received.append(kwargs))
    return received


def _pump_until(condition, timeout_s=_PUMP_TIMEOUT_S):
    """emit() from a worker thread is Qt.AutoConnection-queued, not blocking
    — it posts the event and returns immediately, so the worker thread
    finishing tells us nothing about whether dispatch has actually happened
    yet. Poll the real condition instead, with a bound so a genuine wiring
    bug fails fast instead of hanging the suite."""
    deadline = time.monotonic() + timeout_s
    while not condition():
        QApplication.processEvents()
        if time.monotonic() > deadline:
            raise AssertionError("cross-thread event was never delivered")


def _emit_on_worker_thread_and_pump(event_bus, event_type, received_list, **kwargs):
    """Fires emit() from a real background thread and pumps the Qt event
    loop on the calling (main/test) thread until delivery actually lands —
    mirrors the pattern used for ConfirmationBridge, since this exercises the
    same underlying Qt.AutoConnection cross-thread mechanism."""
    thread = threading.Thread(target=lambda: event_bus.emit(event_type, **kwargs), daemon=True)
    thread.start()
    _pump_until(lambda: len(received_list) > 0)
    thread.join()


class TestEventBusSingleton:
    def test_returns_the_same_instance(self):
        assert EventBus() is EventBus()


class TestSubscribeAndEmit:
    def test_same_thread_emit_is_synchronous(self):
        """No event-loop pump needed here — Qt.AutoConnection resolves same-
        thread emit()/dispatcher as a direct call, identical to the old
        plain-Python behavior every existing test already relies on."""
        bus = EventBus()
        received = _capture(bus, "TEST_EVENT_SYNC")

        bus.emit("TEST_EVENT_SYNC", value=42)

        assert received == [{"value": 42}]

    def test_duplicate_subscribe_is_not_called_twice(self):
        bus = EventBus()
        received = []

        def cb(**kwargs):
            received.append(kwargs)

        bus.subscribe("TEST_EVENT_DUP", cb)
        bus.subscribe("TEST_EVENT_DUP", cb)
        bus.emit("TEST_EVENT_DUP")

        assert len(received) == 1

    def test_unsubscribe_stops_delivery(self):
        bus = EventBus()
        received = []

        def cb(**kwargs):
            received.append(kwargs)

        bus.subscribe("TEST_EVENT_UNSUB", cb)
        bus.unsubscribe("TEST_EVENT_UNSUB", cb)
        bus.emit("TEST_EVENT_UNSUB")

        assert received == []

    def test_exception_in_one_subscriber_does_not_stop_others(self):
        bus = EventBus()
        received = []
        bus.subscribe("TEST_EVENT_ERR", lambda **kw: (_ for _ in ()).throw(RuntimeError("boom")))
        bus.subscribe("TEST_EVENT_ERR", lambda **kw: received.append("second ran"))

        bus.emit("TEST_EVENT_ERR")  # must not raise

        assert received == ["second ran"]


class TestCrossThreadDispatch:
    """The actual FASE 3 fix: a subscriber must be safely reachable from an
    emit() called on a background worker thread, without any bespoke
    Signal/QueuedConnection of its own (unlike chat_window.py's fix, which
    needed one because it predates this)."""

    def test_emit_from_background_thread_is_delivered(self):
        bus = EventBus()
        received = _capture(bus, "TEST_EVENT_CROSS_THREAD")

        _emit_on_worker_thread_and_pump(bus, "TEST_EVENT_CROSS_THREAD", received, speech="oi de outra thread")

        assert received == [{"speech": "oi de outra thread"}]

    def test_cross_thread_dispatch_runs_on_the_main_thread(self):
        bus = EventBus()
        seen_thread_ids = []
        bus.subscribe("TEST_EVENT_THREAD_ID", lambda **kw: seen_thread_ids.append(threading.get_ident()))
        worker_thread_id = {}

        def _worker():
            worker_thread_id["id"] = threading.get_ident()
            bus.emit("TEST_EVENT_THREAD_ID")

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        _pump_until(lambda: len(seen_thread_ids) > 0)
        thread.join()

        assert seen_thread_ids == [threading.get_ident()]  # ran on the main/test thread
        assert worker_thread_id["id"] != threading.get_ident()  # emitted from a genuinely different thread


class TestReset:
    def test_reset_clears_all_subscribers(self):
        bus = EventBus()
        received = _capture(bus, "TEST_EVENT_RESET")

        bus.reset()
        bus.emit("TEST_EVENT_RESET")

        assert received == []
