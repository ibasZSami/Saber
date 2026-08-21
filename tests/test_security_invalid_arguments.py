"""FASE 15 — argumentos inválidos.

A parsed AI response is untrusted input from the model's point of view: a
malformed/hallucinated JSON payload can hand any JSON-decodable shape as
action_param, not just the string/dict shape a tool expects. These tests
prove every dispatch function fails cleanly (returns False, no exception,
no downstream call) instead of crashing on the wrong type — see
src/core/tool_registry.py's dispatch functions."""

from unittest.mock import MagicMock

import pytest

from src.core.tool_registry import build_default_registry

# Shapes a malformed/hallucinated action_param could plausibly take instead
# of the expected string — every string-expecting tool must reject all of these.
WRONG_TYPES_FOR_STRING_PARAM = [None, 123, 4.5, True, False, [], {}, ["chrome"], {"application": "chrome"}]


@pytest.fixture
def registry_and_managers():
    action_manager, memory_manager = MagicMock(), MagicMock()
    audio_mixer_manager = MagicMock()
    registry = build_default_registry(action_manager, memory_manager, audio_mixer_manager)
    return registry, action_manager, memory_manager, audio_mixer_manager


class TestStringParamToolsRejectWrongTypes:
    @pytest.mark.parametrize("bad_param", WRONG_TYPES_FOR_STRING_PARAM)
    def test_open_application_rejects_non_string(self, registry_and_managers, bad_param):
        registry, action_manager, _, _ = registry_and_managers
        result = registry.get("open_application").dispatch(bad_param)
        assert result is False
        action_manager.open_application.assert_not_called()

    @pytest.mark.parametrize("bad_param", WRONG_TYPES_FOR_STRING_PARAM)
    def test_close_application_rejects_non_string(self, registry_and_managers, bad_param):
        registry, action_manager, _, _ = registry_and_managers
        result = registry.get("close_application").dispatch(bad_param)
        assert result is False
        action_manager.close_application.assert_not_called()

    @pytest.mark.parametrize("bad_param", WRONG_TYPES_FOR_STRING_PARAM)
    def test_open_url_rejects_non_string(self, registry_and_managers, bad_param):
        registry, action_manager, _, _ = registry_and_managers
        result = registry.get("open_url").dispatch(bad_param)
        assert result is False
        action_manager.open_url.assert_not_called()

    @pytest.mark.parametrize("bad_param", WRONG_TYPES_FOR_STRING_PARAM)
    def test_search_web_rejects_non_string(self, registry_and_managers, bad_param):
        registry, action_manager, _, _ = registry_and_managers
        result = registry.get("search_web").dispatch(bad_param)
        assert result is False
        action_manager.search_web.assert_not_called()

    def test_whitespace_only_string_is_rejected(self, registry_and_managers):
        registry, action_manager, _, _ = registry_and_managers
        assert registry.get("open_application").dispatch("   ") is False
        action_manager.open_application.assert_not_called()


class TestRememberForgetRejectMalformedParams:
    def test_remember_rejects_non_dict(self, registry_and_managers):
        registry, _, memory_manager, _ = registry_and_managers
        assert registry.get("remember").dispatch("cor_favorita") is False
        memory_manager.remember.assert_not_called()

    def test_remember_rejects_non_string_key(self, registry_and_managers):
        registry, _, memory_manager, _ = registry_and_managers
        assert registry.get("remember").dispatch({"key": 123, "value": "roxo"}) is False
        memory_manager.remember.assert_not_called()

    def test_forget_memory_rejects_empty_dict(self, registry_and_managers):
        """Regression test: an empty dict used to resolve key=None and still
        call memory_manager.forget(None), reporting success for nothing."""
        registry, _, memory_manager, _ = registry_and_managers
        result = registry.get("forget_memory").dispatch({})
        assert result is False
        memory_manager.forget.assert_not_called()

    def test_forget_memory_rejects_list_param(self, registry_and_managers):
        """Regression test: a non-dict, non-string param (e.g. a list) used
        to be passed straight through to memory_manager.forget(), which
        would crash on the real sqlite-backed implementation (sqlite3
        rejects list-typed query parameters)."""
        registry, _, memory_manager, _ = registry_and_managers
        result = registry.get("forget_memory").dispatch(["cor_favorita"])
        assert result is False
        memory_manager.forget.assert_not_called()

    def test_forget_memory_rejects_non_string_key_in_dict(self, registry_and_managers):
        registry, _, memory_manager, _ = registry_and_managers
        assert registry.get("forget_memory").dispatch({"key": 123}) is False
        memory_manager.forget.assert_not_called()


class TestSetAppVolumeClampsAndValidates:
    def test_rejects_non_string_application(self, registry_and_managers):
        registry, _, _, audio_mixer_manager = registry_and_managers
        result = registry.get("set_app_volume").dispatch({"application": 42, "level": 50})
        assert result is False
        audio_mixer_manager.set_volume.assert_not_called()

    def test_clamps_level_above_100(self, registry_and_managers):
        """Regression test / hardening: an AI-hallucinated level of 500 used
        to reach pycaw's scalar volume call as 5.0 — undefined behavior for
        an API whose contract is [0.0, 1.0]."""
        registry, _, _, audio_mixer_manager = registry_and_managers
        audio_mixer_manager.set_volume.return_value = True

        registry.get("set_app_volume").dispatch({"application": "discord", "level": 500})

        audio_mixer_manager.set_volume.assert_called_once_with("discord", 1.0)

    def test_clamps_negative_level(self, registry_and_managers):
        registry, _, _, audio_mixer_manager = registry_and_managers
        audio_mixer_manager.set_volume.return_value = True

        registry.get("set_app_volume").dispatch({"application": "discord", "level": -50})

        audio_mixer_manager.set_volume.assert_called_once_with("discord", 0.0)

    def test_in_range_level_is_unaffected_by_clamping(self, registry_and_managers):
        registry, _, _, audio_mixer_manager = registry_and_managers
        audio_mixer_manager.set_volume.return_value = True

        registry.get("set_app_volume").dispatch({"application": "discord", "level": 40})

        audio_mixer_manager.set_volume.assert_called_once_with("discord", 0.4)
