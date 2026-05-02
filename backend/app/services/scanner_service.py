"""
Scanner service — discovers films in library source directories.
Supports local paths and SSH/SFTP remote paths.
Parses .nfo files for metadata, detects video files, images, and subtitle files.

Progress is tracked in-memory and queryable for real-time UI updates.
Each film is committed individually so progress is visible during long scans.
"""

import os
import re
import xmltodict
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.core.logging import get_logger
from app.models.database import LibrarySource

logger = get_logger(__name__)

# ─── File patterns ────────────────────────────────────────────────────────────

VIDEO_EXTENSIONS = {'.mkv', '.mp4', '.avi', '.webm', '.mov', '.wmv', '.flv', '.m4v'}
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.tiff', '.bmp', '.webp'}
SUBTITLE_EXTENSIONS = {'.srt', '.vtt', '.ass', '.ssa'}
NFO_EXTENSION = '.nfo'

SUBTITLE_PATTERN = re.compile(
    r'[.\\/]([a-z]{2,3}(?:-[a-zA-Z]{2,4})?)'
    r'(?:\.(sdh|hi|cc))?'
    r'(?:\.(forced))?'
    r'\.(srt|vtt|ass|ssa)$',
    re.IGNORECASE
)

GENDERED_LANGUAGES = {
    'es', 'fr', 'de', 'it', 'pt', 'ru', 'ar', 'he', 'hi',
    'cs', 'pl', 'ro', 'nl', 'sv', 'da', 'no', 'fi',
}


def parse_subtitle_filename(filename: str) -> Dict[str, Any]:
    """Parse a subtitle filename to extract language, SDH, and forced flags."""
    result: Dict[str, Any] = {"language": None, "is_sdh": False, "is_forced": False}
    match = SUBTITLE_PATTERN.search(filename)
    if match:
        result["language"] = match.group(1).lower()
        if match.group(2):
            result["is_sdh"] = True
        if match.group(3):
            result["is_forced"] = True
    else:
        ext = Path(filename).suffix.lower()
        if ext in SUBTITLE_EXTENSIONS:
            result["language"] = "und"
    return result


def is_gendered_language(lang: str) -> bool:
    base = lang.split('-')[0].lower() if lang else ''
    return base in GENDERED_LANGUAGES


def _sanitize_nfo_value(val):
    """Ensure all values in NFO dict are JSON-serializable primitives."""
    if isinstance(val, dict):
        return {str(k): _sanitize_nfo_value(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_sanitize_nfo_value(v) for v in val]
    if isinstance(val, (str, int, float, bool)) or val is None:
        return val
    return str(val)


def parse_nfo_content(xml_content: str) -> Optional[Dict[str, Any]]:
    """Parse NFO XML content and return structured metadata.
    Handles Jellyfin/Kodi NFO quirks: genre/studio/director can be lists,
    values can be OrderedDicts or other non-primitive types.
    """
    try:
        data = xmltodict.parse(xml_content)
        movie = data.get('movie', data.get('tvshow', {}))

        # Normalize actors to a list
        actors = movie.get('actor', []) or []
        if isinstance(actors, dict):
            actors = [actors]
        cast = []
        for actor in actors:
            if isinstance(actor, dict):
                name = str(actor.get('name', actor.get('Name', '')) or '')
                role = str(actor.get('role', actor.get('Role', '')) or '')
                if name:
                    cast.append({"name": name, "role": role})
            elif isinstance(actor, str) and actor.strip():
                cast.append({"name": actor.strip(), "role": ""})

        # Genre/studio/director can be string or list — normalize to string
        _list_fields = {'genre': movie.get('genre', ''),
                        'studio': movie.get('studio', ''),
                        'director': movie.get('director', movie.get('Director', '')) or ''}
        for key, val in list(_list_fields.items()):
            if isinstance(val, list):
                _list_fields[key] = ', '.join(str(v) for v in val)
            else:
                _list_fields[key] = str(val) if val else ''

        result = {
            "title": str(movie.get('title', movie.get('Name', '')) or ''),
            "year": movie.get('year', movie.get('Year')),
            "director": _list_fields['director'],
            "plot": str(movie.get('plot', movie.get('Overview', '')) or ''),
            "cast": cast,
            "rating": movie.get('rating', movie.get('Score')),
            "mpaa": str(movie.get('mpaa', movie.get('ContentRating', '')) or ''),
            "genre": _list_fields['genre'],
            "studio": _list_fields['studio'],
            "tmdbid": str(movie.get('tmdbid', movie.get('TMDbId', '')) or ''),
            "imdb_id": str(movie.get('imdb_id', movie.get('IMDB_ID', '')) or ''),
        }

        # Final pass: ensure all values are JSON-serializable
        result = _sanitize_nfo_value(result)
        return result

    except Exception as e:
        logger.warning("Failed to parse NFO content", error=str(e))
        return None


# ─── In-memory progress tracker ────────────────────────────────────────────────

@dataclass
class ScanProgress:
    """Real-time progress for a library scan. Shared in-memory."""
    library_id: str
    status: str = "idle"  # idle | scanning | completed | error
    total_dirs: int = 0
    scanned_dirs: int = 0
    current_dir: str = ""
    films_found: int = 0
    films_created: int = 0
    films_updated: int = 0
    errors: list = field(default_factory=list)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "library_id": self.library_id,
            "status": self.status,
            "total_dirs": self.total_dirs,
            "scanned_dirs": self.scanned_dirs,
            "current_dir": self.current_dir,
            "films_found": self.films_found,
            "films_created": self.films_created,
            "films_updated": self.films_updated,
            "errors": self.errors[-20:],  # last 20 errors
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


# Global progress dict — keyed by library_id
_scan_progress: Dict[str, ScanProgress] = {}


def get_scan_progress(library_id: str) -> Optional[ScanProgress]:
    return _scan_progress.get(library_id)


def get_all_scan_progress() -> Dict[str, dict]:
    return {lid: p.to_dict() for lid, p in _scan_progress.items()}


# ─── Abstract filesystem interface ────────────────────────────────────────────

class FilesystemProvider(ABC):
    """Abstract interface for filesystem operations. Local, SSH, future: SMB, NFS."""

    @abstractmethod
    async def listdir(self, path: str) -> List[str]: ...

    @abstractmethod
    async def is_dir(self, path: str) -> bool: ...

    @abstractmethod
    async def is_file(self, path: str) -> bool: ...

    @abstractmethod
    async def read_text(self, path: str, encoding: str = 'utf-8') -> Optional[str]: ...

    @abstractmethod
    async def read_bytes(self, path: str) -> Optional[bytes]: ...

    @abstractmethod
    async def exists(self, path: str) -> bool: ...


class LocalFilesystem(FilesystemProvider):
    """Local filesystem provider."""

    async def listdir(self, path: str) -> List[str]:
        try:
            return sorted(os.listdir(path))
        except (PermissionError, FileNotFoundError):
            return []

    async def is_dir(self, path: str) -> bool:
        return os.path.isdir(path)

    async def is_file(self, path: str) -> bool:
        return os.path.isfile(path)

    async def read_text(self, path: str, encoding: str = 'utf-8') -> Optional[str]:
        try:
            with open(path, 'r', encoding=encoding, errors='replace') as f:
                return f.read()
        except (FileNotFoundError, PermissionError):
            return None

    async def read_bytes(self, path: str) -> Optional[bytes]:
        try:
            with open(path, 'rb') as f:
                return f.read()
        except (FileNotFoundError, PermissionError):
            return None

    async def exists(self, path: str) -> bool:
        return os.path.exists(path)


class SSHFilesystem(FilesystemProvider):
    """SSH/SFTP filesystem provider using asyncssh."""

    def __init__(
        self,
        host: str,
        port: int = 22,
        username: str = 'root',
        password: Optional[str] = None,
        private_key_path: Optional[str] = None,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.private_key_path = private_key_path
        self._conn = None
        self._sftp = None

    async def connect(self):
        """Establish SSH connection and open SFTP session."""
        import asyncssh

        kwargs = {
            'host': self.host,
            'port': self.port,
            'username': self.username,
            'known_hosts': None,  # accept all host keys (dev mode)
        }
        if self.private_key_path:
            kwargs['client_keys'] = [self.private_key_path]
        if self.password:
            kwargs['password'] = self.password

        try:
            self._conn = await asyncssh.connect(**kwargs)
            self._sftp = await self._conn.start_sftp_client()
            logger.info("SSH connected", host=self.host, port=self.port, user=self.username)
        except Exception as e:
            logger.error("SSH connection failed", host=self.host, error=str(e))
            raise

    async def disconnect(self):
        """Close SSH connection."""
        if self._sftp:
            self._sftp.exit()
            self._sftp = None
        if self._conn:
            self._conn.close()
            await self._conn.wait_closed()
            self._conn = None
            logger.info("SSH disconnected", host=self.host)

    async def listdir(self, path: str) -> List[str]:
        import asyncssh
        if not self._sftp:
            raise RuntimeError("SFTP not connected")
        try:
            entries = await self._sftp.readdir(path)
            return sorted([e.filename for e in entries])
        except Exception as e:
            logger.warning("SSH listdir failed", path=path, error=str(e))
            return []

    async def is_dir(self, path: str) -> bool:
        import asyncssh
        if not self._sftp:
            raise RuntimeError("SFTP not connected")
        try:
            attr = await self._sftp.stat(path)
            # asyncssh SFTPAttrs has is_dir if we check the permissions
            if hasattr(attr, 'is_dir'):
                return attr.is_dir()
            # Fallback: check if it's a directory by trying readdir
            try:
                await self._sftp.readdir(path)
                return True
            except (asyncssh.SFTPError, asyncssh.SFTPFailure):
                return False
        except Exception:
            return False

    async def is_file(self, path: str) -> bool:
        if not self._sftp:
            raise RuntimeError("SFTP not connected")
        try:
            attr = await self._sftp.stat(path)
            if hasattr(attr, 'is_file'):
                return attr.is_file()
            # If not a dir, assume file
            return not await self.is_dir(path)
        except Exception:
            return False

    async def read_text(self, path: str, encoding: str = 'utf-8') -> Optional[str]:
        import asyncssh
        if not self._sftp:
            raise RuntimeError("SFTP not connected")
        try:
            async with self._sftp.open(path, 'r') as f:
                content = await f.read()
                if isinstance(content, bytes):
                    return content.decode(encoding, errors='replace')
                return str(content)
        except asyncssh.SFTPError:
            return None
        except Exception:
            return None

    async def read_bytes(self, path: str) -> Optional[bytes]:
        import asyncssh
        if not self._sftp:
            raise RuntimeError("SFTP not connected")
        try:
            async with self._sftp.open(path, 'rb') as f:
                content = await f.read()
                return content if isinstance(content, bytes) else content.encode('utf-8')
        except asyncssh.SFTPError:
            return None
        except Exception:
            return None

    async def exists(self, path: str) -> bool:
        if not self._sftp:
            raise RuntimeError("SFTP not connected")
        try:
            await self._sftp.stat(path)
            return True
        except Exception:
            return False


# ─── Directory scanning ────────────────────────────────────────────────────────

async def scan_directory(
    fs: FilesystemProvider,
    dir_path: str,
    scan_depth: int = 2,
    progress: Optional[ScanProgress] = None,
) -> List[Dict[str, Any]]:
    """
    Scan a directory for film folders using any filesystem provider.
    If progress is provided, updates total_dirs before scanning.
    """
    results = []
    if not await fs.exists(dir_path):
        logger.warning("Scan directory does not exist", path=dir_path)
        return results
    if not await fs.is_dir(dir_path):
        logger.warning("Scan path is not a directory", path=dir_path)
        return results

    if scan_depth == 1:
        entry = await _scan_single_directory(fs, dir_path, dir_path)
        if entry and entry.get('video_files'):
            results.append(entry)
    else:
        # Jellyfin-style: list subdirectories first (quick), then scan each
        entries = await fs.listdir(dir_path)
        subdirs = []
        for name in entries:
            if name.startswith('.'):
                continue
            child_path = f"{dir_path.rstrip('/')}/{name}"
            if await fs.is_dir(child_path):
                subdirs.append((name, child_path))

        if progress:
            progress.total_dirs = len(subdirs)

        for idx, (name, child_path) in enumerate(subdirs):
            if progress:
                progress.current_dir = name
                progress.scanned_dirs = idx

            entry = await _scan_single_directory(fs, child_path, child_path)
            if entry and entry.get('video_files'):
                results.append(entry)

        if progress:
            progress.scanned_dirs = len(subdirs)

    return results


def _classify_file(name: str) -> str:
    """Classify a filename by type."""
    ext = Path(name).suffix.lower()
    if ext in VIDEO_EXTENSIONS: return 'video'
    if ext == NFO_EXTENSION: return 'nfo'
    if ext in IMAGE_EXTENSIONS: return 'image'
    if ext in SUBTITLE_EXTENSIONS: return 'subtitle'
    return 'other'


async def _scan_single_directory(
    fs: FilesystemProvider,
    dir_path: str,
    film_dir: str,
) -> Optional[Dict[str, Any]]:
    """Scan a single directory for all relevant files."""
    video_files = []
    nfo_file = None
    images = []
    subtitles = []

    entries = await fs.listdir(dir_path)
    for name in entries:
        full_path = f"{dir_path.rstrip('/')}/{name}"
        if not await fs.is_file(full_path):
            continue

        ftype = _classify_file(name)

        if ftype == 'video':
            video_files.append(full_path)
        elif ftype == 'nfo':
            nfo_file = full_path
        elif ftype == 'image':
            name_lower = Path(name).stem.lower()
            is_poster = any(kw in name_lower for kw in ['poster', 'folder', 'cover', 'thumb'])
            is_fanart = any(kw in name_lower for kw in ['fanart', 'backdrop', 'landscape'])
            if is_poster:
                images.append({'path': full_path, 'type': 'poster'})
            elif is_fanart:
                images.append({'path': full_path, 'type': 'fanart'})
            elif name_lower == Path(dir_path).name.rsplit('/', 1)[-1].lower() or name_lower.startswith('default'):
                images.append({'path': full_path, 'type': 'poster'})
        elif ftype == 'subtitle':
            sub_info = parse_subtitle_filename(name)
            subtitles.append({
                'path': full_path,
                'filename': name,
                'language': sub_info['language'],
                'is_sdh': sub_info['is_sdh'],
                'is_forced': sub_info['is_forced'],
                'is_gendered': is_gendered_language(sub_info['language'] or 'und'),
                'format': Path(name).suffix.lstrip('.'),
            })

    if not video_files:
        return None

    dir_name = dir_path.rstrip('/').rsplit('/', 1)[-1]
    title = dir_name
    year = None
    director = None
    summary = None
    cast = []
    raw_metadata = None

    if nfo_file:
        nfo_content = await fs.read_text(nfo_file)
        if nfo_content:
            nfo_data = parse_nfo_content(nfo_content)
            if nfo_data:
                title = nfo_data.get('title') or title
                year_raw = nfo_data.get('year')
                try:
                    year = int(year_raw) if year_raw else None
                except (ValueError, TypeError):
                    year = None
                director = nfo_data.get('director')
                summary = nfo_data.get('plot')
                cast = nfo_data.get('cast', [])
                raw_metadata = nfo_data

    if not year:
        year_match = re.search(r'\((\d{4})\)', dir_name)
        if year_match:
            year = int(year_match.group(1))

    poster_file = next((img['path'] for img in images if img['type'] == 'poster'), None)

    return {
        'title': title,
        'year': year,
        'director': director,
        'summary': summary,
        'cast': cast,
        'directory': dir_path,
        'video_files': video_files,
        'nfo_file': nfo_file,
        'poster_file': poster_file,
        'subtitles': subtitles,
        'raw_metadata': raw_metadata,
    }


# ─── SSH connection test ─────────────────────────────────────────────────────

async def test_ssh_connection(
    host: str, port: int = 22, username: str = 'root',
    password: Optional[str] = None, private_key_path: Optional[str] = None,
    remote_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Test SSH connection and optionally list target directory."""
    ssh = SSHFilesystem(host=host, port=port, username=username,
                        password=password, private_key_path=private_key_path)
    try:
        await ssh.connect()
        result: Dict[str, Any] = {"connected": True, "host": host, "username": username}
        if remote_path:
            exists = await ssh.exists(remote_path)
            result["path_exists"] = exists
            if exists:
                result["path_is_dir"] = await ssh.is_dir(remote_path)
                entries = await ssh.listdir(remote_path)
                result["entries"] = entries[:50]
                result["total_entries"] = len(entries)
        return result
    except Exception as e:
        return {"connected": False, "error": str(e)}
    finally:
        await ssh.disconnect()


# ─── Poster caching (SSH posters stored locally) ───────────────────────────────

POSTER_CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'posters')


def _ensure_poster_dir():
    """Ensure the poster cache directory exists."""
    os.makedirs(POSTER_CACHE_DIR, exist_ok=True)


async def cache_poster_locally(
    fs: FilesystemProvider,
    remote_poster_path: str,
    film_id: str,
) -> Optional[str]:
    """Download a poster from remote filesystem and cache it locally.
    Returns the local path where the poster was saved, or None on failure.
    """
    _ensure_poster_dir()
    ext = Path(remote_poster_path).suffix.lower()
    if ext not in {'.jpg', '.jpeg', '.png', '.webp', '.tiff', '.bmp'}:
        ext = '.jpg'  # default extension
    local_path = os.path.join(POSTER_CACHE_DIR, f"{film_id}{ext}")

    content = await fs.read_bytes(remote_poster_path)
    if not content:
        return None

    try:
        with open(local_path, 'wb') as f:
            f.write(content)
        return local_path
    except Exception as e:
        logger.warning("Failed to cache poster", path=remote_poster_path, error=str(e))
        return None


# ─── Scanner service ─────────────────────────────────────────────────────────

class ScannerService:
    """Scans library sources for films and creates/updates entries."""

    async def scan_library(self, library_id: str) -> None:
        """
        Scan all sources in a library and create/update films.
        Runs as a background task. Commits each film individually for real-time progress.
        """
        from app.core.database import async_session
        from app.models.database import Film, Library
        from sqlalchemy import select as sa_select

        progress = ScanProgress(library_id=library_id, status="scanning")
        progress.started_at = datetime.now(timezone.utc).isoformat()
        _scan_progress[library_id] = progress

        async with async_session() as session:
            library = await session.get(Library, library_id)
            if not library:
                progress.status = "error"
                progress.errors.append("Library not found")
                progress.completed_at = datetime.now(timezone.utc).isoformat()
                return

            for source in library.sources:
                if not source.enabled:
                    continue

                # Mark source as scanning
                source.scan_status = "scanning"
                source.scan_error = None
                await session.commit()

                try:
                    if source.source_type == "local":
                        fs = LocalFilesystem()
                    elif source.source_type == "ssh":
                        fs = await self._connect_ssh(source, progress)
                        if fs is None:
                            continue  # error already logged in progress
                    else:
                        progress.errors.append(f"Unsupported source type: {source.source_type}")
                        source.scan_status = "error"
                        source.scan_error = f"Unsupported: {source.source_type}"
                        await session.commit()
                        continue

                    # --- Phase 1: Count directories (quick) ---
                    scan_path = source.ssh_remote_path if source.source_type == "ssh" else source.path
                    if source.scan_depth > 1:
                        top_entries = await fs.listdir(scan_path)
                        subdirs = []
                        for name in top_entries:
                            if name.startswith('.'):
                                continue
                            child = f"{scan_path.rstrip('/')}/{name}"
                            if await fs.is_dir(child):
                                subdirs.append(name)
                        progress.total_dirs = len(subdirs)
                    else:
                        progress.total_dirs = 1

                    # --- Phase 2: Scan each directory, commit each film ---
                    entries = await scan_directory(fs, scan_path, source.scan_depth, progress)

                    progress.films_found = len(entries)
                    progress.current_dir = ""

                    for idx, entry in enumerate(entries):
                        progress.scanned_dirs = idx + 1
                        progress.current_dir = entry.get('title', f"Film {idx+1}")

                        # Use a fresh session for each film to ensure commits are visible
                        async with async_session() as film_session:
                            # Check if film exists by path
                            existing = await film_session.execute(
                                sa_select(Film).where(Film.path == entry['directory'])
                            )
                            film = existing.scalars().first()

                            # For SSH sources, cache poster locally
                            is_ssh = source.source_type == 'ssh'
                            poster_local = None
                            if is_ssh and entry.get('poster_file') and fs is not None:
                                # Need film_id first — create/update film, then cache poster
                                pass  # handled below after commit
                            elif entry.get('poster_file'):
                                poster_local = entry['poster_file']

                            if film:
                                # Update existing film
                                if entry.get('title') and film.title != entry['title']:
                                    film.title = entry['title']
                                if entry.get('year') is not None:
                                    film.year = entry.get('year')
                                if entry.get('director') and film.director != entry.get('director'):
                                    film.director = entry.get('director')
                                if entry.get('summary') and film.summary != entry.get('summary'):
                                    film.summary = entry.get('summary')
                                if entry.get('raw_metadata'):
                                    film.raw_metadata = entry['raw_metadata']
                                if entry.get('video_files'):
                                    film.video_path = entry['video_files'][0]
                                if poster_local:
                                    film.poster_path = poster_local
                                if not film.has_existing_subs and entry.get('subtitles'):
                                    film.has_existing_subs = True
                                if not film.library_id:
                                    film.library_id = library_id
                                progress.films_updated += 1
                            else:
                                film = Film(
                                    title=entry.get('title', Path(entry['directory']).name),
                                    year=entry.get('year'),
                                    director=entry.get('director'),
                                    summary=entry.get('summary'),
                                    source_language='en',
                                    target_language='fr',
                                    library_id=library_id,
                                    path=entry['directory'],
                                    video_path=entry.get('video_files', [None])[0],
                                    raw_metadata=entry.get('raw_metadata'),
                                    poster_path=poster_local or '',
                                    has_existing_subs=bool(entry.get('subtitles')),
                                )
                                film_session.add(film)
                                progress.films_created += 1

                            await film_session.commit()
                            await film_session.refresh(film)

                            # Cache SSH poster after film is committed (has ID now)
                            if is_ssh and entry.get('poster_file') and fs is not None and film.id:
                                cached = await cache_poster_locally(fs, entry['poster_file'], film.id)
                                if cached:
                                    film.poster_path = cached
                                    await film_session.commit()

                        logger.debug("Film processed", title=entry.get('title'), idx=idx+1, total=len(entries))

                    # Mark source done
                    source = await session.get(LibrarySource, source.id)
                    if source:
                        source.scan_status = "idle"
                        source.last_scan_at = datetime.now(timezone.utc)
                        await session.commit()

                    # Disconnect SSH if needed
                    if source.source_type == "ssh" and isinstance(fs, SSHFilesystem):
                        await fs.disconnect()

                except Exception as e:
                    logger.error("Source scan failed", source_id=source.id, error=str(e), exc_info=True)
                    try:
                        source = await session.get(LibrarySource, source.id)
                        if source:
                            source.scan_status = "error"
                            source.scan_error = str(e)[:500]
                            await session.commit()
                    except Exception:
                        pass
                    progress.errors.append(f"{source.path}: {str(e)[:200]}")

        progress.status = "completed"
        progress.completed_at = datetime.now(timezone.utc).isoformat()
        progress.current_dir = ""
        logger.info("Library scan complete", library_id=library_id,
                    found=progress.films_found, created=progress.films_created,
                    updated=progress.films_updated, errors=len(progress.errors))

    async def _connect_ssh(self, source, progress: ScanProgress) -> Optional[SSHFilesystem]:
        """Connect to SSH source. Returns filesystem or None on failure."""
        ssh = SSHFilesystem(
            host=source.ssh_host,
            port=source.ssh_port or 22,
            username=source.ssh_username or 'root',
            password=source.ssh_password if source.ssh_auth_type == 'password' else None,
            private_key_path=source.ssh_private_key_path if source.ssh_auth_type == 'key' else None,
        )
        try:
            await ssh.connect()
            return ssh
        except Exception as e:
            progress.errors.append(f"SSH connection failed ({source.ssh_host}): {str(e)[:200]}")
            logger.error("SSH connection failed", host=source.ssh_host, error=str(e))
            return None


scanner_service = ScannerService()