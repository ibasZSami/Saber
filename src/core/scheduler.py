"""FASE 12 — Scheduler. Reminders/timers persisted to SQLite (see
src/memory/database.py's reminders table) so "me lembra em 30 minutos"
survives an app restart within that window. Due reminders are checked by
whoever calls check_due() — CompanionOrchestrator wires that to a QTimer,
same pattern as vision_timer/spontaneous_talk_timer — deliberately no Qt
dependency in this class itself, so it's plain-Python testable."""

import logging
import time
from dataclasses import dataclass
from typing import Callable, List, Optional

from src.core.event_bus import EventBus, REMINDER_CREATED, REMINDER_FIRED


@dataclass(frozen=True)
class Reminder:
    id: int
    message: str
    fire_at: float
    recurring_seconds: Optional[float]


class Scheduler:
    def __init__(self, database, event_bus: EventBus, on_fire: Callable[[str], None]):
        """on_fire(message) is called for each due reminder — orchestrator
        wires this to speak the message aloud, the same voice path
        spontaneous comments use."""
        self.database = database
        self.event_bus = event_bus
        self.on_fire = on_fire

    def create(self, message: str, fire_at: float, recurring_seconds: Optional[float] = None) -> int:
        reminder_id = self.database.add_reminder(message, fire_at, recurring_seconds)
        self.event_bus.emit(REMINDER_CREATED, reminder_id=reminder_id, message=message, fire_at=fire_at)
        return reminder_id

    def list_pending(self) -> List[Reminder]:
        return [Reminder(**row) for row in self.database.get_all_reminders()]

    def cancel(self, reminder_id: int):
        self.database.delete_reminder(reminder_id)

    def check_due(self, now: Optional[float] = None):
        now = now if now is not None else time.time()
        for row in self.database.get_all_reminders():
            if row["fire_at"] > now:
                continue
            try:
                self.on_fire(row["message"])
            except Exception as e:
                # A crash in the speech callback must not stop the reminder
                # from being marked fired/rescheduled — otherwise a single
                # bad callback would jam every reminder behind it forever.
                logging.error(f"Reminder fire callback failed: {e}")
            self.event_bus.emit(REMINDER_FIRED, reminder_id=row["id"], message=row["message"])
            if row["recurring_seconds"]:
                self.database.update_reminder_fire_at(row["id"], now + row["recurring_seconds"])
            else:
                self.database.delete_reminder(row["id"])
