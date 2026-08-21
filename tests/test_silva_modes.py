from src.core.silva_modes import MODE_DESCRIPTIONS, SILVA_MODES, get_preset, is_valid_mode


class TestSilvaModesData:
    def test_every_mode_has_a_description(self):
        assert set(SILVA_MODES.keys()) == set(MODE_DESCRIPTIONS.keys())

    def test_expected_modes_exist(self):
        assert set(SILVA_MODES.keys()) == {
            "silencioso", "trabalho", "companhia", "foco", "privacidade", "jogo",
        }

    def test_every_preset_value_is_a_bool(self):
        for preset in SILVA_MODES.values():
            for value in preset.values():
                assert isinstance(value, bool)


class TestIsValidMode:
    def test_known_mode_is_valid(self):
        assert is_valid_mode("jogo") is True

    def test_unknown_mode_is_invalid(self):
        assert is_valid_mode("inventado") is False


class TestGetPreset:
    def test_returns_the_preset_dict(self):
        assert get_preset("foco") == SILVA_MODES["foco"]

    def test_unknown_mode_returns_none(self):
        assert get_preset("inventado") is None
