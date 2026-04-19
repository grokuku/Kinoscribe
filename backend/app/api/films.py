"""
Film-related API routes: CRUD + metadata.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.logging import get_logger
from app.models.database import Film, Character
from app.models.schemas import FilmCreate, FilmOut, CharacterOut

logger = get_logger(__name__)
router = APIRouter(prefix="/films", tags=["films"])


@router.post("/", response_model=FilmOut, status_code=201)
async def create_film(
    data: FilmCreate,
    session: AsyncSession = Depends(get_session),
):
    """Register a new film in the system."""
    film = Film(
        title=data.title,
        year=data.year,
        director=data.director,
        summary=data.summary,
        source_language=data.source_language,
        target_language=data.target_language,
    )
    session.add(film)
    await session.commit()
    await session.refresh(film)
    logger.info("Film created", film_id=film.id, title=film.title)
    return film


@router.get("/", response_model=List[FilmOut])
async def list_films(
    session: AsyncSession = Depends(get_session),
):
    """List all registered films."""
    result = await session.execute(select(Film))
    films = result.scalars().all()
    return films


@router.get("/{film_id}", response_model=FilmOut)
async def get_film(
    film_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get a specific film by ID."""
    film = await session.get(Film, film_id)
    if not film:
        raise HTTPException(404, "Film not found")
    return film


@router.get("/{film_id}/characters", response_model=List[CharacterOut])
async def get_film_characters(
    film_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get character profiles for a film."""
    film = await session.get(Film, film_id)
    if not film:
        raise HTTPException(404, "Film not found")
    result = await session.execute(
        select(Character).where(Character.film_id == film_id)
    )
    return result.scalars().all()


@router.delete("/{film_id}", status_code=204)
async def delete_film(
    film_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Delete a film and all its associated data."""
    film = await session.get(Film, film_id)
    if not film:
        raise HTTPException(404, "Film not found")
    await session.delete(film)
    await session.commit()
    logger.info("Film deleted", film_id=film_id)