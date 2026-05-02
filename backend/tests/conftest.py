"""
Shared test fixtures — database, HTTP client, sample data.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.main import app
from app.core.database import get_session
from app.models.database import Base, Film, Setting


@pytest_asyncio.fixture(scope="function")
async def async_engine(tmp_path):
    """Create a fresh SQLite database for each test function."""
    db_path = tmp_path / "test.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def async_session(async_engine):
    """
    Provide a DB session and override FastAPI's dependency.
    Each test gets its own isolated session + clean DB.
    """
    sessionmaker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with sessionmaker() as session:
        async def _override_get_session():
            """Async generator that FastAPI's Depends will consume."""
            yield session

        app.dependency_overrides[get_session] = _override_get_session
        yield session
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def async_client(async_session):
    """HTTP client that talks to the FastAPI app directly (no network)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ─── Sample data fixtures ──────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def sample_film(async_session) -> Film:
    """A minimal film persisted in the test DB."""
    film = Film(
        title="Inception",
        year=2010,
        director="Christopher Nolan",
        source_language="en",
        target_language="fr",
    )
    async_session.add(film)
    await async_session.commit()
    await async_session.refresh(film)
    return film


@pytest.fixture
def sample_srt_content() -> str:
    """A realistic SRT with SDH markers and multi-speaker dialogue."""
    return """1
00:00:01,000 --> 00:00:04,500
[COBB]: What is the most resilient parasite?

2
00:00:05,000 --> 00:00:08,200
An idea. A single idea from the human mind.

3
00:00:09,000 --> 00:00:13,800
(ARTHUR): Can you steal an idea from someone's mind?

4
00:00:14,500 --> 00:00:18,000
[thunder rumbling]
If you can steal it, why can't you plant one?

5
00:00:19,000 --> 00:00:22,500
(heavy breathing) We have to go deeper.

6
00:01:00,000 --> 00:01:01,000
This line is way too long for comfortable reading at this speed, it exceeds the CPS limit by a lot

7
00:02:00,000 --> 00:02:02,000
Normal short line.
"""
