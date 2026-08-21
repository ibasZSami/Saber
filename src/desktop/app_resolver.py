import glob
import logging
import os
import shutil

try:
    import winreg
except ImportError:
    winreg = None


def _resolve_from_app_paths_registry(app_name: str):
    """Windows registers most installed apps at HKLM/HKCU\\Software\\Microsoft\\
    Windows\\CurrentVersion\\App Paths\\<name>.exe — the same lookup the Start
    Menu/Run dialog uses to resolve a bare name like "firefox" to its real
    install path, so this piggybacks on data installers already provide
    instead of maintaining our own list of install locations."""
    if winreg is None:
        return None
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for key_name in (f"{app_name}.exe", app_name):
            try:
                with winreg.OpenKey(hive, rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{key_name}", 0, winreg.KEY_READ) as key:
                    path, _ = winreg.QueryValueEx(key, "")
                    if path and os.path.exists(path):
                        return path
            except OSError:
                continue
    return None


def _resolve_shortcut_target(lnk_path: str):
    try:
        import comtypes.client
        shell = comtypes.client.CreateObject("WScript.Shell")
        shortcut = shell.CreateShortCut(lnk_path)
        return shortcut.Targetpath or None
    except Exception as e:
        logging.debug(f"Failed to resolve shortcut {lnk_path}: {e}")
        return None


# Below this length, bidirectional substring matching gets dangerously
# unspecific — e.g. needle "ai" matches stem "explain" (contains "ai" as a
# substring), sending Silva to launch unrelated software for a short/mistyped
# name. Exact matches (any length) always still short-circuit immediately.
_MIN_FUZZY_MATCH_LENGTH = 3


def _resolve_from_start_menu(app_name: str):
    """Searches the Start Menu shortcut folders (current user + all users) for
    a .lnk whose file name matches the requested app, then resolves it to the
    real target .exe via the WScript.Shell COM object — through `comtypes`,
    already a project dependency for pycaw, so no extra dependency (like
    pywin32) is needed just to read a shortcut.

    An exact stem match always wins immediately (unambiguous). Short of that,
    a bidirectional substring match is only attempted for names of reasonable
    length (see _MIN_FUZZY_MATCH_LENGTH) — fuzzy candidates are collected
    across the whole scan and only the first one is resolved, so a later exact
    match anywhere else still takes priority over an earlier fuzzy one."""
    search_roots = [
        os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
        os.path.join(os.environ.get("ProgramData", ""), r"Microsoft\Windows\Start Menu\Programs"),
    ]
    needle = app_name.lower()
    fuzzy_candidates = []
    for root in search_roots:
        if not root or not os.path.isdir(root):
            continue
        for lnk_path in glob.glob(os.path.join(root, "**", "*.lnk"), recursive=True):
            stem = os.path.splitext(os.path.basename(lnk_path))[0].lower()
            if stem == needle:
                target = _resolve_shortcut_target(lnk_path)
                if target and os.path.exists(target):
                    return target
            elif len(needle) >= _MIN_FUZZY_MATCH_LENGTH and (needle in stem or stem in needle):
                fuzzy_candidates.append(lnk_path)

    for lnk_path in fuzzy_candidates:
        target = _resolve_shortcut_target(lnk_path)
        if target and os.path.exists(target):
            return target
    return None


def resolve_app_path(app_name: str):
    """Best-effort resolution of an app name that isn't in the allowlist yet —
    tries the same places Windows itself uses to resolve a bare app name (App
    Paths registry, Start Menu shortcuts, then PATH), so Silva can open an app
    it was never explicitly configured for. Only ever returns a real path that
    already exists on disk (or None), never the raw name back — the caller
    launches that resolved path, not arbitrary user/AI-provided text, so this
    can't turn into arbitrary command execution.

    A legitimate app *name* never contains a path separator or a drive-letter
    colon — only a full/relative filesystem path would. Without rejecting
    those upfront, shutil.which() below treats an input containing a
    separator as a literal path and returns it as-is if executable: asking to
    "open" the literal string "C:\\Windows\\System32\\cmd.exe" would resolve
    and launch it directly, bypassing both the allowlist and the "resolve by
    name" intent this whole function exists for."""
    app_name = (app_name or "").strip()
    if not app_name or any(sep in app_name for sep in ("\\", "/", ":")):
        return None

    resolved = _resolve_from_app_paths_registry(app_name)
    if resolved:
        return resolved

    resolved = _resolve_from_start_menu(app_name)
    if resolved:
        return resolved

    return shutil.which(app_name) or shutil.which(f"{app_name}.exe")
