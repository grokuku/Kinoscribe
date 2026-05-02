"""
Work directory management for Kinoscribe.

Ensures all temporary/working files are isolated from the film's source directory.
The source directory (local path or SSH mount) must NEVER be written to by Kinoscribe.

Layout:
    data/
        work/
            {film_id}/
                audio/          ← extracted audio tracks (WAV for Whisper)
                subs/           ← extracted embedded subtitles (SRT/ASS)
                whisper/        ← Whisper transcription output
                uploads/        ← user-uploaded subtitles
                sync/           ← synced subtitle files
        output/
            {film_id}/
                *.fr.srt       ← final translated subtitles (ready for download)

Principles:
    - The film's source directory is READ-ONLY
    - data/work/ is temporary and can be cleaned at any time
    - data/output/ is the canonical location for translated subtitles
    - Each film's work area has typed subdirectories so the film folder stays clean
"""

import os
import shutil
from pathlib import Path
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)

# ─── Base paths ────────────────────────────────────────────────────────────────

BASE_DIR = os.path.join("data")
WORK_BASE = os.path.join(BASE_DIR, "work")
OUTPUT_BASE = os.path.join(BASE_DIR, "output")


# ─── Film work directory ──────────────────────────────────────────────────────

def film_work_dir(film_id: str) -> str:
    """Root working directory for a film: data/work/{film_id}/"""
    path = os.path.join(WORK_BASE, film_id)
    os.makedirs(path, exist_ok=True)
    return path


def audio_dir(film_id: str) -> str:
    """Directory for extracted audio tracks: data/work/{film_id}/audio/"""
    path = os.path.join(WORK_BASE, film_id, "audio")
    os.makedirs(path, exist_ok=True)
    return path


def extracted_subs_dir(film_id: str) -> str:
    """Directory for extracted embedded subtitles: data/work/{film_id}/subs/"""
    path = os.path.join(WORK_BASE, film_id, "subs")
    os.makedirs(path, exist_ok=True)
    return path


def whisper_dir(film_id: str) -> str:
    """Directory for Whisper output: data/work/{film_id}/whisper/"""
    path = os.path.join(WORK_BASE, film_id, "whisper")
    os.makedirs(path, exist_ok=True)
    return path


def uploads_dir(film_id: str) -> str:
    """Directory for user-uploaded subtitles: data/work/{film_id}/uploads/"""
    path = os.path.join(WORK_BASE, film_id, "uploads")
    os.makedirs(path, exist_ok=True)
    return path


def sync_dir(film_id: str) -> str:
    """Directory for synced subtitle files: data/work/{film_id}/sync/"""
    path = os.path.join(WORK_BASE, film_id, "sync")
    os.makedirs(path, exist_ok=True)
    return path


def output_dir(film_id: str) -> str:
    """Directory for final translated subtitles: data/output/{film_id}/"""
    path = os.path.join(OUTPUT_BASE, film_id)
    os.makedirs(path, exist_ok=True)
    return path


# ─── Cleanup ────────────────────────────────────────────────────────────────────

def clean_work_dir(film_id: str) -> None:
    """Remove the entire work directory for a film (audio, subs, whisper, etc.)."""
    path = os.path.join(WORK_BASE, film_id)
    if os.path.isdir(path):
        shutil.rmtree(path)
        logger.info("Cleaned work directory", film_id=film_id)


def clean_audio_dir(film_id: str) -> None:
    """Remove extracted audio files (can be large WAVs)."""
    path = os.path.join(WORK_BASE, film_id, "audio")
    if os.path.isdir(path):
        shutil.rmtree(path)
        logger.info("Cleaned audio directory", film_id=film_id)


def clean_output_dir(film_id: str) -> None:
    """Remove the output directory for a film."""
    path = os.path.join(OUTPUT_BASE, film_id)
    if os.path.isdir(path):
        shutil.rmtree(path)
        logger.info("Cleaned output directory", film_id=film_id)


def clean_all_for_film(film_id: str) -> None:
    """Remove both work and output directories for a film."""
    clean_work_dir(film_id)
    clean_output_dir(film_id)


# ─── Migration / compatibility ──────────────────────────────────────────────────

def migrate_legacy_dirs(film_id: str) -> None:
    """
    Migrate files from the old flat data/uploads/{film_id}/ and
    data/output/{film_id}/ structure to the new work dir layout.

    This is called lazily when needed. Old files in data/uploads/
    are moved into data/work/{film_id}/uploads/ or subs/ as appropriate.
    """
    legacy_upload = os.path.join(BASE_DIR, "uploads", film_id)
    if os.path.isdir(legacy_upload):
        dest_upload = uploads_dir(film_id)
        dest_subs = extracted_subs_dir(film_id)

        for name in os.listdir(legacy_upload):
            src = os.path.join(legacy_upload, name)
            if not os.path.isfile(src):
                continue

            ext = Path(name).suffix.lower()
            # Audio files go to audio dir
            if ext == ".wav":
                dest = os.path.join(audio_dir(film_id), name)
            # Subtitle files go to subs dir (or uploads if user-uploaded)
            elif ext in (".srt", ".vtt", ".ass", ".ssa"):
                # If it starts with "extracted." or "whisper_", it's extracted/whisper output
                if name.startswith("extracted.") or name.startswith("whisper_"):
                    dest = os.path.join(dest_subs, name)
                elif name.startswith("audio_"):
                    # shouldn't be an SRT with this prefix but just in case
                    dest = os.path.join(dest_subs, name)
                else:
                    dest = os.path.join(dest_upload, name)
            else:
                dest = os.path.join(dest_upload, name)

            if not os.path.exists(dest):
                shutil.move(src, dest)
                logger.info("Migrated file", src=src, dest=dest)

        # Remove legacy dir if empty
        try:
            os.rmdir(legacy_upload)
            logger.info("Removed legacy upload dir", path=legacy_upload)
        except OSError:
            pass  # dir not empty yet

    legacy_output = os.path.join(BASE_DIR, "output", film_id)
    if os.path.isdir(legacy_output):
        dest_output = output_dir(film_id)
        for name in os.listdir(legacy_output):
            src = os.path.join(legacy_output, name)
            dest = os.path.join(dest_output, name)
            if os.path.isfile(src) and not os.path.exists(dest):
                shutil.move(src, dest)
                logger.info("Migrated output file", src=src, dest=dest)

        try:
            os.rmdir(legacy_output)
        except OSError:
            pass


# ─── Utility ───────────────────────────────────────────────────────────────────

def list_work_files(film_id: str) -> dict:
    """
    List all working files for a film, organized by category.
    Returns {audio: [...], subs: [...], whisper: [...], uploads: [...], sync: [...]}
    """
    result: dict = {"audio": [], "subs": [], "whisper": [], "uploads": [], "sync": []}
    categories = {
        "audio": os.path.join(WORK_BASE, film_id, "audio"),
        "subs": os.path.join(WORK_BASE, film_id, "subs"),
        "whisper": os.path.join(WORK_BASE, film_id, "whisper"),
        "uploads": os.path.join(WORK_BASE, film_id, "uploads"),
        "sync": os.path.join(WORK_BASE, film_id, "sync"),
    }
    for cat, cat_dir in categories.items():
        if os.path.isdir(cat_dir):
            for name in sorted(os.listdir(cat_dir)):
                full = os.path.join(cat_dir, name)
                if os.path.isfile(full):
                    result[cat].append({
                        "name": name,
                        "path": full,
                        "size": os.path.getsize(full),
                    })
    return result