"""
Slide and Script management routes
"""
import uuid
import os
import hashlib
import io
from typing import List, Optional
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from PIL import Image

from app.db import get_db
from app.db.models import (
    Project, ProjectVersion, Slide, SlideScript, SlideAudio,
    ProjectTranslationRules, ScriptSource
)
from app.core.config import settings
from app.core.paths import to_relative_path, to_absolute_path, slide_image_url, slide_audio_url
from app.api.validation import validate_lang_code

router = APIRouter()

# Allowed image types
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}


# === Schemas ===

class SlideResponse(BaseModel):
    id: uuid.UUID
    slide_index: int
    image_url: str  # URL for serving the image (original slide)
    preview_url: Optional[str] = None  # URL for rendered preview with canvas layers
    notes_text: Optional[str]
    slide_hash: Optional[str]

    class Config:
        from_attributes = True


class ScriptResponse(BaseModel):
    id: uuid.UUID
    slide_id: uuid.UUID
    lang: str
    text: str
    source: str
    updated_at: str

    class Config:
        from_attributes = True


class ScriptUpdate(BaseModel):
    text: str


class AudioResponse(BaseModel):
    id: uuid.UUID
    slide_id: uuid.UUID
    lang: str
    voice_id: str
    audio_url: str  # URL for serving the audio
    duration_sec: float

    class Config:
        from_attributes = True


class ReorderSlidesRequest(BaseModel):
    """Request body for reordering slides"""
    slide_ids: List[uuid.UUID]  # List of slide IDs in new order


# === Slides Routes ===

@router.get("/projects/{project_id}/versions/{version_id}/slides", response_model=List[SlideResponse])
async def get_slides(
    project_id: uuid.UUID,
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get all slides for a version"""
    result = await db.execute(
        select(Slide)
        .where(Slide.project_id == project_id)
        .where(Slide.version_id == version_id)
        .order_by(Slide.slide_index)
    )
    slides = result.scalars().all()
    
    return [
        SlideResponse(
            id=s.id,
            slide_index=s.slide_index,
            image_url=slide_image_url(s.image_path),  # Convert to URL
            preview_url=slide_image_url(s.preview_path) if s.preview_path else None,
            notes_text=s.notes_text,
            slide_hash=s.slide_hash,
        )
        for s in slides
    ]


@router.get("/{slide_id}")
async def get_slide(slide_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get slide with all scripts and audio"""
    result = await db.execute(
        select(Slide)
        .where(Slide.id == slide_id)
        .options(selectinload(Slide.scripts), selectinload(Slide.audio_files))
    )
    slide = result.scalar_one_or_none()
    
    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found")
    
    return {
        "id": str(slide.id),
        "slide_index": slide.slide_index,
        "image_url": slide_image_url(slide.image_path),  # URL instead of path
        "preview_url": slide_image_url(slide.preview_path) if slide.preview_path else None,
        "notes_text": slide.notes_text,
        "scripts": [
            {
                "id": str(s.id),
                "lang": s.lang,
                "text": s.text,
                "source": s.source.value,
                "updated_at": s.updated_at.isoformat(),
            }
            for s in slide.scripts
        ],
        "audio_files": [
            {
                "id": str(a.id),
                "lang": a.lang,
                "voice_id": a.voice_id,
                "audio_url": slide_audio_url(a.audio_path),  # URL instead of path
                "duration_sec": a.duration_sec,
                "created_at": a.created_at.isoformat(),
                "script_text_hash": a.script_text_hash,  # Hash of script used for TTS (for sync tracking)
            }
            for a in slide.audio_files
        ],
    }


@router.delete("/{slide_id}")
async def delete_slide(slide_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Delete a slide and all its associated scripts/audio.
    Also reindexes remaining slides to maintain consecutive numbering.
    """
    # Get slide with related data
    result = await db.execute(
        select(Slide)
        .where(Slide.id == slide_id)
        .options(selectinload(Slide.scripts), selectinload(Slide.audio_files))
    )
    slide = result.scalar_one_or_none()
    
    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found")
    
    project_id = slide.project_id
    version_id = slide.version_id
    deleted_index = slide.slide_index
    
    # Delete physical files (image and audio) - convert relative to absolute
    files_deleted = []
    if slide.image_path:
        abs_image_path = to_absolute_path(slide.image_path)
        if abs_image_path.exists():
            try:
                abs_image_path.unlink()
                files_deleted.append(str(abs_image_path))
            except OSError:
                pass  # File may not exist or be locked
    
    for audio in slide.audio_files:
        if audio.audio_path:
            abs_audio_path = to_absolute_path(audio.audio_path)
            if abs_audio_path.exists():
                try:
                    abs_audio_path.unlink()
                    files_deleted.append(str(abs_audio_path))
                except OSError:
                    pass
    
    # Delete the slide (cascade will remove scripts and audio records)
    await db.delete(slide)
    
    # Reindex remaining slides
    result = await db.execute(
        select(Slide)
        .where(Slide.project_id == project_id)
        .where(Slide.version_id == version_id)
        .where(Slide.slide_index > deleted_index)
        .order_by(Slide.slide_index)
    )
    slides_to_reindex = result.scalars().all()
    
    for s in slides_to_reindex:
        s.slide_index -= 1
    
    await db.commit()
    
    return {
        "deleted_id": str(slide_id),
        "deleted_index": deleted_index,
        "files_deleted": len(files_deleted),
        "slides_reindexed": len(slides_to_reindex),
    }


@router.post("/projects/{project_id}/versions/{version_id}/slides/add")
async def add_slide(
    project_id: uuid.UUID,
    version_id: uuid.UUID,
    file: UploadFile = File(...),
    position: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Add a new slide by uploading an image.
    Position is 1-based; if not provided, adds at the end.
    """
    # Validate file type
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid file type. Allowed: PNG, JPEG, WebP"
        )
    
    # Verify version exists
    result = await db.execute(
        select(ProjectVersion)
        .where(ProjectVersion.id == version_id)
        .where(ProjectVersion.project_id == project_id)
    )
    version = result.scalar_one_or_none()
    
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    
    # Get current slides count
    result = await db.execute(
        select(Slide)
        .where(Slide.project_id == project_id)
        .where(Slide.version_id == version_id)
        .order_by(Slide.slide_index)
    )
    existing_slides = result.scalars().all()
    current_count = len(existing_slides)
    
    # Determine insert position (1-based)
    if position is None or position > current_count + 1:
        insert_index = current_count + 1
    else:
        insert_index = max(1, position)
    
    # Shift slides if inserting in middle
    if insert_index <= current_count:
        for slide in existing_slides:
            if slide.slide_index >= insert_index:
                slide.slide_index += 1
    
    # Read uploaded image and normalize to PNG bytes
    content = await file.read()
    try:
        img = Image.open(io.BytesIO(content))
        # Ensure PNG-compatible mode
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA")
        png_buf = io.BytesIO()
        img.save(png_buf, format="PNG")
        png_bytes = png_buf.getvalue()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid image file")
    
    slide_hash = hashlib.sha256(png_bytes).hexdigest()
    
    # Create slides directory (DATA_DIR already points to .../data/projects)
    slides_dir = settings.DATA_DIR / str(project_id) / "versions" / str(version_id) / "slides"
    slides_dir.mkdir(parents=True, exist_ok=True)
    
    # Use a UUID-based filename to avoid collisions when slides are reordered/deleted
    new_slide_id = uuid.uuid4()
    filename = f"slide_{new_slide_id}.png"
    file_path = slides_dir / filename
    file_path.write_bytes(png_bytes)
    
    # Get project for base language to create initial script
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Create slide + scripts with relative path
    relative_image_path = to_relative_path(file_path)
    new_slide = Slide(
        id=new_slide_id,
        project_id=project_id,
        version_id=version_id,
        slide_index=insert_index,
        image_path=relative_image_path,
        notes_text=None,
        slide_hash=slide_hash,
    )
    db.add(new_slide)
    
    # Base language script
    db.add(
        SlideScript(
            slide_id=new_slide_id,
            lang=project.base_language,
            text="",
            source=ScriptSource.MANUAL,
        )
    )
    
    # Other allowed languages (if any)
    for lang in (project.allowed_languages or []):
        if lang != project.base_language:
            db.add(
                SlideScript(
                    slide_id=new_slide_id,
                    lang=lang,
                    text="",
                    source=ScriptSource.MANUAL,
                )
            )
    
    await db.commit()
    
    return {
        "id": str(new_slide_id),
        "slide_index": insert_index,
        "image_url": slide_image_url(relative_image_path),  # Return URL
        "total_slides": current_count + 1,
    }


@router.put("/projects/{project_id}/versions/{version_id}/slides/reorder")
async def reorder_slides(
    project_id: uuid.UUID,
    version_id: uuid.UUID,
    data: ReorderSlidesRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Reorder slides by providing the new order as a list of slide IDs.
    """
    # Verify version exists
    result = await db.execute(
        select(ProjectVersion)
        .where(ProjectVersion.id == version_id)
        .where(ProjectVersion.project_id == project_id)
    )
    version = result.scalar_one_or_none()
    
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    
    # Get all slides for this version
    result = await db.execute(
        select(Slide)
        .where(Slide.project_id == project_id)
        .where(Slide.version_id == version_id)
    )
    slides = {s.id: s for s in result.scalars().all()}
    
    # Validate that all provided IDs exist and belong to this version
    if len(data.slide_ids) != len(slides):
        raise HTTPException(
            status_code=400,
            detail=f"Expected {len(slides)} slide IDs, got {len(data.slide_ids)}"
        )
    
    for slide_id in data.slide_ids:
        if slide_id not in slides:
            raise HTTPException(
                status_code=400,
                detail=f"Slide {slide_id} not found in this version"
            )
    
    # Check for duplicates
    if len(set(data.slide_ids)) != len(data.slide_ids):
        raise HTTPException(status_code=400, detail="Duplicate slide IDs in request")
    
    # Update slide indices (1-based)
    for new_index, slide_id in enumerate(data.slide_ids, start=1):
        slides[slide_id].slide_index = new_index
    
    await db.commit()
    
    return {
        "success": True,
        "new_order": [str(sid) for sid in data.slide_ids],
        "slides_reordered": len(data.slide_ids),
    }


# === Scripts Routes ===

@router.get("/{slide_id}/scripts", response_model=List[ScriptResponse])
async def get_slide_scripts(slide_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get all scripts for a slide"""
    result = await db.execute(
        select(SlideScript).where(SlideScript.slide_id == slide_id)
    )
    scripts = result.scalars().all()
    
    return [
        ScriptResponse(
            id=s.id,
            slide_id=s.slide_id,
            lang=s.lang,
            text=s.text,
            source=s.source.value,
            updated_at=s.updated_at.isoformat(),
        )
        for s in scripts
    ]


@router.patch("/{slide_id}/scripts/{lang}")
async def update_script(
    slide_id: uuid.UUID,
    lang: str,
    data: ScriptUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update script text for a slide/language"""
    # Validate language code
    safe_lang = validate_lang_code(lang)
    
    result = await db.execute(
        select(SlideScript)
        .where(SlideScript.slide_id == slide_id)
        .where(SlideScript.lang == safe_lang)
    )
    script = result.scalar_one_or_none()
    
    if not script:
        # Create new script
        result = await db.execute(select(Slide).where(Slide.id == slide_id))
        slide = result.scalar_one_or_none()
        if not slide:
            raise HTTPException(status_code=404, detail="Slide not found")
        
        script = SlideScript(
            slide_id=slide_id,
            lang=safe_lang,
            text=data.text,
            source=ScriptSource.MANUAL,
        )
        db.add(script)
    else:
        script.text = data.text
        script.source = ScriptSource.MANUAL
    
    await db.commit()
    await db.refresh(script)
    
    return {
        "id": str(script.id),
        "lang": script.lang,
        "text": script.text,
        "source": script.source.value,
        "updated_at": script.updated_at.isoformat(),
    }


# === Language Management ===

@router.post("/projects/{project_id}/versions/{version_id}/languages/add")
async def add_language(
    project_id: uuid.UUID,
    version_id: uuid.UUID,
    lang: str,
    db: AsyncSession = Depends(get_db)
):
    """Add a new language to all slides (creates empty script entries)"""
    # Validate language code against global whitelist
    safe_lang = validate_lang_code(lang)
    
    # Get project to update allowed_languages
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Get all slides
    result = await db.execute(
        select(Slide)
        .where(Slide.project_id == project_id)
        .where(Slide.version_id == version_id)
    )
    slides = result.scalars().all()
    
    if not slides:
        raise HTTPException(status_code=404, detail="No slides found")
    
    # Add language to project.allowed_languages if not already present
    current_allowed = list(project.allowed_languages or [])
    if safe_lang not in current_allowed:
        current_allowed.append(safe_lang)
        project.allowed_languages = current_allowed
    
    # Create script entries for each slide
    created = 0
    for slide in slides:
        # Check if script already exists
        result = await db.execute(
            select(SlideScript)
            .where(SlideScript.slide_id == slide.id)
            .where(SlideScript.lang == safe_lang)
        )
        existing = result.scalar_one_or_none()
        
        if not existing:
            script = SlideScript(
                slide_id=slide.id,
                lang=safe_lang,
                text="",
                source=ScriptSource.MANUAL,
            )
            db.add(script)
            created += 1
    
    await db.commit()
    
    return {
        "lang": safe_lang,
        "slides_count": len(slides),
        "scripts_created": created,
    }


@router.post("/projects/{project_id}/versions/{version_id}/languages/remove")
async def remove_language(
    project_id: uuid.UUID,
    version_id: uuid.UUID,
    lang: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Remove a language from a project/version.
    Deletes slide scripts + generated audio for that language and removes it from project.allowed_languages.
    """
    safe_lang = validate_lang_code(lang)

    # Get project to check base_language + update allowed_languages
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if safe_lang == project.base_language:
        raise HTTPException(status_code=400, detail="Cannot remove base language")

    # Get slide IDs for this version
    result = await db.execute(
        select(Slide.id)
        .where(Slide.project_id == project_id)
        .where(Slide.version_id == version_id)
    )
    slide_ids = [row[0] for row in result.all()]
    if not slide_ids:
        raise HTTPException(status_code=404, detail="No slides found")

    # Delete physical audio files first
    files_deleted = 0
    result = await db.execute(
        select(SlideAudio)
        .where(SlideAudio.slide_id.in_(slide_ids))
        .where(SlideAudio.lang == safe_lang)
    )
    audios = result.scalars().all()
    for audio in audios:
        if audio.audio_path:
            abs_audio_path = to_absolute_path(audio.audio_path)
            if abs_audio_path.exists():
                try:
                    abs_audio_path.unlink()
                    files_deleted += 1
                except OSError:
                    pass

    # Delete DB rows
    audio_delete_result = await db.execute(
        delete(SlideAudio)
        .where(SlideAudio.slide_id.in_(slide_ids))
        .where(SlideAudio.lang == safe_lang)
    )
    scripts_delete_result = await db.execute(
        delete(SlideScript)
        .where(SlideScript.slide_id.in_(slide_ids))
        .where(SlideScript.lang == safe_lang)
    )

    # Remove from allowed_languages if present
    current_allowed = list(project.allowed_languages or [])
    if safe_lang in current_allowed:
        project.allowed_languages = [l for l in current_allowed if l != safe_lang]

    await db.commit()

    return {
        "lang": safe_lang,
        "scripts_deleted": int(getattr(scripts_delete_result, "rowcount", 0) or 0),
        "audio_deleted": int(getattr(audio_delete_result, "rowcount", 0) or 0),
        "audio_files_deleted": files_deleted,
    }


@router.post("/projects/{project_id}/versions/{version_id}/import_notes")
async def import_speaker_notes(
    project_id: uuid.UUID,
    version_id: uuid.UUID,
    lang: str = "en",
    db: AsyncSession = Depends(get_db)
):
    """Import speaker notes from PPTX as scripts for specified language"""
    # Get slides with notes
    result = await db.execute(
        select(Slide)
        .where(Slide.project_id == project_id)
        .where(Slide.version_id == version_id)
        .where(Slide.notes_text.isnot(None))
    )
    slides = result.scalars().all()
    
    imported = 0
    for slide in slides:
        if slide.notes_text:
            # Check if script exists
            result = await db.execute(
                select(SlideScript)
                .where(SlideScript.slide_id == slide.id)
                .where(SlideScript.lang == lang)
            )
            script = result.scalar_one_or_none()
            
            if script:
                script.text = slide.notes_text
                script.source = ScriptSource.IMPORTED_NOTES
            else:
                script = SlideScript(
                    slide_id=slide.id,
                    lang=lang,
                    text=slide.notes_text,
                    source=ScriptSource.IMPORTED_NOTES,
                )
                db.add(script)
            imported += 1
    
    await db.commit()
    
    return {
        "lang": lang,
        "imported_count": imported,
    }


@router.post("/projects/{project_id}/versions/{version_id}/translate")
async def translate_all_slides(
    project_id: uuid.UUID,
    version_id: uuid.UUID,
    target_lang: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Translate all slides from base language to target language.
    Enqueues batch translation job.
    """
    from app.workers.tasks import translate_batch_task
    
    # Validate target language
    safe_target_lang = validate_lang_code(target_lang)
    
    # Get project for base language
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Add target language to project.allowed_languages if not already present
    current_allowed = list(project.allowed_languages or [])
    if safe_target_lang not in current_allowed:
        current_allowed.append(safe_target_lang)
        project.allowed_languages = current_allowed
    
    # Get slide count for progress tracking
    result = await db.execute(
        select(Slide)
        .where(Slide.project_id == project_id)
        .where(Slide.version_id == version_id)
    )
    slides = result.scalars().all()
    slide_count = len(slides)
    
    await db.commit()  # Commit allowed_languages update
    
    # Enqueue translation task
    task = translate_batch_task.delay(
        str(project_id),
        str(version_id),
        project.base_language,
        safe_target_lang
    )
    
    return {
        "task_id": task.id,
        "source_lang": project.base_language,
        "target_lang": safe_target_lang,
        "slide_count": slide_count,
        "status": "queued",
    }


@router.get("/tasks/{task_id}/status")
async def get_task_status(task_id: str):
    """
    Get status of a Celery task (for translation, TTS, etc.)
    """
    from celery.result import AsyncResult
    from app.workers.celery_app import celery_app
    
    result = AsyncResult(task_id, app=celery_app)
    
    response = {
        "task_id": task_id,
        "status": result.state,  # PENDING, STARTED, SUCCESS, FAILURE, etc.
        "ready": result.ready(),
    }
    
    if result.ready():
        if result.successful():
            response["result"] = result.result
        elif result.failed():
            response["error"] = str(result.result)
    
    return response


# === TTS Generation ===

@router.post("/{slide_id}/tts")
async def generate_slide_tts(
    slide_id: uuid.UUID,
    lang: str,
    voice_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Generate TTS audio for a single slide.
    Enqueues Celery job.
    """
    from app.workers.tasks import tts_slide_task
    
    # Get slide
    result = await db.execute(select(Slide).where(Slide.id == slide_id))
    slide = result.scalar_one_or_none()
    
    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found")
    
    # Enqueue TTS task
    task = tts_slide_task.delay(
        str(slide.project_id),
        str(slide.version_id),
        str(slide_id),
        lang,
        voice_id
    )
    
    return {
        "task_id": task.id,
        "slide_id": str(slide_id),
        "lang": lang,
        "status": "queued",
    }


@router.post("/projects/{project_id}/versions/{version_id}/tts")
async def generate_version_tts(
    project_id: uuid.UUID,
    version_id: uuid.UUID,
    lang: str,
    voice_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Generate TTS audio for all slides in a version/language.
    Enqueues batch job.
    """
    from app.workers.tasks import tts_batch_task
    
    # Verify version exists
    result = await db.execute(
        select(ProjectVersion)
        .where(ProjectVersion.id == version_id)
        .where(ProjectVersion.project_id == project_id)
    )
    version = result.scalar_one_or_none()
    
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    
    # Enqueue batch TTS task
    task = tts_batch_task.delay(
        str(project_id),
        str(version_id),
        lang,
        voice_id
    )
    
    return {
        "task_id": task.id,
        "lang": lang,
        "status": "queued",
    }

