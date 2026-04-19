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
    yield
    # Shutdown
    logger.info("Shutting down")


app = FastAPI(
    title="Kinoscribe",
    version="0.2.0",
    lifespan=lifespan,
)

# ─── Middleware ───────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routes ─────────────────────────────────────────────────────────────────

app.include_router(films_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(settings_router, prefix="/api")


@app.get("/")
async def root():
    return {
        "message": "Kinoscribe is running",
        "version": "0.2.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}