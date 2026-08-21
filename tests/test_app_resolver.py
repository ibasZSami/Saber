from unittest.mock import patch

import src.desktop.app_resolver as app_resolver


class _FakeKey:
    def __init__(self, registry):
        self.registry = registry

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _RecordingFakeWinreg:
    """Minimal in-memory stand-in for winreg, keyed by full (hive, path) so a
    test can control exactly which (hive, key name) combination resolves —
    mirrors the pattern already used in tests/test_autostart.py. Records which
    value the last successful OpenKey resolved to, so QueryValueEx (which
    winreg's real signature doesn't pass the path to) can return the right one."""
    HKEY_CURRENT_USER = "HKCU"
    HKEY_LOCAL_MACHINE = "HKLM"
    KEY_READ = 1

    def __init__(self, values=None):
        self.values = values or {}  # {(hive, path): "C:\\...\\app.exe"}

    def OpenKey(self, hive, path, reserved, access):
        if (hive, path) not in self.values:
            raise FileNotFoundError()
        self._last_value = self.values[(hive, path)]
        return _FakeKey(self)

    def QueryValueEx(self, key, name):
        return (key.registry._last_value, 1)


class TestResolveFromAppPathsRegistry:
    def test_resolves_from_current_user_hive(self):
        fake = _RecordingFakeWinreg({
            ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\App Paths\firefox.exe"): r"C:\Firefox\firefox.exe",
        })
        with patch.object(app_resolver, "winreg", fake), patch("os.path.exists", return_value=True):
            assert app_resolver._resolve_from_app_paths_registry("firefox") == r"C:\Firefox\firefox.exe"

    def test_returns_none_when_not_registered(self):
        fake = _RecordingFakeWinreg({})
        with patch.object(app_resolver, "winreg", fake):
            assert app_resolver._resolve_from_app_paths_registry("nonexistent") is None

    def test_returns_none_when_registered_path_no_longer_exists(self):
        fake = _RecordingFakeWinreg({
            ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\App Paths\firefox.exe"): r"C:\Firefox\firefox.exe",
        })
        with patch.object(app_resolver, "winreg", fake), patch("os.path.exists", return_value=False):
            assert app_resolver._resolve_from_app_paths_registry("firefox") is None

    def test_returns_none_when_winreg_unavailable(self):
        with patch.object(app_resolver, "winreg", None):
            assert app_resolver._resolve_from_app_paths_registry("firefox") is None


class TestResolveFromStartMenu:
    @patch("src.desktop.app_resolver._resolve_shortcut_target")
    @patch("glob.glob")
    @patch("os.path.isdir", return_value=True)
    @patch("os.path.exists", return_value=True)
    def test_matches_shortcut_by_name_and_resolves_target(self, mock_exists, mock_isdir, mock_glob, mock_target):
        mock_glob.return_value = [r"C:\Start Menu\Programs\Spotify.lnk"]
        mock_target.return_value = r"C:\Users\x\AppData\Roaming\Spotify\Spotify.exe"

        result = app_resolver._resolve_from_start_menu("spotify")

        assert result == r"C:\Users\x\AppData\Roaming\Spotify\Spotify.exe"

    @patch("glob.glob", return_value=[])
    @patch("os.path.isdir", return_value=True)
    def test_returns_none_when_no_shortcut_matches(self, mock_isdir, mock_glob):
        assert app_resolver._resolve_from_start_menu("totally_unknown_app") is None

    @patch("os.path.isdir", return_value=False)
    def test_returns_none_when_start_menu_dirs_missing(self, mock_isdir):
        assert app_resolver._resolve_from_start_menu("spotify") is None

    @patch("src.desktop.app_resolver._resolve_shortcut_target")
    @patch("glob.glob")
    @patch("os.path.isdir", return_value=True)
    @patch("os.path.exists", return_value=True)
    def test_short_needle_does_not_fuzzy_match_unrelated_shortcut(self, mock_exists, mock_isdir, mock_glob, mock_target):
        """Regression test: bidirectional substring matching with no length
        guard let a short needle like "ai" match any shortcut whose name
        merely contains those two letters in sequence — e.g. "explain" —
        resolving to completely unrelated software."""
        mock_glob.return_value = [r"C:\Start Menu\Programs\Explain Everything.lnk"]

        result = app_resolver._resolve_from_start_menu("ai")

        assert result is None
        mock_target.assert_not_called()

    @patch("src.desktop.app_resolver._resolve_shortcut_target")
    @patch("glob.glob")
    @patch("os.path.isdir", return_value=True)
    @patch("os.path.exists", return_value=True)
    def test_needle_at_the_minimum_length_can_still_fuzzy_match(self, mock_exists, mock_isdir, mock_glob, mock_target):
        mock_glob.return_value = [r"C:\Start Menu\Programs\Code.lnk"]
        mock_target.return_value = r"C:\vscode\Code.exe"

        result = app_resolver._resolve_from_start_menu("cod")  # 3 chars — meets the minimum

        assert result == r"C:\vscode\Code.exe"

    @patch("src.desktop.app_resolver._resolve_shortcut_target")
    @patch("glob.glob")
    @patch("os.path.isdir", return_value=True)
    @patch("os.path.exists", return_value=True)
    def test_exact_match_wins_over_an_earlier_fuzzy_candidate(self, mock_exists, mock_isdir, mock_glob, mock_target):
        """A fuzzy hit found earlier in scan order must not win over an exact
        stem match found later — exact identity is the only unambiguous
        signal here, scan order is filesystem-dependent and shouldn't matter."""
        mock_glob.return_value = [
            r"C:\Start Menu\Programs\Code Runner.lnk",  # fuzzy candidate, scanned first
            r"C:\Start Menu\Programs\Code.lnk",          # exact match, scanned second
        ]
        mock_target.side_effect = lambda path: {
            r"C:\Start Menu\Programs\Code Runner.lnk": r"C:\wrong\CodeRunner.exe",
            r"C:\Start Menu\Programs\Code.lnk": r"C:\vscode\Code.exe",
        }[path]

        result = app_resolver._resolve_from_start_menu("code")

        assert result == r"C:\vscode\Code.exe"


class TestResolveAppPath:
    def test_empty_name_returns_none_without_lookups(self):
        assert app_resolver.resolve_app_path("   ") is None

    @patch("shutil.which")
    def test_rejects_absolute_windows_path_without_calling_which(self, mock_which):
        """Regression test / security fix: shutil.which() treats an input
        containing a path separator as a literal path and returns it as-is if
        executable — without the upfront guard, asking to "open" a literal
        path like this launched it directly, bypassing the allowlist and the
        "resolve by name" intent entirely."""
        assert app_resolver.resolve_app_path(r"C:\Windows\System32\cmd.exe") is None
        mock_which.assert_not_called()

    @patch("shutil.which")
    def test_rejects_forward_slash_path(self, mock_which):
        assert app_resolver.resolve_app_path("C:/Windows/System32/cmd.exe") is None
        mock_which.assert_not_called()

    @patch("shutil.which")
    def test_rejects_relative_path_with_directory_separator(self, mock_which):
        assert app_resolver.resolve_app_path(r"..\..\Windows\System32\cmd") is None
        mock_which.assert_not_called()

    @patch("shutil.which")
    @patch("src.desktop.app_resolver._resolve_from_start_menu", return_value=None)
    @patch("src.desktop.app_resolver._resolve_from_app_paths_registry", return_value=None)
    def test_bare_name_without_separators_is_still_resolved_normally(self, mock_registry, mock_start_menu, mock_which):
        mock_which.return_value = r"C:\Program Files\App\app.exe"

        assert app_resolver.resolve_app_path("app") == r"C:\Program Files\App\app.exe"

    @patch("shutil.which")
    @patch("src.desktop.app_resolver._resolve_from_start_menu")
    @patch("src.desktop.app_resolver._resolve_from_app_paths_registry")
    def test_prefers_registry_over_start_menu_and_path(self, mock_registry, mock_start_menu, mock_which):
        mock_registry.return_value = r"C:\registry\app.exe"
        mock_start_menu.return_value = r"C:\startmenu\app.exe"
        mock_which.return_value = r"C:\path\app.exe"

        assert app_resolver.resolve_app_path("app") == r"C:\registry\app.exe"
        mock_start_menu.assert_not_called()
        mock_which.assert_not_called()

    @patch("shutil.which")
    @patch("src.desktop.app_resolver._resolve_from_start_menu")
    @patch("src.desktop.app_resolver._resolve_from_app_paths_registry", return_value=None)
    def test_falls_back_to_start_menu_when_registry_misses(self, mock_registry, mock_start_menu, mock_which):
        mock_start_menu.return_value = r"C:\startmenu\app.exe"

        assert app_resolver.resolve_app_path("app") == r"C:\startmenu\app.exe"
        mock_which.assert_not_called()

    @patch("shutil.which")
    @patch("src.desktop.app_resolver._resolve_from_start_menu", return_value=None)
    @patch("src.desktop.app_resolver._resolve_from_app_paths_registry", return_value=None)
    def test_falls_back_to_path_when_nothing_else_matches(self, mock_registry, mock_start_menu, mock_which):
        mock_which.side_effect = [None, r"C:\path\app.exe"]

        assert app_resolver.resolve_app_path("app") == r"C:\path\app.exe"

    @patch("shutil.which", return_value=None)
    @patch("src.desktop.app_resolver._resolve_from_start_menu", return_value=None)
    @patch("src.desktop.app_resolver._resolve_from_app_paths_registry", return_value=None)
    def test_returns_none_when_nothing_resolves(self, mock_registry, mock_start_menu, mock_which):
        assert app_resolver.resolve_app_path("totally_unknown_app_xyz") is None
