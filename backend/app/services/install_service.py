"""
Install service — copy translated subtitles to the film's source directory.

This is the final step: after translation, the user can "install" the SRT
next to the video file in the source directory (local or SSH).
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

    For local films, returns (None, local_path) — we use plain os calls.
    For SSH films, returns (SSHFilesystem, remote_path) — we use SFTP.
    For films without a library, returns (None, film.path).
    """
    if not film.library_id:
        # No library — film was created manually, use local path
        return None, film.path

    # Load the library and its sources
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

    # Find which source contains this film's path
    for source in sources:
        if source.source_type == "local":
            source_path = source.path
            # Check if the film's dir is under this source
            if film.path and film.path.startswith(source_path):
                return None, film.path
        elif source.source_type == "ssh":
            remote_path = source.ssh_remote_path or ""
            # For SSH, the film's local cached path won't match,
            # but we can match by checking the library
            if film.path:
                # The film.path for SSH sources is the local cache path.
                # The remote path is stored differently.
                fs = SSHFilesystem(
                    host=source.ssh_host,
                    port=source.ssh_port or 22,
                    username=source.ssh_username or "root",
                    password=decrypt(source.ssh_password) if source.ssh_auth_type == "password" else None,
                    private_key_path=source.ssh_private_key_path if source.ssh_auth_type == "key" else None,
                )
                await fs.connect()
                # For SSH films, we need to compute the remote path
                # film.path for SSH looks like: data/cache/{source_id}/{relative_path}
                # The remote path is: ssh_remote_path / {relative_path}
                # We need to find the relative part
                return fs, source  # type: ignore

    # Fallback: local path
    return None, film.path


async def install_subtitle_to_source(
    film: Film,
    task_id: str,
    session: AsyncSession,
) -> str:
    """
    Copy the translated subtitle file from data/output/ to the film's
    source directory (next to the video file).

    For local films: plain file copy.
    For SSH films: SFTP upload.

    Returns the destination path.
    """
    # Find the output file
    from app.models.database import TranslationTask

    task = await session.get(TranslationTask, task_id)
    if not task:
        raise ValueError(f"Task {task_id} not found")

    if not task.target_path or not os.path.isfile(task.target_path):
        raise FileNotFoundError(f"Output file not found: {task.target_path}")

    # Read the translated SRT content
    with open(task.target_path, "rb") as f:
        content = f.read()

    # Determine where to install
    if not film.video_path:
        raise ValueError("Film has no video_path — cannot determine install location")

    # Build destination filename: same name as video but with .{lang}.srt
    video_basename = os.path.splitext(os.path.basename(film.video_path))[0]
    dest_filename = f"{video_basename}.{film.target_language}.srt"

    # Try to find the filesystem provider
    fs, source_info = await _get_filesystem_for_film(film, session)

    if isinstance(fs, SSHFilesystem) and isinstance(source_info, LibrarySource):
        # SSH source — upload via SFTP
        # Compute the remote directory from the film's cached path
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
            # Disconnect after use
            await fs.disconnect()
            return remote_dest
        except Exception as e:
            await fs.disconnect()
            raise RuntimeError(f"Failed to write subtitle via SSH: {e}")

    else:
        # Local filesystem — simple copy
        if not film.path or not os.path.isdir(film.path):
            raise ValueError(f"Film directory not found: {film.path}")

        dest_path = os.path.join(film.path, dest_filename)

        # Write the file (overwriting if exists)
        with open(dest_path, "wb") as f:
            f.write(content)

        logger.info("Installed subtitle locally", path=dest_path, film_id=film.id)
        return dest_path