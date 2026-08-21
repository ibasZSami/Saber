"""Agent Engine — FASE 2. Tracks the lifecycle of a multi-step agentic task
(see src/core/agent_engine.py for the loop that actually drives one):
step history, hard safety limits (max steps, timeout, repetition), and
pause/resume/cancel. Deliberately doesn't execute anything itself —
AgentEngine polls exceeded_limits()/get_task() and calls
record_step()/complete()/fail()."""

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from src.core.event_bus import (
    EventBus,
    TASK_LOOP_STARTED, TASK_LOOP_STEP, TASK_LOOP_PAUSED, TASK_LOOP_RESUMED,
    TASK_LOOP_CANCELLED, TASK_LOOP_COMPLETED, TASK_LOOP_FAILED,
)

# Conservative defaults — a runaway task loop calling the AI (and real tools)
# unattended is the actual risk FASE 2 exists to contain. Callers can pass
# tighter (never looser without a reason) values per task.
DEFAULT_MAX_STEPS = 15
DEFAULT_TIMEOUT_SECONDS = 300.0
# Same (action, action_param) chosen this many times in a row — the AI is
# stuck, not making progress, and would otherwise loop until max_steps.
REPETITION_LIMIT = 3


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


_ACTIVE_STATUSES = (TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.PAUSED)


@dataclass(frozen=True)
class TaskStep:
    action: str
    action_param: Any
    observation: str
    timestamp: float


@dataclass
class Task:
    id: str
    goal: str
    max_steps: int
    timeout_seconds: float
    status: TaskStatus = TaskStatus.PENDING
    steps: List[TaskStep] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    result: Optional[str] = None
    error: Optional[str] = None

    @property
    def step_count(self) -> int:
        return len(self.steps)

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.created_at


class TaskManager:
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self._tasks: Dict[str, Task] = {}

    def create_task(self, goal: str, max_steps: int = DEFAULT_MAX_STEPS,
                     timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> Task:
        task = Task(id=str(uuid.uuid4()), goal=goal, max_steps=max_steps, timeout_seconds=timeout_seconds)
        self._tasks[task.id] = task
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def list_tasks(self) -> List[Task]:
        return list(self._tasks.values())

    def start(self, task_id: str):
        task = self._tasks[task_id]
        task.status = TaskStatus.RUNNING
        self.event_bus.emit(TASK_LOOP_STARTED, task_id=task_id, goal=task.goal)

    def record_step(self, task_id: str, action: str, action_param, observation: str):
        task = self._tasks[task_id]
        task.steps.append(TaskStep(action=action, action_param=action_param, observation=observation, timestamp=time.time()))
        self.event_bus.emit(
            TASK_LOOP_STEP, task_id=task_id, action=action, action_param=action_param,
            observation=observation, step_number=task.step_count,
        )

    def pause(self, task_id: str):
        task = self._tasks[task_id]
        if task.status == TaskStatus.RUNNING:
            task.status = TaskStatus.PAUSED
            self.event_bus.emit(TASK_LOOP_PAUSED, task_id=task_id)

    def resume(self, task_id: str):
        task = self._tasks[task_id]
        if task.status == TaskStatus.PAUSED:
            task.status = TaskStatus.RUNNING
            self.event_bus.emit(TASK_LOOP_RESUMED, task_id=task_id)

    def cancel(self, task_id: str):
        task = self._tasks[task_id]
        if task.status in _ACTIVE_STATUSES:
            task.status = TaskStatus.CANCELLED
            self.event_bus.emit(TASK_LOOP_CANCELLED, task_id=task_id)

    def complete(self, task_id: str, result: str):
        task = self._tasks[task_id]
        task.status = TaskStatus.COMPLETED
        task.result = result
        self.event_bus.emit(TASK_LOOP_COMPLETED, task_id=task_id, result=result)

    def fail(self, task_id: str, error: str):
        task = self._tasks[task_id]
        task.status = TaskStatus.FAILED
        task.error = error
        self.event_bus.emit(TASK_LOOP_FAILED, task_id=task_id, error=error)

    def exceeded_limits(self, task_id: str) -> Optional[str]:
        """Returns a human-readable stop reason if the task has hit a hard
        limit, else None. Checked by AgentEngine before every step."""
        task = self._tasks[task_id]
        if task.step_count >= task.max_steps:
            return f"Limite de {task.max_steps} passos atingido."
        if task.elapsed_seconds >= task.timeout_seconds:
            return f"Tempo limite de {int(task.timeout_seconds)}s atingido."
        if self._is_repeating(task):
            return "A mesma ação se repetiu — parando pra evitar loop infinito."
        return None

    def _is_repeating(self, task: Task) -> bool:
        if len(task.steps) < REPETITION_LIMIT:
            return False
        last_n = task.steps[-REPETITION_LIMIT:]
        first = (last_n[0].action, last_n[0].action_param)
        return all((s.action, s.action_param) == first for s in last_n)
