from datetime import datetime

from src.core.reminder_parser import parse


class TestNoTrigger:
    def test_ordinary_message_returns_none(self):
        assert parse("qual é a capital da frança?") is None

    def test_time_phrase_without_a_trigger_word_returns_none(self):
        assert parse("às 18h eu vou sair") is None


class TestRelativeReminders:
    def test_minutes(self):
        now = 1_700_000_000.0
        parsed = parse("me lembra em 10 minutos de tirar o bolo", now=now)
        assert parsed is not None
        assert parsed.fire_at == now + 600
        assert parsed.recurring_seconds is None
        assert "bolo" in parsed.message

    def test_seconds(self):
        now = 1_700_000_000.0
        parsed = parse("me avisa em 30 segundos", now=now)
        assert parsed.fire_at == now + 30

    def test_hours(self):
        now = 1_700_000_000.0
        parsed = parse("me lembre em 2 horas de ligar pro dentista", now=now)
        assert parsed.fire_at == now + 7200
        assert "dentista" in parsed.message

    def test_message_defaults_when_nothing_meaningful_is_left(self):
        now = 1_700_000_000.0
        parsed = parse("me lembra em 5 minutos", now=now)
        assert parsed.message == "lembrete"


class TestAbsoluteReminders:
    def test_time_later_today(self):
        now = datetime(2026, 1, 1, 10, 0, 0).timestamp()
        parsed = parse("me lembra às 18h de sair", now=now)
        assert datetime.fromtimestamp(parsed.fire_at) == datetime(2026, 1, 1, 18, 0)
        assert parsed.recurring_seconds is None
        assert "sair" in parsed.message

    def test_time_already_passed_today_rolls_to_tomorrow(self):
        now = datetime(2026, 1, 1, 20, 0, 0).timestamp()
        parsed = parse("lembrete às 9h de tomar remédio", now=now)
        assert datetime.fromtimestamp(parsed.fire_at) == datetime(2026, 1, 2, 9, 0)

    def test_with_minutes(self):
        now = datetime(2026, 1, 1, 10, 0, 0).timestamp()
        parsed = parse("me avisa às 14:30", now=now)
        assert datetime.fromtimestamp(parsed.fire_at) == datetime(2026, 1, 1, 14, 30)

    def test_daily_recurrence(self):
        now = datetime(2026, 1, 1, 10, 0, 0).timestamp()
        parsed = parse("me lembra todo dia às 9h de tomar água", now=now)
        assert parsed.recurring_seconds == 86400.0
        assert "água" in parsed.message

    def test_invalid_hour_returns_none(self):
        assert parse("me lembra às 25h de algo") is None
