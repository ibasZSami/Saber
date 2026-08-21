import os
import re
import subprocess
import webbrowser
import logging
from urllib.parse import quote_plus

import psutil

from src.desktop.app_resolver import resolve_app_path
from src.desktop.permissions import PermissionManager

class DesktopActionManager:
    def __init__(self, permission_manager: PermissionManager, on_app_resolved=None):
        self.permission_manager = permission_manager
        # Called (name, command) when open_application resolves a brand-new app
        # outside the allowlist, so a caller with access to the UI can tell the
        # user about it. Deliberately NOT auto-persisted to the allowlist here
        # (see permission_manager below) — the allowlist is the user's real
        # permission boundary (also gates close_application), so a name Silva
        # happened to resolve once shouldn't silently become permanent
        # permission without the user explicitly adding it via Configurações →
        # Aplicativos.
        self.on_app_resolved = on_app_resolved

    def open_application(self, app_name: str) -> bool:
        app_name_clean = app_name.lower().strip()
        cmd = self.permission_manager.get_app_command(app_name_clean) if self.permission_manager.is_app_allowed(app_name_clean) else None

        if not cmd:
            # Not pre-approved — try to resolve it the way Windows itself would
            # (App Paths registry, Start Menu shortcuts, PATH). Only ever
            # launches a real path found on disk, never the raw name, so this
            # can't become arbitrary command execution — see app_resolver.py.
            # This resolution is one-off: it is NOT written to the allowlist,
            # so it has to be re-resolved (and re-launched) each time it's
            # asked for again, unless the user adds it permanently themselves.
            resolved = resolve_app_path(app_name_clean)
            if not resolved:
                logging.warning(f"Application '{app_name}' is not in the allowlist and could not be resolved!")
                return False
            cmd = resolved
            logging.info(f"Auto-resolved '{app_name}' -> {cmd} (not persisted to allowlist)")
            if self.on_app_resolved:
                self.on_app_resolved(app_name_clean, cmd)

        try:
            # shell=True runs the string through cmd.exe, which splits on the
            # first unquoted space. Unquoted paths like "C:\Program Files\..."
            # break into separate tokens and fail to launch, so quote the
            # executable portion (keeping any trailing arguments unquoted).
            match = re.match(r'^(.*?\.exe)(\s+.*)?$', cmd, re.IGNORECASE)
            if match and not cmd.startswith('"'):
                exe_path, args = match.group(1), match.group(2) or ""
                quoted_cmd = f'"{exe_path}"{args}'
            elif " " in cmd and not cmd.startswith('"'):
                quoted_cmd = f'"{cmd}"'
            else:
                quoted_cmd = cmd

            subprocess.Popen(quoted_cmd, shell=True)
            logging.info(f"Successfully launched {app_name}")
            return True
        except Exception as e:
            logging.error(f"Failed to launch {app_name}: {e}")
            return False

    def close_application(self, app_name: str) -> bool:
        """Closes a running app — gated by the same allowlist as open_application,
        so the AI can only ever close something the user explicitly permitted it
        to touch, never an arbitrary process by name.

        The allowlist stores a launch *command* (e.g. an install path, or in
        Discord's case an updater stub that isn't the real running process), not
        the actual running executable's name — so instead of parsing that command,
        this matches the allowlist key against real running process names in
        either direction (e.g. key "vscode" matches process "Code.exe" via the
        shared "code" substring). Restricted to allowlisted keys only, so a loose
        substring match can't be used to close something not permitted.
        """
        app_name_clean = app_name.lower().strip()
        if not self.permission_manager.is_app_allowed(app_name_clean):
            logging.warning(f"Application '{app_name}' is not in the allowlist, refusing to close it!")
            return False

        closed = False
        for proc in psutil.process_iter(["name"]):
            try:
                proc_name = (proc.info.get("name") or "")
                proc_stem = os.path.splitext(proc_name)[0].lower()
                if not proc_stem:
                    continue
                if proc_stem in app_name_clean or app_name_clean in proc_stem:
                    proc.terminate()
                    closed = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if closed:
            logging.info(f"Successfully closed {app_name}")
        else:
            logging.warning(f"No running process found matching '{app_name}'")
        return closed

    def open_url(self, url: str) -> bool:
        try:
            if not url.startswith("http://") and not url.startswith("https://"):
                url = "https://" + url
            webbrowser.open(url)
            return True
        except Exception as e:
            logging.error(f"Failed to open URL {url}: {e}")
            return False

    def search_web(self, query: str) -> bool:
        url = f"https://www.google.com/search?q={quote_plus(query)}"
        return self.open_url(url)
