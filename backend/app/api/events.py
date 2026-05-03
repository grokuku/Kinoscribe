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


async def task_events_generator(request: Request) -> AsyncGenerator[str, None]:
    """
    Generate SSE events for task progress.

    Sends an event every second with a snapshot of all active tasks.
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

            # Fetch current task states
            async with async_session() as session:
                result = await session.execute(
                    select(TranslationTask).order_by(TranslationTask.created_at.desc())
                )
                tasks = result.scalars().all()

            # Build event data
            active_statuses = {"pending", "analyzing_context", "translating", "refining", "extracting", "transcribing", "syncing", "rescanning"}
            active = any(t.status in active_statuses for t in tasks)

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
async def task_events(request: Request):
    """SSE endpoint for real-time task progress updates."""
    from fastapi.responses import StreamingResponse

    return StreamingResponse(
        task_events_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )