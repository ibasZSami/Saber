from src.core.activity_log import MAX_ENTRIES, ActivityLog, format_activity_log
from src.core.event_bus import EventBus


def _bus():
    bus = EventBus()
    bus.reset()
    return bus


class TestActionEvents:
    def test_executed_open_application_is_logged(self):
        bus = _bus()
        log = ActivityLog(bus)
        bus.emit("ACTION_EXECUTED", action="open_application", action_param="chrome")
        assert 'Abriu o aplicativo "chrome".' in log.entries()[-1].text

    def test_rejected_open_application_is_logged_as_failure(self):
        bus = _bus()
        log = ActivityLog(bus)
        bus.emit("ACTION_REJECTED", action="open_application", action_param="chrome")
        assert "Não conseguiu abrir" in log.entries()[-1].text

    def test_confirm_auto_approved_counts_as_executed(self):
        bus = _bus()
        log = ActivityLog(bus)
        bus.emit("ACTION_CONFIRM_AUTO_APPROVED", action="close_application", action_param="discord")
        assert 'Fechou o aplicativo "discord".' in log.entries()[-1].text

    def test_set_app_volume_reads_dict_param(self):
        bus = _bus()
        log = ActivityLog(bus)
        bus.emit("ACTION_EXECUTED", action="set_app_volume", action_param={"application": "spotify", "level": 40})
        assert 'volume de "spotify" para 40%' in log.entries()[-1].text

    def test_mouse_click_is_logged(self):
        bus = _bus()
        log = ActivityLog(bus)
        bus.emit("ACTION_EXECUTED", action="mouse_click", action_param={"x": 1, "y": 2})
        assert "mouse_click" in log.entries()[-1].text

    def test_run_terminal_tool_is_logged_with_the_binary_name(self):
        bus = _bus()
        log = ActivityLog(bus)
        bus.emit("ACTION_EXECUTED", action="run_terminal_tool", action_param={"name": "nmap", "args": "-sV"})
        assert '"nmap"' in log.entries()[-1].text

    def test_unknown_action_gets_generic_fallback(self):
        bus = _bus()
        log = ActivityLog(bus)
        bus.emit("ACTION_EXECUTED", action="some_future_tool", action_param="x")
        assert '"some_future_tool"' in log.entries()[-1].text


class TestOtherLoggedEvents:
    def test_app_auto_resolved(self):
        bus = _bus()
        log = ActivityLog(bus)
        bus.emit("APP_AUTO_RESOLVED", app_name="notion", command="Notion.exe")
        assert '"notion"' in log.entries()[-1].text

    def test_memory_created(self):
        bus = _bus()
        log = ActivityLog(bus)
        bus.emit("MEMORY_CREATED", key="cor favorita", value="azul")
        assert '"cor favorita"' in log.entries()[-1].text

    def test_nerd_mode_toggled_on_and_off(self):
        bus = _bus()
        log = ActivityLog(bus)
        bus.emit("NERD_MODE_TOGGLED", enabled=True)
        bus.emit("NERD_MODE_TOGGLED", enabled=False)
        assert log.entries()[-2].text == "Modo Nerd ativado."
        assert log.entries()[-1].text == "Modo Nerd desativado."

    def test_vision_toggled(self):
        bus = _bus()
        log = ActivityLog(bus)
        bus.emit("VISION_MONITORING_TOGGLED", enabled=True)
        assert log.entries()[-1].text == "Visão de tela ativada."

    def test_task_completed_and_failed(self):
        bus = _bus()
        log = ActivityLog(bus)
        bus.emit("TASK_COMPLETED", task_id="1", task_type="research", description="pesquisa sobre gatos", result="ok")
        bus.emit("TASK_FAILED", task_id="2", task_type="research", description="pesquisa sobre cães", error="timeout")
        assert "Concluiu: pesquisa sobre gatos" in log.entries()[-2].text
        assert "Não conseguiu concluir: pesquisa sobre cães" in log.entries()[-1].text

    def test_error_occurred(self):
        bus = _bus()
        log = ActivityLog(bus)
        bus.emit("ERROR_OCCURRED", source="handle_user_message", error="boom")
        assert "handle_user_message" in log.entries()[-1].text

    def test_reminder_created(self):
        bus = _bus()
        log = ActivityLog(bus)
        bus.emit("REMINDER_CREATED", reminder_id=1, message="tirar o bolo", fire_at=123.0)
        assert '"tirar o bolo"' in log.entries()[-1].text

    def test_reminder_fired(self):
        bus = _bus()
        log = ActivityLog(bus)
        bus.emit("REMINDER_FIRED", reminder_id=1, message="tirar o bolo")
        assert '"tirar o bolo"' in log.entries()[-1].text


class TestNoiseIsNotLogged:
    def test_memory_recalled_is_not_logged(self):
        bus = _bus()
        log = ActivityLog(bus)
        bus.emit("MEMORY_RECALLED", count=3)
        assert log.entries() == []

    def test_window_changed_is_not_logged(self):
        bus = _bus()
        log = ActivityLog(bus)
        bus.emit("WINDOW_CHANGED", title="Chrome")
        assert log.entries() == []


class TestCapAndClear:
    def test_entries_are_capped_at_max(self):
        bus = _bus()
        log = ActivityLog(bus)
        for i in range(MAX_ENTRIES + 20):
            bus.emit("MEMORY_CREATED", key=f"k{i}", value="v")
        assert len(log.entries()) == MAX_ENTRIES
        assert log.entries()[-1].text == f'Guardou uma memória: "k{MAX_ENTRIES + 19}".'

    def test_clear_empties_the_log(self):
        bus = _bus()
        log = ActivityLog(bus)
        bus.emit("MEMORY_CREATED", key="k", value="v")
        log.clear()
        assert log.entries() == []


class TestFormatActivityLog:
    def test_empty_log_has_a_friendly_message(self):
        assert format_activity_log([]) == "Nenhuma atividade registrada ainda."

    def test_entries_are_shown_newest_first(self):
        bus = _bus()
        log = ActivityLog(bus)
        bus.emit("MEMORY_CREATED", key="primeiro", value="v")
        bus.emit("MEMORY_CREATED", key="segundo", value="v")
        report = format_activity_log(log.entries())
        assert report.index("segundo") < report.index("primeiro")
