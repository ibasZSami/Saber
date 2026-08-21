from src.core.event_bus import EventBus
from src.core.scheduler import Scheduler
from src.memory.database import Database


def _scheduler(tmp_path, on_fire=None):
    db = Database(db_path=str(tmp_path / "test.db"))
    bus = EventBus()
    bus.reset()
    fired = []
    return Scheduler(db, bus, on_fire=on_fire or (lambda msg: fired.append(msg))), bus, fired


class TestCreateAndList:
    def test_create_returns_an_id_and_persists_the_reminder(self, tmp_path):
        scheduler, _, _ = _scheduler(tmp_path)
        reminder_id = scheduler.create("tirar o bolo", fire_at=9999999999.0)

        pending = scheduler.list_pending()

        assert len(pending) == 1
        assert pending[0].id == reminder_id
        assert pending[0].message == "tirar o bolo"

    def test_create_emits_reminder_created(self, tmp_path):
        scheduler, bus, _ = _scheduler(tmp_path)
        received = []
        bus.subscribe("REMINDER_CREATED", lambda **kw: received.append(kw))

        scheduler.create("beber água", fire_at=123.0)

        assert received == [{"reminder_id": 1, "message": "beber água", "fire_at": 123.0}]


class TestCancel:
    def test_cancel_removes_the_reminder(self, tmp_path):
        scheduler, _, _ = _scheduler(tmp_path)
        reminder_id = scheduler.create("algo", fire_at=9999999999.0)

        scheduler.cancel(reminder_id)

        assert scheduler.list_pending() == []


class TestCheckDue:
    def test_due_reminder_fires_the_callback(self, tmp_path):
        scheduler, _, fired = _scheduler(tmp_path)
        scheduler.create("tirar o bolo", fire_at=1000.0)

        scheduler.check_due(now=1001.0)

        assert fired == ["tirar o bolo"]

    def test_not_yet_due_reminder_does_not_fire(self, tmp_path):
        scheduler, _, fired = _scheduler(tmp_path)
        scheduler.create("algo no futuro", fire_at=9999999999.0)

        scheduler.check_due(now=1001.0)

        assert fired == []

    def test_one_shot_reminder_is_removed_after_firing(self, tmp_path):
        scheduler, _, _ = _scheduler(tmp_path)
        scheduler.create("algo", fire_at=1000.0)

        scheduler.check_due(now=1001.0)

        assert scheduler.list_pending() == []

    def test_recurring_reminder_is_rescheduled_not_removed(self, tmp_path):
        scheduler, _, fired = _scheduler(tmp_path)
        scheduler.create("beber água", fire_at=1000.0, recurring_seconds=3600.0)

        scheduler.check_due(now=1001.0)

        pending = scheduler.list_pending()
        assert len(pending) == 1
        assert pending[0].fire_at == 1001.0 + 3600.0
        assert fired == ["beber água"]

    def test_emits_reminder_fired(self, tmp_path):
        scheduler, bus, _ = _scheduler(tmp_path)
        received = []
        bus.subscribe("REMINDER_FIRED", lambda **kw: received.append(kw))
        reminder_id = scheduler.create("algo", fire_at=1000.0)

        scheduler.check_due(now=1001.0)

        assert received == [{"reminder_id": reminder_id, "message": "algo"}]

    def test_a_crashing_callback_does_not_prevent_the_reminder_from_being_cleared(self, tmp_path):
        """Regression guard: one bad callback must not jam every reminder
        behind it forever — see Scheduler.check_due's docstring."""
        def _boom(msg):
            raise RuntimeError("boom")

        scheduler, _, _ = _scheduler(tmp_path, on_fire=_boom)
        scheduler.create("algo", fire_at=1000.0)

        scheduler.check_due(now=1001.0)  # must not raise

        assert scheduler.list_pending() == []

    def test_multiple_due_reminders_all_fire(self, tmp_path):
        scheduler, _, fired = _scheduler(tmp_path)
        scheduler.create("primeiro", fire_at=1000.0)
        scheduler.create("segundo", fire_at=1000.0)

        scheduler.check_due(now=1001.0)

        assert sorted(fired) == ["primeiro", "segundo"]
