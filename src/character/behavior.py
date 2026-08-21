import random
from PySide6.QtCore import QTimer
from src.character.state_manager import CharacterStateManager

class AutonomousBehaviorManager:
    def __init__(self, state_manager: CharacterStateManager, interval_ms: int = 12000):
        self.state_manager = state_manager
        self.interval_ms = interval_ms
        self.is_enabled = True

        self.timer = QTimer()
        self.timer.timeout.connect(self._on_tick)
        self.timer.start(self.interval_ms)

    def set_enabled(self, enabled: bool):
        self.is_enabled = enabled
        if enabled and not self.timer.isActive():
            self.timer.start(self.interval_ms)
        elif not enabled and self.timer.isActive():
            self.timer.stop()

    def _on_tick(self):
        if not self.is_enabled:
            return

        current_state = self.state_manager.state_machine.get_state()
        # Only perform autonomous actions if in IDLE or SLEEP
        if current_state in ["IDLE", "SLEEP"]:
            action = random.choice(["wander", "sit_idle", "sleep_check", "stretch"])

            if action == "wander" and current_state != "SLEEP":
                self.state_manager.set_state("WALK", reason="Autonomous wander")
            elif action == "sleep_check" and random.random() < 0.15:
                self.state_manager.set_state("SLEEP", reason="Autonomous sleep")
            elif current_state == "SLEEP" and random.random() < 0.3:
                self.state_manager.set_state("IDLE", reason="Autonomous wake up")
            elif current_state == "IDLE":
                self.state_manager.set_state("IDLE", reason="Autonomous idle tick")
