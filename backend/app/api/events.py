"""
Server-Sent Events (SSE) for real-time task progress updates.

Simpler than WebSockets, unidirectional (server→client), and works
through proxies without special configuration.

Endpoint: GET /api/tasks/events
Streams task status/progress updates every second when active tasks exist.
"""

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session, async_session
from app.core.logging import get_logger
from app.models.database import TranslationTask, TaskStatusEnum as TSE

logger = get_logger(__name__)
router = APIRouter(prefix="/events", tags=["events"])

# Tracking connected clients for cleanup
_connected_clients: set[str] = set()


_ACTIVE_STATUSES = {
    "pending", "analyzing_context", "translating", "refining",
    "extracting", "transcribing", "syncing", "rescanning",
    "installing",
}


async def task_events_generator(request: Request, limit: int = 50) -> AsyncGenerator[str, None]:
    """
    Generate SSE events for task progress.

    Sends an event every second with a snapshot of active/recent tasks.
    Only returns:
    - Tasks with active status (pending, running, etc.)
    - The N most recent completed/failed tasks (default: 50)
    When no tasks are active, sends a heartbeat every 5 seconds.
    """
    client_id = id(request)
    _connected_clients.add(client_id)
    logger.info("SSE client connected", clients=len(_connected_clients))

    try:
        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                break

            # Fetch current task states: active tasks + N most recent
            async with async_session() as session:
                # Get active tasks (no limit — all active tasks matter)
                active_result = await session.execute(
                    select(TranslationTask)
                    .where(TranslationTask.status.in_(_ACTIVE_STATUSES))
                    .order_by(TranslationTask.created_at.desc())
                )
                active_tasks = active_result.scalars().all()

                # Get recent completed/failed tasks (up to limit)
                recent_result = await session.execute(
                    select(TranslationTask)
                    .where(~TranslationTask.status.in_(_ACTIVE_STATUSES))
                    .order_by(TranslationTask.created_at.desc())
                    .limit(limit)
                )
                recent_tasks = recent_result.scalars().all()

            # Merge: active first, then recent
            seen_ids = set()
            tasks = []
            for t in active_tasks + recent_tasks:
                if t.id not in seen_ids:
                    seen_ids.add(t.id)
                    tasks.append(t)

            # Build event data
            active = bool(active_tasks)

            events = []
            for task in tasks:
                events.append({
                    "id": task.id,
                    "film_id": task.film_id,
                    "task_type": getattr(task, 'task_type', 'translation') or 'translation',
                    "status": task.status,
                    "progress_pct": task.progress_pct,
                    "error_message": task.error_message,
                    "source_filename": task.source_filename,
                    "total_lines": task.total_lines,
                    "translated_lines": task.translated_lines,
                })

            data = json.dumps({
                "tasks": events,
                "active": active,
            })

            yield f"data: {data}\n\n"

            # Poll faster when active, slower when idle
            wait_time = 1 if active else 5
            await asyncio.sleep(wait_time)

    except asyncio.CancelledError:
        pass
    finally:
        _connected_clients.discard(client_id)
        logger.info("SSE client disconnected", clients=len(_connected_clients))


@router.get("")
async def task_events(
    request: Request,
    limit: int = 50,
):
    """SSE endpoint for real-time task progress updates."""
    from fastapi.responses import StreamingResponse

    return StreamingResponse(
        task_events_generator(request, limit=limit),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )