import logging
import os
import sys

try:
    import winreg
except ImportError:
    winreg = None

REGISTRY_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
REGISTRY_VALUE_NAME = "Silva"


def _launch_command() -> str:
    """Command written to the registry Run key: pythonw.exe (no console window)
    running main.py from this project, using the same interpreter/venv this
    process is already running under — so it matches however the user actually
    installed/launches the app, no separate install-path config needed."""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    main_py = os.path.join(project_root, "main.py")
    python_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(python_dir, "pythonw.exe")
    interpreter = pythonw if os.path.exists(pythonw) else sys.executable
    return f'"{interpreter}" "{main_py}"'


def is_enabled() -> bool:
    """Whether Silva is registered to launch on Windows login — reads the
    registry directly rather than a config flag, so it can never drift from
    the actual OS state."""
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY_PATH, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, REGISTRY_VALUE_NAME)
            return True
    except FileNotFoundError:
        return False
    except OSError as e:
        logging.error(f"Failed to read autostart registry key: {e}")
        return False


def set_enabled(enabled: bool) -> bool:
    """Adds/removes the HKCU Run-key entry — per-user, no admin rights needed.
    Returns whether the change actually applied."""
    if winreg is None:
        logging.warning("winreg indisponível; inicialização automática não é suportada nesta plataforma.")
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
