"""
Mount service — manages SSHFS and CIFS mounts inside the container.

Mounts remote filesystems (SSH/SFTP, SMB/CIFS) to local paths
so that ffprobe, ffmpeg, and video streaming work natively on remote files.

Mounting is automatic and transparent:
  - On source creation: auto-mount immediately
  - On scan: auto-mount if not already mounted
  - On source deletion: auto-unmount
  - On boot: auto-mount all enabled remote sources
  - On shutdown: unmount all

Mount layout:
  /app/data/mounts/
    {source_id}/
      → mounted remote directory (sshfs/cifs)
"""

import asyncio
import os
import shutil
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.core.crypto import decrypt
from app.core.logging import get_logger

logger = get_logger(__name__)

# ─── Configuration ─────────────────────────────────────────────────────────

MOUNT_BASE = "/app/data/mounts"


def mount_base_dir() -> str:
    """Base directory for all mounts. Always returns an absolute normalized path."""
    custom = getattr(settings, 'mount_base_dir', '') or ''
    base = custom.strip() if custom.strip() else MOUNT_BASE
    base = os.path.normpath(base)
    os.makedirs(base, exist_ok=True)
    return base


def mount_point(source_id: str) -> str:
    """Full mount point path for a source: {mount_base_dir}/{source_id}/"""
    mp = os.path.normpath(os.path.join(mount_base_dir(), source_id))
    return mp


# ─── Auto-mount integration ────────────────────────────────────────────────

async def ensure_mounted(source, session=None) -> dict:
    """
    Ensure a source is mounted. If already mounted, return success.
    If not, mount it and update the DB.

    This is the main entry point for automatic mounting.
    Called by the scanner before scanning, and by film endpoints.
    """
    if source.source_type == "local":
        return {"mounted": True, "mount_point": source.path, "error": None}

    # Check existing mount status
    mp = getattr(source, 'mount_point', None) or mount_point(source.id)

    # Verify the mount is actually alive (not stale)
    if await _is_mounted(mp) and await _mount_is_alive(mp):
        logger.debug("Source already mounted and alive", source_id=source.id, path=mp)
        return {"mounted": True, "mount_point": mp, "error": None}

    # Mount needed
    logger.info("Auto-mounting source", source_id=source.id, type=source.source_type)
    result = await mount_source(source)

    # Update DB if session provided
    if session:
        if result.get("mounted"):
            source.mount_status = "mounted"
            source.mount_point = result["mount_point"]
            source.mount_error = None
        else:
            source.mount_status = "error"
            source.mount_point = None
            source.mount_error = result.get("error", "Unknown error")
        await session.commit()

    return result


# ─── Mount management ─────────────────────────────────────────────────────

async def mount_source(source) -> dict:
    """
    Mount a library source to a local path.
    Supports SSH (sshfs) and SMB/CIFS.

    Returns dict with: mounted (bool), mount_point (str), error (str|None)
    """
    mp = mount_point(source.id)

    if source.source_type == "local":
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

    # Ensure /etc/fuse.conf allows allow_other
    _ensure_fuse_config()

    # Ensure mount point exists
    os.makedirs(mount_point_path, exist_ok=True)

    # If already mounted and alive, skip
    if await _is_mounted(mount_point_path) and await _mount_is_alive(mount_point_path):
        logger.info("SSHFS already mounted and alive, skipping", path=mount_point_path)
        return {"mounted": True, "mount_point": mount_point_path, "error": None}

    # If stale mount exists, try to clean it up first
    if await _is_mounted(mount_point_path):
        logger.info("Stale SSHFS mount detected, cleaning up", path=mount_point_path)
        await unmount_path(mount_point_path)
        # Give it a moment
        await asyncio.sleep(0.5)

    host = source.ssh_host
    port = source.ssh_port or 22
    username = source.ssh_username or "root"
    remote_path = source.ssh_remote_path or source.path
    remote_path = remote_path.rstrip("/")

    # Build sshfs command
    cmd = [
        "sshfs",
        f"{username}@{host}:{remote_path}",
        mount_point_path,
        "-o", f"Port={port}",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "allow_other",
        "-o", "reconnect",
        "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=3",
        "-o", "auto_unmount",
        "-o", "follow_symlinks",
        "-o", "noatime",
    ]

    # Authentication
    if source.ssh_auth_type == "password" and source.ssh_password:
        password = decrypt(source.ssh_password)
        if shutil.which("sshpass"):
            cmd = ["sshpass", "-p", password] + cmd
        else:
            return {"mounted": False, "mount_point": None, "error": "sshpass not installed — needed for password auth"}
    elif source.ssh_auth_type == "key" and source.ssh_private_key_path:
        key_path = source.ssh_private_key_path
        if os.path.isfile(key_path):
            cmd.extend(["-o", f"IdentityFile={key_path}"])
        else:
            return {"mounted": False, "mount_point": None, "error": f"SSH key not found: {key_path}"}

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
            logger.error("SSHFS mount failed", error=err_msg)
            return {"mounted": False, "mount_point": None, "error": f"sshfs failed: {err_msg[:300]}"}

        # Verify mount by trying to list contents
        if await _mount_is_alive(mount_point_path):
            logger.info("SSHFS mounted successfully", path=mount_point_path)
            return {"mounted": True, "mount_point": mount_point_path, "error": None}
        else:
            # Mount exists but can't access — might need a moment
            await asyncio.sleep(1)
            if await _mount_is_alive(mount_point_path):
                logger.info("SSHFS mounted successfully (after delay)", path=mount_point_path)
                return {"mounted": True, "mount_point": mount_point_path, "error": None}
            return {"mounted": False, "mount_point": None, "error": "Mount succeeded but directory is not accessible (permission issue or empty remote?)"}

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

    if await _is_mounted(mount_point_path) and await _mount_is_alive(mount_point_path):
        logger.info("CIFS already mounted and alive, skipping", path=mount_point_path)
        return {"mounted": True, "mount_point": mount_point_path, "error": None}

    if await _is_mounted(mount_point_path):
        logger.info("Stale CIFS mount detected, cleaning up", path=mount_point_path)
        await unmount_path(mount_point_path)
        await asyncio.sleep(0.5)

    unc_path = source.path  # e.g. //192.168.1.100/Films
    username = source.ssh_username or "guest"
    password = decrypt(source.ssh_password) if source.ssh_password else ""

    opts = [
        f"username={username}",
        f"password={password}",
        "vers=3.0",
        "iocharset=utf8",
        "ro",
        "nofail",
    ]

    if source.ssh_port and source.ssh_port != 445:
        opts.append(f"port={source.ssh_port}")

    cmd = ["mount.cifs", unc_path, mount_point_path, "-o", ",".join(opts)]

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
            # Try vers=2.0 fallback
            opts_fallback = [o for o in opts if not o.startswith("vers=")]
            opts_fallback.append("vers=2.0")
            cmd2 = ["mount.cifs", unc_path, mount_point_path, "-o", ",".join(opts_fallback)]
            proc2 = await asyncio.create_subprocess_exec(
                *cmd2,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout2, stderr2 = await asyncio.wait_for(proc2.communicate(), timeout=30)
            if proc2.returncode != 0:
                err_msg2 = stderr2.decode("utf-8", errors="replace").strip()
                return {"mounted": False, "mount_point": None, "error": f"CIFS mount failed: {err_msg2[:300]}"}

        if await _mount_is_alive(mount_point_path):
            logger.info("CIFS mounted successfully", path=mount_point_path)
            return {"mounted": True, "mount_point": mount_point_path, "error": None}
        else:
            return {"mounted": False, "mount_point": None, "error": "CIFS mount succeeded but directory is not accessible"}

    except asyncio.TimeoutError:
        return {"mounted": False, "mount_point": None, "error": "CIFS mount timed out (30s)"}
    except Exception as e:
        logger.error("CIFS mount exception", error=str(e), exc_info=True)
        return {"mounted": False, "mount_point": None, "error": str(e)}


async def unmount_source(source) -> dict:
    """Unmount a library source."""
    if source.source_type == "local":
        return {"unmounted": True, "error": None}

    mp = mount_point(source.id)
    return await unmount_path(mp)


async def unmount_path(path: str) -> dict:
    """Unmount a specific path (sshfs or cifs). Always uses normalized path."""
    path = os.path.normpath(path)

    if not await _is_mounted(path):
        # Not mounted — just clean up mount point directory
        if os.path.isdir(path):
            try:
                os.rmdir(path)  # only removes empty dir
            except OSError:
                pass
        return {"unmounted": True, "error": None}

    logger.info("Unmounting", path=path)

    # Try multiple unmount methods
    for cmd_args in [
        ["fusermount", "-uz", path],   # lazy unmount for FUSE (sshfs)
        ["umount", "-l", path],         # lazy unmount (generic)
        ["umount", path],               # regular unmount
    ]:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
            if not await _is_mounted(path):
                # Successfully unmounted — clean up mount point
                try:
                    os.rmdir(path)
                except OSError:
                    pass
                logger.info("Unmounted successfully", path=path, method=cmd_args[0])
                return {"unmounted": True, "error": None}
        except (FileNotFoundError, asyncio.TimeoutError):
            continue
        except Exception as e:
            logger.debug("Unmount method failed", method=cmd_args[0], error=str(e))
            continue

    # Still mounted after all attempts
    if await _is_mounted(path):
        logger.warning("Failed to unmount after all methods", path=path)
        return {"unmounted": False, "error": f"Could not unmount {path} — try restarting the container"}

    try:
        os.rmdir(path)
    except OSError:
        pass
    return {"unmounted": True, "error": None}


# ─── Internal helpers ─────────────────────────────────────────────────────

async def _is_mounted(path: str) -> bool:
    """Check if a path is a mount point by reading /proc/mounts.
    Uses normalized path to match kernel's path representation."""
    path = os.path.normpath(path)
    if not os.path.isdir(path):
        return False

    try:
        with open("/proc/mounts", "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2 and os.path.normpath(parts[1]) == path:
                    return True
    except Exception:
        pass

    # Fallback: findmnt
    try:
        proc = await asyncio.create_subprocess_exec(
            "findmnt", "-n", "-o", "TARGET", "--target", path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        if stdout.strip():
            return True
    except Exception:
        pass

    return False


async def _mount_is_alive(path: str) -> bool:
    """Check if a mount point is actually working (not stale).
    Tries to list the directory. A stale sshfs mount will hang or error."""
    path = os.path.normpath(path)
    try:
        # Use a subprocess with timeout to avoid hanging on stale mounts
        proc = await asyncio.create_subprocess_exec(
            "ls", path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)
        return proc.returncode == 0
    except (asyncio.TimeoutError, Exception):
        # If ls hangs, the mount is stale
        return False


def _ensure_fuse_config():
    """Ensure /etc/fuse.conf has user_allow_other uncommented.
    Required for sshfs -o allow_other to work."""
    fuse_conf = "/etc/fuse.conf"
    try:
        if os.path.isfile(fuse_conf):
            with open(fuse_conf, "r") as f:
                content = f.read()
            if "user_allow_other" not in content:
                with open(fuse_conf, "a") as f:
                    f.write("\nuser_allow_other\n")
                logger.info("Added user_allow_other to /etc/fuse.conf")
            elif "#user_allow_other" in content and "user_allow_other\n" not in content:
                # Uncomment it
                content = content.replace("#user_allow_other", "user_allow_other")
                with open(fuse_conf, "w") as f:
                    f.write(content)
                logger.info("Uncommented user_allow_other in /etc/fuse.conf")
        else:
            with open(fuse_conf, "w") as f:
                f.write("user_allow_other\n")
            logger.info("Created /etc/fuse.conf with user_allow_other")
    except Exception as e:
        logger.warning("Could not configure /etc/fuse.conf", error=str(e))


# ─── Batch operations ───────────────────────────────────────────────────────

async def unmount_all() -> list:
    """Unmount all managed mounts. Called on shutdown."""
    base = mount_base_dir()
    results = []

    if not os.path.isdir(base):
        return results

    # Read /proc/mounts for our base dir (paths are already normalized from kernel)
    try:
        with open("/proc/mounts", "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    mp = os.path.normpath(parts[1])
                    if mp.startswith(base):
                        result = await unmount_path(mp)
                        results.append({"path": mp, **result})
    except Exception as e:
        logger.warning("Failed to read /proc/mounts for unmount-all", error=str(e))

    return results


async def auto_mount_all(session) -> list:
    """Auto-mount all enabled SSH/CIFS sources at boot."""
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
        mount_result = await ensure_mounted(source, session)
        results.append({
            "source_id": source.id,
            "source_type": source.source_type,
            **mount_result,
        })

    return results