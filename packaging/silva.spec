# PyInstaller spec for Silva.
#
# Builds a **onedir** bundle (not onefile): onefile re-extracts the whole
# app to a fresh temp dir on every launch, which is slow to start and pointless
# here since Silva already writes its own data (config.json, data/memory/*,
# plugins/) next to the executable — onedir lets those live directly beside
# Silva.exe instead of a throwaway temp folder.
#
# Run from the project root:
#   pyinstaller packaging/silva.spec --noconfirm
#
# Output lands in dist/Silva/Silva.exe. See packaging/silva.iss to turn that
# folder into a real Silva-Setup.exe installer (requires Inno Setup, a
# separate one-time download — see packaging/README.md).

import sys
from pathlib import Path

block_cipher = None

PROJECT_ROOT = Path(SPECPATH).resolve().parent


def _tree_datas(src_dir: Path, dest_prefix: str):
    """Walks src_dir and returns (file, dest_dir) pairs for Analysis(datas=...),
    skipping __pycache__ — plain os.walk copy (the "(dir, dest)" tuple form)
    pulls in stray .pyc caches left over from running the plugin under test/dev,
    which have no business in a shipped installer."""
    pairs = []
    for path in src_dir.rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts:
            rel_dir = path.parent.relative_to(src_dir)
            dest = f"{dest_prefix}/{rel_dir}".rstrip("/.")
            pairs.append((str(path), dest))
    return pairs


a = Analysis(
    [str(PROJECT_ROOT / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=(
        # Character sprites — src/config/settings.py's DEFAULT_ASSETS_PATH
        # looks for these next to the executable in a frozen build.
        _tree_datas(PROJECT_ROOT / "extracted_assets" / "silva", "extracted_assets/silva")
        # Plugin examples — kept editable next to the exe, same as source layout.
        + _tree_datas(PROJECT_ROOT / "plugins", "plugins")
    ),
    hiddenimports=[
        "edge_tts",
        "pyttsx3.drivers",
        "pyttsx3.drivers.sapi5",
        "pygame",
        "cv2",
        "playwright.sync_api",
        "pynput.keyboard._win32",
        "pynput.mouse._win32",
        "faster_whisper",
        "soundcard",
        "sounddevice",
        "pycaw",
        "comtypes",
        "keyboard",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Silva",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(PROJECT_ROOT / "packaging" / "silva.ico"),
    # PyInstaller >=6.0 defaults to tucking everything but the exe itself into
    # a "_internal" subfolder (this belongs on EXE, not COLLECT — COLLECT just
    # inherits it from the EXE instance it's passed). src/config/settings.py's
    # frozen-mode PROJECT_ROOT is sys.executable's own directory (see the
    # comment there), so extracted_assets/ and plugins/ need to sit right next
    # to Silva.exe, not one level down in _internal. "." restores the flat
    # pre-6.0 layout.
    contents_directory=".",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="Silva",
)
