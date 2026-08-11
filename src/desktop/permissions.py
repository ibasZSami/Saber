import logging
from typing import Dict, Any

class PermissionManager:
    def __init__(self, allowlist: Dict[str, str] = None):
        self.allowlist = allowlist or {}

    def is_app_allowed(self, app_key: str) -> bool:
        return app_key.lower() in self.allowlist

    def get_app_command(self, app_key: str) -> str:
        return self.allowlist.get(app_key.lower())

    def update_allowlist(self, app_key: str, command_path: str):
        self.allowlist[app_key.lower()] = command_path
