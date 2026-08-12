import logging

try:
    from pycaw.pycaw import AudioUtilities
except ImportError:
    AudioUtilities = None


class AudioMixerManager:
    """Per-application volume control via Windows' audio session API (WASAPI) —
    the same per-app sliders shown in the Windows Volume Mixer. Not gated by the
    desktop-actions allowlist: unlike launching/closing a program, this can only
    ever adjust the volume of something already running, never start, stop, or
    otherwise affect a process — trivially reversible, so any running app's
    session is a fair target.
    """

    def _find_session(self, app_name: str):
        if AudioUtilities is None:
            logging.warning("pycaw não instalado; controle de volume por app indisponível.")
            return None

        app_name_clean = app_name.lower().strip()
        try:
            sessions = AudioUtilities.GetAllSessions()
        except Exception as e:
            logging.error(f"Failed to list audio sessions: {e}")
            return None

        for session in sessions:
            proc = getattr(session, "Process", None)
            if proc is None:
                continue
            try:
                proc_name = proc.name() or ""
            except Exception:
                continue
            proc_stem = proc_name.lower()
            if proc_stem.endswith(".exe"):
                proc_stem = proc_stem[:-4]
            if proc_stem and (proc_stem in app_name_clean or app_name_clean in proc_stem):
                return session
        return None

    def set_volume(self, app_name: str, level: float) -> bool:
        """level: 0.0 (silent) to 1.0 (full volume)."""
        session = self._find_session(app_name)
        if session is None:
            logging.warning(f"No audio session found for '{app_name}'")
            return False

        try:
            volume = session.SimpleAudioVolume
            volume.SetMasterVolume(max(0.0, min(1.0, level)), None)
            return True
        except Exception as e:
            logging.error(f"Failed to set volume for {app_name}: {e}")
            return False
