import sys

from src.core.event_bus import EventBus
from src.desktop.terminal_tool import TerminalToolManager

_PYTHON = sys.executable


def _manager(allowlist=None):
    bus = EventBus()
    bus.reset()
    return TerminalToolManager(allowlist or {}, bus), bus


class TestAllowlist:
    def test_binary_not_in_allowlist_is_refused(self):
        manager, _ = _manager()
        result = manager.run("nmap", "-sV localhost")
        assert result["success"] is False
        assert "allowlist" in result["error"]

    def test_name_is_case_and_whitespace_insensitive(self):
        manager, _ = _manager({"echo": _PYTHON})
        result = manager.run("  Echo  ", "-c pass")
        # Doesn't fail on the allowlist lookup itself (may still fail running
        # python with that arg — the point here is the lookup succeeded).
        assert "allowlist" not in (result["error"] or "")


class TestArgumentValidation:
    def test_rejects_shell_metacharacters(self):
        manager, _ = _manager({"py": _PYTHON})
        result = manager.run("py", "-c 'print(1)' | evil")
        assert result["success"] is False
        assert "não permitido" in result["error"]

    def test_rejects_malformed_quoting(self):
        manager, _ = _manager({"py": _PYTHON})
        result = manager.run("py", 'unterminated "quote')
        assert result["success"] is False
        assert "Argumentos inválidos" in result["error"]


class TestExecution:
    def test_runs_the_binary_and_captures_stdout(self):
        manager, _ = _manager({"py": _PYTHON})
        result = manager.run("py", '-c "print(1+1)"')
        assert result["success"] is True
        assert "2" in result["output"]

    def test_nonzero_exit_code_is_reported_as_failure(self):
        manager, _ = _manager({"py": _PYTHON})
        result = manager.run("py", "-c \"import sys; sys.exit(1)\"")
        assert result["success"] is False

    def test_output_is_capped(self):
        manager, _ = _manager({"py": _PYTHON})
        result = manager.run("py", "-c \"print('x' * 10000)\"")
        from src.desktop.terminal_tool import MAX_OUTPUT_CHARS
        assert len(result["output"]) <= MAX_OUTPUT_CHARS

    def test_no_args_runs_fine(self):
        manager, _ = _manager({"py": _PYTHON})
        result = manager.run("py", "--version")
        assert result["success"] is True


class TestEventEmission:
    def test_emits_terminal_tool_executed_on_success(self):
        manager, bus = _manager({"py": _PYTHON})
        received = []
        bus.subscribe("TERMINAL_TOOL_EXECUTED", lambda **kw: received.append(kw))

        manager.run("py", '-c "print(42)"')

        assert len(received) == 1
        assert received[0]["name"] == "py"
        assert received[0]["success"] is True
        assert "42" in received[0]["output"]

    def test_emits_terminal_tool_executed_on_allowlist_refusal(self):
        manager, bus = _manager()
        received = []
        bus.subscribe("TERMINAL_TOOL_EXECUTED", lambda **kw: received.append(kw))

        manager.run("nmap", "-sV localhost")

        assert len(received) == 1
        assert received[0]["success"] is False
