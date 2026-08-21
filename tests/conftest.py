import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from PySide6.QtWidgets import QApplication

from src.core.event_bus import EventBus

_app = QApplication.instance() or QApplication(sys.argv)


@pytest.fixture(autouse=True)
def _reset_event_bus():
    """EventBus is a process-wide singleton (see src/core/event_bus.py) that
    now dispatches through a real Qt signal — without this, subscribers a
    test registers (very common pattern: `_capture(event_bus, "SOME_EVENT")`)
    pile up for the rest of the whole pytest session, and since dispatch can
    be a queued Qt event now instead of always-immediate, a stale subscriber
    from an unrelated earlier test could fire when a later test pumps the
    event loop (e.g. via QApplication.processEvents())."""
    EventBus().reset()
    yield
    EventBus().reset()
