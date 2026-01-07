"""
Celery background tasks

Note on async handling:
Celery workers are sync by default (prefork pool). To safely run async code,
we create a fresh event loop for each task execution. This avoids issues with:
- Stale loops from previous executions
- Conflicts with loops that may exist in the worker process
- Event loop state bleeding between tasks
"""
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional
import uuid
import shutil

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.workers.celery_app import celery_app
from app.core.config import settings
from app.db.database import get_celery_db
from app.db.models import (
    Project, ProjectVersion, Slide, SlideScript, SlideAudio,
    RenderJob, ProjectAudioSettings, ProjectTranslationRules, AudioAsset,
    JobStatus, JobType, ScriptSource, ProjectStatus
)
from app.adapters.pptx_converter import pptx_converter
from app.adapters.media_converter import media_converter, MediaType, AspectRatioError
from app.adapters.tts import tts_adapter, TTSAdapter
from app.adapters.translate import translate_adapter
from app.adapters.render import render_adapter
from app.core.paths import to_relative_path, to_absolute_path, file_exists


def run_async(coro):
    """
    Safely run async code in sync Celery context.
    
    Creates a new event loop for each task execution to avoid:
    - RuntimeError: Event loop is closed
    - RuntimeError: There is no current event loop
    - Issues with prefork pool where loops may be in inconsistent state
    
    The loop is explicitly closed after use to prevent resource leaks.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        try:
            # Cancel any remaining tasks
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            # Allow cancelled tasks to complete
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.run_until_complete(loop.shutdown_asyncgens())
        finally:
            loop.close()
            asyncio.set_event_loop(None)


# === Media Conversion (PPTX, PDF, Images) ===

@celery_app.task(
    bind=True, 
    name="app.workers.tasks.convert_pptx_task",
    time_limit=settings.CONVERT_TASK_TIMEOUT_SEC,
    soft_time_limit=settings.CONVERT_TASK_TIMEOUT_SEC - 30,
)
def convert_pptx_task(self, project_id: str, version_id: str):
    """
    Convert media file (PPTX, PDF, or image) to PNG slides.
    Task name kept as convert_pptx_task for backward compatibility.
    """
    return run_async(_convert_media_async(self, project_id, version_id))


async def _convert_media_async(task, project_id: str, version_id: str):
    async with get_celery_db() as db:
        # Get version
        result = await db.execute(
            select(ProjectVersion).where(ProjectVersion.id == uuid.UUID(version_id))
        )
        version = result.scalar_one_or_none()
        
        if not version or not version.pptx_asset_path:
            return {"status": "error", "message": "Version or media file not found"}
        
        # Convert relative DB path to absolute for file operations
        input_path = to_absolute_path(version.pptx_asset_path)
        version_dir = input_path.parent
        slides_dir = version_dir / "slides"
        
        # Detect media type for special handling
        media_type = media_converter.get_media_type(input_path)
        
        try:
            # If this version was converted before, clean old slide records to avoid duplicates
            result = await db.execute(
                select(Slide).where(Slide.version_id == uuid.UUID(version_id))
            )
            existing_slides = result.scalars().all()
            for s in existing_slides:
                await db.delete(s)
            await db.flush()

            # Clean old slide images on disk (avoid stale files)
            if slides_dir.exists():
                shutil.rmtree(slides_dir)
            slides_dir.mkdir(parents=True, exist_ok=True)
            
            # Clean old audio files (they reference old slides)
            audio_dir = version_dir / "audio"
            if audio_dir.exists():
                shutil.rmtree(audio_dir)
            
            # Clean old exports (they're built from old slides/audio)
            exports_dir = version_dir / "exports"
            if exports_dir.exists():
                shutil.rmtree(exports_dir)
            
            # Clean old timelines
            timelines_dir = version_dir / "timelines"
            if timelines_dir.exists():
                shutil.rmtree(timelines_dir)

            # Convert to PNG using universal media converter
            # This handles PPTX, PDF, and images with aspect ratio validation
            png_paths, aspect_ratio = await media_converter.convert(
                input_path, slides_dir, validate_ratio=True
            )
            
            # Extract speaker notes (only for real .pptx files; .ppt is not supported by python-pptx)
            notes = []
            if media_type == MediaType.PPTX and input_path.suffix.lower() == ".pptx":
                notes = pptx_converter.extract_speaker_notes(input_path)
            
            # Compute file hash for change detection
            slides_hash = media_converter.compute_file_hash(input_path)
            version.slides_hash = slides_hash
            
            # Get project for base language
            result = await db.execute(
                select(Project).where(Project.id == uuid.UUID(project_id))
            )
            project = result.scalar_one()
            
            # Create slide records
            for i, png_path in enumerate(png_paths):
                slide_index = i + 1
                notes_text = notes[i] if i < len(notes) else None
                slide_hash = media_converter.compute_slide_hash(png_path)
                
                slide = Slide(
                    project_id=uuid.UUID(project_id),
                    version_id=uuid.UUID(version_id),
                    slide_index=slide_index,
                    image_path=to_relative_path(png_path),  # Store relative path
                    notes_text=notes_text,
                    slide_hash=slide_hash,
                )
                db.add(slide)
                await db.flush()
                
                # Create base language script (empty or from notes)
                script = SlideScript(
                    slide_id=slide.id,
                    lang=project.base_language,
                    text=notes_text or "",
                    source=ScriptSource.IMPORTED_NOTES if notes_text else ScriptSource.MANUAL,
                )
                db.add(script)
            
            version.status = ProjectStatus.READY
            await db.commit()
            
            return {
                "status": "done",
                "slides_count": len(png_paths),
                "slides_hash": slides_hash,
                "aspect_ratio": aspect_ratio,
                "media_type": media_type.value,
            }
            
        except AspectRatioError as e:
            # Return specific error for invalid aspect ratio
            version.status = ProjectStatus.FAILED
            await db.commit()
            return {
                "status": "error",
                "error_type": "aspect_ratio",
                "message": str(e),
                "width": e.width,
                "height": e.height,
                "detected_ratio": e.detected_ratio,
            }
            
        except Exception as e:
            version.status = ProjectStatus.FAILED
            await db.commit()
            raise


# === TTS Generation ===

@celery_app.task(
    bind=True, 
    name="app.workers.tasks.tts_slide_task",
    time_limit=settings.TTS_TASK_TIMEOUT_SEC,
    soft_time_limit=settings.TTS_TASK_TIMEOUT_SEC - 10,
)
def tts_slide_task(
    self,
    project_id: str,
    version_id: str,
    slide_id: str,
    lang: str,
    voice_id: Optional[str] = None
):
    """Generate TTS for a single slide"""
    return run_async(_tts_slide_async(self, project_id, version_id, slide_id, lang, voice_id))


async def _tts_slide_async(
    task,
    project_id: str,
    version_id: str,
    slide_id: str,
    lang: str,
    voice_id: Optional[str] = None
):
    async with get_celery_db() as db:
        # Get slide and script
        result = await db.execute(
            select(Slide)
            .where(Slide.id == uuid.UUID(slide_id))
            .options(selectinload(Slide.scripts))
        )
        slide = result.scalar_one_or_none()
        
        if not slide:
            return {"status": "error", "message": "Slide not found"}
        
        # Find script for language
        script = next((s for s in slide.scripts if s.lang == lang), None)
        if not script or not script.text:
            return {"status": "error", "message": f"No script for language {lang}"}
        
        # Get voice_id: parameter > project settings > default
        if not voice_id:
            result = await db.execute(
                select(ProjectAudioSettings)
                .where(ProjectAudioSettings.project_id == uuid.UUID(project_id))
            )
            audio_settings = result.scalar_one_or_none()
            voice_id = (audio_settings.voice_id if audio_settings else None) or settings.DEFAULT_VOICE_ID
        
        # Compute audio hash for caching
        audio_hash = TTSAdapter.compute_audio_hash(
            script.text, voice_id, lang, settings.DEFAULT_TTS_MODEL
        )
        
        # Check if audio already exists with same hash
        result = await db.execute(
            select(SlideAudio)
            .where(SlideAudio.slide_id == slide.id)
            .where(SlideAudio.lang == lang)
            .where(SlideAudio.audio_hash == audio_hash)
        )
        existing_audio = result.scalar_one_or_none()
        
        if existing_audio and file_exists(existing_audio.audio_path):
            return {
                "status": "cached",
                "audio_path": existing_audio.audio_path,
                "duration_sec": existing_audio.duration_sec,
            }
        
        # Generate audio
        version_dir = Path(settings.DATA_DIR) / project_id / "versions" / version_id
        audio_dir = version_dir / "audio" / lang
        # Use slide UUID in the filename to avoid collisions when slides are reordered.
        # (Legacy assets still use slide_001.wav etc and are still served by /static/audio.)
        audio_path = audio_dir / f"slide_{slide.id}.wav"
        
        try:
            duration = await tts_adapter.generate_speech(
                text=script.text,
                output_path=audio_path,
                voice_id=voice_id,
            )
            
            # Delete old audio record if exists
            result = await db.execute(
                select(SlideAudio)
                .where(SlideAudio.slide_id == slide.id)
                .where(SlideAudio.lang == lang)
            )
            old_audio = result.scalar_one_or_none()
            if old_audio:
                await db.delete(old_audio)
            
            # Create new audio record with relative path
            relative_audio_path = to_relative_path(audio_path)
            audio_record = SlideAudio(
                slide_id=slide.id,
                lang=lang,
                voice_id=voice_id,
                audio_path=relative_audio_path,
                duration_sec=duration,
                audio_hash=audio_hash,
            )
            db.add(audio_record)
            await db.commit()
            
            return {
                "status": "done",
                "audio_path": relative_audio_path,
                "duration_sec": duration,
            }
            
        except Exception as e:
            raise


@celery_app.task(
    bind=True, 
    name="app.workers.tasks.tts_batch_task",
    time_limit=settings.TTS_TASK_TIMEOUT_SEC * 10,  # batch can take longer
    soft_time_limit=settings.TTS_TASK_TIMEOUT_SEC * 10 - 60,
)
def tts_batch_task(
    self,
    project_id: str,
    version_id: str,
    lang: str,
    voice_id: Optional[str] = None
):
    """Generate TTS for all slides in a version"""
    return run_async(_tts_batch_async(self, project_id, version_id, lang, voice_id))


async def _tts_batch_async(task, project_id: str, version_id: str, lang: str, voice_id: Optional[str]):
    """Generate TTS for all slides - processes each slide with its own session to avoid connection conflicts"""
    # First get all slide IDs with a quick query
    async with get_celery_db() as db:
        result = await db.execute(
            select(Slide.id)
            .where(Slide.version_id == uuid.UUID(version_id))
            .order_by(Slide.slide_index)
        )
        slide_ids = [str(row[0]) for row in result.all()]
    
    # Process each slide with its own session (sequentially to avoid connection pool issues)
    results = []
    for slide_id in slide_ids:
        result = await _tts_slide_async(
            task, project_id, version_id, slide_id, lang, voice_id
        )
        results.append(result)
    
    return {
        "status": "done",
        "processed_count": len(results),
        "results": results,
    }


# === Translation ===

@celery_app.task(
    bind=True, 
    name="app.workers.tasks.translate_batch_task",
    time_limit=settings.CONVERT_TASK_TIMEOUT_SEC,  # use same as convert
    soft_time_limit=settings.CONVERT_TASK_TIMEOUT_SEC - 30,
)
def translate_batch_task(
    self,
    project_id: str,
    version_id: str,
    source_lang: str,
    target_lang: str
):
    """Translate all slides from source to target language"""
    return run_async(_translate_batch_async(self, project_id, version_id, source_lang, target_lang))


async def _translate_batch_async(
    task,
    project_id: str,
    version_id: str,
    source_lang: str,
    target_lang: str
):
    async with get_celery_db() as db:
        # Get translation rules
        result = await db.execute(
            select(ProjectTranslationRules)
            .where(ProjectTranslationRules.project_id == uuid.UUID(project_id))
        )
        rules = result.scalar_one_or_none()
        
        do_not_translate = rules.do_not_translate if rules else []
        preferred_translations = rules.preferred_translations if rules else []
        style = rules.style.value if rules else "formal"
        extra_rules = rules.extra_rules if rules else None
        
        # Get all slides with source scripts
        result = await db.execute(
            select(Slide)
            .where(Slide.version_id == uuid.UUID(version_id))
            .options(selectinload(Slide.scripts))
            .order_by(Slide.slide_index)
        )
        slides = result.scalars().all()
        
        # Collect source texts
        source_texts = []
        slide_ids = []
        for slide in slides:
            source_script = next((s for s in slide.scripts if s.lang == source_lang), None)
            if source_script and source_script.text:
                source_texts.append(source_script.text)
                slide_ids.append(slide.id)
        
        if not source_texts:
            return {"status": "error", "message": "No source texts found"}
        
        # Batch translate
        translations = await translate_adapter.translate_batch(
            texts=source_texts,
            source_lang=source_lang,
            target_lang=target_lang,
            do_not_translate=do_not_translate,
            preferred_translations=preferred_translations,
            style=style,
            extra_rules=extra_rules,
        )
        
        # Save translations
        for slide_id, (translated_text, metadata) in zip(slide_ids, translations):
            # Check if target script exists
            result = await db.execute(
                select(SlideScript)
                .where(SlideScript.slide_id == slide_id)
                .where(SlideScript.lang == target_lang)
            )
            script = result.scalar_one_or_none()
            
            if script:
                script.text = translated_text
                script.source = ScriptSource.TRANSLATED
                script.translation_meta_json = metadata
            else:
                script = SlideScript(
                    slide_id=slide_id,
                    lang=target_lang,
                    text=translated_text,
                    source=ScriptSource.TRANSLATED,
                    translation_meta_json=metadata,
                )
                db.add(script)
        
        await db.commit()
        
        return {
            "status": "done",
            "translated_count": len(translations),
            "target_lang": target_lang,
        }


# === Video Render ===

@celery_app.task(
    bind=True, 
    name="app.workers.tasks.render_language_task",
    time_limit=settings.RENDER_TASK_TIMEOUT_SEC,
    soft_time_limit=settings.RENDER_TASK_TIMEOUT_SEC - 60,
)
def render_language_task(
    self,
    project_id: str,
    version_id: str,
    lang: str,
    job_id: str
):
    """Render video for a specific language"""
    return run_async(_render_language_async(self, project_id, version_id, lang, job_id))


async def _render_language_async(task, project_id: str, version_id: str, lang: str, job_id: str):
    async with get_celery_db() as db:
        # Update job status
        result = await db.execute(
            select(RenderJob).where(RenderJob.id == uuid.UUID(job_id))
        )
        job = result.scalar_one()
        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        await db.commit()
        
        try:
            # Get audio settings (includes render settings now)
            result = await db.execute(
                select(ProjectAudioSettings)
                .where(ProjectAudioSettings.project_id == uuid.UUID(project_id))
            )
            audio_settings = result.scalar_one_or_none()
            
            # Use project settings or fall back to defaults
            pre_padding = audio_settings.pre_padding_sec if audio_settings else settings.PRE_PADDING_SEC
            post_padding = audio_settings.post_padding_sec if audio_settings else settings.POST_PADDING_SEC
            first_hold = audio_settings.first_slide_hold_sec if audio_settings else settings.FIRST_SLIDE_HOLD_SEC
            last_hold = audio_settings.last_slide_hold_sec if audio_settings else settings.LAST_SLIDE_HOLD_SEC
            transition_type = audio_settings.transition_type.value if audio_settings else settings.TRANSITION_TYPE
            transition_duration = audio_settings.transition_duration_sec if audio_settings else settings.TRANSITION_DURATION_SEC
            
            # Get slides with audio
            result = await db.execute(
                select(Slide)
                .where(Slide.version_id == uuid.UUID(version_id))
                .options(selectinload(Slide.audio_files), selectinload(Slide.scripts))
                .order_by(Slide.slide_index)
            )
            slides = result.scalars().all()
            
            version_dir = Path(settings.DATA_DIR) / project_id / "versions" / version_id
            timelines_dir = version_dir / "timelines"
            exports_dir = version_dir / "exports" / lang
            job_tag = job_id.replace("-", "")
            timelines_dir.mkdir(parents=True, exist_ok=True)
            exports_dir.mkdir(parents=True, exist_ok=True)
            
            # Minimum duration for slides without audio
            MIN_FIRST_SLIDE_DURATION = 5.0  # First slide shows for at least 5 seconds
            MIN_SLIDE_DURATION = 3.0  # Other slides show for at least 3 seconds
            
            # Process ALL slides, including those without audio
            all_slides_data = []  # [(slide, audio_or_none, script_or_none, audio_file_path_or_none), ...]
            
            for slide in slides:
                audio = next((a for a in slide.audio_files if a.lang == lang), None)
                script = next((s for s in slide.scripts if s.lang == lang), None)
                audio_file_path = None
                
                if audio:
                    # Validate audio file exists on disk
                    audio_file_path = to_absolute_path(audio.audio_path)
                    if not audio_file_path.exists():
                        # Stale DB record - audio file was deleted
                        await db.delete(audio)
                        await db.flush()
                        audio = None
                        audio_file_path = None
                
                all_slides_data.append((slide, audio, script, audio_file_path))
            
            # Check if we have at least one slide
            if not all_slides_data:
                raise ValueError(f"No slides found for version '{version_id}'.")
            
            # Build voice timeline
            audio_files = []
            slide_data = []
            subtitles = []
            current_time = 0.0
            num_slides = len(all_slides_data)
            
            for idx, (slide, audio, script, audio_file_path) in enumerate(all_slides_data):
                # Determine if this is first/last slide
                is_first = idx == 0
                is_last = idx == num_slides - 1
                
                if audio and audio_file_path:
                    # Slide has audio - use normal duration calculation
                    pre_pad = first_hold if is_first else pre_padding
                    post_pad = last_hold if is_last else post_padding
                    
                    audio_files.append((audio_file_path, pre_pad, post_pad))
                    
                    # Calculate duration
                    duration = pre_pad + audio.duration_sec + post_pad
                    
                    # Build subtitle entry
                    if script and script.text:
                        subtitle_start = current_time + pre_pad
                        subtitle_end = current_time + pre_pad + audio.duration_sec
                        subtitles.append((subtitle_start, subtitle_end, script.text))
                else:
                    # Slide has no audio - use minimum duration (silence)
                    min_duration = MIN_FIRST_SLIDE_DURATION if is_first else MIN_SLIDE_DURATION
                    duration = min_duration
                    # No audio file to add, but we need to account for silence
                    # We'll add a silent gap in the voice timeline
                    audio_files.append((None, 0.0, duration))  # None path signals silence
                
                slide_data.append((to_absolute_path(slide.image_path), duration))
                current_time += duration
            
            job.progress_pct = 20
            await db.commit()
            
            # Build voice timeline
            voice_timeline = timelines_dir / f"voice_timeline_{lang}_{job_tag}.wav"
            await render_adapter.build_voice_timeline(audio_files, voice_timeline)
            
            job.progress_pct = 40
            await db.commit()
            
            # Mix audio (voice + music)
            final_audio = timelines_dir / f"final_audio_{lang}_{job_tag}.wav"
            
            music_path = None
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"[RENDER] audio_settings exists: {audio_settings is not None}")
            if audio_settings:
                logger.info(f"[RENDER] background_music_enabled: {audio_settings.background_music_enabled}")
                logger.info(f"[RENDER] music_asset_id: {audio_settings.music_asset_id}")
            
            if audio_settings and audio_settings.background_music_enabled and audio_settings.music_asset_id:
                result = await db.execute(
                    select(AudioAsset).where(AudioAsset.id == audio_settings.music_asset_id)
                )
                music_asset = result.scalar_one_or_none()
                logger.info(f"[RENDER] music_asset found: {music_asset is not None}")
                if music_asset:
                    music_path = to_absolute_path(music_asset.file_path)
                    logger.info(f"[RENDER] music_path: {music_path}, exists: {music_path.exists()}")
            
            await render_adapter.mix_audio(
                voice_path=voice_timeline,
                music_path=music_path,
                output_path=final_audio,
                voice_gain_db=audio_settings.voice_gain_db if audio_settings else 0.0,
                music_gain_db=audio_settings.music_gain_db if audio_settings else -22.0,
                ducking_enabled=audio_settings.ducking_enabled if audio_settings else True,
                ducking_strength=audio_settings.ducking_strength.value if audio_settings else "default",
                target_lufs=audio_settings.target_lufs if audio_settings else -14,
            )
            
            job.progress_pct = 60
            await db.commit()
            
            # Generate SRT
            final_srt_path = exports_dir / f"deck_{lang}.srt"
            tmp_srt_path = exports_dir / f"deck_{lang}.{job_tag}.tmp.srt"
            await render_adapter.generate_srt(subtitles, tmp_srt_path)
            
            job.progress_pct = 70
            await db.commit()
            
            # Render video with project settings
            final_video_path = exports_dir / f"deck_{lang}.mp4"
            tmp_video_path = exports_dir / f"deck_{lang}.{job_tag}.tmp.mp4"
            await render_adapter.render_video_from_slides(
                slides=slide_data,
                audio_path=final_audio,
                output_path=tmp_video_path,
                transition_type=transition_type,
                transition_duration=transition_duration,
                job_id=job_id,
            )

            # Atomically replace final exports to avoid clobbering a previous successful export
            # if the user cancels mid-render.
            tmp_srt_path.replace(final_srt_path)
            tmp_video_path.replace(final_video_path)

            # Timeline files are temporary; clean them up after success
            for p in (voice_timeline, final_audio):
                try:
                    p.unlink(missing_ok=True)
                except Exception:
                    pass
            
            # Update job with relative paths
            job.status = JobStatus.DONE
            job.progress_pct = 100
            job.output_video_path = to_relative_path(final_video_path)
            job.output_srt_path = to_relative_path(final_srt_path)
            job.finished_at = datetime.utcnow()
            await db.commit()
            
            return {
                "status": "done",
                "video_path": to_relative_path(final_video_path),
                "srt_path": to_relative_path(final_srt_path),
            }
            
        except Exception as e:
            job.status = JobStatus.FAILED
            job.error_message = str(e)
            job.finished_at = datetime.utcnow()
            await db.commit()
            raise

