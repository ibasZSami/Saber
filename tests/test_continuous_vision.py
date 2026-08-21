import time
from unittest.mock import patch

from src.vision.continuous_vision import ContinuousVisionBuffer, VisionMode


class TestVisionMode:
    def test_all_four_modes_exist_with_expected_values(self):
        assert VisionMode.OFF == "OFF"
        assert VisionMode.CONTEXT == "CONTEXT"
        assert VisionMode.AWARENESS == "AWARENESS"
        assert VisionMode.ACTIVE == "ACTIVE"


class TestContinuousVisionBuffer:
    def test_empty_buffer_has_no_freshest_entry(self):
        buf = ContinuousVisionBuffer()
        assert buf.freshest() is None

    def test_add_then_freshest_returns_the_latest_entry(self):
        buf = ContinuousVisionBuffer()
        buf.add(window_title="Notepad", category="general", changed=False)
        buf.add(window_title="Chrome", category="browser", changed=True)

        entry = buf.freshest()

        assert entry.window_title == "Chrome"
        assert entry.category == "browser"
        assert entry.changed is True

    def test_entries_older_than_ttl_are_excluded_from_freshest(self):
        buf = ContinuousVisionBuffer(ttl_seconds=10)
        with patch("time.time", return_value=1000.0):
            buf.add(window_title="Notepad", category="general", changed=False)
        with patch("time.time", return_value=1000.0 + 999):
            assert buf.freshest() is None

    def test_recent_excludes_expired_entries_but_keeps_fresh_ones(self):
        buf = ContinuousVisionBuffer(ttl_seconds=10)
        with patch("time.time", return_value=1000.0):
            buf.add(window_title="Old", category="general", changed=False)
        with patch("time.time", return_value=1005.0):
            buf.add(window_title="Recent", category="general", changed=False)
        with patch("time.time", return_value=1012.0):
            titles = [e.window_title for e in buf.recent()]

        assert titles == ["Recent"]

    def test_buffer_is_capped_at_max_entries(self):
        buf = ContinuousVisionBuffer(max_entries=3)
        for i in range(10):
            buf.add(window_title=f"win{i}", category="general", changed=False)
        assert len(buf.recent()) == 3
        assert buf.freshest().window_title == "win9"

    def test_clear_empties_the_buffer(self):
        buf = ContinuousVisionBuffer()
        buf.add(window_title="Notepad", category="general", changed=False)
        buf.clear()
        assert buf.freshest() is None
        assert buf.recent() == []

    def test_entry_has_a_real_timestamp(self):
        buf = ContinuousVisionBuffer()
        before = time.time()
        buf.add(window_title="Notepad", category="general", changed=False)
        after = time.time()
        assert before <= buf.freshest().timestamp <= after
