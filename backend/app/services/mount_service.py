"""
Mount service — manages SSHFS and CIFS mounts inside the container.

Mounts remote filesystems (SSH/SFTP, SMB/CIFS, NFS) to local paths
so that ffprobe, ffmpeg, and video streaming work natively on remote files.

Lifecycle:
  - On boot: auto-mount all enabled SSH/CIFS sources that have mount enabled.
  - On source creation: optionally mount immediately.
  - On source deletion: unmount and clean up.
  - On shutdown: unmount all.

Mount layout:
  {mount_base_dir}/
    {source_id}/
      → mounted remote directory (sshfs/cifs/nfs)

The mount point path replaces the remote path in all scanner/film operations,
making remote files appear as local.
"""

import asyncio
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.core.crypto import decrypt
from app.core.logging import get_logger

logger = get_logger(__name__)

# ─── Configuration ─────────────────────────────────────────────────────────

def mount_base_dir() -> str:
    """Base directory for all mounts."""
    base = getattr(settings, 'mount_base_dir', '') or os.path.join(
        os.path.dirname(__file__), '..', '..', 'data', 'mounts'
    )
    os.makedirs(base, exist_ok=True)
    return base


def mount_point(source_id: str) -> str:
    """Full mount point path for a source: {mount_base_dir}/{source_id}/"""
    return os.path.join(mount_base_dir(), source_id)


# ─── Mount management ─────────────────────────────────────────────────────

async def mount_source(source) -> dict:
    """
    Mount a library source to a local path.
    Supports SSH (sshfs) and SMB/CIFS.

    Args:
        source: LibrarySource ORM object

    Returns:
        dict with: mounted (bool), mount_point (str), error (str|None)
    """
    mp = mount_point(source.id)

    if source.source_type == "local":
        # Local sources don't need mounting — they're already local
        return {"mounted": True, "mount_point": source.path, "error": None}

    if source.source_type == "ssh":
        return await _mount_sshfs(source, mp)
    elif source.source_type in ("smb", "cifs"):
        return await _mount_cifs(source, mp)
    else:
        return {"mounted": False, "mount_point": None, "error": f"Unsupported source type: {source.source_type}"}


async def _mount_sshfs(source, mount_point_path: str) -> dict:
    """Mount an SSH source using sshfs."""
    if not shutil.which("sshfs"):
        return {"mounted": False, "mount_point": None, "error": "sshfs is not installed in the container"}

    # Ensure mount point exists
    os.makedirs(mount_point_path, exist_ok=True)

    # Check if already mounted
    if await _is_mounted(mount_point_path):
        logger.info("SSHFS already mounted, skipping", path=mount_point_path)
        return {"mounted": True, "mount_point": mount_point_path, "error": None}

    host = source.ssh_host
    port = source.ssh_port or 22
    username = source.ssh_username or "root"
    remote_path = source.ssh_remote_path or source.path
    # Clean up any trailing slashes but keep leading /
    remote_path = remote_path.rstrip("/")

    # Build sshfs command
    cmd = [
        "sshfs",
        f"{username}@{host}:{remote_path}",
        mount_point_path,
        "-o", f"Port={port}",
        "-o", "StrictHostKeyChecking=no",     # Accept new host keys
        "-o", "UserKnownHostsFile=/dev/null",  # Don't save host keys
        "-o", "allow_other",                   # Allow container processes to access
        "-o", "reconnect",                     # Auto-reconnect on disconnect
        "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=3",
        "-o", "auto_unmount",                  # Auto-unmount if connection dies
        "-o", "follow_symlinks",              # Follow symlinks on remote
        "-o", "noatime",                       # Don't update access times (performance)
    ]

    # Authentication
    if source.ssh_auth_type == "password" and source.ssh_password:
        password = decrypt(source.ssh_password)
        # Use sshpass for password-based auth
        if shutil.which("sshpass"):
            cmd = ["sshpass", "-p", password] + cmd
        else:
            # Fallback: write password to temporary pipe
            logger.warning("sshpass not installed, SSH password auth may fail")
            return {"mounted": False, "mount_point": None, "error": "sshpass is required for password-based SSH auth. Install it in the container."}
    elif source.ssh_auth_type == "key" and source.ssh_private_key_path:
        key_path = source.ssh_private_key_path
        if os.path.isfile(key_path):
            cmd.extend(["-o", f"IdentityFile={key_path}"])
        else:
            logger.warning("SSH key not found", path=key_path)

    # Add known_hosts policy from settings
    from app.core.config import settings as app_settings
    kh = app_settings.ssh_known_hosts.strip().lower()
    if kh in ("none", ""):
        cmd.extend(["-o", "StrictHostKeyChecking=no"])
    elif kh == "auto":
        # System known_hosts — we already have no for container
        pass

    logger.info("Mounting SSHFS", host=host, port=port, user=username, remote=remote_path, mount=mount_point_path)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

        if proc.returncode != 0:
            err_msg = stderr.decode("utf-8", errors="replace").strip()
            logger.error("SSHFS mount failed", error=err_msg, cmd=" ".join(cmd))
            return {"mounted": False, "mount_point": None, "error": f"sshfs failed: {err_msg[:300]}"}

        # Verify mount
        if await _is_mounted(mount_point_path):
            logger.info("SSHFS mounted successfully", path=mount_point_path)
            return {"mounted": True, "mount_point": mount_point_path, "error": None}
        else:
            return {"mounted": False, "mount_point": None, "error": "Mount succeeded but path is not accessible"}

    except asyncio.TimeoutError:
        logger.error("SSHFS mount timed out", host=host)
        return {"mounted": False, "mount_point": None, "error": "sshfs mount timed out (30s)"}
    except Exception as e:
        logger.error("SSHFS mount exception", error=str(e), exc_info=True)
        return {"mounted": False, "mount_point": None, "error": str(e)}


async def _mount_cifs(source, mount_point_path: str) -> dict:
    """Mount a SMB/CIFS source using mount.cifs."""
    if not shutil.which("mount.cifs"):
        return {"mounted": False, "mount_point": None, "error": "cifs-utils (mount.cifs) not installed in the container"}

    os.makedirs(mount_point_path, exist_ok=True)

    if await _is_mounted(mount_point_path):
        logger.info("CIFS already mounted, skipping", path=mount_point_path)
        return {"mounted": True, "mount_point": mount_point_path, "error": None}

    # source properties for CIFS:
    #   source.path → //server/share
    #   source.ssh_remote_path → subdirectory within the share (optional)
    #   source.ssh_username → SMB username
    #   source.ssh_password → SMB password (encrypted)
    #   source.ssh_host → SMB server (optional, can be derived from path)

    unc_path = source.path  # e.g. //192.168.1.100/Films
    username = source.ssh_username or "guest"
    password = decrypt(source.ssh_password) if source.ssh_password else ""

    cmd = [
        "mount.cifs",
        unc_path,
        mount_point_path,
        "-o",
    ]

    opts = [
        f"username={username}",
        f"password={password}",
        "vers=3.0",            # Try SMB3 first
        "iocharset=utf8",
        "ro",                   # Read-only mount for safety
        "nofail",
    ]

    if source.ssh_port and source.ssh_port != 445:
        opts.append(f"port={source.ssh_port}")

    cmd.append(",".join(opts))

    logger.info("Mounting CIFS", unc=unc_path, mount=mount_point_path)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

        if proc.returncode != 0:
            err_msg = stderr.decode("utf-8", errors="replace").strip()
            logger.error("CIFS mount failed", error=err_msg)
            # Try vers=2.0 fallback
            opts_fallback = [o for o in opts if not o.startswith("vers=")]
            opts_fallback.append("vers=2.0")
            cmd_fallback = [
                "mount.cifs", unc_path, mount_point_path,
                "-o", ",".join(opts_fallback),
            ]
            proc2 = await asyncio.create_subprocess_exec(
                *cmd_fallback,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout2, stderr2 = await asyncio.wait_for(proc2.communicate(), timeout=30)
            if proc2.returncode != 0:
                err_msg2 = stderr2.decode("utf-8", errors="replace").strip()
                return {"mounted": False, "mount_point": None, "error": f"CIFS mount failed: {err_msg2[:300]}"}

        if await _is_mounted(mount_point_path):
            logger.info("CIFS mounted successfully", path=mount_point_path)
            return {"mounted": True, "mount_point": mount_point_path, "error": None}
        else:
            return {"mounted": False, "mount_point": None, "error": "Mount succeeded but path is not accessible"}

    except asyncio.TimeoutError:
        return {"mounted": False, "mount_point": None, "error": "CIFS mount timed out (30s)"}
    except Exception as e:
        logger.error("CIFS mount exception", error=str(e), exc_info=True)
        return {"mounted": False, "mount_point": None, "error": str(e)}


async def unmount_source(source) -> dict:
    """
    Unmount a library source.
    Returns dict with: unmounted (bool), error (str|None)
    """
    if source.source_type == "local":
        return {"unmounted": True, "error": None}

    mp = mount_point(source.id)
    return await unmount_path(mp)


async def unmount_path(path: str) -> dict:
    """Unmount a specific path (sshfs or cifs)."""
    if not await _is_mounted(path):
        # Remove empty mount point directory
        if os.path.isdir(path):
            try:
                shutil.rmtree(path)
            except Exception:
                pass
        return {"unmounted": True, "error": None}

    logger.info("Unmounting", path=path)

    # Try fusermount -u (for FUSE mounts like sshfs)
    for cmd_args in [
        ["fusermount", "-uz", path],   # lazy unmount for FUSE
        ["umount", "-l", path],         # lazy unmount fallback
    ]:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=15)
            if await _is_mounted(path):
                continue
            # Clean up mount point
            try:
                shutil.rmtree(path)
            except Exception:
                pass
            logger.info("Unmounted successfully", path=path)
            return {"unmounted": True, "error": None}
        except (FileNotFoundError, asyncio.TimeoutError):
            continue

    # Still mounted — force
    if await _is_mounted(path):
        logger.warning("Failed to unmount", path=path)
        return {"unmounted": False, "error": f"Could not unmount {path}"}

    try:
        shutil.rmtree(path)
    except Exception:
        pass
    return {"unmounted": True, "error": None}


async def _is_mounted(path: str) -> bool:
    """Check if a path is a mount point by reading /proc/mounts."""
    if not os.path.isdir(path):
        return False
    try:
        # Check if the path appears in /proc/mounts
        with open("/proc/mounts", "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2 and parts[1] == path:
                    return True
        # Also check with findmnt
        proc = await asyncio.create_subprocess_exec(
            "findmnt", "-n", "-o", "TARGET", "--target", path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        return bool(stdout.strip())
    except Exception:
        # Fallback: try to list directory; if empty and sshfs, probably mounted but empty remote
        try:
            entries = os.listdir(path)
            # If we can list it, the mount is working
            return True if entries else False  # Empty could mean mounted on empty dir
        except OSError:
            return False


async def unmount_all() -> list:
    """Unmount all managed mounts. Called on shutdown."""
    base = mount_base_dir()
    results = []

    if not os.path.isdir(base):
        return results

    # Read /proc/mounts for our base dir
    try:
        with open("/proc/mounts", "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2 and parts[1].startswith(base):
                    result = await unmount_path(parts[1])
                    results.append({"path": parts[1], **result})
    except Exception as e:
        logger.warning("Failed to read /proc/mounts for unmount-all", error=str(e))

    # Also try directory-based cleanup
    try:
        for entry in os.listdir(base):
            mp = os.path.join(base, entry)
            if os.path.isdir(mp):
                result = await unmount_path(mp)
                results.append({"path": mp, **result})
    except Exception:
        pass

    return results


async def auto_mount_all(session) -> list:
    """
    Auto-mount all enabled SSH/CIFS sources at boot.
    Called from the app lifespan startup.

    Args:
        session: AsyncSession for querying sources
    """
    from app.models.database import LibrarySource
    from sqlalchemy import select

    result = await session.execute(
        select(LibrarySource).where(
            LibrarySource.enabled == True,
            LibrarySource.source_type.in_(["ssh", "smb", "cifs"]),
        )
    )
    sources = result.scalars().all()

    results = []
    for source in sources:
        logger.info("Auto-mounting source", source_id=source.id, type=source.source_type, host=getattr(source, 'ssh_host', None))
        mount_result = await mount_source(source)
        results.append({
            "source_id": source.id,
            "source_type": source.source_type,
            **mount_result,
        })

        # Update source with mount info in DB
        if mount_result.get("mounted"):
            source.mount_point = mount_result["mount_point"]
            source.mount_status = "mounted"
        else:
            source.mount_point = None
            source.mount_status = "error"
            source.mount_error = mount_result.get("error", "")
        await session.commit()

    return results