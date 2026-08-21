import logging
import os
import subprocess
import sys
import tempfile

try:
    import winreg
except ImportError:
    winreg = None

TASK_NAME = "Silva"

# Preferred mechanism is the Scheduled Task below (covers resume-from-sleep,
# not just fresh logon). This Run-key is kept as a fallback: on some machines
# `schtasks /create` is denied to the current account even for a per-user task
# (observed in the field — split-token admin account, "Acesso negado" with no
# further detail from Task Scheduler itself, not something this app can fix).
# A plain HKCU registry write needs no special privilege, so when the
# Scheduled Task can't be created, autostart still works via this, just
# without the sleep/unlock trigger.
REGISTRY_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
REGISTRY_VALUE_NAME = "Silva"


def _launch_paths():
    """(interpreter, main.py path) using the same venv/interpreter this
    process is already running under — pythonw.exe when available (no console
    window), falling back to the current interpreter otherwise."""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    main_py = os.path.join(project_root, "main.py")
    python_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(python_dir, "pythonw.exe")
    interpreter = pythonw if os.path.exists(pythonw) else sys.executable
    return interpreter, main_py


def _launch_command() -> str:
    """Kept for backwards compatibility with anything still reading it (and
    tests) — same quoted "interpreter" "main.py" shape the old Run-key value used."""
    interpreter, main_py = _launch_paths()
    return f'"{interpreter}" "{main_py}"'


def _task_xml() -> str:
    """A LogonTrigger alone reproduces the old Run-key limitation (fresh logon
    only) — the SessionStateChangeTrigger/SessionUnlock is what actually
    covers "I woke my PC from sleep", the far more common real case.
    MultipleInstancesPolicy=IgnoreNew stops the unlock trigger from spawning a
    second Silva if one from an earlier logon/unlock is still running."""
    interpreter, main_py = _launch_paths()
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
    <SessionStateChangeTrigger>
      <Enabled>true</Enabled>
      <StateChange>SessionUnlock</StateChange>
    </SessionStateChangeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{interpreter}</Command>
      <Arguments>"{main_py}"</Arguments>
    </Exec>
  </Actions>
</Task>
"""


def _write_run_key(enabled: bool) -> bool:
    """Sets/clears the legacy HKCU Run-key entry — the fallback mechanism (see
    module docstring above) as well as the cleanup step that removes it once
    the Scheduled Task is confirmed working, so the two mechanisms never both
    end up active and launching Silva twice on logon."""
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, REGISTRY_VALUE_NAME, 0, winreg.REG_SZ, _launch_command())
            else:
                try:
                    winreg.DeleteValue(key, REGISTRY_VALUE_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError as e:
        logging.error(f"Failed to update autostart registry key: {e}")
        return False


def _run_key_exists() -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY_PATH, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, REGISTRY_VALUE_NAME)
            return True
    except OSError:
        return False


def _task_exists() -> bool:
    """`schtasks /query` exits non-zero when the task doesn't exist."""
    try:
        result = subprocess.run(
            ["schtasks", "/query", "/tn", TASK_NAME],
            capture_output=True, timeout=10,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError) as e:
        logging.error(f"Failed to query autostart task: {e}")
        return False


def is_enabled() -> bool:
    """Whether Silva is registered to auto-launch by either mechanism —
    queries actual OS state directly rather than a config flag, so it can
    never drift from what's really registered."""
    return _task_exists() or _run_key_exists()


def _set_task_enabled(enabled: bool) -> bool:
    """Creates/removes the "Silva" Scheduled Task (logon + session-unlock
    triggers — see _task_xml). Per-user task, no admin rights needed on most
    machines — see set_enabled() for what happens when it's denied anyway."""
    try:
        if enabled:
            fd, xml_path = tempfile.mkstemp(suffix=".xml")
            try:
                with os.fdopen(fd, "w", encoding="utf-16") as f:
                    f.write(_task_xml())
                result = subprocess.run(
                    ["schtasks", "/create", "/tn", TASK_NAME, "/xml", xml_path, "/f"],
                    capture_output=True, timeout=10,
                )
            finally:
                os.unlink(xml_path)
        else:
            result = subprocess.run(
                ["schtasks", "/delete", "/tn", TASK_NAME, "/f"],
                capture_output=True, timeout=10,
            )
            if result.returncode != 0 and not _task_exists():
                # Deleting a task that was already gone isn't a real failure.
                return True

        if result.returncode != 0:
            logging.error(f"Failed to update autostart task: {result.stderr.decode(errors='replace')}")
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError) as e:
        logging.error(f"Failed to update autostart task: {e}")
        return False


def set_enabled(enabled: bool) -> bool:
    """Prefers the Scheduled Task (covers resume-from-sleep, not just fresh
    logon). If schtasks can't create/delete it — denied by local policy/AV on
    some machines, seen in the field as a bare "Acesso negado" — falls back to
    the legacy Run-key, which needs no special privilege. Whichever mechanism
    ends up NOT active is actively cleaned up, so a later successful switch
    can't leave both registered and launching Silva twice."""
    if _set_task_enabled(enabled):
        _write_run_key(False)
        return True

    logging.warning("Autostart via Scheduled Task failed; falling back to the legacy Run-key.")
    return _write_run_key(enabled)
