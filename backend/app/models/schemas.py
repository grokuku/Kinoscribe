"""
Pydantic schemas — API request/response models.
These are the *public contract* of the API, independent from DB models.
"""

from enum import Enum
from typing import Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


# ─── Enums ──────────────────────────────────────────────────────────────────

class Gender(str, Enum):
    male = "male"
    female = "female"
    neutral = "neutral"
    unknown = "unknown"


class TaskStatus(str, Enum):
    pending = "pending"
    analyzing_context = "analyzing_context"
    translating = "translating"
    refining = "refining"
    extracting = "extracting"
    transcribing = "transcribing"
    syncing = "syncing"
    rescanning = "rescanning"
    completed = "completed"
    failed = "failed"


class TaskType(str, Enum):
    translation = "translation"
    improve = "improve"
    sync = "sync"
    transcription = "transcription"
    extract_subs = "extract_subs"
    extract_audio = "extract_audio"
    analyze = "analyze"


class SubtitleFormat(str, Enum):
    srt = "srt"
    vtt = "vtt"
    ass = "ass"


# ─── Characters ──────────────────────────────────────────────────────────────

class CharacterOut(BaseModel):
    name: str
    gender: Gender = Gender.unknown
    description: Optional[str] = None


# ─── Films ──────────────────────────────────────────────────────────────────

class FilmCreate(BaseModel):
    title: str
    year: Optional[int] = None
    director: Optional[str] = None
    summary: Optional[str] = None
    source_language: str = "en"
    target_language: str = "fr"


class FilmOut(BaseModel):
    id: str
    title: str
    year: Optional[int] = None
    director: Optional[str] = None
    summary: Optional[str] = None
    source_language: str
    target_language: str
    characters: List[CharacterOut] = Field(default_factory=list)
    # Analysis
    lore_summary: Optional[str] = None
    analysis_status: str = "idle"  # idle | analyzing | failed
    # NFO / metadata enrichment fields
    genre: Optional[str] = None
    studio: Optional[str] = None
    rating: Optional[float] = None
    imdb_id: Optional[str] = None
    tmdb_id: Optional[str] = None
    # Library / file system integration
    library_id: Optional[str] = None
    path: Optional[str] = None
    video_path: Optional[str] = None
    poster_path: Optional[str] = None
    has_existing_subs: bool = False
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ─── Translation Tasks ───────────────────────────────────────────────────────

class TaskOut(BaseModel):
    id: str
    film_id: str
    task_type: str = "translation"
    status: TaskStatus = TaskStatus.pending
    source_filename: str
    source_format: str = "srt"
    target_filename: Optional[str] = None
    progress_pct: int = 0
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TaskProgressOut(BaseModel):
    """Lightweight status response for polling."""
    id: str
    status: TaskStatus
    progress_pct: int
    error_message: Optional[str] = None


# ─── Glossary ───────────────────────────────────────────────────────────────

class GlossaryEntryOut(BaseModel):
    source_term: str
    target_term: str = ""
    notes: Optional[str] = None


# ─── Settings ───────────────────────────────────────────────────────────────

class SettingOut(BaseModel):
    key: str
    value: str
    description: Optional[str] = None
    input_type: str = "text"
    options: Optional[str] = None
    category: str = "general"

    model_config = {"from_attributes": True}


class SettingsUpdate(BaseModel):
    updates: Dict[str, str] = Field(default_factory=dict)


# ─── Libraries & Sources ──────────────────────────────────────────────────────

class LibrarySourceCreate(BaseModel):
    source_type: str = "local"  # 'local' | 'ssh' | 'smb' | 'cifs'
    path: str  # For local: absolute path. For SSH: display name / identifier. For SMB: //server/share
    ssh_host: Optional[str] = None
    ssh_port: int = 22
    ssh_username: Optional[str] = None
    ssh_auth_type: Optional[str] = None  # 'key' | 'password'
    ssh_private_key_path: Optional[str] = None
    ssh_password: Optional[str] = None
    ssh_remote_path: Optional[str] = None
    enabled: bool = True
    scan_depth: int = 2
    auto_mount: bool = False  # Mount on creation if SSH/SMB


class LibrarySourceOut(BaseModel):
    id: str
    library_id: str
    source_type: str = "local"
    path: str
    # SSH fields
    ssh_host: Optional[str] = None
    ssh_port: Optional[int] = 22
    ssh_username: Optional[str] = None
    ssh_auth_type: Optional[str] = None
    ssh_private_key_path: Optional[str] = None
    ssh_password: Optional[str] = None  # masked in output via model_validator
    ssh_remote_path: Optional[str] = None
    # Common
    enabled: bool = True
    scan_depth: int = 2
    last_scan_at: Optional[datetime] = None
    scan_status: str = "idle"
    scan_error: Optional[str] = None
    # Mount fields
    mount_status: str = "unmounted"  # unmounted | mounted | error | unsupported
    mount_point: Optional[str] = None
    mount_error: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_with_mask(cls, obj):
        """Create output model, masking SSH password if present."""
        data = {
            "id": obj.id,
            "library_id": obj.library_id,
            "source_type": obj.source_type,
            "path": obj.path,
            "ssh_host": obj.ssh_host,
            "ssh_port": obj.ssh_port,
            "ssh_username": obj.ssh_username,
            "ssh_auth_type": obj.ssh_auth_type,
            "ssh_private_key_path": obj.ssh_private_key_path,
            "ssh_password": "********" if obj.ssh_password else None,
            "ssh_remote_path": obj.ssh_remote_path,
            "enabled": obj.enabled,
            "scan_depth": obj.scan_depth,
            "last_scan_at": obj.last_scan_at,
            "scan_status": obj.scan_status,
            "scan_error": obj.scan_error,
            "mount_status": getattr(obj, 'mount_status', 'unsupported'),
            "mount_point": getattr(obj, 'mount_point', None),
            "mount_error": getattr(obj, 'mount_error', None),
            "created_at": obj.created_at,
            "updated_at": obj.updated_at,
        }
        return cls(**data)


class LibraryCreate(BaseModel):
    name: str
    description: Optional[str] = None


class LibraryOut(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    sources: List[LibrarySourceOut] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class LibraryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class ScanResultOut(BaseModel):
    """Result of a library scan."""
    library_id: str
    films_found: int = 0
    films_created: int = 0
    films_updated: int = 0
    errors: List[str] = Field(default_factory=list)


# ─── Generic ────────────────────────────────────────────────────────────────

class MessageResponse(BaseModel):
    message: str


# ─── Existing Subtitles ──────────────────────────────────────────────────────

class ExistingSubtitleOut(BaseModel):
    """A subtitle file found in the film's directory or uploaded."""
    filename: str
    path: str
    language: Optional[str] = None
    is_sdh: bool = False
    is_forced: bool = False
    is_gendered: bool = False
    format: str = "srt"
    source: str = "scanner"  # 'scanner' | 'uploaded' | 'extracted' | 'transcribed'


class StartFromSubtitle(BaseModel):
    """Start a translation from an existing subtitle file."""
    subtitle_path: str
    source_language: Optional[str] = None  # auto-detected if None