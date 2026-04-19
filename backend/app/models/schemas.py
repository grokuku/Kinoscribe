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
    completed = "completed"
    failed = "failed"


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
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ─── Translation Tasks ───────────────────────────────────────────────────────

class TaskOut(BaseModel):
    id: str
    film_id: str
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


# ─── Generic ────────────────────────────────────────────────────────────────

class MessageResponse(BaseModel):
    message: str