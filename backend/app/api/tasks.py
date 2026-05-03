"""
Translation task routes: start, monitor, download.
"""

import os
import asyncio
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.services.task_runner import start_task
from app.core.database import get_session
from app.models.database import Film, TranslationTask, TaskStatusEnum, GlossaryEntry
from app.models.schemas import TaskOut, TaskProgressOut, GlossaryEntryOut
from app.services.llm_provider import OllamaProvider
from app.services.subtitle_service import SubtitleService
from app.services.context_service import ContextService
from app.services.translation_service import TranslationService
from app.services.settings_service import settings_service

logger = get_logger(__name__)
router = APIRouter(prefix="/tasks", tags=["tasks"])


def _build_services_from_settings(base_url: str, model: str, cps_limit: int):
    """Create service instances using runtime settings from DB."""
    llm = OllamaProvider(base_url=base_url, model=model)
    sub_svc = SubtitleService(cps_limit=cps_limit)
    ctx = ContextService(llm)
    tx = TranslationService(llm, ctx, sub_svc)
    return llm, ctx, tx, sub_svc


# ─── Endpoints ──────────────────────────────────────────────────────────────

@router.post("/{film_id}/upload", response_model=TaskOut, status_code=201)
async def upload_subtitle_and_start(
    film_id: str,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    """
    Upload a subtitle file for a film and automatically create a translation task.
    Source language is auto-detected from the filename (e.g. film.en.srt → en).
    """
    from app.services.scanner_service import parse_subtitle_filename

    film = await session.get(Film, film_id)
    if not film:
        raise HTTPException(404, "Film not found")

    # Save uploaded file to work dir
    from app.services.workdir import uploads_dir
    upload_path = uploads_dir(film_id)
    file_path = os.path.join(upload_path, file.filename or "subtitle.srt")

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    # Auto-detect source language from filename
    filename = file.filename or "subtitle.srt"
    sub_info = parse_subtitle_filename(filename)
    source_language = sub_info.get("language") or "en"
    is_sdh = sub_info.get("is_sdh", False)

    logger.info("Subtitle uploaded", film_id=film_id, filename=filename,
                source_language=source_language, sdh=is_sdh, size=len(content))

    # Determine format from extension
    fmt = os.path.splitext(filename)[1].lstrip(".").lower()
    if fmt not in ("srt", "vtt", "ass", "ssa"):
        fmt = "srt"

    # Override film source language if we detected a specific one
    if film.source_language == "en" and source_language != "en":
        film.source_language = source_language

    # Create translation task
    task = TranslationTask(
        film_id=film_id,
        source_filename=filename,
        source_format=fmt,
        source_path=file_path,
        source_language=source_language,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)

    return task


@router.post("/{film_id}/translate-existing", response_model=TaskOut, status_code=201)
async def translate_existing_subtitle(
    film_id: str,
    data: dict,
    session: AsyncSession = Depends(get_session),
):
    """
    Start a task from an existing subtitle file (found by scan or upload).
    Body: { "subtitle_path": "/path/to/film.en.srt", "source_language": "en" (optional), "task_type": "translation"|"improve"|"sync" (optional) }
    """
    from app.services.scanner_service import parse_subtitle_filename

    film = await session.get(Film, film_id)
    if not film:
        raise HTTPException(404, "Film not found")

    subtitle_path = data.get("subtitle_path", "")
    if not subtitle_path:
        raise HTTPException(400, "subtitle_path is required")

    task_type = data.get("task_type", "translation")

    # ── Path traversal protection ────────────────────────────────────────
    from app.services.workdir import WORK_BASE, OUTPUT_BASE

    allowed_dirs = [
        os.path.abspath(WORK_BASE),
        os.path.abspath(OUTPUT_BASE),
        os.path.abspath(os.path.join("data", "uploads")),  # legacy compat
    ]
    if film.path and os.path.isdir(film.path):
        allowed_dirs.append(os.path.abspath(film.path))
    abs_path = os.path.abspath(subtitle_path)
    if not any(abs_path.startswith(d + os.sep) or abs_path == d for d in allowed_dirs):
        raise HTTPException(403, "Access denied: file path is outside allowed directories")

    if not os.path.isfile(subtitle_path):
        raise HTTPException(400, f"Subtitle file not found: {subtitle_path}")

    # Auto-detect source language
    filename = os.path.basename(subtitle_path)
    sub_info = parse_subtitle_filename(filename)
    source_language = data.get("source_language") or sub_info.get("language") or "en"

    # Copy to work dir uploads/ for consistency
    from app.services.workdir import uploads_dir
    upload_dir = uploads_dir(film_id)
    dest_path = os.path.join(upload_dir, filename)
    if dest_path != subtitle_path:
        import shutil
        shutil.copy2(subtitle_path, dest_path)

    fmt = os.path.splitext(filename)[1].lstrip(".").lower()
    if fmt not in ("srt", "vtt", "ass", "ssa"):
        fmt = "srt"

    task = TranslationTask(
        film_id=film_id,
        task_type=task_type,
        source_filename=filename,
        source_format=fmt,
        source_path=dest_path,
        source_language=source_language,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)

    logger.info("Task from existing subtitle", film_id=film_id, task_type=task_type, path=subtitle_path, lang=source_language)
    return task


@router.post("/{task_id}/start", response_model=TaskProgressOut)
async def start_translation(
    task_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Kick off the workflow for a task (translation, improve, sync, etc.)."""
    task = await session.get(TranslationTask, task_id)
    if not task:
        raise HTTPException(404, "Task not found")

    if task.status not in ("pending", "failed"):
        raise HTTPException(409, f"Task is already {task.status}")

    # Dispatch based on task type
    if task.task_type == "sync":
        task.status = "syncing"
        await session.commit()
        start_task(task_id, _run_sync_workflow(task_id))
    elif task.task_type == "improve":
        task.status = "analyzing_context"
        await session.commit()
        start_task(task_id, _run_improve_workflow(task_id))
    else:
        # Default: translation workflow
        task.status = TaskStatusEnum.analyzing_context
        await session.commit()
        start_task(task_id, _run_translation_workflow(task_id))

    logger.info("Task started", task_id=task_id, task_type=task.task_type)
    return task


@router.get("/", response_model=List[TaskOut])
async def list_tasks(
    session: AsyncSession = Depends(get_session),
):
    """List all translation tasks."""
    result = await session.execute(select(TranslationTask))
    return result.scalars().all()


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(
    task_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get full task details."""
    task = await session.get(TranslationTask, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return task


@router.get("/{task_id}/progress", response_model=TaskProgressOut)
async def get_task_progress(
    task_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Lightweight endpoint for progress polling."""
    task = await session.get(TranslationTask, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return task


@router.get("/{task_id}/glossary", response_model=List[GlossaryEntryOut])
async def get_task_glossary(
    task_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get the glossary built for this task's film."""
    task = await session.get(TranslationTask, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    result = await session.execute(
        select(GlossaryEntry).where(GlossaryEntry.film_id == task.film_id)
    )
    return result.scalars().all()


@router.get("/{task_id}/download")
async def download_translated_subtitle(
    task_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Download the translated subtitle file."""
    from fastapi.responses import FileResponse

    task = await session.get(TranslationTask, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status != TaskStatusEnum.completed:
        raise HTTPException(409, "Translation not yet completed")
    if not task.target_path or not os.path.exists(task.target_path):
        raise HTTPException(404, "Output file not found")

    return FileResponse(
        path=task.target_path,
        filename=task.target_filename or "translated.srt",
        media_type="application/octet-stream",
    )


@router.post("/{task_id}/install")
async def install_subtitle_to_source(
    task_id: str,
    session: AsyncSession = Depends(get_session),
):
    """
    Install the translated subtitle file next to the video in the source directory.

    For local films: copies to the film's directory.
    For SSH films: uploads via SFTP.
    The film's source directory is NEVER modified by any other Kinoscribe operation.
    """
    from app.services.install_service import install_subtitle_to_source as do_install

    task = await session.get(TranslationTask, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status != TaskStatusEnum.completed:
        raise HTTPException(409, "Translation not yet completed")
    if not task.target_path or not os.path.exists(task.target_path):
        raise HTTPException(404, "Output file not found")

    film = await session.get(Film, task.film_id)
    if not film:
        raise HTTPException(404, "Film not found")
    if not film.path and not film.video_path:
        raise HTTPException(400, "No source directory or video path for this film")

    try:
        dest_path = await do_install(film, task_id, session)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    except Exception as e:
        logger.error("Install failed", task_id=task_id, error=str(e))
        raise HTTPException(500, f"Install failed: {str(e)[:200]}")

    return {
        "status": "installed",
        "task_id": task_id,
        "destination": dest_path,
    }


# ─── Background workflow ────────────────────────────────────────────────────

async def _run_translation_workflow(task_id: str):
    """
    Full translation pipeline, running in the background.
    Reads ALL configuration from the DB settings table.
    """
    from app.core.database import async_session

    async with async_session() as session:
        # Ensure settings exist
        await settings_service.seed_if_empty(session)

        # Read runtime config from DB
        ollama_url = await settings_service.get(session, "ollama_base_url")
        ollama_model = await settings_service.get(session, "ollama_model")
        ollama_refine_model = await settings_service.get(session, "ollama_refine_model")
        cps_limit = await settings_service.get_int(session, "cps_limit")
        window_size = await settings_service.get_int(session, "sliding_window_size")
        batch_size = await settings_service.get_int(session, "batch_size")
        temperature = await settings_service.get_float(session, "llm_temperature")
        auto_clean_sdh = await settings_service.get_bool(session, "auto_clean_sdh")
        draft_think = await settings_service.get_bool(session, "draft_think")
        refine_think = await settings_service.get_bool(session, "refine_think")

        # Use refine model if configured, otherwise same as draft model
        refine_model = ollama_refine_model.strip() if ollama_refine_model and ollama_refine_model.strip() else None

        # Build services with runtime settings
        llm, ctx, tx, sub_svc = _build_services_from_settings(ollama_url, ollama_model, cps_limit)

        task = await session.get(TranslationTask, task_id)
        if not task:
            logger.error("Task disappeared", task_id=task_id)
            return

        film = await session.get(Film, task.film_id)
        if not film:
            task.status = TaskStatusEnum.failed
            task.error_message = "Film not found"
            await session.commit()
            return

        try:
            # ── Phase 1: Parse subtitles ────────────────────────────
            parsed = sub_svc.parse_file(task.source_path)
            logger.info("Subtitles parsed", task_id=task_id, lines=len(parsed.lines))

            # Clean SDH tags if enabled (before context analysis & translation)
            if auto_clean_sdh:
                parsed = sub_svc.clean_sdh_from_parsed(parsed)
                logger.info("SDH tags cleaned for translation", task_id=task_id)

            # ── Phase 2: Context analysis ───────────────────────────
            task.status = TaskStatusEnum.analyzing_context
            await session.commit()

            # Build character profiles
            characters = await ctx.build_character_profiles(film, parsed, sub_svc)
            for c in characters:
                session.add(c)
            film.characters = characters
            await session.commit()

            # Generate lore summary
            lore = await ctx.generate_lore_summary(parsed, characters)
            task.lore_summary = lore
            await session.commit()

            # Build glossary
            glossary_data = await ctx.build_glossary(parsed, film.target_language)
            for entry in glossary_data:
                g = GlossaryEntry(
                    film_id=film.id,
                    source_term=entry.get("source", ""),
                    target_term=entry.get("target", ""),
                    notes=entry.get("notes", ""),
                )
                session.add(g)
            await session.commit()
            await session.refresh(film)

            # ── Phase 3: Translation ────────────────────────────────
            task.status = TaskStatusEnum.translating
            await session.commit()

            # Pass runtime settings to translation
            translated_lines = await tx.translate_film_subtitles(
                task, film, parsed,
                window_size=window_size,
                batch_size=batch_size,
                temperature=temperature,
                think=draft_think,
                db_session=session,
            )

            # ── Phase 4: Refine pass (optional) ─────────────────────
            if refine_model:
                task.status = TaskStatusEnum.refining
                await session.commit()
                logger.info(
                    "Starting refine pass",
                    task_id=task_id,
                    model=refine_model,
                    think=refine_think,
                )
                refine_llm = OllamaProvider(base_url=ollama_url, model=refine_model)
                refine_ctx = ContextService(refine_llm)
                refine_tx = TranslationService(refine_llm, refine_ctx, sub_svc)
                translated_lines = await refine_tx.refine_translation(
                    task, film, translated_lines, parsed,
                    batch_size=batch_size,
                    temperature=temperature,
                    think=refine_think,
                    db_session=session,
                )

            # ── Phase 5: Write output ───────────────────────────────
            from app.services.workdir import output_dir as get_output_dir
            out_dir = get_output_dir(film.id)
            base_name = os.path.splitext(task.source_filename)[0]
            output_path = os.path.join(out_dir, f"{base_name}.{film.target_language}.srt")

            sub_svc.write_srt(translated_lines, output_path)
            task.target_filename = f"{base_name}.{film.target_language}.srt"
            task.target_path = output_path

            task.status = TaskStatusEnum.completed
            task.progress_pct = 100
            await session.commit()

            logger.info(
                "Translation workflow complete",
                task_id=task_id,
                output=output_path,
                lines=len(translated_lines),
            )

        except Exception as e:
            logger.error("Translation workflow failed", task_id=task_id, error=str(e))
            task = await session.get(TranslationTask, task_id)
            if task:
                task.status = TaskStatusEnum.failed
                task.error_message = str(e)
                await session.commit()


# ─── Improve workflow ─────────────────────────────────────────────────────────

async def _run_improve_workflow(task_id: str):
    """
    Improve an existing target-language subtitle.
    Uses context analysis + LLM to re-translate while preserving timings.
    """
    from app.core.database import async_session

    async with async_session() as session:
        await settings_service.seed_if_empty(session)

        ollama_url = await settings_service.get(session, "ollama_base_url")
        ollama_model = await settings_service.get(session, "ollama_model")
        ollama_refine_model = await settings_service.get(session, "ollama_refine_model")
        cps_limit = await settings_service.get_int(session, "cps_limit")
        window_size = await settings_service.get_int(session, "sliding_window_size")
        batch_size = await settings_service.get_int(session, "batch_size")
        temperature = await settings_service.get_float(session, "llm_temperature")
        draft_think = await settings_service.get_bool(session, "draft_think")
        refine_think = await settings_service.get_bool(session, "refine_think")

        # Use refine model for improvement pass
        refine_model = ollama_refine_model.strip() if ollama_refine_model and ollama_refine_model.strip() else ollama_model

        llm = OllamaProvider(base_url=ollama_url, model=refine_model)
        ctx = ContextService(llm)
        sub_svc = SubtitleService(cps_limit=cps_limit)
        tx = TranslationService(llm, ctx, sub_svc)

        task = await session.get(TranslationTask, task_id)
        if not task:
            logger.error("Task disappeared", task_id=task_id)
            return

        film = await session.get(Film, task.film_id)
        if not film:
            task.status = TaskStatusEnum.failed
            task.error_message = "Film not found"
            await session.commit()
            return

        try:
            # Parse existing subtitle
            parsed = sub_svc.parse_file(task.source_path)
            logger.info("Subtitles parsed for improvement", task_id=task_id, lines=len(parsed.lines))

            # Build context
            task.status = TaskStatusEnum.analyzing_context
            await session.commit()

            characters = await ctx.build_character_profiles(film, parsed, sub_svc)
            from app.models.database import Character, GlossaryEntry
            existing_chars = await session.execute(
                select(Character).where(Character.film_id == film.id)
            )
            for c in existing_chars.scalars().all():
                await session.delete(c)
            for c in characters:
                session.add(c)
            await session.commit()

            lore = await ctx.generate_lore_summary(parsed, characters)
            task.lore_summary = lore
            film.lore_summary = lore
            await session.commit()

            # Translate (improve mode uses the source subtitle as both source and reference)
            task.status = TaskStatusEnum.translating
            await session.commit()

            translated_lines = await tx.translate_film_subtitles(
                task, film, parsed,
                window_size=window_size,
                batch_size=batch_size,
                temperature=temperature,
                think=refine_think,
                db_session=session,
            )

            # Write output
            from app.services.workdir import output_dir as get_output_dir
            out_dir = get_output_dir(film.id)
            base_name = os.path.splitext(task.source_filename)[0]
            # Add .improved suffix to distinguish from original translation
            output_path = os.path.join(out_dir, f"{base_name}.improved.{film.target_language}.srt")

            sub_svc.write_srt(translated_lines, output_path)
            task.target_filename = f"{base_name}.improved.{film.target_language}.srt"
            task.target_path = output_path

            task.status = TaskStatusEnum.completed
            task.progress_pct = 100
            await session.commit()

            logger.info("Improve workflow complete", task_id=task_id, output=output_path)

        except Exception as e:
            logger.error("Improve workflow failed", task_id=task_id, error=str(e))
            task = await session.get(TranslationTask, task_id)
            if task:
                task.status = TaskStatusEnum.failed
                task.error_message = str(e)
                await session.commit()


# ─── Sync (Whisper) workflow ────────────────────────────────────────────────

async def _run_sync_workflow(task_id: str):
    """
    Re-sync an existing subtitle using Whisper.
    Adjusts timings to better match the audio.
    """
    from app.core.database import async_session
    from app.services.whisper_service import sync_with_whisper
    from app.services.media_service import extract_audio_track
    from app.services.workdir import audio_dir, whisper_dir

    async with async_session() as session:
        task = await session.get(TranslationTask, task_id)
        if not task:
            logger.error("Task disappeared", task_id=task_id)
            return

        film = await session.get(Film, task.film_id)
        if not film:
            task.status = TaskStatusEnum.failed
            task.error_message = "Film not found"
            await session.commit()
            return

        try:
            # Extract audio if not already present
            audio_files = os.listdir(audio_dir(film.id)) if os.path.isdir(audio_dir(film.id)) else []
            audio_path = None
            for f in audio_files:
                if f.endswith('.wav'):
                    audio_path = os.path.join(audio_dir(film.id), f)
                    break

            if not audio_path:
                if not film.video_path or not os.path.isfile(film.video_path):
                    task.status = TaskStatusEnum.failed
                    task.error_message = "No video file found for audio extraction"
                    await session.commit()
                    return
                task.status = TaskStatusEnum.extracting
                task.progress_pct = 10
                await session.commit()
                audio_path = await asyncio.to_thread(extract_audio_track, film.video_path, task.source_language or 'und')

            task.status = TaskStatusEnum.syncing
            task.progress_pct = 30
            await session.commit()

            # Run Whisper sync
            ollama_url = await settings_service.get(session, "ollama_base_url")
            whisper_model = await settings_service.get(session, "whisper_model") or "medium"

            result = await sync_with_whisper(
                audio_path,
                task.source_path,
                film.id,
                model_size=whisper_model,
            )

            # Write output
            from app.services.workdir import output_dir as get_output_dir
            # Result contains the synced subtitle path
            result_path = result.get("output_path") if isinstance(result, dict) else None
            if result_path and os.path.isfile(result_path):
                out_dir = get_output_dir(film.id)
                base_name = os.path.splitext(task.source_filename)[0]
                output_path = os.path.join(out_dir, f"{base_name}.synced.{film.target_language}.srt")

                import shutil
                shutil.copy2(result_path, output_path)
                task.target_filename = f"{base_name}.synced.{film.target_language}.srt"
                task.target_path = output_path

            task.status = TaskStatusEnum.completed
            task.progress_pct = 100
            await session.commit()

            logger.info("Sync workflow complete", task_id=task_id, output=output_path)

        except Exception as e:
            logger.error("Sync workflow failed", task_id=task_id, error=str(e))
            task = await session.get(TranslationTask, task_id)
            if task:
                task.status = TaskStatusEnum.failed
                task.error_message = str(e)
                await session.commit()