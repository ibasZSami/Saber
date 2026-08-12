import logging
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from src.core.event_bus import EventBus, TASK_STARTED, TASK_COMPLETED, TASK_FAILED

STATUS_PENDING = "PENDING"
STATUS_RUNNING = "RUNNING"
STATUS_COMPLETED = "COMPLETED"
STATUS_FAILED = "FAILED"


class BackgroundTaskManager:
    """Runs work off the UI thread and tracks its lifecycle/result, so a
    request like "pesquisa isso" can return immediately while the real work
    happens in the background and the app stays usable. Mirrors the
    threading.Thread(daemon=True) pattern already used elsewhere in this
    codebase (spontaneous talk, voice transcription) — just with tracked
    state and completion events instead of a fire-and-forget thread."""

    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create_task(self, task_type: str, description: str, work_fn: Callable[[], Any]) -> str:
        """Starts `work_fn` on a background thread immediately and returns a
        task id right away. `work_fn` takes no arguments and its return value
        becomes the task's `result`."""
        task_id = str(uuid.uuid4())
        task = {
            "id": task_id,
            "type": task_type,
            "description": description,
            "status": STATUS_PENDING,
            "created_at": time.time(),
            "started_at": None,
            "finished_at": None,
            "result": None,
            "error": None,
        }
        with self._lock:
            self._tasks[task_id] = task

        def _run():
            with self._lock:
                task["status"] = STATUS_RUNNING
                task["started_at"] = time.time()
            self.event_bus.emit(TASK_STARTED, task_id=task_id, task_type=task_type, description=description)
            try:
                result = work_fn()
                with self._lock:
                    task["result"] = result
                    task["status"] = STATUS_COMPLETED
                    task["finished_at"] = time.time()
                self.event_bus.emit(
                    TASK_COMPLETED, task_id=task_id, task_type=task_type, description=description, result=result
                )
            except Exception as e:
                logging.error(f"Background task {task_id} ({task_type}) failed: {e}")
                with self._lock:
                    task["error"] = str(e)
                    task["status"] = STATUS_FAILED
                    task["finished_at"] = time.time()
                self.event_bus.emit(
                    TASK_FAILED, task_id=task_id, task_type=task_type, description=description, error=str(e)
                )

        threading.Thread(target=_run, daemon=True).start()
        return task_id

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            task = self._tasks.get(task_id)
            return dict(task) if task else None

    def list_tasks(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(t) for t in self._tasks.values()]
