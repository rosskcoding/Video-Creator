"""
Render and export routes
"""
import uuid
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db import get_db
from app.db.models import Project, ProjectVersion, RenderJob, JobType, JobStatus
from app.core.config import settings
from app.core.paths import to_absolute_path
from app.workers.celery_app import celery_app
from app.api.validation import (
    SUPPORTED_LANGUAGES,
    project_allowed_languages,
    validate_lang_code,
    validate_lang_for_project,
    sanitize_filename,
)

router = APIRouter()


# Backwards-compatible alias for callers that only need global validation
def validate_lang(lang: str) -> str:
    """Validate language code against global whitelist"""
    return validate_lang_code(lang)


def _path_to_download_url(path: Optional[str], project_id: str, version_id: str, lang: str) -> Optional[str]:
    """
    Convert absolute file path to relative download URL.
    Returns None if path is None or doesn't match expected pattern.
    """
    if not path:
        return None
    p = Path(path)
    if not p.name:
        return None
    # Return relative download endpoint URL
    return f"/api/render/projects/{project_id}/versions/{version_id}/download/{lang}/{p.name}"


@router.post("/projects/{project_id}/versions/{version_id}/render")
async def render_video(
    project_id: uuid.UUID,
    version_id: uuid.UUID,
    lang: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Start video render for a specific language.
    Enqueues Celery job.
    """
    from app.workers.tasks import render_language_task
    
    # Load project (for per-project language allowlist)
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    project = proj_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Validate language (global + per-project)
    safe_lang = validate_lang_for_project(lang, project)
    
    # Verify version exists
    result = await db.execute(
        select(ProjectVersion)
        .where(ProjectVersion.id == version_id)
        .where(ProjectVersion.project_id == project_id)
    )
    version = result.scalar_one_or_none()
    
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    
    # Create render job record
    job = RenderJob(
        project_id=project_id,
        version_id=version_id,
        lang=safe_lang,
        job_type=JobType.RENDER,
        status=JobStatus.QUEUED,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    
    # Enqueue render task
    # IMPORTANT: set celery task_id == job.id so cancel endpoint can revoke reliably
    task = render_language_task.apply_async(
        args=(str(project_id), str(version_id), safe_lang, str(job.id)),
        task_id=str(job.id),
    )
    
    return {
        "job_id": str(job.id),
        "task_id": task.id,
        "lang": safe_lang,
        "status": "queued",
    }


@router.post("/projects/{project_id}/versions/{version_id}/render_all")
async def render_all_languages(
    project_id: uuid.UUID,
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Start video render for all configured languages.
    """
    from app.workers.tasks import render_language_task
    from app.db.models import SlideScript, Slide

    # Load project (for per-project language allowlist)
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    project = proj_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Verify version exists
    result = await db.execute(
        select(ProjectVersion)
        .where(ProjectVersion.id == version_id)
        .where(ProjectVersion.project_id == project_id)
    )
    version = result.scalar_one_or_none()
    
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    
    # Get all languages with scripts
    result = await db.execute(
        select(SlideScript.lang)
        .join(Slide)
        .where(Slide.version_id == version_id)
        .distinct()
    )
    languages = [row[0] for row in result.all()]
    
    if not languages:
        raise HTTPException(status_code=400, detail="No scripts found for any language")

    # Filter + normalize languages to those enabled on this project
    safe_languages: list[str] = []
    seen: set[str] = set()
    for raw_lang in languages:
        try:
            safe_lang = validate_lang_for_project(raw_lang, project)
        except HTTPException:
            continue
        if safe_lang not in seen:
            safe_languages.append(safe_lang)
            seen.add(safe_lang)

    if not safe_languages:
        raise HTTPException(status_code=400, detail="No enabled languages found for this project")
    
    jobs = []
    for lang in safe_languages:
        # Create job record
        job = RenderJob(
            project_id=project_id,
            version_id=version_id,
            lang=lang,
            job_type=JobType.RENDER,
            status=JobStatus.QUEUED,
        )
        db.add(job)
        await db.flush()
        
        # Enqueue task
        # IMPORTANT: set celery task_id == job.id so cancel endpoint can revoke reliably
        task = render_language_task.apply_async(
            args=(str(project_id), str(version_id), lang, str(job.id)),
            task_id=str(job.id),
        )
        
        jobs.append({
            "job_id": str(job.id),
            "task_id": task.id,
            "lang": lang,
        })
    
    await db.commit()
    
    return {
        "jobs": jobs,
        "languages_count": len(safe_languages),
    }


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get render job status"""
    result = await db.execute(select(RenderJob).where(RenderJob.id == job_id))
    job = result.scalar_one_or_none()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return {
        "id": str(job.id),
        "project_id": str(job.project_id),
        "version_id": str(job.version_id),
        "lang": job.lang,
        "job_type": job.job_type.value,
        "status": job.status.value,
        "progress_pct": job.progress_pct,
        "download_video_url": _path_to_download_url(job.output_video_path, str(job.project_id), str(job.version_id), job.lang),
        "download_srt_url": _path_to_download_url(job.output_srt_path, str(job.project_id), str(job.version_id), job.lang),
        "error_message": job.error_message,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


@router.get("/projects/{project_id}/jobs")
async def list_project_jobs(
    project_id: uuid.UUID,
    limit: int = 20,
    db: AsyncSession = Depends(get_db)
):
    """List recent jobs for a project"""
    result = await db.execute(
        select(RenderJob)
        .where(RenderJob.project_id == project_id)
        .order_by(RenderJob.started_at.desc())
        .limit(limit)
    )
    jobs = result.scalars().all()
    
    return [
        {
            "id": str(j.id),
            "lang": j.lang,
            "job_type": j.job_type.value,
            "status": j.status.value,
            "progress_pct": j.progress_pct,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "finished_at": j.finished_at.isoformat() if j.finished_at else None,
        }
        for j in jobs
    ]


# === All Jobs (Admin) ===

@router.get("/jobs")
async def list_all_jobs(
    limit: int = 50,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """List all jobs across all projects (for admin panel)"""
    query = select(RenderJob).order_by(RenderJob.started_at.desc().nulls_last())
    
    # Filter by status if provided
    if status:
        try:
            status_enum = JobStatus(status)
            query = query.where(RenderJob.status == status_enum)
        except ValueError:
            pass
    
    query = query.limit(limit)
    result = await db.execute(query)
    jobs = result.scalars().all()
    
    # Get project names for display
    project_ids = list(set(j.project_id for j in jobs))
    project_names = {}
    if project_ids:
        proj_result = await db.execute(
            select(Project).where(Project.id.in_(project_ids))
        )
        for p in proj_result.scalars().all():
            project_names[str(p.id)] = p.name
    
    return [
        {
            "id": str(j.id),
            "project_id": str(j.project_id),
            "project_name": project_names.get(str(j.project_id), "Unknown"),
            "version_id": str(j.version_id),
            "lang": j.lang,
            "job_type": j.job_type.value,
            "status": j.status.value,
            "progress_pct": j.progress_pct,
            "error_message": j.error_message,
            "download_video_url": _path_to_download_url(j.output_video_path, str(j.project_id), str(j.version_id), j.lang),
            "download_srt_url": _path_to_download_url(j.output_srt_path, str(j.project_id), str(j.version_id), j.lang),
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "finished_at": j.finished_at.isoformat() if j.finished_at else None,
        }
        for j in jobs
    ]


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Cancel a running or queued job and clean up temporary files"""
    result = await db.execute(select(RenderJob).where(RenderJob.id == job_id))
    job = result.scalar_one_or_none()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Only allow cancelling queued or running jobs
    if job.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot cancel job with status: {job.status.value}"
        )
    
    # Try to revoke celery task
    # Note: This will work for queued tasks, but running tasks may not stop immediately
    try:
        celery_app.control.revoke(str(job_id), terminate=True, signal='SIGTERM')
    except Exception as e:
        # Log error but continue - we'll still mark as cancelled in DB
        pass
    
    # Clean up temporary files created during render
    files_cleaned = 0
    try:
        job_id_str = str(job.id)
        job_tag = job_id_str.replace("-", "")
        version_dir = (
            settings.DATA_DIR / str(job.project_id) / "versions" / str(job.version_id)
        )
        
        # Clean up timeline files for this job
        timelines_dir = version_dir / "timelines"
        if timelines_dir.exists():
            for temp_file in [
                timelines_dir / f"voice_timeline_{job.lang}_{job_tag}.wav",
                timelines_dir / f"final_audio_{job.lang}_{job_tag}.wav",
            ]:
                if temp_file.exists():
                    temp_file.unlink()
                    files_cleaned += 1
        
        # Clean up job-scoped temp exports (do NOT touch final deck_{lang}.*)
        exports_lang_dir = version_dir / "exports" / job.lang
        if exports_lang_dir.exists():
            tmp_mp4_file = exports_lang_dir / f"deck_{job.lang}.{job_tag}.tmp.mp4"
            tmp_srt_file = exports_lang_dir / f"deck_{job.lang}.{job_tag}.tmp.srt"

            for f in [tmp_mp4_file, tmp_srt_file]:
                if f.exists():
                    f.unlink()
                    files_cleaned += 1

            # Render adapter temp directory (clips, intermediate files)
            tmp_dir = exports_lang_dir / f"_tmp_{job_id_str}"
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir)
                files_cleaned += 1
            
            # Remove empty lang directory
            if exports_lang_dir.exists() and not any(exports_lang_dir.iterdir()):
                exports_lang_dir.rmdir()
    except Exception:
        # Continue even if cleanup fails
        pass
    
    # Update job status
    job.status = JobStatus.CANCELLED
    job.error_message = "Cancelled by user"
    job.finished_at = datetime.utcnow()
    await db.commit()
    
    return {
        "id": str(job.id),
        "status": job.status.value,
        "message": "Job has been cancelled",
        "files_cleaned": files_cleaned,
    }


@router.post("/projects/{project_id}/jobs/cancel_all")
async def cancel_all_project_jobs(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Cancel all queued/running jobs for a project and clean up temporary files"""
    # Verify project exists
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Find cancellable jobs
    result = await db.execute(
        select(RenderJob)
        .where(RenderJob.project_id == project_id)
        .where(RenderJob.status.in_((JobStatus.QUEUED, JobStatus.RUNNING)))
    )
    jobs = result.scalars().all()

    now = datetime.utcnow()
    cancelled_ids = []
    total_files_cleaned = 0

    for job in jobs:
        try:
            # task_id == job.id for render tasks
            celery_app.control.revoke(str(job.id), terminate=True, signal="SIGTERM")
        except Exception:
            pass

        # Clean up temporary files for this job
        try:
            job_id_str = str(job.id)
            job_tag = job_id_str.replace("-", "")
            version_dir = (
                settings.DATA_DIR / str(job.project_id) / "versions" / str(job.version_id)
            )
            
            # Clean up timeline files
            timelines_dir = version_dir / "timelines"
            if timelines_dir.exists():
                for temp_file in [
                    timelines_dir / f"voice_timeline_{job.lang}_{job_tag}.wav",
                    timelines_dir / f"final_audio_{job.lang}_{job_tag}.wav",
                ]:
                    if temp_file.exists():
                        temp_file.unlink()
                        total_files_cleaned += 1
            
            # Clean up job-scoped temp exports (do NOT touch final deck_{lang}.*)
            exports_lang_dir = version_dir / "exports" / job.lang
            if exports_lang_dir.exists():
                for f in [
                    exports_lang_dir / f"deck_{job.lang}.{job_tag}.tmp.mp4",
                    exports_lang_dir / f"deck_{job.lang}.{job_tag}.tmp.srt",
                ]:
                    if f.exists():
                        f.unlink()
                        total_files_cleaned += 1

                tmp_dir = exports_lang_dir / f"_tmp_{job_id_str}"
                if tmp_dir.exists():
                    shutil.rmtree(tmp_dir)
                    total_files_cleaned += 1
                
                if exports_lang_dir.exists() and not any(exports_lang_dir.iterdir()):
                    exports_lang_dir.rmdir()
        except Exception:
            pass

        job.status = JobStatus.CANCELLED
        job.error_message = "Cancelled by user (project cancel)"
        job.finished_at = now
        cancelled_ids.append(str(job.id))

    await db.commit()

    return {
        "project_id": str(project_id),
        "cancelled_count": len(cancelled_ids),
        "cancelled_job_ids": cancelled_ids,
        "files_cleaned": total_files_cleaned,
    }


# === Workspace (All Exports) ===

@router.get("/workspace")
async def list_workspace_exports(
    db: AsyncSession = Depends(get_db)
):
    """List all available exports across all projects"""
    from sqlalchemy.orm import selectinload
    
    # Get all projects with their current versions
    result = await db.execute(
        select(Project)
        .options(selectinload(Project.versions))
        .order_by(Project.updated_at.desc())
    )
    projects = result.scalars().all()
    
    workspace_items = []
    
    for project in projects:
        if not project.current_version_id:
            continue

        allowed_langs = project_allowed_languages(project)
        
        # Get current version for PPTX path
        current_version = next(
            (v for v in project.versions if v.id == project.current_version_id), 
            None
        )
        
        # Check PPTX availability
        pptx_file = None
        has_pptx = False
        if current_version and current_version.pptx_asset_path:
            pptx_path = to_absolute_path(current_version.pptx_asset_path)
            if pptx_path.exists():
                has_pptx = True
                pptx_file = pptx_path.name
            
        # Check if exports exist for current version
        exports_dir = (
            settings.DATA_DIR / str(project.id) / "versions" / 
            str(project.current_version_id) / "exports"
        )
        
        if not exports_dir.exists():
            continue
        
        for lang_dir in exports_dir.iterdir():
            if not lang_dir.is_dir():
                continue
            if lang_dir.name not in SUPPORTED_LANGUAGES:
                continue
            if lang_dir.name not in allowed_langs:
                continue
            
            mp4_file = lang_dir / f"deck_{lang_dir.name}.mp4"
            srt_file = lang_dir / f"deck_{lang_dir.name}.srt"
            
            if not mp4_file.exists():
                continue
            
            # Get file info
            mp4_stat = mp4_file.stat()
            
            workspace_items.append({
                "project_id": str(project.id),
                "project_name": project.name,
                "version_id": str(project.current_version_id),
                "lang": lang_dir.name,
                "video_file": mp4_file.name,
                "video_size_mb": round(mp4_stat.st_size / (1024 * 1024), 2),
                "has_srt": srt_file.exists(),
                "has_pptx": has_pptx,
                "pptx_file": pptx_file,
                "created_at": datetime.fromtimestamp(mp4_stat.st_mtime).isoformat(),
            })
    
    # Sort by creation date, newest first
    workspace_items.sort(key=lambda x: x["created_at"], reverse=True)
    
    return {"exports": workspace_items}


@router.delete("/workspace/exports/{project_id}/{version_id}/{lang}")
async def delete_workspace_export(
    project_id: uuid.UUID,
    version_id: uuid.UUID,
    lang: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete an export from workspace"""
    # Load project (for per-project language allowlist)
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    project = proj_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Validate language (global + per-project)
    safe_lang = validate_lang_for_project(lang, project)
    
    # Build exports directory path
    exports_dir = (
        settings.DATA_DIR / str(project_id) / "versions" / 
        str(version_id) / "exports" / safe_lang
    )
    
    if not exports_dir.exists():
        raise HTTPException(status_code=404, detail="Export not found")
    
    # Verify it's within expected directory (security check)
    try:
        exports_dir = exports_dir.resolve()
        expected_base = (settings.DATA_DIR / str(project_id)).resolve()
        if not str(exports_dir).startswith(str(expected_base)):
            raise HTTPException(status_code=400, detail="Invalid path")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid path")
    
    # Delete the language export directory
    try:
        shutil.rmtree(exports_dir)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete: {str(e)}")
    
    return {"status": "deleted", "lang": safe_lang}


# === Exports ===

@router.get("/projects/{project_id}/versions/{version_id}/exports")
async def list_exports(
    project_id: uuid.UUID,
    version_id: uuid.UUID,
    lang: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """List available exports for a version"""
    # Load project (for per-project language allowlist)
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    project = proj_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    allowed_langs = project_allowed_languages(project)

    exports_dir = settings.DATA_DIR / str(project_id) / "versions" / str(version_id) / "exports"
    
    if not exports_dir.exists():
        return {"exports": []}
    
    # Validate lang if provided
    filter_lang = validate_lang_for_project(lang, project) if lang else None
    
    exports = []
    for lang_dir in exports_dir.iterdir():
        if lang_dir.is_dir():
            # Only show directories that match supported languages
            if lang_dir.name not in SUPPORTED_LANGUAGES:
                continue
            if lang_dir.name not in allowed_langs:
                continue
            
            if filter_lang and lang_dir.name != filter_lang:
                continue
            
            export_info = {"lang": lang_dir.name, "files": [], "created_at": None}
            
            mp4_file = lang_dir / f"deck_{lang_dir.name}.mp4"
            srt_file = lang_dir / f"deck_{lang_dir.name}.srt"
            
            if mp4_file.exists():
                mp4_stat = mp4_file.stat()
                export_info["files"].append({
                    "type": "video",
                    "filename": mp4_file.name,
                    "size_mb": round(mp4_stat.st_size / (1024 * 1024), 2),
                })
                # Use video file modification time as export creation time
                export_info["created_at"] = datetime.fromtimestamp(mp4_stat.st_mtime).isoformat()
            
            if srt_file.exists():
                export_info["files"].append({
                    "type": "subtitles",
                    "filename": srt_file.name,
                    "size_kb": round(srt_file.stat().st_size / 1024, 2),
                })
            
            if export_info["files"]:
                exports.append(export_info)
    
    return {"exports": exports}


@router.get("/projects/{project_id}/versions/{version_id}/download/{lang}/{filename}")
async def download_export(
    project_id: uuid.UUID,
    version_id: uuid.UUID,
    lang: str,
    filename: str,
    db: AsyncSession = Depends(get_db),
):
    """Download exported file"""
    # Load project (for per-project language allowlist)
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    project = proj_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Sanitize inputs to prevent path traversal
    safe_lang = validate_lang_for_project(lang, project)
    safe_filename = sanitize_filename(filename)
    
    # Build expected exports directory
    exports_dir = (
        settings.DATA_DIR / str(project_id) / "versions" / str(version_id) / "exports"
    ).resolve()
    
    # Build file path with sanitized components
    file_path = exports_dir / safe_lang / safe_filename
    
    # Resolve to absolute path and verify it's within exports_dir
    resolved_path = file_path.resolve()
    if not resolved_path.is_relative_to(exports_dir):
        raise HTTPException(status_code=400, detail="Invalid file path")
    
    if not resolved_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    # Determine media type
    if safe_filename.endswith(".mp4"):
        media_type = "video/mp4"
    elif safe_filename.endswith(".srt"):
        media_type = "text/plain"
    elif safe_filename.endswith(".vtt"):
        media_type = "text/vtt"
    else:
        media_type = "application/octet-stream"
    
    return FileResponse(
        path=resolved_path,
        media_type=media_type,
        filename=safe_filename,
    )


@router.get("/projects/{project_id}/versions/{version_id}/download-pptx")
async def download_pptx(
    project_id: uuid.UUID,
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Download the original PPTX file for a project version"""
    # Get version
    result = await db.execute(
        select(ProjectVersion).where(ProjectVersion.id == version_id)
    )
    version = result.scalar_one_or_none()
    
    if not version or version.project_id != project_id:
        raise HTTPException(status_code=404, detail="Version not found")
    
    if not version.pptx_asset_path:
        raise HTTPException(status_code=404, detail="PPTX file not found")
    
    # Convert relative DB path to absolute
    pptx_path = to_absolute_path(version.pptx_asset_path)
    
    if not pptx_path.exists():
        raise HTTPException(status_code=404, detail="PPTX file not found on disk")
    
    # Security check - ensure path is within expected data directory
    version_dir = (
        settings.DATA_DIR / str(project_id) / "versions" / str(version_id)
    ).resolve()
    resolved_path = pptx_path.resolve()
    
    if not resolved_path.is_relative_to(version_dir):
        raise HTTPException(status_code=400, detail="Invalid file path")
    
    return FileResponse(
        path=resolved_path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=pptx_path.name,
    )
