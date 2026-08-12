import logging
import threading
import time
from PySide6.QtCore import QTimer

from src.config.settings import Settings, DEFAULT_ASSETS_PATH
from src.core.event_bus import (
    EventBus,
    GAME_STARTED, GAME_ENDED, APPLICATION_CHANGED, WINDOW_CHANGED, SCREEN_CHANGED,
    AI_STARTED, AI_FINISHED, ACTION_REQUESTED, ACTION_EXECUTED, ACTION_REJECTED,
    VISION_REQUESTED, VISION_RESULT, TRANSLATION_REQUESTED,
    USER_SPOKE, SYSTEM_AUDIO_DETECTED, VOICE_STARTED, VOICE_FINISHED,
    ERROR_OCCURRED, SPONTANEOUS_SPEECH,
)
from src.core.state_machine import StateMachine
from src.character.sprite_loader import SpriteLoader
from src.character.animation_manager import AnimationManager
from src.character.state_manager import CharacterStateManager
from src.character.behavior import AutonomousBehaviorManager

from src.ai.provider import OpenAIProvider, OllamaProvider, NvidiaProvider
from src.ai.prompts import SYSTEM_PROMPT
from src.ai.tools import parse_ai_response
from src.ai.context import ContextManager

from src.vision.screen_capture import ScreenCapture, encode_image_base64
from src.vision.change_detector import ScreenChangeDetector
from src.vision.translation import ScreenTranslationManager

from src.desktop.window_manager import WindowManager
from src.desktop.application_manager import ApplicationManager
from src.desktop.permissions import PermissionManager
from src.desktop.actions import DesktopActionManager

from src.memory.manager import MemoryManager
from src.voice.tts import EdgeTTSProvider, Pyttsx3Provider, DEFAULT_VOICE
from src.voice.input import VoiceInput
from src.voice.system_audio import SystemAudioListener

# Words that suggest the user is asking about what's currently on screen.
# Vision models are noticeably slower than text-only ones on the free tier, so a
# screenshot is only attached when it's actually likely to be relevant — not on
# every single chat message.
VISION_TRIGGER_KEYWORDS = [
    "tela", "screen", "vê isso", "olha isso", "olha aqui", "vendo isso",
    "o que você vê", "o que tem aqui", "isso aqui", "analisa isso", "traduz",
]

# Explicit spoken/typed command that turns on full screen vision immediately.
VISION_ACTIVATION_PHRASE = "minha tela"

# Explicit spoken/typed commands that turn on system-audio listening (game/PC sound).
SYSTEM_AUDIO_ACTIVATION_PHRASES = ["está ouvindo o som do jogo", "está ouvindo o som do pc"]

# Explicit spoken/typed commands that toggle spontaneous, unprompted remarks
# ("como numa chamada" — a companion who occasionally comments on its own,
# not just when spoken to) on and off.
SPONTANEOUS_TALK_DISABLE_PHRASE = "pare de falar aleatoriamente"
SPONTANEOUS_TALK_ENABLE_PHRASE = "ativar falar aleatoriamente"

# How often to even consider making a spontaneous remark, and how long to
# stay quiet after the user last spoke, so it doesn't talk over a fresh
# exchange or chatter constantly.
SPONTANEOUS_TALK_CHECK_INTERVAL_S = 75
SPONTANEOUS_TALK_IDLE_GAP_S = 45

SPONTANEOUS_TALK_PROMPT = (
    "[Comentário espontâneo — você está apenas acompanhando o usuário casualmente, como em uma "
    "chamada de voz juntos, não respondendo a uma pergunta. Fale direto, em primeira pessoa, "
    "NUNCA narrando em terceira pessoa. Se tiver algo breve e natural para comentar sobre o "
    "contexto atual (o que está na tela, se está jogando, etc.), diga. Se não houver nada "
    "específico pra comentar, puxe assunto por conta própria — escolha um destes tipos de "
    "assunto e varie bastante, não repita sempre o mesmo tipo:\n"
    "- Uma piada curta ou trocadilho (pode ser de gato/magia, já que você é um gato-mago);\n"
    "- Uma curiosidade aleatória e divertida (sobre gatos, magia, jogos, tecnologia, o que vier);\n"
    "- Uma pergunta casual sobre o dia, o humor ou o que o usuário está fazendo/sentindo;\n"
    "- Um comentário sobre algo que você lembra do usuário (memórias salvas, se houver);\n"
    "- Uma observação brincalhona sobre si mesmo (você como personagem: sono, fome de petisco, "
    "vontade de caçar algo, feitiço que deu errado, etc.);\n"
    "- Se o usuário estiver há muito tempo sem falar/parado, uma sugestão leve de pausa, água ou "
    "alongar as pernas, com carinho, sem ser chato;\n"
    "- Uma mini-história ou pensamento aleatório e engraçado, de poucas frases.\n"
    "Se realmente não tiver nada bom pra dizer agora, responda com \"speech\": \"\" e ação "
    "Nenhuma — NÃO force um comentário ruim.]"
)

# A smaller text model responds noticeably faster (~3s vs ~8s measured for the
# 70b model on ordinary questions) while still following the action/JSON format
# reliably *given explicit examples in the system prompt* (see ai/prompts.py) —
# without those examples it mis-formats "remember"/"forget_memory"'s nested
# key/value and skips "search_web" entirely, so don't drop the examples.
DEFAULT_TEXT_MODEL = "meta/llama-3.1-8b-instruct"
DEFAULT_VISION_MODEL = "meta/llama-3.2-11b-vision-instruct"

class CompanionOrchestrator:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.event_bus = EventBus()
        self.state_machine = StateMachine("IDLE")

        # Tracked so _check_screen_and_app can emit *_CHANGED/*_STARTED/*_ENDED only on
        # actual transitions, and so GAMING has somewhere to revert to when a game closes.
        self._last_window_title = None
        self._last_app_category = None
        self._is_game_active = False

        # Spontaneous/unprompted remarks ("como numa chamada")
        self.spontaneous_talk_enabled = self.settings.get("spontaneous_talk_enabled", True)
        self._last_interaction_time = time.monotonic()
        self._last_spontaneous_time = 0.0

        # Initialize Character & Animation
        assets_path = self.settings.get("assets_path", DEFAULT_ASSETS_PATH)
        self.sprite_loader = SpriteLoader(assets_path)
        self.animation_manager = AnimationManager(self.sprite_loader)
        self.state_manager = CharacterStateManager(self.state_machine, self.animation_manager)
        self.behavior_manager = AutonomousBehaviorManager(self.state_manager)

        # Initialize AI & Context
        self.context_manager = ContextManager()
        self.memory_manager = MemoryManager()
        self.ai_provider = self._init_ai_provider()
        self.ai_vision_provider = self._init_vision_provider()

        # Initialize Vision
        self.screen_capture = ScreenCapture()
        self.change_detector = ScreenChangeDetector()
        self.translation_manager = ScreenTranslationManager(self.screen_capture)

        # Initialize Desktop Actions
        self.window_manager = WindowManager()
        self.app_manager = ApplicationManager(self.window_manager)
        self.permission_manager = PermissionManager(self.settings.get("allowlist", {}))
        self.action_manager = DesktopActionManager(self.permission_manager)

        # Initialize TTS & Voice Input
        self.tts = self._init_tts_provider()
        self.voice_input = VoiceInput(
            language=self.settings.get("language", "pt-BR").split("-")[0],
            model_size=self.settings.get("whisper_model", "small"),
        )
        self.voice_input.listening_started.connect(lambda: self.state_manager.set_state("LISTENING", reason="Voice input started"))
        self.voice_input.listening_started.connect(lambda: self.event_bus.emit(VOICE_STARTED))
        self.voice_input.listening_stopped.connect(lambda: self.state_manager.set_state("THINKING", reason="Processing voice input"))
        self.voice_input.listening_stopped.connect(lambda: self.event_bus.emit(VOICE_FINISHED))
        self.voice_input.transcription_failed.connect(self._on_voice_transcription_failed)
        self.voice_input.speech_recognized.connect(lambda text: self.event_bus.emit(USER_SPOKE, text=text, source="microphone"))
        if self.settings.get("microphone_enabled", False):
            # Downloads/loads the whisper model ahead of time so the first real
            # Push-to-Talk doesn't sit stuck in "THINKING" for ~20s+ waiting on it.
            self.voice_input.warm_up_model_async()

        # System audio (game/PC sound) listening — shares VoiceInput's whisper
        # model instead of loading a second copy of it.
        self.system_audio_listener = SystemAudioListener(
            language=self.settings.get("language", "pt-BR").split("-")[0],
            model_provider=self.voice_input._ensure_model,
        )
        self.system_audio_listener.transcription_failed.connect(
            lambda reason: logging.warning(f"System audio listening: {reason}")
        )
        self.system_audio_listener.audio_transcribed.connect(
            lambda text: self.event_bus.emit(SYSTEM_AUDIO_DETECTED, text=text)
        )

        # Vision Timer
        self.vision_timer = QTimer()
        self.vision_timer.timeout.connect(self._check_screen_and_app)
        if self.settings.get("screen_monitoring_enabled", False):
            self.vision_timer.start(int(self.settings.get("screen_interval_seconds", 2.0) * 1000))

        # Spontaneous Talk Timer — periodically considers making an unprompted remark
        self.spontaneous_talk_timer = QTimer()
        self.spontaneous_talk_timer.timeout.connect(self._maybe_speak_spontaneously)
        self.spontaneous_talk_timer.start(SPONTANEOUS_TALK_CHECK_INTERVAL_S * 1000)

    def _init_tts_provider(self):
        provider_name = self.settings.get("voice_provider", "edge_tts")
        if provider_name == "pyttsx3":
            return Pyttsx3Provider()
        return EdgeTTSProvider()

    def _init_ai_provider(self):
        provider_name = self.settings.get("ai_provider", "nvidia")
        if provider_name == "nvidia":
            return NvidiaProvider(api_key=self.settings.get("api_key", ""), model=self.settings.get("ai_model", DEFAULT_TEXT_MODEL))
        elif provider_name == "ollama":
            return OllamaProvider()
        return OpenAIProvider(api_key=self.settings.get("api_key", ""), model=self.settings.get("ai_model", "gpt-4o-mini"))

    def _init_vision_provider(self):
        """A second provider dedicated to vision-relevant messages. Returns None
        when the current AI provider has no reliable vision option (e.g. Ollama
        today) — callers should fall back to the regular text provider then."""
        provider_name = self.settings.get("ai_provider", "nvidia")
        if provider_name == "nvidia":
            return NvidiaProvider(api_key=self.settings.get("api_key", ""), model=self.settings.get("ai_vision_model", DEFAULT_VISION_MODEL))
        elif provider_name == "openai":
            return OpenAIProvider(api_key=self.settings.get("api_key", ""), model=self.settings.get("ai_vision_model", "gpt-4o-mini"))
        return None

    def _on_voice_transcription_failed(self, reason: str):
        logging.info(f"Voice transcription failed: {reason}")
        self.state_manager.set_state("CONFUSED", reason=f"Voice input failed: {reason}")

    def set_vision_monitoring(self, enabled: bool):
        self.settings.set("screen_monitoring_enabled", enabled)
        if enabled:
            if not self.vision_timer.isActive():
                self.vision_timer.start(int(self.settings.get("screen_interval_seconds", 2.0) * 1000))
        else:
            self.vision_timer.stop()

    def set_full_vision(self, enabled: bool):
        """Turns the whole screen-vision pipeline on/off: the periodic context
        timer AND private mode (screenshots are only ever sent when both are set)."""
        self.settings.set("private_mode", not enabled)
        self.set_vision_monitoring(enabled)

    def _check_screen_and_app(self):
        # Application context check
        app_ctx = self.app_manager.detect_context()
        self.context_manager.set_app_context(app_ctx)

        window_title = app_ctx.get("window_title")
        category = app_ctx.get("category")
        is_game = app_ctx.get("is_game", False)

        if window_title != self._last_window_title:
            self._last_window_title = window_title
            self.event_bus.emit(WINDOW_CHANGED, title=window_title)

        if category != self._last_app_category:
            self._last_app_category = category
            self.event_bus.emit(APPLICATION_CHANGED, category=category, title=window_title)

        if is_game and not self._is_game_active:
            self._is_game_active = True
            self.event_bus.emit(GAME_STARTED, title=window_title)
            self.state_manager.set_state("GAMING", reason="Game detected")
        elif not is_game and self._is_game_active:
            # Previously GAMING never reverted once a game closed — the character
            # stayed stuck "playing" indefinitely. This is the fix.
            self._is_game_active = False
            self.event_bus.emit(GAME_ENDED, title=window_title)
            self.state_manager.set_state("IDLE", reason="Game closed")

        # Screen change check
        if self.settings.get("screen_monitoring_enabled", False) and not self.settings.get("private_mode", True):
            img = self.screen_capture.capture_primary()
            if self.change_detector.has_changed(img):
                self.context_manager.set_screen_context({"changed": True, "title": window_title})
                self.event_bus.emit(SCREEN_CHANGED, title=window_title)

    def _maybe_activate_vision_command(self, user_text: str):
        if VISION_ACTIVATION_PHRASE in user_text.lower():
            self.set_full_vision(True)

    def _maybe_activate_system_audio_command(self, user_text: str):
        lowered = user_text.lower()
        if any(phrase in lowered for phrase in SYSTEM_AUDIO_ACTIVATION_PHRASES):
            self.system_audio_listener.set_enabled(True)

    def _maybe_toggle_spontaneous_talk(self, user_text: str):
        lowered = user_text.lower()
        if SPONTANEOUS_TALK_DISABLE_PHRASE in lowered:
            self.spontaneous_talk_enabled = False
            self.settings.set("spontaneous_talk_enabled", False)
        elif SPONTANEOUS_TALK_ENABLE_PHRASE in lowered:
            self.spontaneous_talk_enabled = True
            self.settings.set("spontaneous_talk_enabled", True)

    def _maybe_speak_spontaneously(self):
        if not self.spontaneous_talk_enabled:
            return
        if self.state_machine.get_state() in ("THINKING", "LISTENING"):
            return  # an exchange is already happening — don't talk over it

        now = time.monotonic()
        if now - self._last_interaction_time < SPONTANEOUS_TALK_IDLE_GAP_S:
            return  # the user just interacted — give it a beat
        if now - self._last_spontaneous_time < SPONTANEOUS_TALK_CHECK_INTERVAL_S:
            return

        self._last_spontaneous_time = now
        self._trigger_spontaneous_comment()

    def _trigger_spontaneous_comment(self):
        """A lighter-weight sibling of handle_user_message's worker: speech-only,
        no vision/actions/memory recording, and never counted as a real user turn."""
        def _worker():
            try:
                history = self.memory_manager.get_history(limit=4)
                memories = self.memory_manager.get_memories()
                prompt_payload = self.context_manager.build_prompt_context(memories, SPONTANEOUS_TALK_PROMPT)

                raw_ai = self.ai_provider.chat(prompt_payload, SYSTEM_PROMPT, history, image_base64=None)
                parsed = parse_ai_response(raw_ai)
                speech = parsed.get("speech", "").strip()
                if not speech:
                    return

                anim_name = parsed.get("animation", "TALKING")
                self.state_manager.set_state(anim_name, reason="Spontaneous comment")

                tts_kwargs = {
                    "voice": self.settings.get("voice", DEFAULT_VOICE),
                    "volume": self.settings.get("voice_volume", 1.0),
                    "speed": self.settings.get("voice_speed", 1.0),
                    "pitch": self.settings.get("voice_pitch", "+0Hz"),
                }
                threading.Thread(target=self.tts.speak, args=(speech,), kwargs=tts_kwargs, daemon=True).start()
                self.event_bus.emit(SPONTANEOUS_SPEECH, speech=speech)
            except Exception as e:
                logging.error(f"Spontaneous comment error: {e}")

        threading.Thread(target=_worker, daemon=True).start()

    def _should_attach_vision(self, user_text: str) -> bool:
        vision_available = self.settings.get("screen_monitoring_enabled", False) and not self.settings.get("private_mode", True)
        vision_requested = any(kw in user_text.lower() for kw in VISION_TRIGGER_KEYWORDS)
        return vision_available and vision_requested

    def _select_provider(self, vision_needed: bool):
        if vision_needed and self.ai_vision_provider:
            return self.ai_vision_provider
        return self.ai_provider

    def _execute_action(self, action: str, action_param) -> bool:
        """Dispatches a structured action parsed from the AI response. Returns True if handled."""
        if not action or action == "Nenhuma":
            return False

        self.event_bus.emit(ACTION_REQUESTED, action=action, action_param=action_param)

        success = False
        if action == "open_application" and action_param:
            success = bool(self.action_manager.open_application(action_param))
        elif action == "open_url" and action_param:
            success = bool(self.action_manager.open_url(action_param))
        elif action == "search_web" and action_param:
            success = bool(self.action_manager.search_web(action_param))
        elif action == "remember" and isinstance(action_param, dict) and action_param.get("key"):
            self.memory_manager.remember(action_param["key"], action_param.get("value", ""))
            success = True
        elif action == "forget_memory" and action_param:
            key = action_param.get("key") if isinstance(action_param, dict) else action_param
            self.memory_manager.forget(key)
            success = True

        self.event_bus.emit(ACTION_EXECUTED if success else ACTION_REJECTED, action=action, action_param=action_param)
        return success

    def handle_user_message(self, user_text: str, on_response=None):
        self._last_interaction_time = time.monotonic()
        self.state_manager.set_state("THINKING", reason="Processing user query")

        def _worker():
            try:
                self._maybe_activate_vision_command(user_text)
                self._maybe_activate_system_audio_command(user_text)
                self._maybe_toggle_spontaneous_talk(user_text)

                memories = self.memory_manager.get_memories()
                history = self.memory_manager.get_history(limit=6)

                # Real screen vision: attach a live screenshot only when enabled, not in
                # private mode, AND the message actually seems to be about the screen —
                # vision calls are noticeably slower/less reliable, so we don't pay that
                # cost (or risk it) on every message; see _select_provider.
                vision_needed = self._should_attach_vision(user_text)
                image_b64 = None
                if vision_needed:
                    self.event_bus.emit(VISION_REQUESTED, reason="message_keyword")
                    try:
                        image_b64 = encode_image_base64(self.screen_capture.capture_primary())
                    except Exception as e:
                        logging.error(f"Failed to capture screen for vision: {e}")
                    self.event_bus.emit(VISION_RESULT, success=bool(image_b64))

                provider = self._select_provider(vision_needed=bool(image_b64))
                prompt_payload = self.context_manager.build_prompt_context(memories, user_text, vision_enabled=bool(image_b64))

                # Check explicit translation command
                if any(cmd in user_text.lower() for cmd in ["traduz", "traduza", "translate"]):
                    self.event_bus.emit(TRANSLATION_REQUESTED)
                    res_trans = self.translation_manager.translate_current_screen()
                    prompt_payload += f"\n[Resultado OCR Tela]: {res_trans.get('original_text')}"

                self.event_bus.emit(AI_STARTED)
                raw_ai = provider.chat(prompt_payload, SYSTEM_PROMPT, history, image_base64=image_b64)
                self.event_bus.emit(AI_FINISHED)
                parsed = parse_ai_response(raw_ai)

                speech = parsed.get("speech", "").strip()
                anim_name = parsed.get("animation", "TALKING")
                action = parsed.get("action", "Nenhuma")
                action_param = parsed.get("action_param", "")

                # This is a real question the user asked (unlike the spontaneous-talk
                # path, where staying silent is intentional) — an empty reply here means
                # the model/parsing failed, not that there's nothing to say, so never
                # leave the user with silence after actually asking something.
                if not speech:
                    speech = "Desculpa, não consegui pensar em uma resposta agora. Pode repetir?"
                    anim_name = "CONFUSED"

                # Perform action if requested
                self._execute_action(action, action_param)

                # Record memory
                self.memory_manager.record_turn(user_text, speech)

                # UI Update & TTS Execution
                self.state_manager.set_state(anim_name, reason="AI Response")
                tts_kwargs = {
                    "voice": self.settings.get("voice", DEFAULT_VOICE),
                    "volume": self.settings.get("voice_volume", 1.0),
                    "speed": self.settings.get("voice_speed", 1.0),
                    "pitch": self.settings.get("voice_pitch", "+0Hz"),
                }
                threading.Thread(target=self.tts.speak, args=(speech,), kwargs=tts_kwargs, daemon=True).start()

                if on_response:
                    on_response(speech)
            except Exception as e:
                # Without this, an uncaught exception here (network error, bad JSON,
                # provider crash) silently kills the thread and leaves the character
                # stuck in THINKING forever — the state never gets a chance to recover.
                logging.error(f"Unhandled error processing message: {e}", exc_info=True)
                self.event_bus.emit(ERROR_OCCURRED, source="handle_user_message", error=str(e))
                self.state_manager.set_state("CONFUSED", reason="Internal error")
                if on_response:
                    on_response("Desculpa, tive um problema processando isso. Pode tentar de novo?")

        threading.Thread(target=_worker, daemon=True).start()
