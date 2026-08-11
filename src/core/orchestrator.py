import logging
import threading
from PySide6.QtCore import QTimer

from src.config.settings import Settings
from src.core.event_bus import EventBus
from src.core.state_machine import StateMachine
from src.character.sprite_loader import SpriteLoader
from src.character.animation_manager import AnimationManager
from src.character.state_manager import CharacterStateManager
from src.character.behavior import AutonomousBehaviorManager

from src.ai.provider import OpenAIProvider, OllamaProvider, NvidiaProvider
from src.ai.prompts import SYSTEM_PROMPT
from src.ai.tools import parse_ai_response
from src.ai.context import ContextManager

from src.vision.screen_capture import ScreenCapture
from src.vision.change_detector import ScreenChangeDetector
from src.vision.translation import ScreenTranslationManager

from src.desktop.window_manager import WindowManager
from src.desktop.application_manager import ApplicationManager
from src.desktop.permissions import PermissionManager
from src.desktop.actions import DesktopActionManager

from src.memory.manager import MemoryManager
from src.voice.tts import EdgeTTSProvider, Pyttsx3Provider

class CompanionOrchestrator:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.event_bus = EventBus()
        self.state_machine = StateMachine("IDLE")

        # Initialize Character & Animation
        assets_path = self.settings.get("assets_path", r"C:\Users\ribas\Downloads\shimeji_animations_transparent")
        self.sprite_loader = SpriteLoader(assets_path)
        self.animation_manager = AnimationManager(self.sprite_loader, default_fps=self.settings.get("fps", 12))
        self.state_manager = CharacterStateManager(self.state_machine, self.animation_manager)
        self.behavior_manager = AutonomousBehaviorManager(self.state_manager)

        # Initialize AI & Context
        self.context_manager = ContextManager()
        self.memory_manager = MemoryManager()
        self.ai_provider = self._init_ai_provider()

        # Initialize Vision
        self.screen_capture = ScreenCapture()
        self.change_detector = ScreenChangeDetector()
        self.translation_manager = ScreenTranslationManager(self.screen_capture)

        # Initialize Desktop Actions
        self.window_manager = WindowManager()
        self.app_manager = ApplicationManager(self.window_manager)
        self.permission_manager = PermissionManager(self.settings.get("allowlist", {}))
        self.action_manager = DesktopActionManager(self.permission_manager)

        # Initialize TTS
        self.tts = EdgeTTSProvider()

        # Vision Timer
        self.vision_timer = QTimer()
        self.vision_timer.timeout.connect(self._check_screen_and_app)
        if self.settings.get("screen_monitoring_enabled", False):
            self.vision_timer.start(int(self.settings.get("screen_interval_seconds", 2.0) * 1000))

    def _init_ai_provider(self):
        provider_name = self.settings.get("ai_provider", "nvidia")
        if provider_name == "nvidia":
            return NvidiaProvider(api_key=self.settings.get("api_key", ""), model=self.settings.get("ai_model", "meta/llama-3.1-70b-instruct"))
        elif provider_name == "ollama":
            return OllamaProvider()
        return OpenAIProvider(api_key=self.settings.get("api_key", ""), model=self.settings.get("ai_model", "gpt-4o-mini"))

    def set_vision_monitoring(self, enabled: bool):
        self.settings.set("screen_monitoring_enabled", enabled)
        if enabled:
            if not self.vision_timer.isActive():
                self.vision_timer.start(int(self.settings.get("screen_interval_seconds", 2.0) * 1000))
        else:
            self.vision_timer.stop()

    def _check_screen_and_app(self):
        # Application context check
        app_ctx = self.app_manager.detect_context()
        self.context_manager.set_app_context(app_ctx)

        if app_ctx.get("is_game"):
            self.state_manager.set_state("GAMING", reason="Game detected")

        # Screen change check
        if self.settings.get("screen_monitoring_enabled", False) and not self.settings.get("private_mode", True):
            img = self.screen_capture.capture_primary()
            if self.change_detector.has_changed(img):
                self.context_manager.set_screen_context({"changed": True, "title": app_ctx.get("window_title")})

    def handle_user_message(self, user_text: str, on_response=None):
        self.state_manager.set_state("THINKING", reason="Processing user query")

        def _worker():
            memories = self.memory_manager.get_memories()
            history = self.memory_manager.get_history(limit=6)
            prompt_payload = self.context_manager.build_prompt_context(memories, user_text)

            # Check explicit translation command
            if any(cmd in user_text.lower() for cmd in ["traduz", "traduza", "translate"]):
                res_trans = self.translation_manager.translate_current_screen()
                prompt_payload += f"\n[Resultado OCR Tela]: {res_trans.get('original_text')}"

            raw_ai = self.ai_provider.chat(prompt_payload, SYSTEM_PROMPT, history)
            parsed = parse_ai_response(raw_ai)

            speech = parsed.get("speech", "")
            anim_name = parsed.get("animation", "TALKING")
            action = parsed.get("action", "Nenhuma")
            action_param = parsed.get("action_param", "")

            # Perform action if requested
            if action == "open_application" and action_param:
                self.action_manager.open_application(action_param)
            elif action == "open_url" and action_param:
                self.action_manager.open_url(action_param)
            elif action == "search_web" and action_param:
                self.action_manager.search_web(action_param)
            elif action == "remember" and isinstance(action_param, dict) and action_param.get("key"):
                self.memory_manager.remember(action_param["key"], action_param.get("value", ""))
            elif action == "forget_memory" and action_param:
                key = action_param.get("key") if isinstance(action_param, dict) else action_param
                self.memory_manager.forget(key)

            # Record memory
            self.memory_manager.record_turn(user_text, speech)

            # UI Update & TTS Execution
            self.state_manager.set_state(anim_name, reason="AI Response")
            if speech:
                threading.Thread(target=self.tts.speak, args=(speech,), daemon=True).start()

            if on_response:
                on_response(speech)

        threading.Thread(target=_worker, daemon=True).start()
