import os
import psutil
import logging

try:
    import pygetwindow as gw
except ImportError:
    gw = None

class WindowManager:
    def get_active_window_info(self) -> dict:
        if gw is not None:
            try:
                win = gw.getActiveWindow()
                if win:
                    return {
                        "title": win.title,
                        "width": win.width,
                        "height": win.height,
                        "is_active": True
                    }
            except Exception as e:
                logging.debug(f"Error getting active window title: {e}")

        return {
            "title": "Desktop / Unknown",
            "width": 0,
            "height": 0,
            "is_active": True
        }
