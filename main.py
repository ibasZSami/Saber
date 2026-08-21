import os
import sys

# Must run before QApplication (or anything Qt) is created/imported: without an
# app manifest, python.exe/pythonw.exe defaults to a DPI-awareness level where
# Windows silently rescales window *positions* it's handed, while Qt's own
# geometry queries (availableGeometry(), frameGeometry()) stay in an unscaled
# space — so a window correctly placed at "78% across" by Qt's own accounting
# visibly lands near mid-screen once Windows re-maps that coordinate. Declaring
# Per-Monitor-V2 awareness up front makes both sides agree on one coordinate
# space, which is the standard fix for this exact Windows+Qt placement bug.
if sys.platform == "win32":
    import ctypes
    # SetProcessDpiAwarenessContext returns a BOOL and ctypes does NOT raise on
    # a FALSE return (only on AttributeError/OSError) — on Windows builds where
    # the call exists but rejects the V2 context value (pre-1703), a bare
    # try/except never notices the failure and the shcore fallback below never
    # runs, silently reproducing the exact placement bug this block exists to
    # fix. The bool(...) check is what actually catches that case.
    dpi_awareness_set = False
    try:
        dpi_awareness_set = bool(ctypes.windll.user32.SetProcessDpiAwarenessContext(-4))  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
    except (AttributeError, OSError):
        pass
    if not dpi_awareness_set:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE (Windows 8.1+ fallback)
        except (AttributeError, OSError):
            pass

# Ensure src is in python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from src.core.app import run_app

if __name__ == "__main__":
    run_app()
