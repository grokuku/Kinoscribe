"""
Install service — copy translated subtitles to the film's source directory.

This is the final step: after translation, the user can "install" the SRT
next to the video file in the source directory (local, SSH, or mounted).
"""

import os
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.crypto import decrypt
from app.models.database import Film, Library, LibrarySource
from app.services.scanner_service import FilesystemProvider, LocalFilesystem, SSHFilesystem
from app.services.workdir import output_dir

logger = get_logger(__name__)


async def _get_filesystem_for_film(
    film: Film,
    session: AsyncSession,
) -> tuple[Optional[FilesystemProvider], Optional[str]]:
    """
    Return (filesystem_provider, film_directory_path) for a film.

    For local films or mounted SSH/SMB: returns (None, local_path).
    For SSH films without mount: returns (SSHFilesystem, source) for SFTP upload.
    """
    if not film.library_id:
        return None, film.path

    result = await session.execute(
        select(Library).where(Library.id == film.library_id)
    )
    library = result.scalar_one_or_none()
    if not library:
        return None, film.path

    result2 = await session.execute(
        select(LibrarySource).where(
            LibrarySource.library_id == library.id,
            LibrarySource.enabled == True,
        )
    )
    sources = result2.scalars().all()

    for source in sources:
        source_path = (source.ssh_remote_path or source.path or "").rstrip("/")
        mp = getattr(source, 'mount_point', None)

        # If source is mounted, use the local mount path directly
        if mp and mp.strip():
            mount_path = os.path.normpath(mp)
            # Film path might already be under the mount point (from mount-aware scan)
            normalized_film_path = os.path.normpath(film.path.rstrip("/")) if film.path else ""
            if normalized_film_path.startswith(mount_path) and os.path.isdir(normalized_film_path):
                return None, normalized_film_path
            # Translate remote path to mount path (film scanned before mount was available)
            if film.path and film.path.rstrip("/").startswith(source_path):
                local_path = film.path.rstrip("/").replace(source_path, mount_path.rstrip("/"), 1)
                if os.path.isdir(local_path):
                    return None, local_path

        if source.source_type == "local":
            if film.path and film.path.startswith(source_path):
                return None, film.path
        elif source.source_type == "ssh":
            fs = SSHFilesystem(
                host=source.ssh_host,
                port=source.ssh_port or 22,
                username=source.ssh_username or "root",
                password=decrypt(source.ssh_password) if source.ssh_auth_type == "password" else None,
                private_key_path=source.ssh_private_key_path if source.ssh_auth_type == "key" else None,
            )
            await fs.connect()
            return fs, source  # type: ignore

    return None, film.path


async def install_subtitle_to_source(
    film: Film,
    task_id: str,
    session: AsyncSession,
) -> str:
    """
    Copy the translated subtitle file from data/output/ to the film's
    source directory (next to the video file).

    For local or mounted: plain file copy.
    For SSH without mount: SFTP upload.

    Returns the destination path.
    """
    from app.models.database import TranslationTask

    task = await session.get(TranslationTask, task_id)
    if not task:
        raise ValueError(f"Task {task_id} not found")

    if not task.target_path or not os.path.isfile(task.target_path):
        raise FileNotFoundError(f"Output file not found: {task.target_path}")

    with open(task.target_path, "rb") as f:
        content = f.read()

    if not film.video_path:
        raise ValueError("Film has no video_path — cannot determine install location")

    video_basename = os.path.splitext(os.path.basename(film.video_path))[0]
    dest_filename = f"{video_basename}.{film.target_language}.srt"

    fs, source_info = await _get_filesystem_for_film(film, session)

    if isinstance(fs, SSHFilesystem) and isinstance(source_info, LibrarySource):
        # SSH source without mount — SFTP upload
        cache_prefix = os.path.join("data", "cache", source_info.id)
        if film.path and film.path.startswith(cache_prefix):
            relative = os.path.relpath(film.path, cache_prefix)
        else:
            relative = ""

        remote_dir = os.path.join(source_info.ssh_remote_path or "/", relative)
        remote_dest = os.path.join(remote_dir, dest_filename)

        try:
            await fs.write_bytes(remote_dest, content)
            logger.info("Installed subtitle via SSH", remote=remote_dest, film_id=film.id)
            await fs.disconnect()
            return remote_dest
        except Exception as e:
            await fs.disconnect()
            raise RuntimeError(f"Failed to write subtitle via SSH: {e}")

    else:
        # Local filesystem (or mounted remote) — simple file copy
        # Determine the effective film directory (may be a mount point)
        film_dir = film.path
        if not film_dir:
            raise ValueError(f"Film has no path — cannot determine install directory")

        # Check if the film is on a mounted source
        if film.library_id:
            result = await session.execute(
                select(LibrarySource).where(LibrarySource.library_id == film.library_id)
            )
            sources = result.scalars().all()
            for source in sources:
                mp = getattr(source, 'mount_point', None)
                if mp and mp.strip():
                    mount_path = os.path.normpath(mp)
                    remote_path = (source.ssh_remote_path or source.path or "").rstrip("/")
                    # Film path may already be under mount point
                    normalized_film_path = os.path.normpath(film.path.rstrip("/")) if film.path else ""
                    if normalized_film_path.startswith(mount_path) and os.path.isdir(normalized_film_path):
                        film_dir = normalized_film_path
                        break
                    # Translate remote path to mount path
                    if film.path and film.path.rstrip("/").startswith(remote_path):
                        film_dir = film.path.rstrip("/").replace(remote_path, mount_path.rstrip("/"), 1)
                        break

        if not os.path.isdir(film_dir):
            raise ValueError(f"Film directory not found: {film_dir}")

        dest_path = os.path.join(film_dir, dest_filename)
        with open(dest_path, "wb") as f:
            f.write(content)

        logger.info("Installed subtitle locally", path=dest_path, film_id=film.id)
        return dest_path