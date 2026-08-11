import sys
import os
import unittest
from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Initialize QApplication for QPixmap testing
app = QApplication.instance() or QApplication(sys.argv)

from src.character.sprite_loader import SpriteLoader
from src.character.animation_manager import AnimationManager
from src.core.state_machine import StateMachine
from src.memory.manager import MemoryManager
from src.desktop.permissions import PermissionManager
from src.vision.change_detector import ScreenChangeDetector

class TestLumiCompanion(unittest.TestCase):
    def test_sprite_loader_and_animation(self):
        loader = SpriteLoader(r"C:\Users\ribas\Downloads\shimeji_animations_transparent")
        anim_mgr = AnimationManager(loader)
        self.assertIn("idle", anim_mgr.animations)
        frame = anim_mgr.update()
        self.assertIsNotNone(frame)

    def test_state_machine(self):
        sm = StateMachine("IDLE")
        self.assertEqual(sm.get_state(), "IDLE")
        sm.transition_to("WALK")
        self.assertEqual(sm.get_state(), "WALK")

    def test_permission_manager(self):
        pm = PermissionManager({"chrome": "chrome.exe"})
        self.assertTrue(pm.is_app_allowed("chrome"))
        self.assertFalse(pm.is_app_allowed("unknown_app"))

    def test_change_detector(self):
        cd = ScreenChangeDetector(threshold=0.05)
        from PIL import Image
        img1 = Image.new("RGB", (100, 100), color="white")
        img2 = Image.new("RGB", (100, 100), color="black")
        self.assertTrue(cd.has_changed(img1))
        self.assertTrue(cd.has_changed(img2))

if __name__ == "__main__":
    unittest.main()



