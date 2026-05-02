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
    # Get the most recent completed/running task's lore
    result = await session.execute(
        select(TranslationTask)
        .where(TranslationTask.film_id == film_id)
        .order_by(TranslationTask.created_at.desc())
        .limit(1)
    )
    task = result.scalars().first()
    return {
        "lore_summary": task.lore_summary if task else None,
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


# ─── Existing subtitles ──────────────────────────────────────────────────────

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
    from app.services.scanner_service import parse_subtitle_filename, is_gendered_language, SUBTITLE_EXTENSIONS
    from app.services.workdir import migrate_legacy_dirs

    # Ensure legacy files are migrated to new work dir structure
    migrate_legacy_dirs(film_id)

    film = await session.get(Film, film_id)
    if not film:
        raise HTTPException(404, "Film not found")

    results = []
    seen = set()

    # 1. Subtitles from the film's directory (scanned)
    if film.path and os.path.isdir(film.path):
        try:
            for name in sorted(os.listdir(film.path)):
                ext = Path(name).suffix.lower()
                if ext in SUBTITLE_EXTENSIONS:
                    full_path = os.path.join(film.path, name)
                    if not os.path.isfile(full_path):
                        continue
                    info = parse_subtitle_filename(name)
                    key = (name, full_path)
                    if key not in seen:
                        seen.add(key)
                        results.append(ExistingSubtitleOut(
                            filename=name,
                            path=full_path,
                            language=info.get("language"),
                            is_sdh=info.get("is_sdh", False),
                            is_forced=info.get("is_forced", False),
                            is_gendered=is_gendered_language(info.get("language") or "und"),
                            format=ext.lstrip("."),
                            source="scanner",
                        ))
        except Exception:
            logger.warning("Cannot list subtitles from film directory", path=film.path)

    # 2. Subtitles from the poster cache dir (SSH-cached subtitles)
    poster_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'posters')
    # Not relevant for subtitles, skip

    # 3. Previously uploaded subtitles (in work dir)
    from app.services.workdir import uploads_dir, extracted_subs_dir, whisper_dir

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
                        key = (name, full_path)
                        if key not in seen:
                            seen.add(key)
                            results.append(ExistingSubtitleOut(
                                filename=name,
                                path=full_path,
                                language=info.get("language"),
                                is_sdh=info.get("is_sdh", False),
                                is_forced=info.get("is_forced", False),
                                is_gendered=is_gendered_language(info.get("language") or "und"),
                                format=ext.lstrip("."),
                                source=source_tag,
                            ))
            except PermissionError:
                pass

    return results


# ─── Manual context analysis ────────────────────────────────────────────────

@router.post("/{film_id}/analyze")
async def analyze_film_context(
    film_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Run context analysis (characters, lore, glossary) for a film without starting translation."""
    from app.services.scanner_service import get_scan_progress
    # Import necessary services
    from app.core.database import async_session

    film = await session.get(Film, film_id)
    if not film:
        raise HTTPException(404, "Film not found")

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
            ollama_url = await settings_service.get(s, "ollama_base_url") or "http://ollama:11434"
            ollama_model = await settings_service.get(s, "ollama_model") or "qwen3.5:397b-cloud"
            llm = OllamaProvider(base_url=ollama_url, model=ollama_model)
            ctx = ContextService(llm)
            sub_svc = SubtitleService()

            # Try to load subtitles to analyze
            sub_path = None
            subs = await list_film_subtitles(film_id, s)
            if subs:
                sub_path = subs[0].path

            try:
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
            except Exception as e:
                logger.error("Context analysis failed", film_id=film_id, error=str(e))

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

    from app.core.database import async_session

    async def _run_transcription():
        from app.services.whisper_service import transcribe_video
        try:
            result = await transcribe_video(
                video_path=film.video_path,
                film_id=film_id,
                language=language,
                model_size=model_size,
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

    from app.core.database import async_session

    async def _run_sync():
        from app.services.whisper_service import sync_with_whisper
        try:
            result = await sync_with_whisper(
                video_path=film.video_path,
                subtitle_path=subtitle_path,
                film_id=film_id,
                model_size=model_size,
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

    if not os.path.isfile(film.video_path):
        raise HTTPException(400, f"Video file not found on disk: {film.video_path}")

    if not check_ffmpeg_available():
        raise HTTPException(501, "ffmpeg/ffprobe not installed on the server. Install both to use track discovery.")

    try:
        tracks = probe_tracks(film.video_path)
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

    if not os.path.isfile(film.video_path):
        raise HTTPException(400, f"Video file not found: {film.video_path}")

    if not check_ffmpeg_available():
        raise HTTPException(501, "ffmpeg/ffprobe not installed on the server.")

    try:
        if track_index is not None:
            # Extract a single track
            path = extract_subtitle_track(
                video_path=film.video_path,
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
                video_path=film.video_path,
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

    if not os.path.isfile(film.video_path):
        raise HTTPException(400, f"Video file not found: {film.video_path}")

    if not check_ffmpeg_available():
        raise HTTPException(501, "ffmpeg/ffprobe not installed on the server.")

    try:
        path = extract_audio_track(
            video_path=film.video_path,
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


