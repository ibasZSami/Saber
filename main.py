import os
import sys

# Ensure src is in python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from src.core.app import run_app

if __name__ == "__main__":
    run_app()
