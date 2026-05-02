"""
Async SQLAlchemy session factory + init helper.
"""

import os
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.core.config import settings
from app.models.database import Base

# Ensure data directory exists for SQLite
_db_path = settings.database_url.split("///")[-1]
_db_dir = os.path.dirname(_db_path)
if _db_dir:
    os.makedirs(_db_dir, exist_ok=True)

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
)

async_session = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Create all tables (idempotent for SQLite) + run any pending migrations."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Run migrations for new columns (safe to run multiple times)
    await _migrate_phase5()


async def get_session() -> AsyncSession:
    """FastAPI dependency — yields an async session, auto-closes it."""
    async with async_session() as session:
        yield session


async def _migrate_phase5() -> None:
    """Add new columns to films table for library integration (Phase 5).

    SQLAlchemy create_all only creates NEW tables, it does not add columns
    to existing tables. This migration adds the columns that were added
    after the initial schema.
    """
    import sqlalchemy

    async with engine.begin() as conn:
        # Check which columns exist in the films table
        result = await conn.execute(sqlalchemy.text("PRAGMA table_info(films)"))
        existing = {row[1] for row in result}

        new_columns = {
            "library_id": "TEXT REFERENCES libraries(id)",
            "path": "TEXT",
            "video_path": "TEXT",
            "poster_path": "TEXT",
            "has_existing_subs": "INTEGER DEFAULT 0",
        }

        for col_name, col_type in new_columns.items():
            if col_name not in existing:
                await conn.execute(sqlalchemy.text(
                    f"ALTER TABLE films ADD COLUMN {col_name} {col_type}"
                ))