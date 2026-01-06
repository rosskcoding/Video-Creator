"""
Database models based on ТЗ specification v1.1
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, List

from sqlalchemy import (
    String, Text, Integer, Float, Boolean, DateTime, ForeignKey, JSON, Enum as SQLEnum
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


# === ENUMS ===

class ProjectStatus(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    RENDERING = "rendering"
    DONE = "done"
    FAILED = "failed"


class ScriptSource(str, Enum):
    MANUAL = "manual"
    IMPORTED_NOTES = "imported_notes"
    TRANSLATED = "translated"


class JobType(str, Enum):
    CONVERT = "convert"
    TTS = "tts"
    RENDER = "render"
    PREVIEW = "preview"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class DuckingStrength(str, Enum):
    LIGHT = "light"
    DEFAULT = "default"
    STRONG = "strong"


class TranslationStyle(str, Enum):
    FORMAL = "formal"
    NEUTRAL = "neutral"
    FRIENDLY = "friendly"


# === MODELS ===

class Project(Base):
    """Main project entity"""
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_language: Mapped[str] = mapped_column(String(10), default="en")
    # Allowed languages for this project (base + targets). If empty/None, only base_language is allowed.
    allowed_languages: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    current_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    versions: Mapped[List["ProjectVersion"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    audio_settings: Mapped[Optional["ProjectAudioSettings"]] = relationship(back_populates="project", uselist=False, cascade="all, delete-orphan")
    translation_rules: Mapped[Optional["ProjectTranslationRules"]] = relationship(back_populates="project", uselist=False, cascade="all, delete-orphan")
    audio_assets: Mapped[List["AudioAsset"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class ProjectVersion(Base):
    """Version snapshot of project (scripts/settings)"""
    __tablename__ = "project_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    pptx_asset_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    slides_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(SQLEnum(ProjectStatus), default=ProjectStatus.DRAFT)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="versions")
    slides: Mapped[List["Slide"]] = relationship(back_populates="version", cascade="all, delete-orphan")
    render_jobs: Mapped[List["RenderJob"]] = relationship(back_populates="version", cascade="all, delete-orphan")


class Slide(Base):
    """Single slide in a version"""
    __tablename__ = "slides"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("project_versions.id"), nullable=False)
    slide_index: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-based
    image_path: Mapped[str] = mapped_column(String(500), nullable=False)
    notes_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # From PPT speaker notes
    slide_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    version: Mapped["ProjectVersion"] = relationship(back_populates="slides")
    scripts: Mapped[List["SlideScript"]] = relationship(back_populates="slide", cascade="all, delete-orphan")
    audio_files: Mapped[List["SlideAudio"]] = relationship(back_populates="slide", cascade="all, delete-orphan")


class SlideScript(Base):
    """Script text for a slide in specific language"""
    __tablename__ = "slide_scripts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slide_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("slides.id"), nullable=False)
    lang: Mapped[str] = mapped_column(String(10), nullable=False)  # en, ru, es, etc.
    text: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[ScriptSource] = mapped_column(SQLEnum(ScriptSource), default=ScriptSource.MANUAL)
    translation_meta_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    slide: Mapped["Slide"] = relationship(back_populates="scripts")


class SlideAudio(Base):
    """Generated TTS audio for a slide in specific language"""
    __tablename__ = "slide_audio"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slide_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("slides.id"), nullable=False)
    lang: Mapped[str] = mapped_column(String(10), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), default="elevenlabs")
    voice_id: Mapped[str] = mapped_column(String(100), nullable=False)
    audio_path: Mapped[str] = mapped_column(String(500), nullable=False)
    duration_sec: Mapped[float] = mapped_column(Float, nullable=False)
    audio_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # For cache validation
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    slide: Mapped["Slide"] = relationship(back_populates="audio_files")


class AudioAsset(Base):
    """Background music and other audio assets"""
    __tablename__ = "audio_assets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(50), default="music")
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    original_format: Mapped[str] = mapped_column(String(10), default="mp3")
    duration_sec: Mapped[float] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="audio_assets")


class TransitionType(str, Enum):
    NONE = "none"
    FADE = "fade"
    CROSSFADE = "crossfade"


class ProjectAudioSettings(Base):
    """Audio mix and render settings per project"""
    __tablename__ = "project_audio_settings"

    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), primary_key=True)
    # Audio settings
    background_music_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    music_asset_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("audio_assets.id"), nullable=True)
    voice_gain_db: Mapped[float] = mapped_column(Float, default=0.0)
    music_gain_db: Mapped[float] = mapped_column(Float, default=-22.0)
    ducking_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    ducking_strength: Mapped[DuckingStrength] = mapped_column(SQLEnum(DuckingStrength), default=DuckingStrength.DEFAULT)
    target_lufs: Mapped[int] = mapped_column(Integer, default=-14)
    voice_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # ElevenLabs voice ID
    
    # Render/timing settings
    pre_padding_sec: Mapped[float] = mapped_column(Float, default=3.0)
    post_padding_sec: Mapped[float] = mapped_column(Float, default=3.0)
    first_slide_hold_sec: Mapped[float] = mapped_column(Float, default=1.0)
    last_slide_hold_sec: Mapped[float] = mapped_column(Float, default=1.0)
    # IMPORTANT: Persist enum *values* (none/fade/crossfade) to match the Postgres enum
    # created by Alembic migration `add_render_settings_to_audio_settings.py`.
    transition_type: Mapped[TransitionType] = mapped_column(
        SQLEnum(
            TransitionType,
            name="transitiontype",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        default=TransitionType.FADE,
    )
    transition_duration_sec: Mapped[float] = mapped_column(Float, default=0.5)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="audio_settings")


class ProjectTranslationRules(Base):
    """Translation glossary and rules per project"""
    __tablename__ = "project_translation_rules"

    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), primary_key=True)
    do_not_translate: Mapped[list] = mapped_column(JSON, default=list)  # ["IFRS", "ESG", ...]
    preferred_translations: Mapped[list] = mapped_column(JSON, default=list)  # [{term, lang, translation}, ...]
    style: Mapped[TranslationStyle] = mapped_column(SQLEnum(TranslationStyle), default=TranslationStyle.FORMAL)
    extra_rules: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="translation_rules")


class RenderJob(Base):
    """Background job tracking"""
    __tablename__ = "render_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("project_versions.id"), nullable=False)
    lang: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    job_type: Mapped[JobType] = mapped_column(SQLEnum(JobType), nullable=False)
    status: Mapped[JobStatus] = mapped_column(SQLEnum(JobStatus), default=JobStatus.QUEUED)
    progress_pct: Mapped[int] = mapped_column(Integer, default=0)
    logs_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    output_video_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    output_srt_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    version: Mapped["ProjectVersion"] = relationship(back_populates="render_jobs")

