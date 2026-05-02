"""
Persistent task runner — ensures background tasks survive crashes.

Instead of relying on FastAPI's BackgroundTasks (in-memory, lost on crash),
we use asyncio tasks tracked in-process with DB status updates.

Key improvements over BackgroundTasks:
  - Tasks are always recorded in DB as 'pending' before starting
  - On crash/restart, stale tasks are recovered (already in lifespan)
  - 'pending' tasks can be automatically started on boot
  - Progress updates are written to DB for each state transition
"""

import asyncio
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)

# In-process tracking of running tasks
_running_tasks: dict[str, asyncio.Task] = {}


def start_task(task_id: str, coro) -> asyncio.Task:
    """
    Start an asyncio task and track it in-process.

    Args:
        task_id: The TranslationTask ID from the DB.
        coro: The coroutine to run (e.g. _run_translation_workflow(task_id)).
    """
    # Cancel existing task if already running (shouldn't happen, but safety)
    if task_id in _running_tasks and not _running_tasks[task_id].done():
        _running_tasks[task_id].cancel()

    task = asyncio.create_task(coro, name=f"task-{task_id}")
    _running_tasks[task_id] = task

    def _on_done(t: asyncio.Task):
        _running_tasks.pop(task_id, None)
        if t.cancelled():
            logger.info("Task cancelled", task_id=task_id)
        elif exc := t.exception():
            logger.error("Task failed with exception", task_id=task_id, error=str(exc))

    task.add_done_callback(_on_done)
    logger.info("Started persistent task", task_id=task_id)
    return task


def cancel_task(task_id: str) -> bool:
    """Cancel a running task. Returns True if task was found and cancelled."""
    if task_id in _running_tasks and not _running_tasks[task_id].done():
        _running_tasks[task_id].cancel()
        return True
    return False


def is_running(task_id: str) -> bool:
    """Check if a task is currently running in-process."""
    return task_id in _running_tasks and not _running_tasks[task_id].done()


def running_count() -> int:
    """Number of currently running tasks."""
    return sum(1 for t in _running_tasks.values() if not t.done())


async def recover_pending_tasks():
    """
    Start 'pending' tasks that were never started.
    Called on boot after stale task recovery.
    """
    from app.core.database import async_session
    from app.models.database import TranslationTask
    from sqlalchemy import select

    async with async_session() as session:
        result = await session.execute(
            select(TranslationTask).where(
                TranslationTask.status == "pending"
            )
        )
        pending = result.scalars().all()

    if not pending:
        return

    logger.info("Recovering pending tasks", count=len(pending))
    for task in pending:
        try:
            from app.api.tasks import _run_translation_workflow
            start_task(task.id, _run_translation_workflow(task.id))
        except Exception as e:
            logger.error("Failed to recover task", task_id=task.id, error=str(e))