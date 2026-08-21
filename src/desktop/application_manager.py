from src.desktop.window_manager import WindowManager

GAME_KEYWORDS = ["game", "steam", "play", "unreal", "unity", "minecraft", "roblox", "palworld", "league", "valorant"]

class ApplicationManager:
    def __init__(self, window_manager: WindowManager):
        self.window_manager = window_manager

    def detect_context(self) -> dict:
        info = self.window_manager.get_active_window_info()
        title = info.get("title", "").lower()

        is_game = any(kw in title for kw in GAME_KEYWORDS)
        category = "general"

        if is_game:
            category = "gaming"
        elif any(b in title for b in ["chrome", "firefox", "edge", "brave", "youtube"]):
            category = "browser"
        elif any(c in title for c in ["visual studio", "vscode", "pycharm", "sublime", "git"]):
            category = "coding"
        elif "discord" in title:
            category = "chat"

        return {
            "window_title": info.get("title"),
            "category": category,
            "is_game": is_game
        }
