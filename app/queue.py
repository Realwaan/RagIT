"""
Enterprise Task Queue Decoupling Layer for RagIT.

Decouples heavy ingestion (PDF parsing, OCR, table reconstruction, and vector embedding)
from HTTP request loops. Designed for concurrent multi-user environments (up to 30 active users)
using an in-process bounded async worker pool with pluggable Redis/Celery capability for multi-node scale.
"""

from __future__ import annotations
import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional

from app import config as cfg

logger = logging.getLogger("ragit.queue")


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskJob:
    job_id: str
    task_type: str
    payload: Dict[str, Any]
    user_id: str = "anonymous"
    tenant_id: str = "default"
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


class BaseTaskQueue:
    """Abstract interface for RagIT task queues."""

    async def enqueue(
        self,
        task_type: str,
        payload: Dict[str, Any],
        user_id: str = "anonymous",
        tenant_id: str = "default",
    ) -> TaskJob:
        raise NotImplementedError

    async def get_job(self, job_id: str) -> Optional[TaskJob]:
        raise NotImplementedError

    async def update_progress(self, job_id: str, progress: float, stage: str = "") -> None:
        raise NotImplementedError

    async def complete_job(self, job_id: str, result: Dict[str, Any]) -> None:
        raise NotImplementedError

    async def fail_job(self, job_id: str, error: str) -> None:
        raise NotImplementedError

    async def cancel_job(self, job_id: str) -> bool:
        raise NotImplementedError

    async def list_jobs(self, user_id: Optional[str] = None, limit: int = 50) -> List[TaskJob]:
        raise NotImplementedError


class InMemoryTaskQueue(BaseTaskQueue):
    """
    Lightweight, high-performance in-memory bounded async worker queue.
    Optimal for 1 to 30 concurrent users without requiring external Redis/RabbitMQ infrastructure.
    """

    def __init__(self, max_workers: int = 3):
        self.max_workers = max(1, max_workers)
        self.queue: asyncio.Queue[TaskJob] = asyncio.Queue()
        self.jobs: Dict[str, TaskJob] = {}
        self.workers: List[asyncio.Task] = []
        self._handlers: Dict[str, Callable[[TaskJob], Coroutine[Any, Any, Dict[str, Any]]]] = {}
        self._running = False
        self._lock = asyncio.Lock()

    def register_handler(
        self,
        task_type: str,
        handler: Callable[[TaskJob], Coroutine[Any, Any, Dict[str, Any]]],
    ) -> None:
        self._handlers[task_type] = handler

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        for i in range(self.max_workers):
            task = asyncio.create_task(self._worker_loop(i))
            self.workers.append(task)
        logger.info(f"TaskQueue: Started {self.max_workers} worker threads.")

    async def stop(self) -> None:
        self._running = False
        for worker in self.workers:
            worker.cancel()
        self.workers.clear()

    async def _worker_loop(self, worker_id: int) -> None:
        while self._running:
            try:
                job = await self.queue.get()
                if job.status == TaskStatus.CANCELLED:
                    self.queue.task_done()
                    continue

                job.status = TaskStatus.RUNNING
                job.started_at = time.time()
                handler = self._handlers.get(job.task_type)

                if not handler:
                    job.status = TaskStatus.FAILED
                    job.error = f"No registered handler for task type '{job.task_type}'"
                    job.completed_at = time.time()
                    self.queue.task_done()
                    continue

                try:
                    res = await handler(job)
                    job.status = TaskStatus.COMPLETED
                    job.result = res
                    job.progress = 1.0
                except asyncio.CancelledError:
                    job.status = TaskStatus.CANCELLED
                    job.error = "Job cancelled by worker termination"
                    break
                except Exception as e:
                    logger.exception(f"Worker {worker_id} failed executing job {job.job_id}")
                    job.status = TaskStatus.FAILED
                    job.error = str(e)
                finally:
                    job.completed_at = time.time()
                    self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"TaskQueue worker error: {e}")

    async def enqueue(
        self,
        task_type: str,
        payload: Dict[str, Any],
        user_id: str = "anonymous",
        tenant_id: str = "default",
    ) -> TaskJob:
        job_id = f"job_{uuid.uuid4().hex[:16]}"
        job = TaskJob(
            job_id=job_id,
            task_type=task_type,
            payload=payload,
            user_id=user_id,
            tenant_id=tenant_id,
        )
        async with self._lock:
            self.jobs[job_id] = job
            # Keep memory bounded: retain up to 500 recent completed jobs
            if len(self.jobs) > 500:
                completed_ids = [
                    k for k, v in self.jobs.items()
                    if v.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
                ]
                for old_id in completed_ids[:50]:
                    self.jobs.pop(old_id, None)

        await self.queue.put(job)
        return job

    async def get_job(self, job_id: str) -> Optional[TaskJob]:
        return self.jobs.get(job_id)

    async def update_progress(self, job_id: str, progress: float, stage: str = "") -> None:
        job = self.jobs.get(job_id)
        if job:
            job.progress = max(0.0, min(1.0, progress))
            if stage and job.payload is not None:
                job.payload["current_stage"] = stage

    async def complete_job(self, job_id: str, result: Dict[str, Any]) -> None:
        job = self.jobs.get(job_id)
        if job:
            job.status = TaskStatus.COMPLETED
            job.result = result
            job.progress = 1.0
            job.completed_at = time.time()

    async def fail_job(self, job_id: str, error: str) -> None:
        job = self.jobs.get(job_id)
        if job:
            job.status = TaskStatus.FAILED
            job.error = error
            job.completed_at = time.time()

    async def cancel_job(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if not job or job.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            return False
        job.status = TaskStatus.CANCELLED
        job.completed_at = time.time()
        return True

    async def list_jobs(self, user_id: Optional[str] = None, limit: int = 50) -> List[TaskJob]:
        all_jobs = list(self.jobs.values())
        if user_id:
            all_jobs = [j for j in all_jobs if j.user_id == user_id]
        all_jobs.sort(key=lambda j: j.created_at, reverse=True)
        return all_jobs[:limit]


_GLOBAL_QUEUE: Optional[BaseTaskQueue] = None


def get_task_queue() -> BaseTaskQueue:
    global _GLOBAL_QUEUE
    if _GLOBAL_QUEUE is None:
        workers = getattr(cfg, "TASK_QUEUE_WORKERS", 3)
        _GLOBAL_QUEUE = InMemoryTaskQueue(max_workers=workers)
    return _GLOBAL_QUEUE
