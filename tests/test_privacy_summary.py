from src.core.privacy_summary import format_privacy_summary


def _snapshot(**overrides):
    base = {
        "desktop": {"active_window": None, "category": None, "is_game": False, "idle_seconds": 0},
        "vision": {"monitoring_enabled": False, "private_mode": True},
        "voice": {"listening": False, "hands_free_enabled": False, "system_audio_listening": False},
        "memory": {"saved_keys": [], "saved_count": 0},
    }
    base.update(overrides)
    return base


class TestVisionSection:
    def test_off_when_private_mode(self):
        summary = format_privacy_summary(_snapshot(vision={"monitoring_enabled": True, "private_mode": True}))
        assert "Visão de tela: DESLIGADA" in summary

    def test_off_when_monitoring_disabled(self):
        summary = format_privacy_summary(_snapshot(vision={"monitoring_enabled": False, "private_mode": False}))
        assert "Visão de tela: DESLIGADA" in summary

    def test_active_shows_the_mode(self):
        summary = format_privacy_summary(
            _snapshot(vision={"monitoring_enabled": True, "private_mode": False, "mode": "ACTIVE"})
        )
        assert "Visão de tela: ATIVA (modo ACTIVE)" in summary

    def test_translation_mode_running_is_flagged(self):
        summary = format_privacy_summary(_snapshot(
            vision={"monitoring_enabled": False, "private_mode": True, "translation_mode_state": "RUNNING"}
        ))
        assert "Modo Tradução: ATIVO (RUNNING)" in summary

    def test_translation_mode_off_is_not_mentioned(self):
        summary = format_privacy_summary(_snapshot(
            vision={"monitoring_enabled": False, "private_mode": True, "translation_mode_state": "OFF"}
        ))
        assert "Modo Tradução" not in summary

    def test_shows_active_window(self):
        summary = format_privacy_summary(_snapshot(desktop={"active_window": "Visual Studio Code"}))
        assert "Visual Studio Code" in summary

    def test_no_active_window_shows_nenhuma(self):
        summary = format_privacy_summary(_snapshot(desktop={"active_window": None}))
        assert "nenhuma" in summary


class TestVoiceSection:
    def test_microphone_listening(self):
        summary = format_privacy_summary(_snapshot(voice={"listening": True, "hands_free_enabled": False, "system_audio_listening": False}))
        assert "Microfone: OUVINDO agora" in summary

    def test_microphone_off(self):
        summary = format_privacy_summary(_snapshot(voice={"listening": False, "hands_free_enabled": False, "system_audio_listening": False}))
        assert "Microfone: desligado" in summary

    def test_system_audio_listening(self):
        summary = format_privacy_summary(_snapshot(voice={"listening": False, "hands_free_enabled": False, "system_audio_listening": True}))
        assert "Áudio do jogo/PC: OUVINDO agora" in summary


class TestMemorySection:
    def test_no_memories_saved(self):
        summary = format_privacy_summary(_snapshot(memory={"saved_keys": [], "saved_count": 0}))
        assert "Nenhuma memória de longo prazo salva." in summary
        assert "(0 item(ns))" in summary

    def test_lists_every_saved_key(self):
        summary = format_privacy_summary(_snapshot(memory={"saved_keys": ["cor favorita", "cidade natal"], "saved_count": 2}))
        assert "- cor favorita" in summary
        assert "- cidade natal" in summary
        assert "(2 item(ns))" in summary
