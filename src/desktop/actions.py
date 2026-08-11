import os
import re
import subprocess
import webbrowser
import logging
from urllib.parse import quote_plus
from src.desktop.permissions import PermissionManager

class DesktopActionManager:
    def __init__(self, permission_manager: PermissionManager):
        self.permission_manager = permission_manager

    def open_application(self, app_name: str) -> bool:
        app_name_clean = app_name.lower().strip()
        if not self.permission_manager.is_app_allowed(app_name_clean):
            logging.warning(f"Application '{app_name}' is not in the allowlist!")
            return False

        cmd = self.permission_manager.get_app_command(app_name_clean)
        if not cmd:
            return False

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
