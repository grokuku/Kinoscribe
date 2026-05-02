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
    async with async_session() as session:
        await settings_service.seed_if_empty(session)

    logger.info("Database initialized, settings ready")

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
    version="0.4.0",
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