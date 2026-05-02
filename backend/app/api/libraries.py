"""
Library API routes: CRUD + scan + progress + poster serving.
Libraries are collections of film directories (like Jellyfin).
Each library has one or more sources (local paths, SSH, future: SMB/NFS).
"""

from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.logging import get_logger
from app.models.database import Film, Library, LibrarySource
from app.models.schemas import (
    LibraryCreate, LibraryOut, LibraryUpdate,
    LibrarySourceCreate, LibrarySourceOut,
)
from app.services.scanner_service import get_scan_progress, get_all_scan_progress

logger = get_logger(__name__)
router = APIRouter(prefix="/libraries", tags=["libraries"])


# ─── Libraries CRUD ────────────────────────────────────────────────────────────

@router.get("/", response_model=List[LibraryOut])
async def list_libraries(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Library))
    return result.scalars().all()


@router.get("/{library_id}", response_model=LibraryOut)
async def get_library(library_id: str, session: AsyncSession = Depends(get_session)):
    library = await session.get(Library, library_id)
    if not library:
        raise HTTPException(404, "Library not found")
    return library


@router.post("/", response_model=LibraryOut, status_code=201)
async def create_library(data: LibraryCreate, session: AsyncSession = Depends(get_session)):
    library = Library(name=data.name, description=data.description)
    session.add(library)
    await session.commit()
    await session.refresh(library)
    logger.info("Library created", library_id=library.id, name=library.name)
    return library


@router.put("/{library_id}", response_model=LibraryOut)
async def update_library(library_id: str, data: LibraryUpdate, session: AsyncSession = Depends(get_session)):
    library = await session.get(Library, library_id)
    if not library:
        raise HTTPException(404, "Library not found")
    if data.name is not None:
        library.name = data.name
    if data.description is not None:
        library.description = data.description
    await session.commit()
    await session.refresh(library)
    return library


@router.delete("/{library_id}")
async def delete_library(library_id: str, delete_films: bool = True, session: AsyncSession = Depends(get_session)):
    """Delete a library. By default also deletes all films discovered via this library."""
    library = await session.get(Library, library_id)
    if not library:
        raise HTTPException(404, "Library not found")

    if delete_films:
        # Delete all films associated with this library
        result = await session.execute(
            select(Film).where(Film.library_id == library_id)
        )
        films = result.scalars().all()
        for film in films:
            await session.delete(film)
        if films:
            logger.info("Deleted films from library", library_id=library_id, count=len(films))

    await session.delete(library)
    await session.commit()


# ─── Sources CRUD ──────────────────────────────────────────────────────────────

@router.post("/{library_id}/sources", response_model=LibrarySourceOut, status_code=201)
async def add_source(library_id: str, data: LibrarySourceCreate, session: AsyncSession = Depends(get_session)):
    library = await session.get(Library, library_id)
    if not library:
        raise HTTPException(404, "Library not found")
    source = LibrarySource(
        library_id=library_id, source_type=data.source_type, path=data.path,
        ssh_host=data.ssh_host, ssh_port=data.ssh_port or 22,
        ssh_username=data.ssh_username, ssh_auth_type=data.ssh_auth_type,
        ssh_private_key_path=data.ssh_private_key_path, ssh_password=data.ssh_password,
        ssh_remote_path=data.ssh_remote_path, enabled=data.enabled, scan_depth=data.scan_depth,
    )
    session.add(source)
    await session.commit()
    await session.refresh(source)
    return source


@router.put("/{library_id}/sources/{source_id}", response_model=LibrarySourceOut)
async def update_source(library_id: str, source_id: str, data: LibrarySourceCreate, session: AsyncSession = Depends(get_session)):
    source = await session.get(LibrarySource, source_id)
    if not source or source.library_id != library_id:
        raise HTTPException(404, "Source not found")
    source.source_type = data.source_type
    source.path = data.path
    source.ssh_host = data.ssh_host
    source.ssh_port = data.ssh_port or 22
    source.ssh_username = data.ssh_username
    source.ssh_auth_type = data.ssh_auth_type
    source.ssh_private_key_path = data.ssh_private_key_path
    source.ssh_password = data.ssh_password
    source.ssh_remote_path = data.ssh_remote_path
    source.enabled = data.enabled
    source.scan_depth = data.scan_depth
    await session.commit()
    await session.refresh(source)
    return source


@router.delete("/{library_id}/sources/{source_id}")
async def delete_source(library_id: str, source_id: str, delete_films: bool = True, session: AsyncSession = Depends(get_session)):
    """Remove a source from a library. By default also deletes films discovered from this source path."""
    source = await session.get(LibrarySource, source_id)
    if not source or source.library_id != library_id:
        raise HTTPException(404, "Source not found")

    if delete_films:
        # Determine the scan path for this source
        scan_path = source.ssh_remote_path or source.path
        scan_path = scan_path.rstrip('/')

        # Find all films whose path starts with this source's scan path
        result = await session.execute(
            select(Film).where(Film.library_id == library_id)
        )
        films = result.scalars().all()
        deleted = 0
        for film in films:
            if film.path and film.path.rstrip('/').startswith(scan_path):
                await session.delete(film)
                deleted += 1
        if deleted:
            logger.info("Deleted films from source", source_id=source_id, path=scan_path, count=deleted)

    await session.delete(source)
    await session.commit()


# ─── Scanning ────────────────────────────────────────────────────────────────

@router.post("/{library_id}/scan")
async def scan_library(library_id: str, background_tasks: BackgroundTasks, session: AsyncSession = Depends(get_session)):
    """Trigger a background scan of the library."""
    from app.services.scanner_service import scanner_service

    # Check if already scanning
    progress = get_scan_progress(library_id)
    if progress and progress.status == "scanning":
        raise HTTPException(409, "A scan is already in progress for this library")

    library = await session.get(Library, library_id)
    if not library:
        raise HTTPException(404, "Library not found")

    if not library.sources:
        raise HTTPException(400, "Library has no sources to scan")

    background_tasks.add_task(scanner_service.scan_library, library_id)
    logger.info("Library scan started", library_id=library_id)
    return {"status": "scanning", "library_id": library_id}


@router.get("/{library_id}/scan-progress")
async def scan_progress(library_id: str):
    """Get real-time scan progress."""
    progress = get_scan_progress(library_id)
    if not progress:
        return {"library_id": library_id, "status": "idle", "total_dirs": 0, "scanned_dirs": 0, "current_dir": "", "films_found": 0, "films_created": 0, "films_updated": 0, "errors": [], "started_at": None, "completed_at": None}
    return progress.to_dict()


@router.get("/scan-progress/all")
async def all_scan_progress():
    """Get progress for all library scans."""
    return get_all_scan_progress()


# ─── SSH Connection Test ────────────────────────────────────────────────────

@router.post("/test-ssh")
async def test_ssh(data: dict):
    """Test SSH connection. Body: { host, port, username, auth_type, private_key_path, password, remote_path? }"""
    from app.services.scanner_service import test_ssh_connection
    result = await test_ssh_connection(
        host=data.get("host", ""), port=data.get("port", 22),
        username=data.get("username", "root"), password=data.get("password"),
        private_key_path=data.get("private_key_path"), remote_path=data.get("remote_path"),
    )
    return result