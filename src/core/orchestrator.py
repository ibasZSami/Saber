import logging
import threading
import time
from datetime import datetime
from typing import Optional
from PySide6.QtCore import QTimer, QMetaObject, Qt, Q_ARG

from src.config.settings import Settings, DEFAULT_ASSETS_PATH
from src.core.event_bus import (
    EventBus,
    GAME_STARTED, GAME_ENDED, APPLICATION_CHANGED, WINDOW_CHANGED, SCREEN_CHANGED,
    AI_STARTED, AI_FINISHED,
    VISION_REQUESTED, VISION_RESULT, TRANSLATION_REQUESTED,
    USER_SPOKE, SYSTEM_AUDIO_DETECTED, VOICE_STARTED, VOICE_FINISHED,
    ERROR_OCCURRED, SPONTANEOUS_SPEECH,
    NERD_MODE_TOGGLED, VISION_MONITORING_TOGGLED, APP_AUTO_RESOLVED, TASK_COMPLETED, TASK_FAILED,
)
from src.core.state_machine import StateMachine
from src.core.silva_state import SilvaState
from src.core.activity_log import ActivityLog
from src.core.scheduler import Scheduler
from src.core import reminder_parser
from src.core.task_manager import TaskManager
from src.core.agent_engine import AgentEngine
from src.desktop.input_control import InputController
from src.desktop.terminal_tool import TerminalToolManager
from src.core.translation_mode import TranslationMode, TranslationModeState
from src.vision.translation_engine import TranslationEngine
from src.memory.database import Database
from src.vision.continuous_vision import ContinuousVisionBuffer, VisionMode
from src.core.tool_registry import build_default_registry
from src.core.agent_core import AgentCore
from src.core.news import NewsProvider
from src.core.background_tasks import BackgroundTaskManager
from src.core.research import ResearchManager
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
from src.desktop.permission_policy import PermissionPolicyManager
from src.desktop.actions import DesktopActionManager
from src.desktop.audio_mixer import AudioMixerManager
from src.desktop.web_search import WebSearchProvider

from src.memory.manager import MemoryManager
from src.memory.relevance import select_relevant_memories
from src.voice.tts import EdgeTTSProvider, Pyttsx3Provider, FallbackTTSProvider, DEFAULT_VOICE
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

# NERD MODE: a more proactive posture, toggled by voice/text. The confirmation
# reply is spoken deterministically (see _maybe_toggle_nerd_mode) rather than
# left to the LLM, so it's always exactly this phrase, reliably and instantly —
# it's a pure command, not something that needs an AI call to answer.
NERD_MODE_ENABLE_PHRASES = [
    "ativar modo nerd", "ativa o modo nerd", "modo nerd", "vira nerd", "virar nerd",
]
NERD_MODE_DISABLE_PHRASES = ["desativar modo nerd", "desliga o modo nerd", "sai do modo nerd"]
NERD_MODE_ENABLED_REPLY = "Modo Nerd ativado."
NERD_MODE_DISABLED_REPLY = "Modo Nerd desativado."

# Translation Mode (FASE 7) — continuous OCR+translate+overlay, distinct
# from the existing one-shot "Traduz isso" trigger further down (checked
# AFTER this one short-circuits, so "traduz isso"/"traduza" never reach
# here: neither contains the substring "traduzir"). Disable checked first
# for the same reason as nerd mode above — "parar de traduzir" contains
# "traduzir" as a substring, so checking enable first would misfire "on"
# for a stop command.
TRANSLATION_MODE_ENABLE_PHRASES = ["traduzir a tela", "modo tradução", "ativar tradução", "traduzir"]
TRANSLATION_MODE_DISABLE_PHRASES = ["parar tradução", "parar de traduzir", "desativar tradução", "para a tradução"]
TRANSLATION_MODE_ENABLED_REPLY = "Tradução ativada — vou traduzir o que aparecer na tela."
TRANSLATION_MODE_DISABLED_REPLY = "Tradução desativada."
TRANSLATION_MODE_ALREADY_ON_REPLY = "A tradução já está ativada."
TRANSLATION_MODE_ALREADY_OFF_REPLY = "A tradução já estava desativada."

# Cancels the Agent Engine's currently-running task (FASE 10 chat trigger,
# see _start_agent_task / _maybe_cancel_task).
CANCEL_TASK_PHRASES = ["cancela a tarefa", "cancela isso", "para a tarefa", "para com isso"]
CANCEL_TASK_CANCELLED_REPLY = "Beleza, parei a tarefa."
CANCEL_TASK_NOTHING_RUNNING_REPLY = "Não tem nenhuma tarefa rodando pra cancelar."

# NERD MODE makes spontaneous talk noticeably more present — shorter checks
# and a shorter idle gap — without yet being the full multi-signal relevance
# scoring described in the roadmap (InitiativeEngine, not built yet).
NERD_SPONTANEOUS_TALK_CHECK_INTERVAL_S = 40
NERD_SPONTANEOUS_TALK_IDLE_GAP_S = 20

# How often to even consider making a spontaneous remark, and how long to
# stay quiet after the user last spoke, so it doesn't talk over a fresh
# exchange or chatter constantly.
SPONTANEOUS_TALK_CHECK_INTERVAL_S = 75
SPONTANEOUS_TALK_IDLE_GAP_S = 45

# FASE 12 — how often due reminders are checked.
SCHEDULER_CHECK_INTERVAL_S = 5

# How many spontaneous-talk checks a headline gets offered to the model before
# giving up on it. A single shot meant most headlines were wasted on a turn
# where the (fast, not fully reliable) model picked a different topic instead —
# but offering it too many times made the same story dominate every comment
# once it became the top/[DESTAQUE] headline. 2 is enough to actually land the
# story without it feeling like the only thing Silva ever talks about.
MAX_HEADLINE_OFFERS = 2

SPONTANEOUS_TALK_PROMPT = (
    "[Comentário espontâneo — você está apenas acompanhando o usuário casualmente, como em uma "
    "chamada de voz juntos, não respondendo a uma pergunta. Fale direto, em primeira pessoa, "
    "NUNCA narrando em terceira pessoa.\n"
    "PRIORIDADE MÁXIMA: se houver manchetes reais listadas em [Notícias recentes] abaixo, "
    "SEMPRE prefira comentar uma delas — é o assunto principal que você deve puxar quando não "
    "houver algo específico na tela pra comentar, muito mais do que piada/curiosidade/etc. "
    "Comente como quem viu algo interessante e quer contar — sua opinião/reação em poucas frases, "
    "não uma leitura seca de manchete. Se alguma vier marcada como [DESTAQUE], é prioridade ainda "
    "maior: conte essa, com um tom de \"olha só que notícia\", porque é algo grande sendo muito "
    "comentado agora.\n"
    "IMPORTANTE sobre notícias: SÓ fale de uma notícia se ela estiver literalmente listada em "
    "[Notícias recentes] abaixo. NUNCA invente, deduza ou complete notícias.\n"
    "Se tiver algo breve e natural para comentar sobre o contexto atual (o que está na tela, se "
    "está jogando, etc.), isso também vale, mas notícias reais disponíveis vêm antes.\n"
    "Se não houver notícias novas nem nada específico pra comentar, aí sim puxe assunto por "
    "conta própria — escolha um destes tipos e varie bastante, não repita sempre o mesmo tipo:\n"
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
# For messages that actually need careful reasoning (explanations, comparisons,
# "why"/"how" questions, longer asks) the fast 8B model tends to go incoherent or
# miss the point — this bigger model is measurably slower (~8s vs ~3s) but far
# more reliable, so it's only used when _is_complex_query() says the message
# warrants it, not on every message.
DEFAULT_COMPLEX_MODEL = "meta/llama-3.1-70b-instruct"

# Phrases that suggest the user wants an explanation/reasoning/analysis rather
# than a quick reply — routes the message to DEFAULT_COMPLEX_MODEL instead of
# the fast default. See _is_complex_query.
COMPLEX_QUERY_KEYWORDS = [
    "por que", "porque", "explica", "explique", "como funciona", "compare",
    "diferença entre", "analisa", "analise", "resolve", "resolva", "calcula",
    "calcule", "passo a passo", "detalha", "detalhe", "resuma", "resumo",
    "código", "codigo", "escreve um", "escreva um",
]
# A long message is also treated as complex even without a keyword match —
# elaborate asks tend to run long regardless of phrasing.
COMPLEX_QUERY_WORD_THRESHOLD = 25

class CompanionOrchestrator:
    def __init__(self, settings: Settings, confirm_fn=None):
        self.settings = settings
        # (action, action_param, description) -> bool — asks the user before a
        # CONFIRM-tier tool runs (see src/core/agent_core.py). Injected rather
        # than built here so CompanionOrchestrator doesn't need to know about
        # Qt dialogs; app.py wires the real one (src/ui/confirmation_dialog.py).
        # None (the default) keeps the old auto-approve behavior — used by
        # tests and any caller that hasn't wired a real confirmation UI.
        self.confirm_fn = confirm_fn
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
        self.news_provider = NewsProvider()
        # How many times each headline has been offered to the model. A fast/
        # weak model doesn't reliably follow "prioritize this" every single
        # time, so a headline gets several chances (MAX_HEADLINE_OFFERS) across
        # spontaneous-talk checks before being dropped — marking it "used" after
        # a single offer meant most headlines were burned on a turn where the
        # model happened to pick a different topic, and never came up again.
        self._headline_offer_counts = {}

        # NERD MODE: a more proactive posture, toggled by voice/text (see
        # _maybe_toggle_nerd_mode). Persisted like spontaneous_talk_enabled.
        self.nerd_mode_enabled = self.settings.get("nerd_mode_enabled", False)

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
        self.ai_complex_provider = self._init_complex_provider()

        # Initialize Vision
        self.screen_capture = ScreenCapture()
        self.change_detector = ScreenChangeDetector()
        self.translation_manager = ScreenTranslationManager(self.screen_capture)
        # FASE 10: rolling metadata-only buffer feeding AWARENESS-mode
        # structured context (see _compute_vision_mode, _check_screen_and_app).
        self.vision_buffer = ContinuousVisionBuffer()

        # Translation Mode (FASE 5/6/7) — continuous OCR+translate+overlay,
        # separate from the one-shot "Traduz isso" flow above.
        # ScreenChangeDetector here is a SEPARATE instance from
        # self.change_detector (the periodic vision-monitoring one) — two
        # independent consumers must never share one stateful detector.
        # Reuses translation_manager's own OCR provider rather than
        # constructing a second one.
        self.translation_engine = TranslationEngine(self.ai_provider, self.event_bus)
        self.translation_mode = TranslationMode(
            self.screen_capture, ScreenChangeDetector(), self.translation_manager.ocr,
            self.translation_engine, self.event_bus,
        )

        # Initialize Desktop Actions
        self.window_manager = WindowManager()
        self.app_manager = ApplicationManager(self.window_manager)
        self.permission_manager = PermissionManager(self.settings.get("allowlist", {}))
        self.action_manager = DesktopActionManager(self.permission_manager, on_app_resolved=self._on_app_resolved)
        self.audio_mixer_manager = AudioMixerManager()
        # Per (action, target) CONFIRM policy — "already decided to always
        # allow/block this" — distinct from permission_manager's allowlist
        # (which only answers "do we know how to launch this app at all").
        # See src/desktop/permission_policy.py.
        self.policy_manager = PermissionPolicyManager(self.settings)

        # Background tasks (e.g. "research_topic") — tracked, non-blocking work
        # that reports back via TASK_COMPLETED/TASK_FAILED instead of a
        # fire-and-forget thread. Research uses the complex/strong model since
        # it runs off the interaction path anyway — latency doesn't matter here,
        # quality does.
        self.background_task_manager = BackgroundTaskManager(self.event_bus)
        self.research_manager = ResearchManager(WebSearchProvider(), self.ai_complex_provider or self.ai_provider)
        self.event_bus.subscribe(TASK_COMPLETED, self._on_task_completed)
        self.event_bus.subscribe(TASK_FAILED, self._on_task_failed)

        # Reminders/timers (FASE 12) — persisted via their own Database()
        # instance (same sqlite file MemoryManager uses; sqlite handles the
        # separate-connection sharing fine for this access pattern), checked
        # on a timer below once the rest of __init__ has run.
        self.scheduler = Scheduler(Database(), self.event_bus, on_fire=self._on_reminder_fired)

        # Mouse/keyboard and terminal tools (FASE 3) — each gated by its own
        # Settings master switch, OFF by default. Unless enabled, the
        # corresponding manager stays None and build_default_registry below
        # leaves those tools with no dispatch handler at all — not just
        # unconfirmed, genuinely inert. See src/desktop/input_control.py and
        # src/desktop/terminal_tool.py.
        self.input_controller = (
            InputController() if self.settings.get("input_control_enabled", False) else None
        )
        self.terminal_tool_manager = (
            TerminalToolManager(self.settings.get("terminal_allowlist", {}), self.event_bus)
            if self.settings.get("terminal_tool_enabled", False) else None
        )

        # Tool dispatch (SAFE/CONFIRM/DANGEROUS tiers) — see src/core/tool_registry.py
        # and src/core/agent_core.py for the FASE 2 Agent Core extraction.
        self.tool_registry = build_default_registry(
            self.action_manager, self.memory_manager, self.audio_mixer_manager,
            self.background_task_manager, self.research_manager, self.scheduler,
            self.input_controller, self.terminal_tool_manager,
            self.screen_capture, self.translation_manager.ocr, self.translation_mode,
        )
        self.agent_core = AgentCore(
            self.tool_registry, self.event_bus, confirm_fn=self.confirm_fn, policy_manager=self.policy_manager,
        )

        # Agent Engine (FASE 2/10) — multi-step goal execution (OBSERVAR/
        # DECIDIR/AGIR/VERIFICAR/REPETIR), reusing this same agent_core so a
        # task-loop step still goes through the real CONFIRM/allowlist flow
        # (and only ever sees mouse/keyboard/terminal as options if the
        # switches above are on). Reachable from chat via the AI's own
        # "start_task" action (see handle_user_message) — the AI decides
        # when a request genuinely needs multiple steps, per SYSTEM_PROMPT's
        # explicit rule for when to use it vs. a direct single action.
        self.task_manager = TaskManager(self.event_bus)
        self.agent_engine = AgentEngine(
            self.ai_complex_provider or self.ai_provider, self.agent_core, self.task_manager, self.event_bus,
        )
        # Tracks the most recently started agent task so a deterministic
        # "cancela a tarefa" command has something to cancel — see
        # _maybe_cancel_task. Only one task at a time is supported for now.
        self._active_task_id: Optional[str] = None

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

        # Spontaneous Talk Timer — periodically considers making an unprompted remark.
        # Ticks at the shorter NERD-mode interval always; _maybe_speak_spontaneously
        # itself applies the slower normal-mode thresholds when Nerd mode is off, so
        # toggling the mode doesn't require restarting this timer with a new interval.
        self.spontaneous_talk_timer = QTimer()
        self.spontaneous_talk_timer.timeout.connect(self._maybe_speak_spontaneously)
        self.spontaneous_talk_timer.start(NERD_SPONTANEOUS_TALK_CHECK_INTERVAL_S * 1000)

        # Reminder check — deliberately more frequent than the spontaneous
        # talk timers above since a reminder is a real commitment ("me lembra
        # em 1 minuto"), not idle chatter; a few seconds of slack is fine.
        self.scheduler_timer = QTimer()
        self.scheduler_timer.timeout.connect(self.scheduler.check_due)
        self.scheduler_timer.start(SCHEDULER_CHECK_INTERVAL_S * 1000)

        # Read-only "what's happening right now" facade over everything
        # constructed above — see src/core/silva_state.py. Built last, once
        # every subsystem it reads from actually exists.
        self.silva_state = SilvaState(self)

        # Friendly action history ("Atividade" tab in Settings) — subscribes
        # to the EventBus above, so it must be built after everything that
        # emits the events it listens for is already wired up.
        self.activity_log = ActivityLog(self.event_bus)

    def _init_tts_provider(self):
        provider_name = self.settings.get("voice_provider", "edge_tts")
        if provider_name == "pyttsx3":
            return Pyttsx3Provider()
        # EdgeTTS needs network; fall back to fully-offline pyttsx3 on failure
        # instead of going silent — see FallbackTTSProvider's docstring.
        return FallbackTTSProvider(EdgeTTSProvider(), Pyttsx3Provider())

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

    def _init_complex_provider(self):
        """A second text provider for messages that seem to need real reasoning
        (see _is_complex_query) — the fast default model trades that away for
        speed. Returns None for providers with no separate strong-model concept
        worth swapping to (e.g. Ollama's single local model); callers fall back
        to the regular fast provider then."""
        provider_name = self.settings.get("ai_provider", "nvidia")
        if provider_name == "nvidia":
            return NvidiaProvider(api_key=self.settings.get("api_key", ""), model=self.settings.get("ai_model_complex", DEFAULT_COMPLEX_MODEL))
        elif provider_name == "openai":
            return OpenAIProvider(api_key=self.settings.get("api_key", ""), model=self.settings.get("ai_model_complex", "gpt-4o"))
        return None

    def _on_app_resolved(self, app_name: str, command: str):
        """DesktopActionManager calls this after auto-resolving an app the
        user asked to open that wasn't in the allowlist yet (see
        app_resolver.py). Deliberately does NOT persist it — the allowlist is
        the user's real permission boundary, so an app Silva happened to
        resolve once shouldn't silently become permanently allowed. Just lets
        the UI tell the user it was a one-off resolution, and that they can
        add it for real via Configurações → Aplicativos if they want it
        remembered."""
        self.event_bus.emit(APP_AUTO_RESOLVED, app_name=app_name, command=command)

    def _on_voice_transcription_failed(self, reason: str):
        logging.info(f"Voice transcription failed: {reason}")
        self.state_manager.set_state("IDLE", reason=f"Voice input failed: {reason}")
        self.state_manager.set_emotion("CONFUSED", reason=f"Voice input failed: {reason}")

    def set_vision_monitoring(self, enabled: bool):
        # Callers include voice/text commands (handled on a worker thread) and
        # the global "-" hotkey (handled on the `keyboard` package's own listener
        # thread) — QTimer.start()/.stop() must run on the thread that owns the
        # timer (the main/Qt thread), so this is dispatched via invokeMethod
        # instead of called directly, which would be unsafe from those threads.
        self.settings.set("screen_monitoring_enabled", enabled)
        if enabled:
            interval_ms = int(self.settings.get("screen_interval_seconds", 2.0) * 1000)
            QMetaObject.invokeMethod(self.vision_timer, "start", Qt.AutoConnection, Q_ARG(int, interval_ms))
        else:
            QMetaObject.invokeMethod(self.vision_timer, "stop", Qt.AutoConnection)

    def set_full_vision(self, enabled: bool):
        """Turns the whole screen-vision pipeline on/off: the periodic context
        timer AND private mode (screenshots are only ever sent when both are set).
        Emits VISION_MONITORING_TOGGLED so callers that bypass handle_user_message
        (the "-" hotkey, tray menu, "minha tela" command) can still show the user
        a confirmation — before this, toggling here gave no feedback at all."""
        self.settings.set("private_mode", not enabled)
        self.set_vision_monitoring(enabled)
        self.event_bus.emit(VISION_MONITORING_TOGGLED, enabled=enabled)

    def _compute_vision_mode(self) -> VisionMode:
        """FASE 10: explicit modes instead of a single on/off toggle.

        Backward compatible by construction: unless the new optional
        `screen_vision_mode` setting is explicitly set, this derives OFF/
        ACTIVE from the same two legacy toggles exactly as the code used to
        check inline — private_mode=True ("Nenhuma captura ou OCR" per its
        own UI label) means OFF, full stop, same as before. CONTEXT and
        AWARENESS are new capabilities only reachable by explicitly setting
        screen_vision_mode, so no existing install's behavior changes."""
        explicit = self.settings.get("screen_vision_mode", None)
        if explicit:
            try:
                return VisionMode(explicit)
            except ValueError:
                logging.warning(f"Invalid screen_vision_mode {explicit!r}; falling back to legacy toggles.")
        if not self.settings.get("screen_monitoring_enabled", False) or self.settings.get("private_mode", True):
            return VisionMode.OFF
        return VisionMode.ACTIVE

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

        # Screen change check — see _compute_vision_mode for what drives each mode.
        vision_mode = self._compute_vision_mode()
        if vision_mode is not VisionMode.OFF:
            img = self.screen_capture.capture_primary()
            changed = self.change_detector.has_changed(img)
            # Recorded every tick (not just on change) so staleness can
            # actually be measured later — FASE 11's prompt text relies on
            # this timestamp to say "as of Xs atrás" instead of presenting a
            # possibly-old reading as current.
            self.context_manager.set_screen_context({
                "window_title": window_title, "category": category,
                "changed": changed, "timestamp": time.time(),
            })
            self.vision_buffer.add(window_title=window_title or "", category=category or "geral", changed=changed)
            if changed:
                self.event_bus.emit(SCREEN_CHANGED, title=window_title)

    @staticmethod
    def _contains_any(user_text: str, *phrases: str) -> bool:
        lowered = user_text.lower()
        return any(phrase in lowered for phrase in phrases)

    def _maybe_activate_vision_command(self, user_text: str):
        if self._contains_any(user_text, VISION_ACTIVATION_PHRASE):
            self.set_full_vision(True)

    def _maybe_activate_system_audio_command(self, user_text: str):
        if self._contains_any(user_text, *SYSTEM_AUDIO_ACTIVATION_PHRASES):
            self.system_audio_listener.set_enabled(True)

    def _maybe_toggle_spontaneous_talk(self, user_text: str):
        if self._contains_any(user_text, SPONTANEOUS_TALK_DISABLE_PHRASE):
            self.spontaneous_talk_enabled = False
            self.settings.set("spontaneous_talk_enabled", False)
        elif self._contains_any(user_text, SPONTANEOUS_TALK_ENABLE_PHRASE):
            self.spontaneous_talk_enabled = True
            self.settings.set("spontaneous_talk_enabled", True)

    def _maybe_toggle_nerd_mode(self, user_text: str) -> Optional[str]:
        """Unlike the other _maybe_* toggles, this one returns the
        deterministic confirmation reply (or None) instead of just flipping a
        flag — handle_user_message uses that to skip the AI call entirely for
        a pure mode-toggle command, so the confirmation is instant and always
        exactly right, not something the LLM has to be trusted to phrase.

        Disable phrases are checked first: "desativar modo nerd"/"desliga o
        modo nerd" both contain the bare enable phrase "modo nerd" as a
        substring, so checking enable first would misfire "on" for a disable
        command."""
        if self._contains_any(user_text, *NERD_MODE_DISABLE_PHRASES):
            self.nerd_mode_enabled = False
            self.settings.set("nerd_mode_enabled", False)
            self.event_bus.emit(NERD_MODE_TOGGLED, enabled=False)
            self.state_manager.set_state("IDLE", reason="Nerd mode disabled")
            return NERD_MODE_DISABLED_REPLY
        if self._contains_any(user_text, *NERD_MODE_ENABLE_PHRASES):
            self.nerd_mode_enabled = True
            self.settings.set("nerd_mode_enabled", True)
            self.event_bus.emit(NERD_MODE_TOGGLED, enabled=True)
            self.state_manager.set_state("NERD_ACTIVE", reason="Nerd mode enabled")
            return NERD_MODE_ENABLED_REPLY
        return None

    def _maybe_toggle_translation_mode(self, user_text: str) -> Optional[str]:
        """Same deterministic short-circuit pattern as _maybe_toggle_nerd_mode
        — see TRANSLATION_MODE_* constants' comment for why disable is
        checked first and how this avoids colliding with the existing
        one-shot "Traduz isso" command."""
        if self._contains_any(user_text, *TRANSLATION_MODE_DISABLE_PHRASES):
            if self.translation_mode.state == TranslationModeState.OFF:
                return TRANSLATION_MODE_ALREADY_OFF_REPLY
            self.translation_mode.stop()
            return TRANSLATION_MODE_DISABLED_REPLY
        if self._contains_any(user_text, *TRANSLATION_MODE_ENABLE_PHRASES):
            if self.translation_mode.state != TranslationModeState.OFF:
                return TRANSLATION_MODE_ALREADY_ON_REPLY
            self.translation_mode.start()
            return TRANSLATION_MODE_ENABLED_REPLY
        return None

    def _maybe_cancel_task(self, user_text: str) -> Optional[str]:
        """Deterministic short-circuit, same pattern as the others above —
        stopping a running Agent Engine task is exactly the kind of command
        that should never wait on an AI round-trip to take effect."""
        if not self._contains_any(user_text, *CANCEL_TASK_PHRASES):
            return None
        if self._active_task_id is None:
            return CANCEL_TASK_NOTHING_RUNNING_REPLY
        self.task_manager.cancel(self._active_task_id)
        self._active_task_id = None
        return CANCEL_TASK_CANCELLED_REPLY

    def _start_agent_task(self, goal):
        """Hands a goal off to the Agent Engine's multi-step loop instead of
        a single ToolRegistry dispatch — see handle_user_message's
        "start_task" branch and SYSTEM_PROMPT's rule for when the AI should
        choose this over a direct action. Only one task tracked at a time
        (see _active_task_id) — starting a new one while another runs just
        replaces what "cancela a tarefa" would target next, it doesn't stop
        the previous one (TaskManager itself has no such limit; this is
        purely about what the single cancel command reaches)."""
        if not isinstance(goal, str) or not goal.strip():
            return
        self._active_task_id = self.agent_engine.run(goal.strip(), on_finish=self._on_agent_task_finished)

    def _on_agent_task_finished(self, result: str, success: bool):
        """agent_engine's on_finish callback — runs on the Agent Engine's own
        worker thread, not the GUI thread. Safe to call state_manager/
        _speak_async from here anyway: both ultimately go through Qt
        Signals (AnimationManager.frame_changed, EventBus's own dispatcher)
        that auto-queue across threads — same reasoning already relied on by
        _on_reminder_fired and the spontaneous-comment/task-outcome workers."""
        self._active_task_id = None
        speech = result.strip() if isinstance(result, str) and result.strip() else (
            "Terminei a tarefa." if success else "Não consegui terminar a tarefa."
        )
        self.state_manager.set_state("TALKING", reason="Agent task finished")
        self.state_manager.set_emotion("HAPPY" if success else "SAD", reason="Agent task finished")
        self.memory_manager.record_turn("", speech)
        self._speak_async(speech)
        self.event_bus.emit(SPONTANEOUS_SPEECH, speech=speech)

    def _maybe_create_reminder(self, user_text: str) -> Optional[str]:
        """Same deterministic short-circuit pattern as _maybe_toggle_nerd_mode:
        a real reminder request ("me lembra em 10 minutos de X") gets an
        instant, exact confirmation instead of an AI call that might phrase
        the time back wrong. See src/core/reminder_parser.py."""
        parsed = reminder_parser.parse(user_text)
        if parsed is None:
            return None
        self.scheduler.create(parsed.message, parsed.fire_at, parsed.recurring_seconds)
        when = datetime.fromtimestamp(parsed.fire_at).strftime("%H:%M")
        if parsed.recurring_seconds:
            return f'Combinado, vou te lembrar todo dia às {when}: "{parsed.message}".'
        return f'Combinado, te aviso às {when}: "{parsed.message}".'

    def _on_reminder_fired(self, message: str):
        """Scheduler's on_fire callback — runs on the GUI thread (the
        scheduler_timer QTimer calls check_due directly), so speaking here is
        the same as any other direct call to _speak_async elsewhere in this
        class."""
        speech = f"Lembrete: {message}."
        self.state_manager.set_state("TALKING", reason="Reminder fired")
        self.memory_manager.record_turn("", speech)
        self._speak_async(speech)

    def _maybe_speak_spontaneously(self):
        if not self.spontaneous_talk_enabled:
            return
        if self.state_machine.get_state() in ("THINKING", "LISTENING"):
            return  # an exchange is already happening — don't talk over it

        if self.nerd_mode_enabled:
            idle_gap, check_interval = NERD_SPONTANEOUS_TALK_IDLE_GAP_S, NERD_SPONTANEOUS_TALK_CHECK_INTERVAL_S
        else:
            idle_gap, check_interval = SPONTANEOUS_TALK_IDLE_GAP_S, SPONTANEOUS_TALK_CHECK_INTERVAL_S

        now = time.monotonic()
        if now - self._last_interaction_time < idle_gap:
            return  # the user just interacted — give it a beat
        if now - self._last_spontaneous_time < check_interval:
            return

        self._last_spontaneous_time = now
        self._trigger_spontaneous_comment()

    def _build_news_context(self) -> str:
        """Returns a "[Notícias recentes]" block of headlines still worth
        offering to the model, or "" if there's nothing left to offer. Each
        feed's very first headline (Google's own top-story ranking) is flagged
        [DESTAQUE] — the closest proxy available to "important/well covered"
        without building real trend detection. A headline can be offered up to
        MAX_HEADLINE_OFFERS times (see its docstring) before being dropped."""
        headlines = self.news_provider.get_headlines()
        lines = []
        for label, key in (("Brasil", "brasil"), ("Mundo", "mundo")):
            feed = headlines.get(key, [])
            candidates = [h for h in feed if self._headline_offer_counts.get(h, 0) < MAX_HEADLINE_OFFERS]
            if not candidates:
                continue
            lines.append(f"{label}:")
            for headline in candidates[:3]:
                tag = "[DESTAQUE] " if feed and headline == feed[0] else ""
                lines.append(f"- {tag}{headline}")
                self._headline_offer_counts[headline] = self._headline_offer_counts.get(headline, 0) + 1
        if not lines:
            return ""
        return "[Notícias recentes]:\n" + "\n".join(lines)

    def _trigger_spontaneous_comment(self):
        """A lighter-weight sibling of handle_user_message's worker: speech-only,
        no vision/actions/memory recording, and never counted as a real user turn."""
        def _worker():
            try:
                history = self.memory_manager.get_history(limit=4)
                memories = self.memory_manager.get_memories()
                prompt_payload = self.context_manager.build_prompt_context(memories, SPONTANEOUS_TALK_PROMPT)

                news_context = self._build_news_context()
                if news_context:
                    prompt_payload += f"\n\n{news_context}"

                raw_ai = self.ai_provider.chat(prompt_payload, SYSTEM_PROMPT, history, image_base64=None)
                parsed = parse_ai_response(raw_ai)
                speech = parsed.get("speech", "").strip()
                if not speech:
                    return

                self.state_manager.set_state("TALKING", reason="Spontaneous comment")
                self.state_manager.set_emotion(parsed.get("emotion"), reason="Spontaneous comment")

                # Without this, spontaneous remarks never entered conversation
                # history — if the user then asked to hear more about something
                # Silva brought up on their own, the AI genuinely had no record
                # of having said it. Empty user_text means record_turn only
                # writes the assistant's side (see memory/manager.py).
                self.memory_manager.record_turn("", speech)

                self._speak_async(speech)
                self.event_bus.emit(SPONTANEOUS_SPEECH, speech=speech)
            except Exception as e:
                logging.error(f"Spontaneous comment error: {e}")

        threading.Thread(target=_worker, daemon=True).start()

    def _on_task_completed(self, task_id: str, task_type: str, description: str, result):
        self._announce_task_outcome(task_type, description, success=True, detail=result)

    def _on_task_failed(self, task_id: str, task_type: str, description: str, error: str):
        self._announce_task_outcome(task_type, description, success=False, detail=error)

    def _announce_task_outcome(self, task_type: str, description: str, success: bool, detail):
        """Speaks the outcome of a finished background task (e.g. research_topic)
        unprompted — "avisa quando terminar". Same lightweight shape as
        _trigger_spontaneous_comment (speech-only, no actions/vision), reusing
        SYSTEM_PROMPT so the announcement stays in Silva's voice instead of a
        flat "task completed" string. Runs regardless of nerd_mode_enabled —
        the user asked for a specific result, not idle chatter."""
        def _worker():
            try:
                if success:
                    instruction = (
                        f"[Uma tarefa em segundo plano que você iniciou terminou. Tipo: {task_type}. "
                        f"Sobre: {description}. Resultado: {detail}. Anuncie isso pro usuário na sua voz, "
                        "breve e natural, como quem acabou de descobrir algo interessante — pode comentar "
                        "o conteúdo, não só dizer que terminou.]"
                    )
                else:
                    instruction = (
                        f"[Uma tarefa em segundo plano que você iniciou falhou. Tipo: {task_type}. "
                        f"Sobre: {description}. Erro: {detail}. Avise o usuário disso de forma breve e "
                        "natural, sem tecniquês.]"
                    )
                history = self.memory_manager.get_history(limit=4)
                prompt_payload = self.context_manager.build_prompt_context({}, instruction)

                raw_ai = self.ai_provider.chat(prompt_payload, SYSTEM_PROMPT, history, image_base64=None)
                parsed = parse_ai_response(raw_ai)
                speech = parsed.get("speech", "").strip()
                if not speech:
                    return

                self.state_manager.set_state("TALKING", reason="Background task finished")
                self.state_manager.set_emotion(parsed.get("emotion"), reason="Background task finished")
                self.memory_manager.record_turn("", speech)
                self._speak_async(speech)
                self.event_bus.emit(SPONTANEOUS_SPEECH, speech=speech)
            except Exception as e:
                logging.error(f"Task-outcome announcement error: {e}")

        threading.Thread(target=_worker, daemon=True).start()

    def _should_attach_vision(self, user_text: str) -> bool:
        vision_available = self.settings.get("screen_monitoring_enabled", False) and not self.settings.get("private_mode", True)
        vision_requested = any(kw in user_text.lower() for kw in VISION_TRIGGER_KEYWORDS)
        return vision_available and vision_requested

    def _is_complex_query(self, user_text: str) -> bool:
        """Whether this message seems to need real reasoning (explanation,
        comparison, "why"/"how", or just a long/elaborate ask) rather than a
        quick reply — routes to DEFAULT_COMPLEX_MODEL instead of the fast
        default, which trades reliability for speed on ordinary messages."""
        if any(kw in user_text.lower() for kw in COMPLEX_QUERY_KEYWORDS):
            return True
        return len(user_text.split()) > COMPLEX_QUERY_WORD_THRESHOLD

    def _select_provider(self, vision_needed: bool, complex_needed: bool = False):
        if vision_needed and self.ai_vision_provider:
            return self.ai_vision_provider
        if complex_needed and self.ai_complex_provider:
            return self.ai_complex_provider
        return self.ai_provider

    def _execute_action(self, action: str, action_param) -> bool:
        """Dispatches a structured action parsed from the AI response. Returns True if handled.
        Delegates to AgentCore (src/core/agent_core.py) — kept as a thin wrapper so existing
        callers (including tests) using orch._execute_action(...) directly are unaffected."""
        return self.agent_core.execute(action, action_param)

    def _speak_async(self, speech: str):
        """Speaks `speech` on a background thread using the settings-configured
        voice/volume/speed/pitch — shared by handle_user_message and the
        spontaneous-comment worker so a new TTS-affecting setting only needs
        adding in one place."""
        tts_kwargs = {
            "voice": self.settings.get("voice", DEFAULT_VOICE),
            "volume": self.settings.get("voice_volume", 1.0),
            "speed": self.settings.get("voice_speed", 1.0),
            "pitch": self.settings.get("voice_pitch", "+0Hz"),
        }
        threading.Thread(target=self.tts.speak, args=(speech,), kwargs=tts_kwargs, daemon=True).start()

    def handle_user_message(self, user_text: str, on_response=None, is_direct_input: bool = True):
        """is_direct_input=False marks text that Silva only OVERHEARD rather
        than something the user actually said/typed to her — right now that's
        exactly system-audio transcription (game/PC speaker output routed
        through app.py's _on_system_audio_transcribed, prefixed
        "[Áudio do jogo/PC]:"). Content like that must never gain the same
        authority as a real command: without this flag, a YouTube video in
        the background merely saying "vira nerd" or "minha tela" would
        silently flip real app settings, because the keyword-trigger checks
        below used to run against ANY text, regardless of source. Direct
        typed/spoken input (chat, hands-free mic, push-to-talk — every other
        caller) keeps the default True and is unaffected."""
        self._last_interaction_time = time.monotonic()
        self.state_manager.set_state("THINKING", reason="Processing user query")

        def _worker():
            try:
                vision_needed = False
                if is_direct_input:
                    # A pure command ("vira nerd") gets an instant, deterministic
                    # reply — no AI call needed to answer it, and skipping the LLM
                    # guarantees the exact confirmation phrase.
                    nerd_reply = self._maybe_toggle_nerd_mode(user_text)
                    if nerd_reply is not None:
                        self.memory_manager.record_turn(user_text, nerd_reply)
                        self._speak_async(nerd_reply)
                        if on_response:
                            on_response(nerd_reply)
                        return

                    reminder_reply = self._maybe_create_reminder(user_text)
                    if reminder_reply is not None:
                        self.memory_manager.record_turn(user_text, reminder_reply)
                        self._speak_async(reminder_reply)
                        if on_response:
                            on_response(reminder_reply)
                        return

                    translation_mode_reply = self._maybe_toggle_translation_mode(user_text)
                    if translation_mode_reply is not None:
                        self.memory_manager.record_turn(user_text, translation_mode_reply)
                        self._speak_async(translation_mode_reply)
                        if on_response:
                            on_response(translation_mode_reply)
                        return

                    cancel_task_reply = self._maybe_cancel_task(user_text)
                    if cancel_task_reply is not None:
                        self.memory_manager.record_turn(user_text, cancel_task_reply)
                        self._speak_async(cancel_task_reply)
                        if on_response:
                            on_response(cancel_task_reply)
                        return

                    self._maybe_activate_vision_command(user_text)
                    self._maybe_activate_system_audio_command(user_text)
                    self._maybe_toggle_spontaneous_talk(user_text)

                # "Memória em camadas" part 1: every saved memory used to
                # always enter the prompt regardless of relevance — now only
                # memories that actually relate to what the user just said
                # do (see src/memory/relevance.py). Real user text only —
                # never applied to the spontaneous-comment path, which has
                # no specific message to score relevance against.
                memories = select_relevant_memories(self.memory_manager.get_memories(), user_text)
                history = self.memory_manager.get_history(limit=6)

                # Real screen vision: attach a live screenshot only when enabled, not in
                # private mode, AND the message actually seems to be about the screen —
                # vision calls are noticeably slower/less reliable, so we don't pay that
                # cost (or risk it) on every message; see _select_provider. Gated behind
                # is_direct_input too — overheard audio merely mentioning "tela" must not
                # trigger a real screenshot capture on its own.
                if is_direct_input:
                    vision_needed = self._should_attach_vision(user_text)
                image_b64 = None
                if vision_needed:
                    self.event_bus.emit(VISION_REQUESTED, reason="message_keyword")
                    try:
                        image_b64 = encode_image_base64(self.screen_capture.capture_primary())
                    except Exception as e:
                        logging.error(f"Failed to capture screen for vision: {e}")
                    self.event_bus.emit(VISION_RESULT, success=bool(image_b64))

                complex_needed = self._is_complex_query(user_text)
                provider = self._select_provider(vision_needed=bool(image_b64), complex_needed=complex_needed)
                prompt_payload = self.context_manager.build_prompt_context(memories, user_text, vision_enabled=bool(image_b64))

                # Check explicit translation command — same is_direct_input gate: OCR
                # capture is a real (if not disk-persisted) screen read, must only ever
                # fire because the user actually asked, never because overheard audio
                # happened to contain the word "traduz".
                if is_direct_input and any(cmd in user_text.lower() for cmd in ["traduz", "traduza", "translate"]):
                    self.event_bus.emit(TRANSLATION_REQUESTED)
                    res_trans = self.translation_manager.translate_current_screen()
                    prompt_payload += f"\n[Resultado OCR Tela]: {res_trans.get('original_text')}"

                self.event_bus.emit(AI_STARTED)
                raw_ai = provider.chat(prompt_payload, SYSTEM_PROMPT, history, image_base64=image_b64)
                self.event_bus.emit(AI_FINISHED)
                parsed = parse_ai_response(raw_ai)

                speech = parsed.get("speech", "").strip()
                emotion = parsed.get("emotion", "HAPPY")
                action = parsed.get("action", "Nenhuma")
                action_param = parsed.get("action_param", "")

                # This is a real question the user asked (unlike the spontaneous-talk
                # path, where staying silent is intentional) — an empty reply here means
                # the model/parsing failed, not that there's nothing to say, so never
                # leave the user with silence after actually asking something.
                if not speech:
                    speech = "Desculpa, não consegui pensar em uma resposta agora. Pode repetir?"
                    emotion = "CONFUSED"

                # Perform action if requested — "start_task" is special: it's
                # not a ToolRegistry tool, it hands the goal off to the Agent
                # Engine's multi-step loop instead of a single dispatch call.
                if action == "start_task":
                    self._start_agent_task(action_param)
                else:
                    self._execute_action(action, action_param)

                # Record memory
                self.memory_manager.record_turn(user_text, speech)

                # UI Update & TTS Execution — functional state (TALKING) and
                # emotion (the AI's expressive choice) are independent axes,
                # see src/character/state_manager.py (FASE 13).
                self.state_manager.set_state("TALKING", reason="AI Response")
                self.state_manager.set_emotion(emotion, reason="AI Response")
                self._speak_async(speech)

                if on_response:
                    on_response(speech)
            except Exception as e:
                # Without this, an uncaught exception here (network error, bad JSON,
                # provider crash) silently kills the thread and leaves the character
                # stuck in THINKING forever — the state never gets a chance to recover.
                logging.error(f"Unhandled error processing message: {e}", exc_info=True)
                self.event_bus.emit(ERROR_OCCURRED, source="handle_user_message", error=str(e))
                self.state_manager.set_state("IDLE", reason="Internal error")
                self.state_manager.set_emotion("CONFUSED", reason="Internal error")
                if on_response:
                    on_response("Desculpa, tive um problema processando isso. Pode tentar de novo?")

        threading.Thread(target=_worker, daemon=True).start()
