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


class MarkerSource(str, Enum):
    """Source of marker creation for audit purposes"""
    MANUAL = "manual"      # User explicitly created marker
    WORDCLICK = "wordclick"  # Created from word selection in UI
    AUTO = "auto"          # Auto-generated during migration


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
    CANCELLED = "cancelled"


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
    assets: Mapped[List["Asset"]] = relationship(back_populates="project", cascade="all, delete-orphan")


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
    preview_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # Rendered preview with canvas layers
    notes_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # From PPT speaker notes
    slide_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    version: Mapped["ProjectVersion"] = relationship(back_populates="slides")
    scripts: Mapped[List["SlideScript"]] = relationship(back_populates="slide", cascade="all, delete-orphan")
    audio_files: Mapped[List["SlideAudio"]] = relationship(back_populates="slide", cascade="all, delete-orphan")
    # Canvas editor relationships
    scene: Mapped[Optional["SlideScene"]] = relationship(back_populates="slide", uselist=False, cascade="all, delete-orphan")
    markers_data: Mapped[List["SlideMarkers"]] = relationship(back_populates="slide", cascade="all, delete-orphan")
    normalized_scripts: Mapped[List["NormalizedScript"]] = relationship(back_populates="slide", cascade="all, delete-orphan")
    global_markers: Mapped[List["GlobalMarker"]] = relationship(back_populates="slide", cascade="all, delete-orphan")


class SlideScript(Base):
    """Script text for a slide in specific language"""
    __tablename__ = "slide_scripts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slide_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("slides.id"), nullable=False)
    lang: Mapped[str] = mapped_column(String(10), nullable=False)  # en, ru, es, etc.
    text: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[ScriptSource] = mapped_column(SQLEnum(ScriptSource), default=ScriptSource.MANUAL)
    translation_meta_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    needs_retranslate: Mapped[bool] = mapped_column(Boolean, default=False)  # Flag for marker migration
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
    script_text_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # Hash of script used for TTS
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
    # Music fade in/out
    music_fade_in_sec: Mapped[float] = mapped_column(Float, default=2.0)
    music_fade_out_sec: Mapped[float] = mapped_column(Float, default=3.0)
    
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


# === CANVAS EDITOR MODELS ===

class AssetType(str, Enum):
    IMAGE = "image"
    BACKGROUND = "background"
    ICON = "icon"


class SlideScene(Base):
    """Canvas scene data for a slide (layers, positions, animations)"""
    __tablename__ = "slide_scenes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slide_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("slides.id", ondelete="CASCADE"), nullable=False, unique=True)
    canvas_width: Mapped[int] = mapped_column(Integer, default=1920)
    canvas_height: Mapped[int] = mapped_column(Integer, default=1080)
    layers: Mapped[list] = mapped_column(JSON, default=list)  # List of SlideLayer objects
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    render_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # Hash for cache
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    slide: Mapped["Slide"] = relationship(back_populates="scene")


class SlideMarkers(Base):
    """Markers for animation triggers (per slide per language)"""
    __tablename__ = "slide_markers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slide_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("slides.id", ondelete="CASCADE"), nullable=False)
    lang: Mapped[str] = mapped_column(String(10), nullable=False)
    markers: Mapped[list] = mapped_column(JSON, default=list)  # List of Marker objects
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    slide: Mapped["Slide"] = relationship(back_populates="markers_data")


class NormalizedScript(Base):
    """Normalized script text with word timings from TTS"""
    __tablename__ = "normalized_scripts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slide_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("slides.id", ondelete="CASCADE"), nullable=False)
    lang: Mapped[str] = mapped_column(String(10), nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    normalized_text: Mapped[str] = mapped_column(Text, default="")
    tokenization_version: Mapped[int] = mapped_column(Integer, default=1)
    word_timings: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # [{charStart, charEnd, startTime, endTime, word}]
    contains_marker_tokens: Mapped[bool] = mapped_column(Boolean, default=False)  # Has ⟦M:uuid⟧ tokens
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    slide: Mapped["Slide"] = relationship(back_populates="normalized_scripts")


class GlobalMarker(Base):
    """
    Global marker for animation triggers (one per slide, independent of language).
    
    Each GlobalMarker has a unique ID that is referenced by:
    - Animation triggers in layers (trigger.markerId)
    - Marker tokens in script text (⟦M:uuid⟧)
    - MarkerPosition records for each language
    """
    __tablename__ = "global_markers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slide_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("slides.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Optional human-readable name
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    slide: Mapped["Slide"] = relationship(back_populates="global_markers")
    positions: Mapped[List["MarkerPosition"]] = relationship(back_populates="marker", cascade="all, delete-orphan")


class MarkerPosition(Base):
    """
    Position and timing of a marker in a specific language.
    
    Each GlobalMarker can have one MarkerPosition per language.
    The position (char_start/end) is relative to the normalized script text.
    The time_seconds is populated after TTS generation.
    """
    __tablename__ = "marker_positions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    marker_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("global_markers.id", ondelete="CASCADE"), nullable=False)
    lang: Mapped[str] = mapped_column(String(10), nullable=False)
    char_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Position in normalized text
    char_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    time_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Populated after TTS
    source: Mapped[MarkerSource] = mapped_column(SQLEnum(MarkerSource), default=MarkerSource.MANUAL)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    marker: Mapped["GlobalMarker"] = relationship(back_populates="positions")


class RenderCache(Base):
    """
    Cache for rendered video segments (EPIC B).
    
    Stores rendered slide segments to avoid re-rendering when the scene hasn't changed.
    Cache key is: slide_id + lang + render_key + fps + resolution + renderer_version
    """
    __tablename__ = "render_cache"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slide_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("slides.id", ondelete="CASCADE"), nullable=False)
    lang: Mapped[str] = mapped_column(String(10), nullable=False)
    render_key: Mapped[str] = mapped_column(String(64), nullable=False)  # Hash of scene content
    fps: Mapped[int] = mapped_column(Integer, default=30)
    width: Mapped[int] = mapped_column(Integer, default=1920)
    height: Mapped[int] = mapped_column(Integer, default=1080)
    renderer_version: Mapped[str] = mapped_column(String(20), default="1.0")
    segment_path: Mapped[str] = mapped_column(String(500), nullable=False)  # Path to cached mp4/webm
    duration_sec: Mapped[float] = mapped_column(Float, nullable=False)
    frame_count: Mapped[int] = mapped_column(Integer, nullable=False)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    render_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # How long render took
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_accessed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Asset(Base):
    """Project assets (images, backgrounds, icons for canvas)"""
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # image, background, icon
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="assets")

