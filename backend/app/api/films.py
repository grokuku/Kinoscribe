"""
Film-related API routes: CRUD + metadata.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.logging import get_logger
from app.models.database import Film, Character
from app.models.schemas import FilmCreate, FilmOut, CharacterOut, GlossaryEntryOut, ExistingSubtitleOut

import os
import mimetypes
from pathlib import Path

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


@router.get("/{film_id}/glossary", response_model=List[GlossaryEntryOut])
async def get_film_glossary(
    film_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get the glossary for a film."""
    from app.models.database import GlossaryEntry
    film = await session.get(Film, film_id)
    if not film:
        raise HTTPException(404, "Film not found")
    result = await session.execute(
        select(GlossaryEntry).where(GlossaryEntry.film_id == film_id)
    )
    return result.scalars().all()


@router.get("/{film_id}/lore")
async def get_film_lore(
    film_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get the lore summary and any task context for a film."""
    from app.models.database import TranslationTask
    film = await session.get(Film, film_id)
    if not film:
        raise HTTPException(404, "Film not found")

    # Source 1: standalone analysis stored in film.lore_summary
    metadata_lore = film.lore_summary

    # Source 2: most recent task's lore (from translation pipeline)
    result = await session.execute(
        select(TranslationTask)
        .where(TranslationTask.film_id == film_id)
        .order_by(TranslationTask.created_at.desc())
        .limit(1)
    )
    task = result.scalars().first()
    task_lore = task.lore_summary if task else None

    # Prefer task lore (more recent from full pipeline), fallback to metadata lore
    lore = task_lore or metadata_lore

    return {
        "lore_summary": lore,
        "task_id": task.id if task else None,
        "task_status": task.status if task else None,
    }


@router.delete("/{film_id}", status_code=204)
async def delete_film(
    film_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Delete a film and all its associated data (including files on disk)."""
    film = await session.get(Film, film_id)
    if not film:
        raise HTTPException(404, "Film not found")

    # Collect paths before deleting the ORM object
    paths_to_clean = []
    if film.poster_path and os.path.isfile(film.poster_path):
        paths_to_clean.append(film.poster_path)
    # Clean all work/output dirs for this film
    from app.services.workdir import clean_all_for_film
    clean_all_for_film(film_id)

    await session.delete(film)
    await session.commit()

    # Remove files from disk (best-effort, after DB deletion succeeds)
    import shutil
    for p in paths_to_clean:
        try:
            if os.path.isfile(p):
                os.remove(p)
            elif os.path.isdir(p):
                shutil.rmtree(p)
        except OSError as e:
            logger.warning("Failed to clean up film file", path=p, error=str(e))

    logger.info("Film deleted", film_id=film_id)


@router.post("/{film_id}/rescan")
async def rescan_film(
    film_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Rescan a single film's directory and update its metadata."""
    from app.services.scanner_service import LocalFilesystem, SSHFilesystem, _scan_single_directory, cache_poster_locally
    from app.core.database import async_session
    from app.core.crypto import decrypt

    film = await session.get(Film, film_id)
    if not film:
        raise HTTPException(404, "Film not found")
    if not film.path:
        raise HTTPException(400, "Film has no source directory")

    # Determine the filesystem type
    source = None
    if film.library_id:
        from app.models.database import LibrarySource
        result = await session.execute(
            select(LibrarySource).where(LibrarySource.library_id == film.library_id)
        )
        sources = result.scalars().all()
        for s in sources:
            scan_path = (s.ssh_remote_path or s.path).rstrip('/')
            if film.path.rstrip('/').startswith(scan_path):
                source = s
                break

    async def _do_rescan():
        async with async_session() as s:
            f = await s.get(Film, film_id)
            if not f:
                return
            try:
                # Choose filesystem
                if source and source.source_type == 'ssh':
                    fs = SSHFilesystem(
                        host=source.ssh_host,
                        port=source.ssh_port or 22,
                        username=source.ssh_username or 'root',
                        password=decrypt(source.ssh_password) if source.ssh_auth_type == 'password' else None,
                        private_key_path=source.ssh_private_key_path if source.ssh_auth_type == 'key' else None,
                    )
                    await fs.connect()
                else:
                    fs = LocalFilesystem()

                entry = await _scan_single_directory(fs, f.path, f.path)
                if entry:
                    # Update film metadata
                    if entry.get('title'):
                        f.title = entry['title']
                    if entry.get('year') is not None:
                        f.year = entry['year']
                    if entry.get('director'):
                        f.director = entry['director']
                    if entry.get('summary'):
                        f.summary = entry['summary']
                    if entry.get('raw_metadata'):
                        f.raw_metadata = entry['raw_metadata']
                    if entry.get('video_files'):
                        f.video_path = entry['video_files'][0]
                    if entry.get('subtitles'):
                        f.has_existing_subs = True

                    # Handle poster
                    poster_file = entry.get('poster_file')
                    if poster_file:
                        if source and source.source_type == 'ssh':
                            cached = await cache_poster_locally(fs, poster_file, film_id)
                            f.poster_path = cached or poster_file
                        else:
                            f.poster_path = poster_file

                    await s.commit()
                    logger.info("Film rescaned successfully", film_id=film_id)

                # Cleanup SSH
                if source and source.source_type == 'ssh' and isinstance(fs, SSHFilesystem):
                    await fs.disconnect()

            except Exception as e:
                logger.error("Film rescan failed", film_id=film_id, error=str(e))

    asyncio.create_task(_do_rescan())
    return {"status": "rescanning", "film_id": film_id}


@router.post("/{film_id}/enrich")
async def enrich_film_metadata(
    film_id: str,
    session: AsyncSession = Depends(get_session),
):
    """
    Enrich film metadata from online sources (Cinemagoer/IMDb or TMDB).
    No API key needed for Cinemagoer. TMDB requires an API key in settings.
    """
    from app.services.metadata_service import enrich_film_metadata

    film = await session.get(Film, film_id)
    if not film:
        raise HTTPException(404, "Film not found")

    # Get TMDB API key from settings if available
    from app.services.settings_service import settings_service
    tmdb_key = await settings_service.get(session, "tmdb_api_key") or None
    prefer_source = "cinemagoer"  # Default to free source

    result = await enrich_film_metadata(
        title=film.title,
        year=film.year,
        prefer_source=prefer_source,
        tmdb_api_key=tmdb_key if tmdb_key else None,
    )

    if not result:
        raise HTTPException(404, f"No online metadata found for '{film.title}'")

    # Update film with enriched data
    updated = False
    if result.title and not film.title:
        film.title = result.title
        updated = True
    if result.year and not film.year:
        film.year = result.year
        updated = True
    if result.director and not film.director:
        film.director = result.director
        updated = True
    if result.plot and not film.summary:
        film.summary = result.plot
        updated = True
    if result.poster_url and not film.poster_path:
        # Download and cache poster
        import hashlib
        import urllib.request
        try:
            cache_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'posters')
            os.makedirs(cache_dir, exist_ok=True)
            ext = '.jpg'
            if 'png' in (result.poster_url or ''):
                ext = '.png'
            poster_path = os.path.join(cache_dir, f"{film_id}{ext}")
            urllib.request.urlretrieve(result.poster_url, poster_path)
            film.poster_path = poster_path
            updated = True
        except Exception as e:
            logger.warning("Failed to download poster", url=result.poster_url, error=str(e))

    # Update enriched NFO fields
    if result.imdb_id and not film.imdb_id:
        film.imdb_id = result.imdb_id
        updated = True
    if result.rating and not film.rating:
        film.rating = result.rating
        updated = True
    if result.genres and not film.genre:
        film.genre = ', '.join(result.genres)
        updated = True

    # Create Character records from enrichment cast if film has none yet
    if result.cast and not film.characters:
        from app.models.database import Character
        for actor in result.cast[:20]:
            char = Character(
                film_id=film.id,
                name=actor.get('name', ''),
                description=f"Role: {actor.get('role', '')}" if actor.get('role') else None,
            )
            session.add(char)
        updated = True

    if updated:
        await session.commit()
        await session.refresh(film)

    return {
        "status": "enriched",
        "film_id": film_id,
        "source": result.source,
        "title": result.title,
        "year": result.year,
        "director": result.director,
        "plot": result.plot,
        "rating": result.rating,
        "genres": result.genres,
        "cast_count": len(result.cast),
        "poster_url": result.poster_url,
        "imdb_id": result.imdb_id,
        "fields_updated": updated,
    }


@router.get("/{film_id}/poster")
async def get_film_poster(
    film_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Serve a film's poster image from local filesystem."""
    film = await session.get(Film, film_id)
    if not film:
        raise HTTPException(404, "Film not found")

    poster_path = film.poster_path
    if not poster_path or not os.path.isfile(poster_path):
        raise HTTPException(404, "No poster available")

    # Determine content type
    mime_type, _ = mimetypes.guess_type(poster_path)
    if not mime_type:
        mime_type = "image/jpeg"  # default

    try:
        with open(poster_path, "rb") as f:
            image_data = f.read()
        return Response(
            content=image_data,
            media_type=mime_type,
            headers={
                "Cache-Control": "public, max-age=86400",  # 24h cache
                "X-Content-Type-Options": "nosniff",
            },
        )
    except Exception as e:
        logger.warning("Failed to read poster file", path=poster_path, error=str(e))
        raise HTTPException(500, f"Failed to read poster: {e}")


@router.get("/{film_id}/video-stream")
async def stream_film_video(
    film_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Stream the film's video file for HTML5 players.
    Works for local films and mounted remote films (sshfs/cifs)."""
    from starlette.responses import FileResponse

    film = await session.get(Film, film_id)
    if not film:
        raise HTTPException(404, "Film not found")
    logger.info("video-stream: start", film_id=film_id, video_path=film.video_path)
    if not film.video_path:
        raise HTTPException(400, "No video file registered for this film")

    # Determine accessible path
    # First try the streamlined _ensure_local_video which handles all cases
    try:
        accessible_path = await _ensure_local_video(film, session)
        logger.info("video-stream: resolved", accessible_path=accessible_path, 
                   exists=os.path.isfile(accessible_path) if accessible_path else False)
    except Exception as e:
        logger.error("video-stream: error resolving path", error=str(e))
        accessible_path = None
    
    if not accessible_path or not os.path.isfile(accessible_path):
        raise HTTPException(404, f"Video file not found on disk: {film.video_path}. Check that the mount is active.")

    ext = os.path.splitext(accessible_path)[1].lower()
    mime_map = {'.mp4': 'video/mp4', '.mkv': 'video/x-matroska', '.avi': 'video/x-msvideo',
                '.mov': 'video/quicktime', '.wmv': 'video/x-ms-wmv', '.webm': 'video/webm'}
    media_type = mime_map.get(ext, 'video/mp4')

    return FileResponse(
        accessible_path,
        media_type=media_type,
        filename=os.path.basename(accessible_path),
    )


async def _ensure_local_video(film: Film, session) -> str:
    """Ensure video file is accessible locally.
    1. If path exists locally (mount point or local source) → use directly
    2. If mounted (mount_point on source) → translate remote path to mount path
    3. If SSH without mount → download to work dir
    """
    # Fast path: does the video path already exist locally?
    if film.video_path and os.path.isfile(film.video_path):
        return film.video_path

    # Check if the video is on a mounted source — translate remote path
    if film.library_id:
        from app.models.database import LibrarySource
        result = await session.execute(
            select(LibrarySource).where(LibrarySource.library_id == film.library_id)
        )
        sources = result.scalars().all()
        for source in sources:
            mount_mp = getattr(source, 'mount_point', None)
            if mount_mp and mount_mp.strip():
                # Try translating remote path to mount path
                remote_path = (source.ssh_remote_path or source.path or "").rstrip("/")
                mount_path = os.path.normpath(mount_mp)
                if film.video_path and film.video_path.startswith(remote_path):
                    local_path = film.video_path.replace(remote_path, mount_path.rstrip('/'), 1)
                    if os.path.isfile(local_path):
                        return local_path
                # Also try: video path might be inside the mount point but with a different prefix
                # e.g. video_path = /app/data/mounts/abc123/Film/movie.mkv
                normalized_video = os.path.normpath(film.video_path) if film.video_path else ""
                if normalized_video.startswith(mount_path) and os.path.isfile(normalized_video):
                    return normalized_video

    # Must be SSH without mount — download to work dir
    if not film.video_path or not film.library_id:
        raise HTTPException(400, "No video file available for this film.")

    from app.models.database import LibrarySource
    from app.services.scanner_service import SSHFilesystem
    from app.core.crypto import decrypt
    from app.services.workdir import work_dir

    result = await session.execute(
        select(LibrarySource).where(LibrarySource.library_id == film.library_id)
    )
    sources = result.scalars().all()

    for source in sources:
        remote_path = (source.ssh_remote_path or source.path or "").rstrip("/")
        if source.source_type == "ssh" and film.video_path.startswith(remote_path):
            fs = SSHFilesystem(
                host=source.ssh_host,
                port=source.ssh_port or 22,
                username=source.ssh_username or "root",
                password=decrypt(source.ssh_password) if source.ssh_auth_type == "password" else None,
                private_key_path=source.ssh_private_key_path if source.ssh_auth_type == "key" else None,
            )
            await fs.connect()
            try:
                local_dir = os.path.join(work_dir(film.id), "video")
                os.makedirs(local_dir, exist_ok=True)
                local_path = os.path.join(local_dir, os.path.basename(film.video_path))
                if not os.path.isfile(local_path):
                    data = await fs.read_bytes(film.video_path)
                    with open(local_path, "wb") as f:
                        f.write(data)
                return local_path
            finally:
                await fs.disconnect()

    raise HTTPException(400, f"Video file not accessible: {film.video_path}")


# ─── Existing subtitles ──────────────────────────────────────────────────────

async def _list_film_subtitles_raw(film_id: str, session) -> list[dict]:
    """
    Internal helper: return raw subtitle info as list of dicts.
    Used by both the GET endpoint and the analysis background task.
    Handles local AND SSH films.
    """
    from app.services.scanner_service import parse_subtitle_filename, is_gendered_language, SUBTITLE_EXTENSIONS, LocalFilesystem, SSHFilesystem
    from app.services.workdir import migrate_legacy_dirs, uploads_dir, extracted_subs_dir, whisper_dir
    from app.core.crypto import decrypt
    from app.models.database import LibrarySource, Library

    migrate_legacy_dirs(film_id)

    film = await session.get(Film, film_id)
    if not film:
        return []

    results = []
    seen = set()

    # 1. Subtitles from the film's directory (local, mounted, or SSH)
    if film.path:
        try:
            # Check if the film's source is mounted locally
            mount_path = None
            if film.library_id:
                src_result = await session.execute(
                    select(LibrarySource).where(LibrarySource.library_id == film.library_id)
                )
                sources = src_result.scalars().all()
                for source in sources:
                    mp = getattr(source, 'mount_point', None)
                    if mp and mp.strip():
                        remote_path = (source.ssh_remote_path or source.path or "").rstrip("/")
                        if film.path.rstrip("/").startswith(remote_path):
                            mount_path = film.path.rstrip("/").replace(remote_path, mp.rstrip("/"), 1)
                            break

            # Try mount point first, then local path, then SSH fallback
            effective_path = mount_path or film.path

            if os.path.isdir(effective_path):
                for name in sorted(os.listdir(effective_path)):
                    ext = Path(name).suffix.lower()
                    if ext in SUBTITLE_EXTENSIONS:
                        full_path = os.path.join(effective_path, name)
                        if not os.path.isfile(full_path):
                            continue
                        info = parse_subtitle_filename(name)
                        key = name
                        if key not in seen:
                            seen.add(key)
                            results.append({"path": full_path, "filename": name, "language": info.get("language"), "source": "scanner"})
            elif not mount_path:
                # Try SSH filesystem only if no mount point available
                # (mount point exists but dir not found → mount issue, don't fall through to SSH)
                fs = None
                try:
                    if film.library_id:
                        # sources already queried above
                        for source in sources:
                            remote_path = (source.ssh_remote_path or source.path or "").rstrip("/")
                            if source.source_type == "ssh" and film.path.rstrip("/").startswith(remote_path):
                                fs = SSHFilesystem(
                                    host=source.ssh_host,
                                    port=source.ssh_port or 22,
                                    username=source.ssh_username or "root",
                                    password=decrypt(source.ssh_password) if source.ssh_auth_type == "password" else None,
                                    private_key_path=source.ssh_private_key_path if source.ssh_auth_type == "key" else None,
                                )
                                await fs.connect()
                                break
                            elif source.source_type == "local" and film.path.rstrip("/").startswith((source.path or "").rstrip("/")):
                                break

                    if fs and isinstance(fs, SSHFilesystem):
                        try:
                            entries = await fs.listdir(film.path)
                            for name in entries:
                                ext = Path(name).suffix.lower()
                                if ext in SUBTITLE_EXTENSIONS:
                                    full_path = f"{film.path.rstrip('/')}/{name}"
                                    if not await fs.is_file(full_path):
                                        continue
                                    info = parse_subtitle_filename(name)
                                    key = name
                                    if key not in seen:
                                        seen.add(key)
                                        # Cache the subtitle locally for later use
                                        from app.services.workdir import extracted_subs_dir
                                        cache_dir = extracted_subs_dir(film_id)
                                        os.makedirs(cache_dir, exist_ok=True)
                                        local_path = os.path.join(cache_dir, name)
                                        if not os.path.isfile(local_path):
                                            content = await fs.read_text(full_path)
                                            if content:
                                                with open(local_path, "w", encoding="utf-8") as f:
                                                    f.write(content)
                                        results.append({"path": local_path, "filename": name, "language": info.get("language"), "source": "ssh_cache"})
                        finally:
                            await fs.disconnect()
                except Exception as e:
                    logger.warning("Failed to list SSH subtitles", film_id=film_id, error=str(e))
        except Exception:
            pass

    # 2. From work dirs (uploads, extracted, transcribed) — always local
    for sub_dir, source_tag in [
        (uploads_dir(film_id), "uploaded"),
        (extracted_subs_dir(film_id), "extracted"),
        (whisper_dir(film_id), "transcribed"),
    ]:
        if os.path.isdir(sub_dir):
            try:
                for name in sorted(os.listdir(sub_dir)):
                    ext = Path(name).suffix.lower()
                    if ext in SUBTITLE_EXTENSIONS:
                        full_path = os.path.join(sub_dir, name)
                        if not os.path.isfile(full_path):
                            continue
                        info = parse_subtitle_filename(name)
                        key = name
                        if key not in seen:
                            seen.add(key)
                            results.append({"path": full_path, "filename": name, "language": info.get("language"), "source": source_tag})
            except PermissionError:
                pass

    return results


@router.get("/{film_id}/subtitles", response_model=List[ExistingSubtitleOut])
async def list_film_subtitles(
    film_id: str,
    session: AsyncSession = Depends(get_session),
):
    """
    List all available subtitles for a film:
    - Scanned from the film's directory (local or cached from SSH)
    - Previously uploaded, extracted, or transcribed
    """
    from app.services.scanner_service import parse_subtitle_filename, is_gendered_language

    raw = await _list_film_subtitles_raw(film_id, session)

    results = []
    for sub in raw:
        info = parse_subtitle_filename(sub["filename"])
        ext = Path(sub["filename"]).suffix.lstrip(".")
        results.append(ExistingSubtitleOut(
            filename=sub["filename"],
            path=sub["path"],
            language=sub.get("language") or info.get("language"),
            is_sdh=info.get("is_sdh", False),
            is_forced=info.get("is_forced", False),
            is_gendered=is_gendered_language(info.get("language") or "und"),
            format=ext,
            source=sub.get("source", "scanner"),
        ))

    return results


# ─── Manual context analysis ────────────────────────────────────────────────

@router.post("/{film_id}/analyze")
async def analyze_film_context(
    film_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Run context analysis (characters, lore, glossary) for a film without starting translation."""
    from app.core.database import async_session

    film = await session.get(Film, film_id)
    if not film:
        raise HTTPException(404, "Film not found")

    if film.analysis_status == "analyzing":
        raise HTTPException(409, "Analysis already in progress")

    # Mark film as being analyzed
    film.analysis_status = "analyzing"
    await session.commit()

    async def _run_analysis():
        from app.services.llm_provider import OllamaProvider
        from app.services.context_service import ContextService
        from app.services.subtitle_service import SubtitleService
        from app.services.settings_service import settings_service
        from app.models.database import Character, GlossaryEntry
        from sqlalchemy import select as sa_select
        async with async_session() as s:
            f = await s.get(Film, film_id)
            if not f:
                return
            try:
                ollama_url = await settings_service.get(s, "ollama_base_url") or "http://ollama:11434"
                ollama_model = await settings_service.get(s, "ollama_model") or "qwen3.5:397b-cloud"
                llm = OllamaProvider(base_url=ollama_url, model=ollama_model)
                ctx = ContextService(llm)
                sub_svc = SubtitleService()

                # Try to load subtitles to analyze
                sub_path = None
                subs_json = await _list_film_subtitles_raw(film_id, s)
                if subs_json:
                    sub_path = subs_json[0].get("path")

                if sub_path and os.path.isfile(sub_path):
                    parsed = sub_svc.parse_file(sub_path)

                    # Build character profiles
                    characters = await ctx.build_character_profiles(f, parsed, sub_svc)
                    existing_chars = await s.execute(
                        sa_select(Character).where(Character.film_id == film_id)
                    )
                    for c in existing_chars.scalars().all():
                        await s.delete(c)
                    for c in characters:
                        s.add(c)
                    await s.commit()

                    # Generate lore summary
                    lore = await ctx.generate_lore_summary(parsed, characters)
                    f.lore_summary = lore
                    await s.commit()

                    # Build glossary
                    glossary_data = await ctx.build_glossary(parsed, f.target_language)
                    existing_glossary = await s.execute(
                        sa_select(GlossaryEntry).where(GlossaryEntry.film_id == film_id)
                    )
                    for g in existing_glossary.scalars().all():
                        await s.delete(g)
                    for entry in glossary_data:
                        g = GlossaryEntry(
                            film_id=f.id,
                            source_term=entry.get("source", ""),
                            target_term=entry.get("target", ""),
                            notes=entry.get("notes", ""),
                        )
                        s.add(g)
                    await s.commit()

                    logger.info("Context analysis complete", film_id=film_id)
                else:
                    logger.warning("No subtitles found for analysis", film_id=film_id)
                    f.lore_summary = "Aucun sous-titre disponible pour l'analyse."
                    await s.commit()

                # Mark analysis complete
                f.analysis_status = "idle"
                await s.commit()
            except Exception as e:
                logger.error("Context analysis failed", film_id=film_id, error=str(e))
                f = await s.get(Film, film_id)
                if f:
                    f.analysis_status = "failed"
                    await s.commit()

    asyncio.create_task(_run_analysis())
    return {"status": "analyzing", "film_id": film_id}


# ─── Whisper transcription ──────────────────────────────────────────────────

@router.post("/{film_id}/transcribe")
async def transcribe_film(
    film_id: str,
    language: Optional[str] = None,
    model_size: str = "medium",
    session: AsyncSession = Depends(get_session),
):
    """
    Transcribe a film's audio using Whisper and generate subtitles.
    Requires: pip install faster-whisper
    model_size: tiny, base, small, medium, large (default: medium for good quality on CPU)
    """
    film = await session.get(Film, film_id)
    if not film:
        raise HTTPException(404, "Film not found")

    if not film.video_path:
        raise HTTPException(400, "No video file found for this film. Run a library scan first.")
    logger.info("transcribe: start", film_id=film_id, video_path=film.video_path)

    # Ensure video is accessible locally (download from SSH if needed)
    video_path = await _ensure_local_video(film, session)
    logger.info("transcribe: video resolved", video_path=video_path, exists=os.path.isfile(video_path) if video_path else False)
    if not video_path or not os.path.isfile(video_path):
        raise HTTPException(400, f"Video file not accessible: {film.video_path}")

    from app.core.database import async_session

    async def _run_transcription():
        from app.services.whisper_service import transcribe_video
        from app.services.settings_service import settings_service as ssvc
        try:
            async with async_session() as s2:
                wh_model = await ssvc.get(s2, "whisper_model") or model_size
                wh_x = await ssvc.get_bool(s2, "whisperx_enabled")
            result = await transcribe_video(
                video_path=video_path,
                film_id=film_id,
                language=language,
                model_size=wh_model,
                use_whisperx=wh_x,
            )
            logger.info("Whisper transcription complete", film_id=film_id, output=result.get("output_path"))
        except Exception as e:
            logger.error("Whisper transcription failed", film_id=film_id, error=str(e))

    asyncio.create_task(_run_transcription())
    return {"status": "transcribing", "film_id": film_id, "model": model_size}


@router.post("/{film_id}/sync-subtitles")
async def sync_subtitles(
    film_id: str,
    subtitle_path: str = "",
    model_size: str = "medium",
    session: AsyncSession = Depends(get_session),
):
    """
    Re-sync existing subtitles using Whisper for perfect timing.
    Reads the existing .srt, transcribes audio with Whisper, and re-aligns timestamps.
    """
    film = await session.get(Film, film_id)
    if not film:
        raise HTTPException(404, "Film not found")

    if not film.video_path:
        raise HTTPException(400, "No video file found for this film.")

    # Ensure video is accessible locally (download from SSH if needed)
    video_path = await _ensure_local_video(film, session)

    from app.core.database import async_session

    async def _run_sync():
        from app.services.whisper_service import sync_with_whisper
        from app.services.settings_service import settings_service as ssvc
        try:
            async with async_session() as s2:
                wh_model = await ssvc.get(s2, "whisper_model") or model_size
                wh_x = await ssvc.get_bool(s2, "whisperx_enabled")
            result = await sync_with_whisper(
                video_path=video_path,
                subtitle_path=subtitle_path,
                film_id=film_id,
                model_size=wh_model,
                use_whisperx=wh_x,
            )
            logger.info("Subtitle sync complete", film_id=film_id, output=result.get("output_path"))
        except Exception as e:
            logger.error("Subtitle sync failed", film_id=film_id, error=str(e))

    asyncio.create_task(_run_sync())
    return {"status": "syncing", "film_id": film_id}


# ─── Embedded tracks ──────────────────────────────────────────────────────────

@router.get("/{film_id}/tracks")
async def get_film_tracks(
    film_id: str,
    session: AsyncSession = Depends(get_session),
):
    """
    List all embedded audio and subtitle tracks in the film's video file.
    Requires ffmpeg/ffprobe installed on the server.
    """
    from app.services.media_service import probe_tracks, check_ffmpeg_available

    film = await session.get(Film, film_id)
    if not film:
        raise HTTPException(404, "Film not found")

    if not film.video_path:
        raise HTTPException(400, "No video file registered for this film. Run a library scan first.")

    if not check_ffmpeg_available():
        raise HTTPException(501, "ffmpeg/ffprobe not installed on the server. Install both to use track discovery.")
    logger.info("tracks: start", film_id=film_id, video_path=film.video_path)

    # Ensure video is accessible locally (download from SSH if needed)
    video_path = await _ensure_local_video(film, session)
    logger.info("tracks: video resolved", video_path=video_path, exists=os.path.isfile(video_path) if video_path else False)
    if not video_path or not os.path.isfile(video_path):
        raise HTTPException(400, f"Video file not accessible: {film.video_path}")

    try:
        tracks = probe_tracks(video_path)
    except Exception as e:
        raise HTTPException(500, f"Failed to probe video: {str(e)[:200]}")

    return {
        "film_id": film_id,
        "video_path": film.video_path,
        "audio": tracks.get("audio", []),
        "subtitle": tracks.get("subtitle", []),
        "video": tracks.get("video", []),
    }


@router.post("/{film_id}/extract-subtitles")
async def extract_film_subtitles(
    film_id: str,
    track_index: Optional[int] = None,
    extract_all: bool = True,
    session: AsyncSession = Depends(get_session),
):
    """
    Extract embedded subtitle tracks from the film's video file.

    If extract_all=True, extracts all text-based tracks.
    If track_index is specified, extracts only that track.
    Extracted files are saved to data/work/{film_id}/subs/ and become
    available via GET /films/{id}/subtitles.
    """
    from app.services.media_service import extract_all_subtitles, extract_subtitle_track, check_ffmpeg_available

    film = await session.get(Film, film_id)
    if not film:
        raise HTTPException(404, "Film not found")

    if not film.video_path:
        raise HTTPException(400, "No video file registered for this film.")

    if not check_ffmpeg_available():
        raise HTTPException(501, "ffmpeg/ffprobe not installed on the server.")

    # Ensure video is accessible locally (download from SSH if needed)
    video_path = await _ensure_local_video(film, session)

    try:
        if track_index is not None:
            # Extract a single track
            path = extract_subtitle_track(
                video_path=video_path,
                track_index=track_index,
                film_id=film_id,
            )
            return {
                "status": "extracted",
                "film_id": film_id,
                "tracks": [{"index": track_index, "path": path}],
            }
        else:
            # Extract all text-based tracks
            results = extract_all_subtitles(
                video_path=video_path,
                film_id=film_id,
                text_only=True,
            )
            if not results:
                return {
                    "status": "no_extractable_tracks",
                    "film_id": film_id,
                    "tracks": [],
                    "message": "No text-based subtitle tracks found in this video file.",
                }
            return {
                "status": "extracted",
                "film_id": film_id,
                "tracks": results,
            }
    except Exception as e:
        raise HTTPException(500, f"Subtitle extraction failed: {str(e)[:200]}")


@router.post("/{film_id}/extract-audio")
async def extract_film_audio(
    film_id: str,
    track_index: Optional[int] = None,
    language: str = "und",
    session: AsyncSession = Depends(get_session),
):
    """
    Extract an audio track from the film's video file as WAV.

    If track_index is not specified, extracts the default audio track.
    Output is 16kHz mono WAV (Whisper-compatible).
    """
    from app.services.media_service import extract_audio_track, check_ffmpeg_available

    film = await session.get(Film, film_id)
    if not film:
        raise HTTPException(404, "Film not found")

    if not film.video_path:
        raise HTTPException(400, "No video file registered for this film.")

    if not check_ffmpeg_available():
        raise HTTPException(501, "ffmpeg/ffprobe not installed on the server.")

    # Ensure video is accessible locally (download from SSH if needed)
    video_path = await _ensure_local_video(film, session)

    try:
        path = extract_audio_track(
            video_path=video_path,
            film_id=film_id,
            track_index=track_index,
            language=language,
        )
        return {
            "status": "extracted",
            "film_id": film_id,
            "audio_path": path,
        }
    except Exception as e:
        raise HTTPException(500, f"Audio extraction failed: {str(e)[:200]}")


# ─── Work directory management ──────────────────────────────────────────────────

@router.get("/{film_id}/work-files")
async def list_work_files(
    film_id: str,
    session: AsyncSession = Depends(get_session),
):
    """
    List all working files for a film (audio, extracted subs, whisper output, uploads, sync).
    Does NOT include the final translated output.
    """
    from app.services.workdir import list_work_files as _list_work_files, migrate_legacy_dirs

    film = await session.get(Film, film_id)
    if not film:
        raise HTTPException(404, "Film not found")

    migrate_legacy_dirs(film_id)
    return {
        "film_id": film_id,
        "files": _list_work_files(film_id),
    }


@router.delete("/{film_id}/work-files")
async def clean_work_files(
    film_id: str,
    category: str = "all",
    session: AsyncSession = Depends(get_session),
):
    """
    Clean working files for a film.

    Query params:
        category: 'all' (default), 'audio', 'subs', 'whisper', 'uploads', 'sync'
    The film's source directory is NEVER touched.
    The final output (translations) is NOT deleted here.
    """
    from app.services.workdir import clean_work_dir, clean_audio_dir

    film = await session.get(Film, film_id)
    if not film:
        raise HTTPException(404, "Film not found")

    import shutil
    categories_map = {
        "all": lambda: clean_work_dir(film_id),
        "audio": lambda: clean_audio_dir(film_id),
        "subs": lambda: shutil.rmtree(os.path.join("data", "work", film_id, "subs"), ignore_errors=True),
        "whisper": lambda: shutil.rmtree(os.path.join("data", "work", film_id, "whisper"), ignore_errors=True),
        "uploads": lambda: shutil.rmtree(os.path.join("data", "work", film_id, "uploads"), ignore_errors=True),
        "sync": lambda: shutil.rmtree(os.path.join("data", "work", film_id, "sync"), ignore_errors=True),
    }

    cleaner = categories_map.get(category)
    if not cleaner:
        raise HTTPException(400, f"Invalid category: {category}. Use: {', '.join(categories_map.keys())}")

    cleaner()
    logger.info("Cleaned work files", film_id=film_id, category=category)
    return {"status": "cleaned", "film_id": film_id, "category": category}


# ─── Translation versions ──────────────────────────────────────────────────

@router.get("/{film_id}/translations")
async def list_translations(
    film_id: str,
    session: AsyncSession = Depends(get_session),
):
    """
    List all translated subtitle versions for a film.
    Returns the timestamped versions from data/output/{film_id}/.
    """
    film = await session.get(Film, film_id)
    if not film:
        raise HTTPException(404, "Film not found")

    from app.services.workdir import output_dir as get_output_dir
    out_dir = get_output_dir(film_id)

    versions = []
    if os.path.isdir(out_dir):
        for name in sorted(os.listdir(out_dir), reverse=True):
            if not name.endswith('.srt'):
                continue
            full_path = os.path.join(out_dir, name)
            if not os.path.isfile(full_path):
                continue
            stat = os.stat(full_path)
            import time
            versions.append({
                "filename": name,
                "path": full_path,
                "size": stat.st_size,
                "created": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
            })

    return {"film_id": film_id, "target_language": film.target_language, "versions": versions}


@router.post("/{film_id}/translations/install")
async def install_translation(
    film_id: str,
    body: dict,
    session: AsyncSession = Depends(get_session),
):
    """
    Install a selected translated SRT to the film's source directory
    with the standard naming convention: Movie.Name.fre.srt (3-letter ISO code).

    Body: { "path": "/app/data/output/abc/The.Matrix.fr.2026-05-06_14-30.srt" }
    """
    film = await session.get(Film, film_id)
    if not film:
        raise HTTPException(404, "Film not found")

    src_path = body.get("path", "")
    if not src_path or not os.path.isfile(src_path):
        raise HTTPException(400, f"Translation file not found: {src_path}")

    # Determine the film's source directory (mounted, local, or SSH)
    from app.services.install_service import find_film_source_dir
    target_dir, _ = await find_film_source_dir(film, session)
    if not target_dir or not os.path.isdir(target_dir):
        raise HTTPException(400, "Film source directory not accessible. Check that the mount is active or the path exists.")

    # Build the target filename with standard naming convention
    # Use the film's folder name as base (cleanest for media servers)
    import pathlib
    film_folder = pathlib.Path(target_dir).name
    # 3-letter ISO codes for common languages
    ISO3 = {"fr": "fre", "en": "eng", "es": "spa", "de": "ger", "it": "ita", "pt": "por",
            "ja": "jpn", "ko": "kor", "zh": "chi", "ru": "rus", "ar": "ara"}
    lang3 = ISO3.get(film.target_language, film.target_language)
    dest_name = f"{film_folder}.{lang3}.srt"
    dest_path = os.path.join(target_dir, dest_name)

    # Check for existing subtitle and warn
    existing = None
    if os.path.isfile(dest_path):
        # Rename existing to .bak
        bak_path = dest_path + ".bak"
        os.rename(dest_path, bak_path)
        existing = bak_path

    import shutil
    shutil.copy2(src_path, dest_path)

    logger.info("Translation installed", film_id=film_id, dest=dest_path, existing_backup=existing)

    return {
        "status": "installed",
        "film_id": film_id,
        "source": src_path,
        "destination": dest_path,
        "backup": existing,
    }


