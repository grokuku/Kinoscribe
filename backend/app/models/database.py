"""
SQLAlchemy ORM models — the persistent representation of our domain.
Independent from the Pydantic API schemas (schemas.py) to keep
concerns separated (API contract vs DB storage).
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    Column, String, Integer, Float, Text, ForeignKey, Enum as SAEnum,
    DateTime, JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, DeclarativeBase
import enum


# ─── Base ────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ─── Enums ───────────────────────────────────────────────────────────────────

class GenderEnum(str, enum.Enum):
    male = "male"
    female = "female"
    neutral = "neutral"
    unknown = "unknown"


class TaskStatusEnum(str, enum.Enum):
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


class TaskTypeEnum(str, enum.Enum):
    translation = "translation"
    improve = "improve"
    sync = "sync"
    transcription = "transcription"
    extract_subs = "extract_subs"
    extract_audio = "extract_audio"
    analyze = "analyze"


class SubtitleFormatEnum(str, enum.Enum):
    srt = "srt"
    vtt = "vtt"
    ass = "ass"


# ─── Models ──────────────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Film(Base):
    __tablename__ = "films"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String, index=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    director: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_language: Mapped[str] = mapped_column(String, default="en")
    target_language: Mapped[str] = mapped_column(String, default="fr")

    # Raw NFO / external metadata stored as JSON blob
    raw_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Context analysis result
    lore_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    analysis_status: Mapped[str] = mapped_column(String, default="idle")  # idle | analyzing | failed

    # Library / file system integration
    library_id: Mapped[Optional[str]] = mapped_column(ForeignKey("libraries.id", ondelete="SET NULL"), nullable=True)
    path: Mapped[Optional[str]] = mapped_column(String, nullable=True)            # chemin absolu du dossier du film
    video_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)      # chemin du fichier vidéo
    poster_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)     # chemin du poster
    has_existing_subs: Mapped[bool] = mapped_column(default=False)                # a des sous-titres existants

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    # Relationships
    characters: Mapped[List["Character"]] = relationship(
        back_populates="film", cascade="all, delete-orphan", lazy="selectin"
    )
    glossary_entries: Mapped[List["GlossaryEntry"]] = relationship(
        back_populates="film", cascade="all, delete-orphan", lazy="selectin"
    )
    tasks: Mapped[List["TranslationTask"]] = relationship(
        back_populates="film", cascade="all, delete-orphan", lazy="selectin"
    )


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    film_id: Mapped[str] = mapped_column(ForeignKey("films.id"))
    name: Mapped[str] = mapped_column(String)
    gender: Mapped[str] = mapped_column(String, default="unknown")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Additional structured metadata (source of gender info, confidence, etc.)
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    film: Mapped["Film"] = relationship(back_populates="characters")


class GlossaryEntry(Base):
    """Film-specific glossary built automatically during analysis.
    Stores terms (names, slang, neologisms) and their accepted translations."""
    __tablename__ = "glossary_entries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    film_id: Mapped[str] = mapped_column(ForeignKey("films.id"))
    source_term: Mapped[str] = mapped_column(String)
    target_term: Mapped[str] = mapped_column(String, default="")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    film: Mapped["Film"] = relationship(back_populates="glossary_entries")


class TranslationTask(Base):
    __tablename__ = "translation_tasks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    film_id: Mapped[str] = mapped_column(ForeignKey("films.id"))

    # Task type: translation, improve, sync, transcription, extract_subs, extract_audio, analyze
    task_type: Mapped[str] = mapped_column(String, default="translation")

    # Source subtitle info
    source_filename: Mapped[str] = mapped_column(String)
    source_format: Mapped[str] = mapped_column(String, default="srt")
    source_path: Mapped[str] = mapped_column(String, default="")
    source_language: Mapped[str] = mapped_column(String, default="en")

    # Target subtitle info (filled on completion)
    target_filename: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    target_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Status
    status: Mapped[str] = mapped_column(String, default="pending")
    progress_pct: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Context produced during analysis (stored for reuse / debugging)
    lore_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    film: Mapped["Film"] = relationship(back_populates="tasks")


# ─── Settings (key-value store) ───────────────────────────────────────────

class Setting(Base):
    """
    Application-wide settings stored as key-value pairs.
    On first boot, seeded from env vars / defaults.
    UI-editable — the single source of truth at runtime.
    """
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # UI hint: 'url' | 'number' | 'text' | 'select' | 'password'
    input_type: Mapped[str] = mapped_column(String, default="text")
    # For select inputs: comma-separated options (e.g. "en,fr,es,de")
    options: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Grouping in the UI
    category: Mapped[str] = mapped_column(String, default="general")


class Library(Base):
    """A library is a named collection of film directories (like Jellyfin libraries)."""
    __tablename__ = "libraries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    # Relationships
    sources: Mapped[List["LibrarySource"]] = relationship(
        back_populates="library", cascade="all, delete-orphan", lazy="selectin"
    )


class LibrarySource(Base):
    """A folder that belongs to a library. Can be local or remote (SSH, etc.)."""
    __tablename__ = "library_sources"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    library_id: Mapped[str] = mapped_column(ForeignKey("libraries.id"))

    # Source type: 'local', 'ssh' (extensible: 'smb', 'nfs' in future)
    source_type: Mapped[str] = mapped_column(String, default="local")

    # ── Local source ──
    path: Mapped[str] = mapped_column(String, nullable=False)

    # ── SSH source ──
    ssh_host: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ssh_port: Mapped[int] = mapped_column(Integer, default=22, nullable=True)
    ssh_username: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ssh_auth_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # 'key' | 'password'
    ssh_private_key_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ssh_password: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # stored encrypted in future
    ssh_remote_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # ── Common ──
    enabled: Mapped[bool] = mapped_column(default=True)
    scan_depth: Mapped[int] = mapped_column(Integer, default=2)  # 1=flat, 2=one level of subdirs (Jellyfin)
    last_scan_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    scan_status: Mapped[str] = mapped_column(String, default="idle")  # 'idle' | 'scanning' | 'error'
    scan_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    # Relationship
    library: Mapped["Library"] = relationship(back_populates="sources")