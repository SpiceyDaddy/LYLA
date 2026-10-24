from collections import OrderedDict
from dataclasses import asdict, dataclass
from datetime import datetime
import threading
from uuid import uuid4


MAX_CHAT_TASKS = 100


@dataclass
class ChatTask:
    task_id: str
    message: str
    agent_id: str
    routing: str
    status: str
    created_at: str
    completed_at: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


class ChatTaskTracker:
    """Keep a bounded, session-only trace of chat requests."""

    def __init__(self, max_records: int = MAX_CHAT_TASKS):
        if max_records < 1:
            raise ValueError("Task history must keep at least one record.")
        self._max_records = max_records
        self._tasks: OrderedDict[str, ChatTask] = OrderedDict()
        self._lock = threading.Lock()

    def start(self, message: str, agent_id: str, routing: str) -> ChatTask:
        with self._lock:
            while len(self._tasks) >= self._max_records:
                oldest_finished = next(
                    (
                        task_id
                        for task_id, task in self._tasks.items()
                        if task.status in {"completed", "failed"}
                    ),
                    None,
                )
                if oldest_finished is None:
                    raise RuntimeError(
                        "LYLA has reached the limit of active chat tasks."
                    )
                del self._tasks[oldest_finished]

            task = ChatTask(
                task_id=uuid4().hex,
                message=message,
                agent_id=agent_id,
                routing=routing,
                status="in_progress",
                created_at=datetime.now().astimezone().isoformat(
                    timespec="seconds"
                ),
            )
            self._tasks[task.task_id] = task
            return task

    def complete(self, task_id: str) -> ChatTask:
        return self._finish(task_id, "completed")

    def fail(self, task_id: str, error: str) -> ChatTask:
        return self._finish(task_id, "failed", error=error)

    def _finish(
        self, task_id: str, status: str, *, error: str | None = None
    ) -> ChatTask:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise KeyError(f"Unknown chat task: {task_id}")
            if task.status != "in_progress":
                raise RuntimeError(
                    f"Chat task {task_id} is already {task.status}."
                )
            task.status = status
            task.completed_at = datetime.now().astimezone().isoformat(
                timespec="seconds"
            )
            task.error = error
            return task

    def recent(self, limit: int = MAX_CHAT_TASKS) -> list[dict[str, str | None]]:
        if not 1 <= limit <= MAX_CHAT_TASKS:
            raise ValueError(f"Task history limit must be from 1 to {MAX_CHAT_TASKS}.")
        with self._lock:
            return [
                task.to_dict()
                for task in reversed(self._tasks.values())
            ][:limit]
