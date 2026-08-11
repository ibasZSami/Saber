import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication(sys.argv)
