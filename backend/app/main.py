"""
Kinoscribe — FastAPI application entry point.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_db
from app.core.logging import setup_logging, get_logger
from app.api.films import router as films_router
from app.api.tasks import router as tasks_router
from app.api.settings import router as settings_router
from app.api.libraries import router as libraries_router
from app.api.events import router as events_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    # Startup
    setup_logging(debug=settings.debug)
    logger.info("Starting Kinoscribe", debug=settings.debug)
    await init_db()

    # Seed settings from env defaults if first boot
    from app.core.database import async_session
    from app.services.settings_service import settings_service
    ssvc = settings_service
    async with async_session() as session:
        await ssvc.seed_if_empty(session)

    # ── Recover stale tasks ────────────────────────────────────────────
    # If the process was restarted while tasks were running,
    # mark them as failed so the user can retry.
    from app.models.database import TranslationTask, LibrarySource
    from app.models.database import TaskStatusEnum as TSE
    stale_statuses = ("analyzing_context", "translating", "refining")
    recovered = 0
    async with async_session() as session:
        from sqlalchemy import select as sa_select
        result = await session.execute(
            sa_select(TranslationTask).where(
                TranslationTask.status.in_(stale_statuses)
            )
        )
        for task in result.scalars().all():
            task.status = TSE.failed
            task.error_message = "Task interrupted by server restart"
            recovered += 1
        # Also recover stale library scans
        result2 = await session.execute(
            sa_select(LibrarySource).where(
                LibrarySource.scan_status == "scanning"
            )
        )
        for source in result2.scalars().all():
            source.scan_status = "idle"
            source.scan_error = "Scan interrupted by server restart"
            recovered += 1
        if recovered:
            await session.commit()
            logger.info("Recovered stale tasks/sources", count=recovered)

    # ── Migrate cleartext SSH passwords to encrypted ────────────────────
    from app.core.crypto import is_encrypted, encrypt
    async with async_session() as session:
        result = await session.execute(
            sa_select(LibrarySource).where(
                LibrarySource.ssh_password.isnot(None),
                LibrarySource.ssh_password != "",  # type: ignore
            )
        )
        migrated = 0
        for source in result.scalars().all():
            if source.ssh_password and not is_encrypted(source.ssh_password):
                source.ssh_password = encrypt(source.ssh_password)
                migrated += 1
        if migrated:
            await session.commit()
            logger.info("Migrated SSH passwords to encrypted storage", count=migrated)

    logger.info("Database initialized, settings ready")

    # ── Recover pending translation tasks ───────────────────────────────
    # Tasks in 'pending' state were never started (e.g. uploaded but not translated)
    from app.services.task_runner import recover_pending_tasks
    await recover_pending_tasks()

    # Start auto-scan scheduler
    import asyncio
    scheduler_task = asyncio.create_task(_auto_scan_scheduler())

    yield

    # Shutdown
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass
    logger.info("Shutting down")


async def _auto_scan_scheduler():
    """Background task that periodically scans all libraries (if enabled)."""
    from app.core.database import async_session
    from app.services.settings_service import settings_service
    from app.services.scanner_service import scanner_service, get_scan_progress
    from app.models.database import Library
    from sqlalchemy import select

    # Wait a bit before first check
    await asyncio.sleep(30)

    while True:
        try:
            async with async_session() as session:
                enabled = await settings_service.get(session, "auto_scan_enabled") or "false"
                interval_hours = float(await settings_service.get(session, "auto_scan_interval_hours") or "24")

            if enabled.lower() == "true":
                # Find all libraries
                async with async_session() as session:
                    result = await session.execute(select(Library))
                    libraries = result.scalars().all()

                for lib in libraries:
                    # Skip if already scanning
                    prog = get_scan_progress(lib.id)
                    if prog and prog.status == "scanning":
                        continue
                    try:
                        await scanner_service.scan_library(lib.id)
                        logger.info("Auto-scanned library", library_id=lib.id, name=lib.name)
                    except Exception as e:
                        logger.error("Auto-scan failed", library_id=lib.id, error=str(e))

            # Sleep until next check
            sleep_seconds = max(interval_hours * 3600, 300)  # Min 5 minutes
            await asyncio.sleep(sleep_seconds)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Auto-scan scheduler error", error=str(e))
            await asyncio.sleep(300)  # Retry in 5 minutes on error


app = FastAPI(
    title="Kinoscribe",
    version="0.4.1",
    lifespan=lifespan,
)

# ─── Middleware ───────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],  # Docker + dev frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routes ─────────────────────────────────────────────────────────────────

app.include_router(films_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(libraries_router, prefix="/api")
app.include_router(events_router, prefix="/api")


@app.get("/")
async def root():
    return {
        "message": "Kinoscribe is running",
         "version": "0.4.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}