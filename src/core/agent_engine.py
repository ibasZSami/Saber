"""Agent Engine — FASE 2. Drives a multi-step goal end to end:

    OBSERVAR (histórico de passos/observações já feitos)
        -> DECIDIR (uma chamada à IA por passo — ver src/ai/prompts.py's
           build_agent_system_prompt e src/ai/agent_response.py)
        -> AGIR (via AgentCore.execute — mesmo caminho de permissão/
           confirmação de qualquer ação de chat normal, sem atalho)
        -> VERIFICAR (o resultado vira "observação" pro próximo passo)
        -> REPETIR

until the AI marks the task done, or TaskManager cuts it off (max steps,
timeout, or the same action repeating — see src/core/task_manager.py).

Deliberately reuses the SAME AgentCore/ToolRegistry as ordinary chat
actions instead of a parallel dispatch path — a task-loop step that wants
to open an app still goes through the real CONFIRM dialog and allowlist,
nothing here bypasses that."""

import logging
import threading
import time
from typing import Callable, Optional

from src.ai.agent_response import parse_agent_response
from src.ai.prompts import build_agent_system_prompt
from src.core.agent_core import AgentCore
from src.core.event_bus import EventBus
from src.core.task_manager import TaskManager, TaskStatus
from src.core.tool_registry import describe_tools

# How many recent steps are included in the prompt each iteration — enough
# for the AI to see it's stuck/making progress without the prompt growing
# unbounded on a long task (TaskManager's own max_steps caps it further
# anyway, but this keeps prompt size flat even at that cap).
MAX_HISTORY_STEPS_IN_PROMPT = 8

# How long to sleep between polls while a task is PAUSED — short enough
# that resume() feels immediate, long enough not to busy-spin a thread.
PAUSE_POLL_SECONDS = 0.2


class AgentEngine:
    def __init__(self, ai_provider, agent_core: AgentCore, task_manager: TaskManager, event_bus: EventBus):
        self.ai_provider = ai_provider
        self.agent_core = agent_core
        self.task_manager = task_manager
        self.event_bus = event_bus

    def run(
        self, goal: str, on_finish: Optional[Callable[[str, bool], None]] = None,
        max_steps: Optional[int] = None, timeout_seconds: Optional[float] = None,
    ) -> str:
        """Starts a new task on a background thread and returns its id
        immediately — on_finish(result_or_reason, succeeded) is called
        exactly once, when the task stops for any reason."""
        kwargs = {}
        if max_steps is not None:
            kwargs["max_steps"] = max_steps
        if timeout_seconds is not None:
            kwargs["timeout_seconds"] = timeout_seconds
        task = self.task_manager.create_task(goal, **kwargs)
        threading.Thread(target=self._run_loop, args=(task.id, on_finish), daemon=True).start()
        return task.id

    def _run_loop(self, task_id: str, on_finish: Optional[Callable[[str, bool], None]]):
        # A cancel() racing between run() creating the task and this thread
        # actually starting must not be silently undone — start() would
        # otherwise unconditionally flip status back to RUNNING.
        if self.task_manager.get_task(task_id).status == TaskStatus.CANCELLED:
            return
        self.task_manager.start(task_id)
        try:
            while True:
                task = self.task_manager.get_task(task_id)
                if task.status == TaskStatus.CANCELLED:
                    return
                if task.status == TaskStatus.PAUSED:
                    time.sleep(PAUSE_POLL_SECONDS)
                    continue

                stop_reason = self.task_manager.exceeded_limits(task_id)
                if stop_reason:
                    self.task_manager.fail(task_id, stop_reason)
                    if on_finish:
                        on_finish(stop_reason, False)
                    return

                system_prompt = build_agent_system_prompt(describe_tools())
                prompt = self._build_prompt(task)
                raw = self.ai_provider.chat(prompt, system_prompt, [], image_base64=None)
                parsed = parse_agent_response(raw)

                if parsed["done"]:
                    result = parsed.get("result") or "Tarefa concluída."
                    self.task_manager.complete(task_id, result)
                    if on_finish:
                        on_finish(result, True)
                    return

                action = parsed.get("action", "Nenhuma")
                action_param = parsed.get("action_param", "")
                success = self.agent_core.execute(action, action_param)
                observation = "Ação executada com sucesso." if success else "Ação falhou ou foi recusada."
                self.task_manager.record_step(task_id, action, action_param, observation)
        except Exception as e:
            logging.error(f"Agent loop crashed for task {task_id}: {e}", exc_info=True)
            self.task_manager.fail(task_id, str(e))
            if on_finish:
                on_finish(str(e), False)

    def _build_prompt(self, task) -> str:
        lines = [f"[Objetivo]: {task.goal}", ""]
        if task.steps:
            lines.append("[Histórico de passos já executados]:")
            for i, step in enumerate(task.steps[-MAX_HISTORY_STEPS_IN_PROMPT:], 1):
                lines.append(f"{i}. Ação: {step.action}({step.action_param!r}) -> {step.observation}")
        else:
            lines.append("[Nenhum passo executado ainda — este é o primeiro.]")
        return "\n".join(lines)
