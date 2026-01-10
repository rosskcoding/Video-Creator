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
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional
import uuid
import shutil
from urllib.parse import urlparse

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.workers.celery_app import celery_app
from app.core.config import settings
from app.db.database import get_celery_db
from app.db.models import (
    Project, ProjectVersion, Slide, SlideScript, SlideAudio, SlideScene, SlideMarkers, NormalizedScript,
    RenderJob, ProjectAudioSettings, ProjectTranslationRules, AudioAsset,
    JobStatus, JobType, ScriptSource, ProjectStatus
)
from app.adapters.pptx_converter import pptx_converter
from app.adapters.media_converter import media_converter, MediaType, AspectRatioError
from app.adapters.tts import tts_adapter, TTSAdapter
from app.adapters.translate import translate_adapter
from app.adapters.render import render_adapter
from app.adapters.render_service import get_render_service_client
from app.adapters.text_normalizer import normalize_text, align_word_timings, estimate_word_timings
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
            # Backfill script_text_hash for legacy rows so we can detect future script edits
            if not getattr(existing_audio, "script_text_hash", None):
                existing_audio.script_text_hash = hashlib.sha256(script.text.encode()).hexdigest()[:32]
                await db.commit()
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
            # Generate speech with timestamps for word-level timing data
            tts_result = await tts_adapter.generate_speech_with_timestamps(
                text=script.text,
                output_path=audio_path,
                voice_id=voice_id,
            )
            duration = tts_result.duration
            
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
            # Compute hash of the script text used for TTS (for sync tracking)
            script_text_hash = hashlib.sha256(script.text.encode()).hexdigest()[:32]
            audio_record = SlideAudio(
                slide_id=slide.id,
                lang=lang,
                voice_id=voice_id,
                audio_path=relative_audio_path,
                duration_sec=duration,
                audio_hash=audio_hash,
                script_text_hash=script_text_hash,
            )
            db.add(audio_record)
            
            # === Process word timings and save to NormalizedScript ===
            normalized_text = normalize_text(script.text)
            word_timings = []
            
            if tts_result.alignment:
                # Use ElevenLabs alignment data for accurate word timings
                word_timings = align_word_timings(normalized_text, tts_result.alignment)
            
            if not word_timings and duration > 0:
                # Fallback: estimate word timings based on character proportions
                word_timings = estimate_word_timings(normalized_text, duration)
            
            # Upsert NormalizedScript
            result = await db.execute(
                select(NormalizedScript)
                .where(NormalizedScript.slide_id == slide.id)
                .where(NormalizedScript.lang == lang)
            )
            normalized_script = result.scalar_one_or_none()
            
            if normalized_script:
                normalized_script.raw_text = script.text
                normalized_script.normalized_text = normalized_text
                normalized_script.word_timings = word_timings
                normalized_script.updated_at = datetime.utcnow()
            else:
                normalized_script = NormalizedScript(
                    slide_id=slide.id,
                    lang=lang,
                    raw_text=script.text,
                    normalized_text=normalized_text,
                    word_timings=word_timings,
                )
                db.add(normalized_script)
            
            # === Update marker timeSeconds from word_timings ===
            await _update_marker_timings(db, slide.id, lang, word_timings)
            
            await db.commit()
            
            return {
                "status": "done",
                "audio_path": relative_audio_path,
                "duration_sec": duration,
                "word_timings_count": len(word_timings),
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
                music_fade_in_sec=audio_settings.music_fade_in_sec if audio_settings else 2.0,
                music_fade_out_sec=audio_settings.music_fade_out_sec if audio_settings else 3.0,
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
            
            # Check if browser-based render is enabled OR required (when there are animated scenes)
            use_browser_render = settings.USE_RENDER_SERVICE

            # Auto-enable browser render when any slide has a scene with layers
            # (otherwise animations from Canvas Editor would be silently ignored).
            if not use_browser_render:
                try:
                    scene_result = await db.execute(
                        select(SlideScene).where(SlideScene.slide_id.in_([s.id for s in slides]))
                    )
                    scenes = scene_result.scalars().all()
                    if any(sc and sc.layers and len(sc.layers) > 0 for sc in scenes):
                        use_browser_render = True
                except Exception:
                    # If scene detection fails, keep FFmpeg fallback.
                    use_browser_render = False
            
            if use_browser_render:
                # Check if render service is available
                render_client = get_render_service_client()
                if not await render_client.health_check():
                    logger.warning("Render service unavailable, falling back to FFmpeg render")
                    use_browser_render = False
            
            if use_browser_render:
                # Browser-based render with animations
                await _render_with_animations(
                    db=db,
                    slides=slides,
                    slide_data=slide_data,
                    lang=lang,
                    audio_path=final_audio,
                    output_path=tmp_video_path,
                    project_id=project_id,
                    version_id=version_id,
                    transition_type=transition_type,
                    transition_duration=transition_duration,
                    pre_padding_sec=pre_padding,
                    first_slide_hold_sec=first_hold,
                    logger=logger,
                )
            else:
                # Traditional FFmpeg render (no animations)
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


async def _render_with_animations(
    db,
    slides: list,
    slide_data: list,
    lang: str,
    audio_path: Path,
    output_path: Path,
    project_id: str,
    version_id: str,
    transition_type: str,
    transition_duration: float,
    pre_padding_sec: float,
    first_slide_hold_sec: float,
    logger,
):
    """
    Render video using browser-based render service with animated layers.
    
    This function:
    1. For each slide with a scene, calls render-service to create animated video clip
    2. Concatenates all clips with transitions
    3. Mixes with audio track
    """
    from app.api.routes.canvas import compute_render_key

    def _sanitize_for_render_service(obj):
        """
        render-service uses strict Zod schemas. Our stored scene JSON may contain:
        - keys with null values (JSON null -> invalid for optional fields)
        - UI-only keys like 'anchor' or 'fromState'
        This sanitizer removes those so the payload validates.
        """
        if isinstance(obj, dict):
            cleaned = {}
            for k, v in obj.items():
                # Drop UI-only / unsupported keys
                if k in {"anchor", "fromState"}:
                    continue
                # Drop nulls (render-service expects optional fields to be omitted, not null)
                if v is None:
                    continue
                cleaned[k] = _sanitize_for_render_service(v)
            return cleaned
        if isinstance(obj, list):
            return [_sanitize_for_render_service(i) for i in obj]
        return obj
    
    render_client = get_render_service_client()
    version_dir = Path(settings.DATA_DIR) / project_id / "versions" / version_id
    clips_dir = version_dir / "clips" / lang
    clips_dir.mkdir(parents=True, exist_ok=True)
    
    # We build the clips list in slide order.
    rendered_clips_ordered: list[Optional[tuple[Path, float]]] = [None] * len(slide_data)
    batch_requests: list[dict] = []
    batch_meta: dict[str, dict] = {}  # slide_id -> {idx, cached_clip, duration, image_path}
    
    for idx, (slide, (image_path, duration)) in enumerate(zip(slides, slide_data)):
        # Check if slide has a scene with layers
        result = await db.execute(
            select(SlideScene).where(SlideScene.slide_id == slide.id)
        )
        scene = result.scalar_one_or_none()
        
        if scene and scene.layers and len(scene.layers) > 0:
            # Determine the voice start offset within this slide (pre-padding before audio begins).
            # Word/marker timings from TTS are relative to the start of the voice audio, so we add this.
            is_first = idx == 0
            audio = next((a for a in (slide.audio_files or []) if a.lang == lang), None)
            has_voice_audio = bool(audio and getattr(audio, "audio_path", None) and file_exists(audio.audio_path))
            voice_offset_sec = float(first_slide_hold_sec if (is_first and has_voice_audio) else (pre_padding_sec if has_voice_audio else 0.0))

            # Resolve word/marker triggers to time-based (relative to slide start)
            resolved_layers = await _resolve_scene_triggers(
                db=db,
                slide_id=slide.id,
                scene=scene,
                lang=lang,
                slide_duration=float(duration),
                voice_offset_sec=voice_offset_sec,
                project_id=project_id,
            )

            # Ensure strict compatibility with render-service schema
            resolved_layers = _sanitize_for_render_service(resolved_layers)
            
            # DEBUG: Log layers being sent to render-service
            import json
            logger.info(f"Layers for slide {slide.id}: {json.dumps(resolved_layers, indent=2)}")
            
            # Check cache by render_key
            render_key = compute_render_key(resolved_layers, {"width": scene.canvas_width, "height": scene.canvas_height})
            cached_clip = clips_dir / f"{slide.id}_{lang}_{render_key}.webm"
            
            if cached_clip.exists():
                logger.info(f"Using cached clip for slide {slide.id}")
                rendered_clips_ordered[idx] = (cached_clip, duration)
                continue
            
            # IMPORTANT: render-service runs without a user session, so it cannot fetch /static/* (auth-required).
            # We pass filesystem paths instead (shared volume mounted at /data/projects).
            slide_image_url = str(image_path)

            # Queue for batch rendering (parallelized inside render-service)
            batch_requests.append(
                {
                    "slideId": str(slide.id),
                    "slideImageUrl": slide_image_url,
                    "layers": resolved_layers,
                    "duration": float(duration),
                    "width": int(scene.canvas_width),
                    "height": int(scene.canvas_height),
                    "fps": int(settings.VIDEO_FPS),
                    "format": "webm",
                    "renderKey": render_key,
                    "lang": lang,
                }
            )
            batch_meta[str(slide.id)] = {
                "idx": idx,
                "cached_clip": cached_clip,
                "duration": float(duration),
                "image_path": image_path,
            }
        else:
            # No scene or empty layers - create static clip
            static_clip = clips_dir / f"{slide.id}_{lang}_static.webm"
            if not static_clip.exists():
                await render_adapter.create_static_clip(image_path, duration, static_clip)
            rendered_clips_ordered[idx] = (static_clip, duration)
    
    # Execute batch render for slides that need animated rendering
    if batch_requests:
        batch_concurrency = int(getattr(settings, "RENDER_SERVICE_BATCH_CONCURRENCY", 3))
        try:
            batch_resp = await render_client.render_batch(
                slides=batch_requests,
                concurrency=batch_concurrency,
            )
            results = (batch_resp or {}).get("results") or []
            results_by_slide_id: dict[str, dict] = {}
            for r in results:
                sid = r.get("slideId") if isinstance(r, dict) else None
                if sid:
                    results_by_slide_id[sid] = r
            
            for slide_id, meta in batch_meta.items():
                idx = meta["idx"]
                cached_clip: Path = meta["cached_clip"]
                duration = meta["duration"]
                image_path: Path = meta["image_path"]
                
                r = results_by_slide_id.get(slide_id) or {}
                output_name = r.get("outputPath")
                if output_name:
                    try:
                        rendered_file = render_client.get_output_path(output_name)
                        shutil.copy(rendered_file, cached_clip)
                        # Best-effort cleanup of the shared output volume (avoid unbounded growth).
                        try:
                            rendered_file.unlink(missing_ok=True)
                        except Exception:
                            pass
                        rendered_clips_ordered[idx] = (cached_clip, duration)
                    except Exception as e:
                        logger.error(f"Batch clip copy failed for slide {slide_id}: {e}")
                        static_clip = clips_dir / f"{slide_id}_{lang}_static.webm"
                        await render_adapter.create_static_clip(image_path, duration, static_clip)
                        rendered_clips_ordered[idx] = (static_clip, duration)
                else:
                    err = r.get("error") if isinstance(r, dict) else None
                    logger.error(f"Batch render failed for slide {slide_id}: {err or 'unknown error'}")
                    static_clip = clips_dir / f"{slide_id}_{lang}_static.webm"
                    await render_adapter.create_static_clip(image_path, duration, static_clip)
                    rendered_clips_ordered[idx] = (static_clip, duration)
        except Exception as e:
            logger.error(f"Batch render request failed (falling back to per-slide): {e}")
            # Fallback: render each slide individually
            for req in batch_requests:
                slide_id = req["slideId"]
                meta = batch_meta.get(slide_id)
                if not meta:
                    continue
                idx = meta["idx"]
                cached_clip: Path = meta["cached_clip"]
                duration = meta["duration"]
                image_path: Path = meta["image_path"]
                try:
                    result = await render_client.render_slide(
                        slide_id=slide_id,
                        slide_image_url=req["slideImageUrl"],
                        layers=req["layers"],
                        duration=duration,
                        width=req["width"],
                        height=req["height"],
                        fps=req["fps"],
                        output_format="webm",
                        render_key=req.get("renderKey"),
                        lang=req.get("lang", lang),
                    )
                    rendered_file = render_client.get_output_path(result["outputPath"])
                    shutil.copy(rendered_file, cached_clip)
                    try:
                        rendered_file.unlink(missing_ok=True)
                    except Exception:
                        pass
                    rendered_clips_ordered[idx] = (cached_clip, duration)
                except Exception as ee:
                    logger.error(f"Browser render failed for slide {slide_id}: {ee}")
                    static_clip = clips_dir / f"{slide_id}_{lang}_static.webm"
                    await render_adapter.create_static_clip(image_path, duration, static_clip)
                    rendered_clips_ordered[idx] = (static_clip, duration)
    
    # Final ordered clips list
    rendered_clips = [c for c in rendered_clips_ordered if c is not None]
    
    # Concatenate all clips with transitions
    await render_adapter.concatenate_clips(
        clips=rendered_clips,
        output_path=output_path,
        transition_type=transition_type,
        transition_duration=transition_duration,
    )
    
    # Mix with audio
    await render_adapter.add_audio_to_video(
        video_path=output_path,
        audio_path=audio_path,
        output_path=output_path,
    )

def _asset_url_to_filesystem_path(asset_url: str, project_id: str) -> Optional[str]:
    """
    Convert asset URLs to filesystem paths with security validation.
    
    SECURITY: This function is critical for mitigating the --disable-web-security
    flag in the render-service Chromium browser. It ensures:
    1. Only /static/assets/{project_id}/* URLs are converted
    2. Path traversal attacks (../) are blocked via path normalization
    3. All paths must resolve within DATA_DIR
    
    Supported URL formats:
      /static/assets/{project_id}/{filename}
      /static/assets/{project_id}/thumbs/{filename}
      https://domain/static/assets/{project_id}/{filename}
    """
    if not asset_url:
        return None

    # If it's a full URL, extract the path part.
    parsed = urlparse(asset_url)
    path_part = parsed.path if parsed.scheme else asset_url

    if not path_part.startswith("/static/assets/"):
        # Not a /static/assets URL/path. Treat as a filesystem path (absolute only).
        try:
            p = Path(asset_url)
            if p.is_absolute():
                # Normalize to resolve any ../ attempts
                normalized = p.resolve()
                data_dir_resolved = settings.DATA_DIR.resolve()
                # SECURITY: Ensure path is within DATA_DIR
                try:
                    normalized.relative_to(data_dir_resolved)
                    return str(normalized)
                except ValueError:
                    return None
        except Exception:
            pass
        return None

    parts = path_part.lstrip("/").split("/")  # ["static","assets",project_id,...]
    if len(parts) < 4 or parts[0] != "static" or parts[1] != "assets":
        return None

    pid = parts[2]
    # Prefer the provided project_id (safety); but if URL encodes it, use it.
    pid = pid or project_id
    
    # SECURITY: Reject suspicious project IDs (path traversal attempts)
    if ".." in pid or pid.startswith("/") or not pid:
        return None

    # Build path and validate
    if len(parts) >= 5 and parts[3] == "thumbs":
        filename = parts[4]
        # SECURITY: Reject filenames with path traversal
        if ".." in filename or "/" in filename:
            return None
        result_path = settings.DATA_DIR / pid / "assets" / "thumbs" / filename
    else:
        filename = parts[3]
        # SECURITY: Reject filenames with path traversal
        if ".." in filename or "/" in filename:
            return None
        result_path = settings.DATA_DIR / pid / "assets" / filename
    
    # Final validation: ensure resolved path is within DATA_DIR
    try:
        resolved = result_path.resolve()
        data_dir_resolved = settings.DATA_DIR.resolve()
        resolved.relative_to(data_dir_resolved)
        return str(resolved)
    except ValueError:
        # Path escaped DATA_DIR - reject
        return None


async def _update_marker_timings(
    db,
    slide_id,
    lang: str,
    word_timings: list,
) -> int:
    """
    Update marker timeSeconds from word_timings.
    
    EPIC A Enhancement:
    Now updates BOTH legacy SlideMarkers AND new GlobalMarker positions.
    
    This is called after TTS generation to:
    1. Update legacy SlideMarkers for backward compatibility
    2. Update GlobalMarker.MarkerPosition.time_seconds for EPIC A compliant resolution
    
    For translated languages, markers may not have matching charStart positions,
    but if a marker exists with the same ID (from propagation), it will be updated
    based on its position in the translated script, or via token-based lookup.
    
    Returns count of markers updated.
    """
    from app.db.models import GlobalMarker, MarkerPosition
    from app.adapters.marker_tokens import compute_marker_time_from_word_timings
    from sqlalchemy.orm import selectinload
    
    if not word_timings:
        return 0
    
    updated_count = 0
    
    # === PART 1: Update legacy SlideMarkers (backward compatibility) ===
    result = await db.execute(
        select(SlideMarkers)
        .where(SlideMarkers.slide_id == slide_id)
        .where(SlideMarkers.lang == lang)
    )
    markers_record = result.scalar_one_or_none()
    
    if markers_record and markers_record.markers:
        # IMPORTANT: copy marker dicts before mutation.
        markers = []
        for m in (markers_record.markers or []):
            if isinstance(m, dict):
                markers.append(dict(m))
            else:
                markers.append(m)
        
        # Build lookup for word timings by charStart and by word text (case-insensitive)
        timings_by_char_start = {t.get("charStart"): t for t in word_timings if t.get("charStart") is not None}
        timings_by_word_lower = {}
        for t in word_timings:
            word = (t.get("word") or "").lower()
            if word and word not in timings_by_word_lower:
                timings_by_word_lower[word] = t
        
        for marker in markers:
            if not isinstance(marker, dict):
                continue
            char_start = marker.get("charStart")
            word_text = (marker.get("wordText") or "").lower()
            
            resolved_time = None
            
            # Primary: match by charStart
            if char_start is not None and char_start in timings_by_char_start:
                timing = timings_by_char_start[char_start]
                resolved_time = timing.get("startTime")
            
            # Fallback: match by wordText
            if resolved_time is None and word_text and word_text in timings_by_word_lower:
                timing = timings_by_word_lower[word_text]
                resolved_time = timing.get("startTime")
            
            if resolved_time is not None:
                try:
                    marker["timeSeconds"] = float(resolved_time)
                    updated_count += 1
                except (TypeError, ValueError):
                    pass
        
        markers_record.markers = markers
        markers_record.updated_at = datetime.utcnow()
    
    # === PART 2: Update GlobalMarker positions (EPIC A) ===
    # Get normalized script for token-based lookup
    result = await db.execute(
        select(NormalizedScript)
        .where(NormalizedScript.slide_id == slide_id)
        .where(NormalizedScript.lang == lang)
    )
    normalized_script = result.scalar_one_or_none()
    normalized_text = normalized_script.normalized_text if normalized_script else ""
    
    # Get all GlobalMarkers for this slide
    result = await db.execute(
        select(GlobalMarker)
        .where(GlobalMarker.slide_id == slide_id)
        .options(selectinload(GlobalMarker.positions))
    )
    global_markers = result.scalars().all()
    
    for marker in global_markers:
        # Find position for this language
        position = next((p for p in marker.positions if p.lang == lang), None)
        
        resolved_time = None
        
        # Method 1: Token-based lookup (preferred for translated text)
        if normalized_text:
            resolved_time = compute_marker_time_from_word_timings(
                normalized_text,
                str(marker.id),
                word_timings
            )
        
        # Method 2: char_start matching from position
        if resolved_time is None and position and position.char_start is not None:
            for wt in word_timings:
                if wt.get("charStart") == position.char_start:
                    resolved_time = wt.get("startTime")
                    break
        
        if resolved_time is not None:
            if position:
                position.time_seconds = float(resolved_time)
                position.updated_at = datetime.utcnow()
                updated_count += 1
            else:
                # Create new position for this language
                from app.db.models import MarkerSource
                new_position = MarkerPosition(
                    id=uuid.uuid4(),
                    marker_id=marker.id,
                    lang=lang,
                    char_start=None,  # Unknown from token
                    char_end=None,
                    time_seconds=float(resolved_time),
                    source=MarkerSource.AUTO,
                )
                db.add(new_position)
                updated_count += 1
    
    return updated_count


async def _resolve_scene_triggers(
    db,
    slide_id,
    scene,
    lang: str,
    slide_duration: float,
    voice_offset_sec: float,
    project_id: str,
) -> list:
    """
    Resolve word/marker-based animation triggers to time-based triggers.
    Returns a list of layer dicts with all triggers converted to time.
    """
    # Fetch normalized script for word timings
    result = await db.execute(
        select(NormalizedScript)
        .where(NormalizedScript.slide_id == slide_id)
        .where(NormalizedScript.lang == lang)
    )
    normalized_script = result.scalar_one_or_none()
    
    # EPIC A: Prefer GlobalMarker positions (stable across languages).
    # We still merge in legacy SlideMarkers for backwards compatibility.
    from sqlalchemy.orm import selectinload
    from app.db.models import GlobalMarker

    marker_by_id: dict[str, dict] = {}

    # 1) Global markers (new system)
    result = await db.execute(
        select(GlobalMarker)
        .where(GlobalMarker.slide_id == slide_id)
        .options(selectinload(GlobalMarker.positions))
    )
    global_markers = result.scalars().all()
    for gm in global_markers:
        gm_id = str(gm.id)
        # Find position for this language (may be absent)
        pos = next((p for p in (gm.positions or []) if p.lang == lang), None)
        marker_by_id[gm_id] = {
            "id": gm_id,
            "name": gm.name,
            "timeSeconds": getattr(pos, "time_seconds", None) if pos else None,
        }

    # 2) Legacy markers (old system) - fill gaps only
    result = await db.execute(
        select(SlideMarkers)
        .where(SlideMarkers.slide_id == slide_id)
        .where(SlideMarkers.lang == lang)
    )
    markers_record = result.scalar_one_or_none()
    legacy_markers = markers_record.markers if markers_record else []
    for m in legacy_markers or []:
        if not isinstance(m, dict):
            continue
        mid = (m.get("id") or "").strip()
        if not mid:
            continue
        if mid not in marker_by_id:
            marker_by_id[mid] = m

    markers = list(marker_by_id.values())

    # Fetch slide audio for duration fallback
    result = await db.execute(
        select(SlideAudio)
        .where(SlideAudio.slide_id == slide_id)
        .where(SlideAudio.lang == lang)
    )
    slide_audio = result.scalar_one_or_none()
    audio_duration = float(slide_audio.duration_sec) if slide_audio and getattr(slide_audio, "duration_sec", None) is not None else max(0.0, float(slide_duration) - float(voice_offset_sec))
    
    resolved_layers = []
    
    for layer_dict in scene.layers:
        layer = dict(layer_dict)  # Make a copy

        # Rewrite asset URLs to filesystem paths so render-service can load them without auth.
        if layer.get("type") == "image" and isinstance(layer.get("image"), dict):
            img = dict(layer["image"])
            asset_url = img.get("assetUrl") or ""
            fs_path = _asset_url_to_filesystem_path(asset_url, project_id=project_id)
            if fs_path:
                img["assetUrl"] = fs_path
                layer["image"] = img
        
        if "animation" in layer and layer["animation"]:
            animation = layer["animation"]
            
            if "entrance" in animation and animation["entrance"]:
                entrance = dict(animation["entrance"])
                entrance["trigger"] = _resolve_trigger(
                    entrance.get("trigger", {}),
                    normalized_script,
                    markers,
                    audio_duration,
                    voice_offset_sec,
                )
                animation["entrance"] = entrance
            
            if "exit" in animation and animation["exit"]:
                exit_anim = dict(animation["exit"])
                exit_anim["trigger"] = _resolve_trigger(
                    exit_anim.get("trigger", {}),
                    normalized_script,
                    markers,
                    audio_duration,
                    voice_offset_sec,
                )
                animation["exit"] = exit_anim
            
            layer["animation"] = animation
        
        resolved_layers.append(layer)
    
    return resolved_layers


def _resolve_trigger(
    trigger: dict,
    normalized_script,
    markers: list,
    audio_duration: float,
    voice_offset_sec: float,
) -> dict:
    """
    Resolve a single trigger to time-based where needed.
    Keeps start/end/time triggers intact (render-service can evaluate them against slideDuration).
    
    EPIC A strategy (no heuristics):
    1. marker triggers: resolve strictly via markerId -> marker.timeSeconds
    2. word triggers: if markerId present, resolve via markerId; else resolve via exact charStart in word_timings
    3. If not resolvable, return time=0 (deterministic fallback; no \"примерно там\")
    """
    if not trigger:
        return {"type": "start", "offsetSeconds": 0}
    
    trigger_type = trigger.get("type", "start")
    
    if trigger_type in ("time", "start", "end"):
        return trigger

    if trigger_type == "marker":
        marker_id = (trigger.get("markerId") or "").strip()
        resolved_time = None
        for m in markers or []:
            if m.get("id") == marker_id or m.get("name") == marker_id:
                resolved_time = m.get("timeSeconds")
                break
        if resolved_time is None:
            # Best-effort fallback: treat missing marker time as slide start
            return {"type": "time", "seconds": 0}
        try:
            return {
                "type": "time",
                "seconds": float(resolved_time) + float(voice_offset_sec),
                "_original_type": "marker",
                "_original_markerId": marker_id,
            }
        except (TypeError, ValueError):
            return {"type": "time", "seconds": 0}
    
    if trigger_type == "word":
        word_text = (trigger.get("wordText") or "").strip()
        char_start = trigger.get("charStart")
        marker_id = trigger.get("markerId")  # New: word triggers can reference markers
        
        # Strategy 1: Resolve via markerId (best for cross-language consistency)
        if marker_id and markers:
            for m in markers:
                if m.get("id") == marker_id:
                    resolved_time = m.get("timeSeconds")
                    if resolved_time is not None:
                        try:
                            return {
                                "type": "time",
                                "seconds": float(resolved_time) + float(voice_offset_sec),
                                "_original_type": "word",
                                "_original_wordText": word_text,
                                "_resolved_via": "markerId",
                            }
                        except (TypeError, ValueError):
                            pass
                    break
        
        # Strategy 2: Match word_timings by charStart (works for base language)
        if normalized_script and normalized_script.word_timings and char_start is not None:
            for timing in normalized_script.word_timings:
                if timing.get("charStart") == char_start:
                    try:
                        return {
                            "type": "time",
                            "seconds": float(timing.get("startTime", 0)) + float(voice_offset_sec),
                            "_original_type": "word",
                            "_original_wordText": word_text,
                            "_resolved_via": "charStart",
                        }
                    except (TypeError, ValueError):
                        pass

        # Strategy 3: Match by wordText (UI-provided legacy trigger).
        #
        # The Canvas editor currently stores `wordText` without `charStart`.
        # Without this fallback, word triggers will silently resolve to t=0
        # and the layer can become permanently invisible.
        #
        # We keep this STRICT: exact (normalized) word match, first occurrence only.
        if normalized_script and normalized_script.word_timings and word_text:
            import re

            def _norm_word(s: str) -> str:
                # Lowercase and strip non-word characters (punctuation), keep unicode letters/digits.
                return re.sub(r"[^\w]+", "", (s or "").lower())

            target = _norm_word(word_text)
            if target:
                for timing in normalized_script.word_timings:
                    try:
                        if _norm_word(str(timing.get("word", ""))) != target:
                            continue
                        start_time = timing.get("startTime")
                        if start_time is None:
                            continue
                        return {
                            "type": "time",
                            "seconds": float(start_time) + float(voice_offset_sec),
                            "_original_type": "word",
                            "_original_wordText": word_text,
                            "_resolved_via": "wordText",
                        }
                    except (TypeError, ValueError):
                        continue
    
    # Default fallback
    return {"type": "time", "seconds": 0}


# === EPIC A: Migration Utilities ===

async def migrate_word_triggers_to_markers(
    db,
    slide_id: uuid.UUID,
    base_lang: str,
) -> dict:
    """
    Migrate existing word triggers in a scene to GlobalMarkers (EPIC A: A7).
    
    This function:
    1. Scans the scene for layers with word-type triggers
    2. Creates a GlobalMarker for each unique word trigger
    3. Creates MarkerPosition for the base language
    4. Updates the trigger to use markerId instead of word-based matching
    5. Inserts marker tokens into the base language script
    
    Call this when upgrading existing projects to the EPIC A marker system.
    
    Returns:
        {
            "markers_created": int,
            "triggers_migrated": int,
            "tokens_inserted": int,
            "needs_retranslate": list[str]  # languages that need retranslation
        }
    """
    from app.db.models import GlobalMarker, MarkerPosition, MarkerSource, SlideScene, SlideScript
    from app.adapters.marker_tokens import format_marker_token, contains_marker_tokens
    from app.adapters.text_normalizer import normalize_text, tokenize_words
    
    # Get scene
    result = await db.execute(
        select(SlideScene).where(SlideScene.slide_id == slide_id)
    )
    scene = result.scalar_one_or_none()
    
    if not scene or not scene.layers:
        return {"markers_created": 0, "triggers_migrated": 0, "tokens_inserted": 0, "needs_retranslate": []}
    
    # Get base language script
    result = await db.execute(
        select(SlideScript)
        .where(SlideScript.slide_id == slide_id)
        .where(SlideScript.lang == base_lang)
    )
    base_script = result.scalar_one_or_none()
    
    if not base_script:
        return {"markers_created": 0, "triggers_migrated": 0, "tokens_inserted": 0, "needs_retranslate": []}
    
    # NOTE: We avoid in-place mutation of SQLAlchemy JSON values.
    # Deep-copy layers before editing so SQLAlchemy reliably detects changes.
    normalized_text = normalize_text(base_script.text)
    
    # Find word triggers and create markers
    import copy
    from sqlalchemy.orm.attributes import flag_modified

    layers = copy.deepcopy(scene.layers or [])
    markers_created = 0
    triggers_migrated = 0
    token_insertions = []  # (marker_id, char_position)
    
    for layer in layers:
        animation = layer.get("animation")
        if not animation:
            continue
        
        for anim_key in ["entrance", "exit"]:
            anim_config = animation.get(anim_key)
            if not anim_config:
                continue
            
            trigger = anim_config.get("trigger", {})
            if trigger.get("type") != "word":
                continue
            
            # Skip if already has markerId
            if trigger.get("markerId"):
                continue
            
            char_start = trigger.get("charStart")
            char_end = trigger.get("charEnd")
            word_text = trigger.get("wordText", "")
            
            # Create GlobalMarker
            marker_id = uuid.uuid4()
            marker_name = f"Migrated: '{word_text[:20]}'" if word_text else "Migrated marker"
            
            global_marker = GlobalMarker(
                id=marker_id,
                slide_id=slide_id,
                name=marker_name,
            )
            db.add(global_marker)
            markers_created += 1
            
            # Create MarkerPosition for base language
            # Try to compute time from existing normalized script
            time_seconds = None
            result = await db.execute(
                select(NormalizedScript)
                .where(NormalizedScript.slide_id == slide_id)
                .where(NormalizedScript.lang == base_lang)
            )
            norm_script = result.scalar_one_or_none()
            
            if norm_script and norm_script.word_timings and char_start is not None:
                for wt in norm_script.word_timings:
                    if wt.get("charStart") == char_start:
                        time_seconds = wt.get("startTime")
                        break
            
            marker_position = MarkerPosition(
                id=uuid.uuid4(),
                marker_id=marker_id,
                lang=base_lang,
                char_start=char_start,
                char_end=char_end,
                time_seconds=time_seconds,
                source=MarkerSource.AUTO,
            )
            db.add(marker_position)
            
            # Update trigger to use markerId
            trigger["markerId"] = str(marker_id)
            anim_config["trigger"] = trigger
            triggers_migrated += 1
            
            # Record token insertion position
            if char_start is not None:
                token_insertions.append((str(marker_id), char_start))
    
    # Update scene with modified layers
    if triggers_migrated > 0:
        scene.layers = layers
        scene.updated_at = datetime.utcnow()
        # JSON columns are not mutable-tracked by default; ensure changes are persisted.
        flag_modified(scene, "layers")
    
    # Insert marker tokens into base script
    tokens_inserted = 0
    if token_insertions:
        # Sort by position descending
        token_insertions.sort(key=lambda x: x[1], reverse=True)
        
        updated_text = base_script.text
        for marker_id, pos in token_insertions:
            token = format_marker_token(marker_id)
            if token not in updated_text:  # Don't insert duplicates
                updated_text = updated_text[:pos] + token + updated_text[pos:]
                tokens_inserted += 1
        
        if tokens_inserted > 0:
            base_script.text = updated_text
    
    # Mark other languages as needing retranslation
    needs_retranslate = []
    result = await db.execute(
        select(SlideScript)
        .where(SlideScript.slide_id == slide_id)
        .where(SlideScript.lang != base_lang)
    )
    other_scripts = result.scalars().all()
    
    for script in other_scripts:
        if script.text and markers_created > 0:
            # Check if script has marker tokens
            if not contains_marker_tokens(script.text):
                script.needs_retranslate = True
                needs_retranslate.append(script.lang)
    
    await db.flush()
    
    return {
        "markers_created": markers_created,
        "triggers_migrated": triggers_migrated,
        "tokens_inserted": tokens_inserted,
        "needs_retranslate": needs_retranslate,
    }

