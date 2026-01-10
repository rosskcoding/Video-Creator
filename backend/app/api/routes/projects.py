"""
Project management routes
"""
import uuid
import shutil
import aiofiles
import httpx
from pathlib import Path
from typing import List, Optional
from functools import lru_cache
import time

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import get_db
from app.db.models import (
    Project, ProjectVersion, ProjectAudioSettings, 
    ProjectTranslationRules, AudioAsset, ProjectStatus, Slide,
    DuckingStrength, TranslationStyle, TransitionType
)
from app.core.config import settings
from app.core.paths import to_relative_path
from app.api.validation import validate_lang_code
from app.adapters.media_converter import SUPPORTED_EXTENSIONS

# Cache for ElevenLabs voices (refresh every 5 minutes)
_voices_cache: dict = {"voices": [], "timestamp": 0}
VOICES_CACHE_TTL = 300  # 5 minutes

# File upload limits (in bytes)
MAX_MEDIA_SIZE = 100 * 1024 * 1024  # 100 MB for presentations/PDFs/images
MAX_MUSIC_SIZE = 50 * 1024 * 1024  # 50 MB
CHUNK_SIZE = 1024 * 1024  # 1 MB chunks for streaming

router = APIRouter()


# === Schemas ===

class ProjectCreate(BaseModel):
    name: str
    base_language: str = "en"


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    base_language: Optional[str] = None


class UploadPathRequest(BaseModel):
    path: str
    comment: Optional[str] = None


class AudioSettingsUpdate(BaseModel):
    # Audio settings
    background_music_enabled: Optional[bool] = None
    voice_gain_db: Optional[float] = None
    music_gain_db: Optional[float] = None
    ducking_enabled: Optional[bool] = None
    ducking_strength: Optional[str] = None
    target_lufs: Optional[int] = None
    voice_id: Optional[str] = None  # ElevenLabs voice ID
    music_fade_in_sec: Optional[float] = None
    music_fade_out_sec: Optional[float] = None
    # Render/timing settings
    pre_padding_sec: Optional[float] = None
    post_padding_sec: Optional[float] = None
    first_slide_hold_sec: Optional[float] = None
    last_slide_hold_sec: Optional[float] = None
    transition_type: Optional[str] = None  # none, fade, crossfade
    transition_duration_sec: Optional[float] = None


class TranslationRulesUpdate(BaseModel):
    do_not_translate: Optional[List[str]] = None
    preferred_translations: Optional[List[dict]] = None
    style: Optional[str] = None
    extra_rules: Optional[str] = None


class ProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    base_language: str
    current_version_id: Optional[uuid.UUID]
    created_at: str
    updated_at: str
    # Summary fields
    status: str = "draft"
    slide_count: int = 0
    language_count: int = 0

    class Config:
        from_attributes = True


class VersionResponse(BaseModel):
    id: uuid.UUID
    version_number: int
    status: str
    pptx_asset_path: Optional[str]
    slides_hash: Optional[str]
    comment: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


# === Routes ===

# === ElevenLabs Voices ===

@router.get("/voices")
async def get_elevenlabs_voices():
    """
    Get available voices from ElevenLabs API.
    Results are cached for 5 minutes.
    """
    global _voices_cache

    # Check cache
    if time.time() - _voices_cache["timestamp"] < VOICES_CACHE_TTL and _voices_cache["voices"]:
        return {"voices": _voices_cache["voices"]}

    # Fetch from ElevenLabs
    if not settings.ELEVENLABS_API_KEY:
        # Return default voices if no API key
        return {
            "voices": [
                {
                    "voice_id": settings.DEFAULT_VOICE_ID,
                    "name": "Default Voice",
                    "category": "premade",
                    "labels": {"gender": "female", "accent": "american"},
                    "preview_url": None,
                }
            ]
        }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                "https://api.elevenlabs.io/v1/voices",
                headers={"xi-api-key": settings.ELEVENLABS_API_KEY},
            )
            response.raise_for_status()
            data = response.json()

        voices = []
        for v in data.get("voices", []):
            labels = v.get("labels", {})
            voices.append(
                {
                    "voice_id": v["voice_id"],
                    "name": v["name"],
                    "category": v.get("category", "premade"),
                    "labels": {
                        "gender": labels.get("gender", "unknown"),
                        "accent": labels.get("accent", "unknown"),
                        "age": labels.get("age", "unknown"),
                        "description": labels.get("description", ""),
                        "use_case": labels.get("use_case", ""),
                    },
                    "preview_url": v.get("preview_url"),
                }
            )

        # Sort: premade first, then by name
        voices.sort(key=lambda x: (0 if x["category"] == "premade" else 1, x["name"]))

        # Update cache
        _voices_cache = {"voices": voices, "timestamp": time.time()}

        return {"voices": voices}

    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"ElevenLabs API error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching voices: {str(e)}")

@router.post("", response_model=ProjectResponse)
async def create_project(
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new project"""
    safe_base_lang = validate_lang_code(data.base_language)
    project = Project(
        name=data.name,
        base_language=safe_base_lang,
        # Initialize allowed_languages with base language
        allowed_languages=[safe_base_lang],
    )
    db.add(project)
    await db.flush()  # Flush to get the project ID
    
    # Create default audio settings
    audio_settings = ProjectAudioSettings(project_id=project.id)
    db.add(audio_settings)
    
    # Create default translation rules
    translation_rules = ProjectTranslationRules(project_id=project.id)
    db.add(translation_rules)
    
    await db.commit()
    await db.refresh(project)
    
    return ProjectResponse(
        id=project.id,
        name=project.name,
        base_language=project.base_language,
        current_version_id=project.current_version_id,
        created_at=project.created_at.isoformat(),
        updated_at=project.updated_at.isoformat(),
    )


@router.get("", response_model=List[ProjectResponse])
async def list_projects(db: AsyncSession = Depends(get_db)):
    """
    List all projects with summary info.
    
    Optimized to avoid N+1 queries:
    1. Fetch all projects
    2. Batch load all current versions with slides/scripts in one query
    3. Join data in memory
    """
    # Query 1: Get all projects
    result = await db.execute(select(Project).order_by(Project.updated_at.desc()))
    projects = result.scalars().all()
    
    if not projects:
        return []
    
    # Collect all current_version_ids that need loading
    version_ids = [p.current_version_id for p in projects if p.current_version_id]
    
    # Query 2: Batch load all versions with their slides and scripts
    versions_map: dict[uuid.UUID, ProjectVersion] = {}
    if version_ids:
        ver_result = await db.execute(
            select(ProjectVersion)
            .options(selectinload(ProjectVersion.slides).selectinload(Slide.scripts))
            .where(ProjectVersion.id.in_(version_ids))
        )
        versions = ver_result.scalars().all()
        versions_map = {v.id: v for v in versions}
    
    # Build responses using preloaded data
    responses = []
    for p in projects:
        status = "draft"
        slide_count = 0
        language_count = 1  # At minimum, base language exists
        
        if p.current_version_id and p.current_version_id in versions_map:
            version = versions_map[p.current_version_id]
            status = version.status.value
            slide_count = len(version.slides)
            
            # Count unique languages from scripts
            langs = {p.base_language}
            for slide in version.slides:
                for script in slide.scripts:
                    langs.add(script.lang)
            language_count = len(langs)
        
        responses.append(ProjectResponse(
            id=p.id,
            name=p.name,
            base_language=p.base_language,
            current_version_id=p.current_version_id,
            created_at=p.created_at.isoformat(),
            updated_at=p.updated_at.isoformat(),
            status=status,
            slide_count=slide_count,
            language_count=language_count,
        ))
    
    return responses


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get project by ID"""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Summary fields (same logic as list_projects)
    status = "draft"
    slide_count = 0
    language_count = 1
    if project.current_version_id:
        ver_result = await db.execute(
            select(ProjectVersion)
            .options(selectinload(ProjectVersion.slides).selectinload(Slide.scripts))
            .where(ProjectVersion.id == project.current_version_id)
        )
        version = ver_result.scalar_one_or_none()
        if version:
            status = version.status.value
            slide_count = len(version.slides)
            langs = {project.base_language}
            for slide in version.slides:
                for script in slide.scripts:
                    langs.add(script.lang)
            language_count = len(langs)
    
    return ProjectResponse(
        id=project.id,
        name=project.name,
        base_language=project.base_language,
        current_version_id=project.current_version_id,
        created_at=project.created_at.isoformat(),
        updated_at=project.updated_at.isoformat(),
        status=status,
        slide_count=slide_count,
        language_count=language_count,
    )


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    data: ProjectUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update project settings"""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if data.name is not None:
        project.name = data.name
    if data.base_language is not None:
        safe_base_lang = validate_lang_code(data.base_language)
        project.base_language = safe_base_lang
        # Ensure base language is always part of allowed_languages
        current_allowed = list(project.allowed_languages or [])
        if safe_base_lang not in current_allowed:
            current_allowed.append(safe_base_lang)
            project.allowed_languages = current_allowed
    
    await db.commit()
    await db.refresh(project)
    
    return ProjectResponse(
        id=project.id,
        name=project.name,
        base_language=project.base_language,
        current_version_id=project.current_version_id,
        created_at=project.created_at.isoformat(),
        updated_at=project.updated_at.isoformat(),
    )


@router.delete("/{project_id}")
async def delete_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Delete project and all associated data"""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Delete project files
    project_dir = settings.DATA_DIR / str(project_id)
    if project_dir.exists():
        shutil.rmtree(project_dir)
    
    await db.delete(project)
    await db.commit()
    
    return {"status": "deleted"}


# === Media Upload (PPTX, PDF, Images) ===

@router.post("/{project_id}/upload")
async def upload_media(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    comment: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload presentation file (PPTX, PDF, or image) and create new version.
    
    Supported formats:
    - PPTX/PPT: PowerPoint presentations
    - PDF: Multi-page documents (each page becomes a slide)
    - JPEG/PNG/WEBP: Single image (becomes one slide)
    
    All files must have standard aspect ratios: 16:9, 4:3, 9:16, or 1:1
    """
    # Verify project exists
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Validate file extension
    filename = file.filename or ""
    file_ext = Path(filename).suffix.lower()
    
    if file_ext not in SUPPORTED_EXTENSIONS:
        allowed = ", ".join(SUPPORTED_EXTENSIONS.keys())
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid file type: {file_ext}. Allowed: {allowed}"
        )
    
    # Get next version number
    result = await db.execute(
        select(ProjectVersion)
        .where(ProjectVersion.project_id == project_id)
        .order_by(ProjectVersion.version_number.desc())
        .limit(1)
    )
    latest_version = result.scalar_one_or_none()
    next_version = (latest_version.version_number + 1) if latest_version else 1
    
    # Create version record
    version = ProjectVersion(
        project_id=project_id,
        version_number=next_version,
        status=ProjectStatus.DRAFT,
        comment=comment,
    )
    db.add(version)
    await db.flush()  # Get version ID
    
    # Save file with streaming to avoid memory issues
    version_dir = settings.DATA_DIR / str(project_id) / "versions" / str(version.id)
    version_dir.mkdir(parents=True, exist_ok=True)
    
    # Keep original extension for proper processing
    input_path = version_dir / f"input{file_ext}"
    total_size = 0
    
    async with aiofiles.open(input_path, "wb") as f:
        while chunk := await file.read(CHUNK_SIZE):
            total_size += len(chunk)
            if total_size > MAX_MEDIA_SIZE:
                # Clean up partial file
                await f.close()
                input_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413, 
                    detail=f"File too large. Maximum size is {MAX_MEDIA_SIZE // (1024*1024)} MB"
                )
            await f.write(chunk)
    
    # Store relative path in DB (using existing pptx_asset_path field for any media)
    version.pptx_asset_path = to_relative_path(input_path)
    
    # Update project current version
    project.current_version_id = version.id
    
    await db.commit()
    await db.refresh(version)
    
    return {
        "version_id": str(version.id),
        "version_number": version.version_number,
        "file_type": file_ext,
        "status": "uploaded",
        "message": "File uploaded. Call /convert to process slides."
    }


@router.post("/{project_id}/upload_from_path")
async def upload_media_from_path(
    project_id: uuid.UUID,
    data: UploadPathRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    DEV helper: upload a media file by server-side path instead of browser file picker.

    This exists to support automated E2E flows where the OS file picker cannot be controlled.
    Enabled only when ENV=dev.
    """
    if settings.ENV != "dev":
        raise HTTPException(status_code=404, detail="Not found")

    source_path = Path(data.path).expanduser()
    try:
        source_path = source_path.resolve()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid path")

    if not source_path.exists() or not source_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    file_ext = source_path.suffix.lower()
    if file_ext not in SUPPORTED_EXTENSIONS:
        allowed = ", ".join(SUPPORTED_EXTENSIONS.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: {file_ext}. Allowed: {allowed}",
        )

    try:
        total_size = source_path.stat().st_size
    except Exception:
        raise HTTPException(status_code=400, detail="Cannot read file size")

    if total_size > MAX_MEDIA_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_MEDIA_SIZE // (1024*1024)} MB",
        )

    # Verify project exists
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get next version number
    result = await db.execute(
        select(ProjectVersion)
        .where(ProjectVersion.project_id == project_id)
        .order_by(ProjectVersion.version_number.desc())
        .limit(1)
    )
    latest_version = result.scalar_one_or_none()
    next_version = (latest_version.version_number + 1) if latest_version else 1

    # Create version record
    version = ProjectVersion(
        project_id=project_id,
        version_number=next_version,
        status=ProjectStatus.DRAFT,
        comment=data.comment,
    )
    db.add(version)
    await db.flush()  # Get version ID

    # Save file to version dir
    version_dir = settings.DATA_DIR / str(project_id) / "versions" / str(version.id)
    version_dir.mkdir(parents=True, exist_ok=True)
    input_path = version_dir / f"input{file_ext}"

    try:
        shutil.copyfile(source_path, input_path)
    except Exception as e:
        # Best-effort cleanup
        try:
            input_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to copy file: {e}")

    # Store relative path in DB (using existing pptx_asset_path field for any media)
    version.pptx_asset_path = to_relative_path(input_path)

    # Update project current version
    project.current_version_id = version.id

    await db.commit()
    await db.refresh(version)

    return {
        "version_id": str(version.id),
        "version_number": version.version_number,
        "file_type": file_ext,
        "status": "uploaded",
        "message": "File uploaded. Call /convert to process slides.",
    }


# Legacy endpoint for backward compatibility
@router.post("/{project_id}/upload_pptx")
async def upload_pptx(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    comment: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db)
):
    """Legacy endpoint - redirects to upload_media"""
    return await upload_media(project_id, file, comment, db)


# === Versions ===

@router.get("/{project_id}/versions", response_model=List[VersionResponse])
async def list_versions(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """List all versions of a project"""
    result = await db.execute(
        select(ProjectVersion)
        .where(ProjectVersion.project_id == project_id)
        .order_by(ProjectVersion.version_number.desc())
    )
    versions = result.scalars().all()
    
    return [
        VersionResponse(
            id=v.id,
            version_number=v.version_number,
            status=v.status.value,
            pptx_asset_path=v.pptx_asset_path,
            slides_hash=v.slides_hash,
            comment=v.comment,
            created_at=v.created_at.isoformat(),
        )
        for v in versions
    ]


@router.post("/{project_id}/versions/ensure", response_model=VersionResponse)
async def ensure_current_version(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Ensure the project has a current version suitable for manual slide additions.

    - If `project.current_version_id` exists and is READY, returns it.
    - If missing, creates a new READY version (vN) with no uploaded media.

    This enables workflows like: create project -> enter project -> drag/drop images to add slides.
    """
    # Verify project exists
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # If current version exists, return it (but require READY)
    if project.current_version_id:
        ver_result = await db.execute(
            select(ProjectVersion)
            .where(ProjectVersion.id == project.current_version_id)
            .where(ProjectVersion.project_id == project_id)
        )
        current = ver_result.scalar_one_or_none()
        if current:
            if current.status != ProjectStatus.READY:
                raise HTTPException(
                    status_code=409,
                    detail=f"Current version is not ready (status={current.status.value}). Please wait for conversion to finish.",
                )
            return VersionResponse(
                id=current.id,
                version_number=current.version_number,
                status=current.status.value,
                pptx_asset_path=current.pptx_asset_path,
                slides_hash=current.slides_hash,
                comment=current.comment,
                created_at=current.created_at.isoformat(),
            )

    # Create new READY version
    latest_result = await db.execute(
        select(ProjectVersion)
        .where(ProjectVersion.project_id == project_id)
        .order_by(ProjectVersion.version_number.desc())
        .limit(1)
    )
    latest_version = latest_result.scalar_one_or_none()
    next_version = (latest_version.version_number + 1) if latest_version else 1

    version = ProjectVersion(
        project_id=project_id,
        version_number=next_version,
        status=ProjectStatus.READY,
        comment="Manual slides",
    )
    db.add(version)
    await db.flush()  # get version.id

    project.current_version_id = version.id
    await db.commit()
    await db.refresh(version)

    return VersionResponse(
        id=version.id,
        version_number=version.version_number,
        status=version.status.value,
        pptx_asset_path=version.pptx_asset_path,
        slides_hash=version.slides_hash,
        comment=version.comment,
        created_at=version.created_at.isoformat(),
    )


@router.post("/{project_id}/versions/{version_id}/convert")
async def convert_pptx(
    project_id: uuid.UUID,
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Start PPTX conversion to PNG slides.
    Enqueues a Celery job.
    """
    from app.workers.tasks import convert_pptx_task
    
    # Verify version exists
    result = await db.execute(
        select(ProjectVersion)
        .where(ProjectVersion.id == version_id)
        .where(ProjectVersion.project_id == project_id)
    )
    version = result.scalar_one_or_none()
    
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    
    if not version.pptx_asset_path:
        raise HTTPException(status_code=400, detail="No PPTX file uploaded")
    
    # Enqueue conversion task
    task = convert_pptx_task.delay(str(project_id), str(version_id))
    
    return {
        "task_id": task.id,
        "status": "queued",
        "message": "Conversion job started"
    }


# === Audio Settings ===

@router.get("/{project_id}/audio_settings")
async def get_audio_settings(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get project audio and render settings"""
    result = await db.execute(
        select(ProjectAudioSettings).where(ProjectAudioSettings.project_id == project_id)
    )
    settings_obj = result.scalar_one_or_none()
    
    if not settings_obj:
        raise HTTPException(status_code=404, detail="Audio settings not found")
    
    return {
        # Audio settings
        "background_music_enabled": settings_obj.background_music_enabled,
        "music_asset_id": str(settings_obj.music_asset_id) if settings_obj.music_asset_id else None,
        "voice_gain_db": settings_obj.voice_gain_db,
        "music_gain_db": settings_obj.music_gain_db,
        "ducking_enabled": settings_obj.ducking_enabled,
        "ducking_strength": settings_obj.ducking_strength.value,
        "target_lufs": settings_obj.target_lufs,
        "voice_id": settings_obj.voice_id,
        # Render/timing settings
        "pre_padding_sec": settings_obj.pre_padding_sec,
        "post_padding_sec": settings_obj.post_padding_sec,
        "first_slide_hold_sec": settings_obj.first_slide_hold_sec,
        "last_slide_hold_sec": settings_obj.last_slide_hold_sec,
        "transition_type": settings_obj.transition_type.value,
        "transition_duration_sec": settings_obj.transition_duration_sec,
    }


@router.put("/{project_id}/audio_settings")
async def update_audio_settings(
    project_id: uuid.UUID,
    data: AudioSettingsUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update project audio and render settings"""
    result = await db.execute(
        select(ProjectAudioSettings).where(ProjectAudioSettings.project_id == project_id)
    )
    settings_obj = result.scalar_one_or_none()
    
    if not settings_obj:
        raise HTTPException(status_code=404, detail="Audio settings not found")
    
    # Audio settings
    if data.background_music_enabled is not None:
        settings_obj.background_music_enabled = data.background_music_enabled
    if data.voice_gain_db is not None:
        settings_obj.voice_gain_db = data.voice_gain_db
    if data.music_gain_db is not None:
        settings_obj.music_gain_db = data.music_gain_db
    if data.ducking_enabled is not None:
        settings_obj.ducking_enabled = data.ducking_enabled
    if data.ducking_strength is not None:
        try:
            settings_obj.ducking_strength = DuckingStrength(data.ducking_strength)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid ducking_strength: {data.ducking_strength}")
    if data.target_lufs is not None:
        settings_obj.target_lufs = data.target_lufs
    if data.voice_id is not None:
        settings_obj.voice_id = data.voice_id
    if data.music_fade_in_sec is not None:
        settings_obj.music_fade_in_sec = data.music_fade_in_sec
    if data.music_fade_out_sec is not None:
        settings_obj.music_fade_out_sec = data.music_fade_out_sec
    
    # Render/timing settings
    if data.pre_padding_sec is not None:
        settings_obj.pre_padding_sec = data.pre_padding_sec
    if data.post_padding_sec is not None:
        settings_obj.post_padding_sec = data.post_padding_sec
    if data.first_slide_hold_sec is not None:
        settings_obj.first_slide_hold_sec = data.first_slide_hold_sec
    if data.last_slide_hold_sec is not None:
        settings_obj.last_slide_hold_sec = data.last_slide_hold_sec
    if data.transition_type is not None:
        try:
            settings_obj.transition_type = TransitionType(data.transition_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid transition_type: {data.transition_type}")
    if data.transition_duration_sec is not None:
        settings_obj.transition_duration_sec = data.transition_duration_sec
    
    await db.commit()
    
    return {"status": "updated"}


@router.post("/{project_id}/upload_music")
async def upload_music(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """Upload background music MP3"""
    # Verify project exists
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Validate file type
    if not file.filename.endswith('.mp3'):
        raise HTTPException(status_code=400, detail="Only MP3 files are allowed")
    
    # Save file with streaming to avoid memory issues
    music_dir = settings.DATA_DIR / str(project_id) / "music"
    music_dir.mkdir(parents=True, exist_ok=True)
    
    music_path = music_dir / "corporate.mp3"
    total_size = 0
    
    async with aiofiles.open(music_path, "wb") as f:
        while chunk := await file.read(CHUNK_SIZE):
            total_size += len(chunk)
            if total_size > MAX_MUSIC_SIZE:
                # Clean up partial file
                await f.close()
                music_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413, 
                    detail=f"File too large. Maximum size is {MAX_MUSIC_SIZE // (1024*1024)} MB"
                )
            await f.write(chunk)
    
    # Create or update audio asset with relative path
    relative_music_path = to_relative_path(music_path)
    
    result = await db.execute(
        select(AudioAsset)
        .where(AudioAsset.project_id == project_id)
        .where(AudioAsset.type == "music")
    )
    existing_asset = result.scalar_one_or_none()
    
    if existing_asset:
        existing_asset.file_path = relative_music_path
        asset = existing_asset
    else:
        asset = AudioAsset(
            project_id=project_id,
            type="music",
            file_path=relative_music_path,
            original_format="mp3",
        )
        db.add(asset)
    
    await db.flush()
    
    # Update audio settings to link music
    result = await db.execute(
        select(ProjectAudioSettings).where(ProjectAudioSettings.project_id == project_id)
    )
    settings_obj = result.scalar_one_or_none()
    if settings_obj:
        settings_obj.music_asset_id = asset.id
    
    await db.commit()
    
    return {
        "asset_id": str(asset.id),
        "status": "uploaded"
    }


# === Translation Rules ===

@router.get("/{project_id}/translation_rules")
async def get_translation_rules(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get project translation rules (glossary)"""
    result = await db.execute(
        select(ProjectTranslationRules).where(ProjectTranslationRules.project_id == project_id)
    )
    rules = result.scalar_one_or_none()
    
    if not rules:
        raise HTTPException(status_code=404, detail="Translation rules not found")
    
    return {
        "do_not_translate": rules.do_not_translate,
        "preferred_translations": rules.preferred_translations,
        "style": rules.style.value,
        "extra_rules": rules.extra_rules,
    }


@router.put("/{project_id}/translation_rules")
async def update_translation_rules(
    project_id: uuid.UUID,
    data: TranslationRulesUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update project translation rules (glossary)"""
    result = await db.execute(
        select(ProjectTranslationRules).where(ProjectTranslationRules.project_id == project_id)
    )
    rules = result.scalar_one_or_none()
    
    if not rules:
        raise HTTPException(status_code=404, detail="Translation rules not found")
    
    if data.do_not_translate is not None:
        rules.do_not_translate = data.do_not_translate
    if data.preferred_translations is not None:
        rules.preferred_translations = data.preferred_translations
    if data.style is not None:
        rules.style = TranslationStyle(data.style)
    if data.extra_rules is not None:
        rules.extra_rules = data.extra_rules
    
    await db.commit()
    
    return {"status": "updated"}

