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
            "lore_summary": "TEXT",
            "analysis_status": "TEXT DEFAULT 'idle'",
            "genre": "TEXT",
            "studio": "TEXT",
            "rating": "REAL",
            "imdb_id": "TEXT",
            "tmdb_id": "TEXT",
        }

        for col_name, col_type in new_columns.items():
            if col_name not in existing:
                await conn.execute(sqlalchemy.text(
                    f"ALTER TABLE films ADD COLUMN {col_name} {col_type}"
                ))

        # Check columns in translation_tasks table
        result = await conn.execute(sqlalchemy.text("PRAGMA table_info(translation_tasks)"))
        task_cols = {row[1] for row in result}

        task_new_columns = {
            "task_type": "TEXT DEFAULT 'translation'",
        }

        for col_name, col_type in task_new_columns.items():
            if col_name not in task_cols:
                await conn.execute(sqlalchemy.text(
                    f"ALTER TABLE translation_tasks ADD COLUMN {col_name} {col_type}"
                ))

        # ── Phase 6: Mount support columns ──
        result = await conn.execute(sqlalchemy.text("PRAGMA table_info(library_sources)"))
        source_cols = {row[1] for row in result}

        source_new_columns = {
            "mount_status": "TEXT DEFAULT 'unmounted'",
            "mount_point": "TEXT",
            "mount_error": "TEXT",
        }

        for col_name, col_type in source_new_columns.items():
            if col_name not in source_cols:
                await conn.execute(sqlalchemy.text(
                    f"ALTER TABLE library_sources ADD COLUMN {col_name} {col_type}"
                ))

        # ── Phase 8: Live translation feed columns ──
        result = await conn.execute(sqlalchemy.text("PRAGMA table_info(translation_tasks)"))
        task_cols = {row[1] for row in result}

        live_columns = {
            "draft_path": "TEXT",
            "total_lines": "INTEGER",
            "translated_lines": "INTEGER",
        }
        for col_name, col_type in live_columns.items():
            if col_name not in task_cols:
                await conn.execute(sqlalchemy.text(
                    f"ALTER TABLE translation_tasks ADD COLUMN {col_name} {col_type}"
                ))

        # ── Phase 7: Normalize mount points and reset stale mount status ──
        # Old code stored non-normalized paths like /app/app/services/../../data/mounts/...
        # Reset all mount statuses so they get re-mounted with correct paths on next scan.
        import os as _os
        _mount_base = _os.path.normpath("/app/data/mounts")
        try:
            # Reset mount status for all remote sources so they get re-mounted
            await conn.execute(sqlalchemy.text(
                "UPDATE library_sources SET mount_status = 'unmounted', "
                "mount_point = NULL, mount_error = NULL "
                "WHERE source_type IN ('ssh', 'smb', 'cifs')"
            ))
            # Also fix any mount_point that contains the old non-normalized path
            await conn.execute(sqlalchemy.text(
                f"UPDATE library_sources SET mount_point = NULL "
                f"WHERE mount_point IS NOT NULL AND mount_point NOT LIKE '{_mount_base}/%'"
            ))
        except Exception:
            pass  # Non-critical — mount status will be refreshed on next scan