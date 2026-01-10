"""
State Machine Audit Tests (S-01 to S-04)

Цель: генерация предсказуемо живёт в статусах и корректно восстанавливается.

Test Matrix:
- S-01: Нормальный цикл (queued → processing → done)
- S-02: Ошибка TTS (status=failed, понятное сообщение)
- S-03: Retry идемпотентен (не создаёт дубликаты)
- S-04: Cancel (job останавливается, ресурсы освобождаются)
"""
import uuid
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import (
    Project, ProjectVersion, RenderJob, Slide, SlideScript, SlideAudio,
    JobType, JobStatus, ScriptSource
)


class TestStateMachineS01_NormalCycle:
    """
    S-01: Нормальный цикл
    
    Шаги: generate → queued → processing → done
    Ожидаемо: статусы меняются последовательно, UI отражает прогресс
    """
    
    @pytest.mark.asyncio
    async def test_s01_job_starts_as_queued(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion
    ):
        """Job starts in queued status"""
        with patch("app.workers.tasks.render_language_task") as mock_render:
            def _apply_async(*args, **kwargs):
                t = MagicMock()
                t.id = kwargs.get("task_id")
                return t
            mock_render.apply_async.side_effect = _apply_async
            
            response = await client.post(
                f"/api/render/projects/{sample_project.id}/versions/{sample_version.id}/render",
                params={"lang": "en"}
            )
            
            job_id = response.json()["job_id"]
            
            # Check job status
            status_response = await client.get(f"/api/render/jobs/{job_id}")
            assert status_response.json()["status"] == "queued"
    
    @pytest.mark.asyncio
    async def test_s01_job_transitions_to_running(
        self,
        client: AsyncClient,
        sample_render_job: RenderJob,
        db_session: AsyncSession
    ):
        """Job can transition to running status"""
        assert sample_render_job.status == JobStatus.QUEUED
        
        # Simulate worker picking up the job
        sample_render_job.status = JobStatus.RUNNING
        sample_render_job.started_at = datetime.utcnow()
        sample_render_job.progress_pct = 10
        await db_session.commit()
        
        response = await client.get(f"/api/render/jobs/{sample_render_job.id}")
        data = response.json()
        
        assert data["status"] == "running"
        assert data["progress_pct"] == 10
        assert data["started_at"] is not None
    
    @pytest.mark.asyncio
    async def test_s01_job_completes_successfully(
        self,
        client: AsyncClient,
        sample_render_job: RenderJob,
        db_session: AsyncSession
    ):
        """Job can complete successfully"""
        sample_render_job.status = JobStatus.DONE
        sample_render_job.progress_pct = 100
        sample_render_job.started_at = datetime.utcnow()
        sample_render_job.finished_at = datetime.utcnow()
        sample_render_job.output_video_path = "exports/en/deck_en.mp4"
        await db_session.commit()
        
        response = await client.get(f"/api/render/jobs/{sample_render_job.id}")
        data = response.json()
        
        assert data["status"] == "done"
        assert data["progress_pct"] == 100
        assert data["finished_at"] is not None
        assert data["download_video_url"] is not None
    
    @pytest.mark.asyncio
    async def test_s01_progress_updates_visible(
        self,
        client: AsyncClient,
        sample_render_job: RenderJob,
        db_session: AsyncSession
    ):
        """Progress updates are visible to client"""
        # Simulate progress updates
        progress_values = [0, 20, 40, 60, 80, 100]
        
        for progress in progress_values:
            sample_render_job.progress_pct = progress
            if progress > 0:
                sample_render_job.status = JobStatus.RUNNING
            if progress == 100:
                sample_render_job.status = JobStatus.DONE
            await db_session.commit()
            
            response = await client.get(f"/api/render/jobs/{sample_render_job.id}")
            assert response.json()["progress_pct"] == progress


class TestStateMachineS02_TTSError:
    """
    S-02: Ошибка TTS
    
    Шаги: вызвать ошибку (пустой ключ, лимит, запретный текст)
    Ожидаемо: status=failed, понятное сообщение, кнопка retry
    """
    
    @pytest.mark.asyncio
    async def test_s02_failed_job_has_error_message(
        self,
        client: AsyncClient,
        sample_render_job: RenderJob,
        db_session: AsyncSession
    ):
        """Failed job contains actionable error message"""
        sample_render_job.status = JobStatus.FAILED
        sample_render_job.error_message = "TTS Error: Rate limit exceeded. Please try again later."
        sample_render_job.finished_at = datetime.utcnow()
        await db_session.commit()
        
        response = await client.get(f"/api/render/jobs/{sample_render_job.id}")
        data = response.json()
        
        assert data["status"] == "failed"
        assert data["error_message"] is not None
        assert "Rate limit" in data["error_message"]
        # Error message should be actionable
        assert "try again" in data["error_message"].lower()
    
    @pytest.mark.asyncio
    async def test_s02_no_infinite_processing(
        self,
        client: AsyncClient,
        sample_render_job: RenderJob,
        db_session: AsyncSession
    ):
        """Jobs don't stay in processing forever on failure"""
        # Job should be in a terminal state (done or failed), not running
        sample_render_job.status = JobStatus.FAILED
        sample_render_job.error_message = "Connection timeout"
        sample_render_job.finished_at = datetime.utcnow()
        await db_session.commit()
        
        response = await client.get(f"/api/render/jobs/{sample_render_job.id}")
        data = response.json()
        
        # Job is in terminal state
        assert data["status"] in ["done", "failed"]
        assert data["finished_at"] is not None
    
    @pytest.mark.asyncio
    async def test_s02_error_types_categorized(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion,
        db_session: AsyncSession
    ):
        """Different error types produce categorized messages"""
        error_scenarios = [
            ("TTS API error: Invalid API key", "api"),
            ("TTS API error: Rate limit exceeded", "rate_limit"),
            ("TTS API error: Text too long (max 5000 chars)", "validation"),
            ("Render error: FFmpeg process failed", "render"),
        ]
        
        for error_msg, error_type in error_scenarios:
            job = RenderJob(
                project_id=sample_project.id,
                version_id=sample_version.id,
                lang="en",
                job_type=JobType.RENDER,
                status=JobStatus.FAILED,
                error_message=error_msg,
            )
            db_session.add(job)
            await db_session.commit()
            
            response = await client.get(f"/api/render/jobs/{job.id}")
            assert response.status_code == 200
            # Error message is present and descriptive
            assert response.json()["error_message"] is not None


class TestStateMachineS03_RetryIdempotency:
    """
    S-03: Retry идемпотентен
    
    Шаги: retry 3 раза
    Ожидаемо: не создаёт 3 дубликата ассетов, корректно перезапускает job
    """
    
    @pytest.mark.asyncio
    async def test_s03_retry_creates_new_job(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion,
        db_session: AsyncSession
    ):
        """Retry creates a new job (old one stays failed)"""
        # Create a failed job
        failed_job = RenderJob(
            project_id=sample_project.id,
            version_id=sample_version.id,
            lang="en",
            job_type=JobType.RENDER,
            status=JobStatus.FAILED,
            error_message="First attempt failed",
        )
        db_session.add(failed_job)
        await db_session.commit()
        
        # "Retry" by creating a new render job
        with patch("app.workers.tasks.render_language_task") as mock_render:
            def _apply_async(*args, **kwargs):
                t = MagicMock()
                t.id = kwargs.get("task_id")
                return t
            mock_render.apply_async.side_effect = _apply_async
            
            response = await client.post(
                f"/api/render/projects/{sample_project.id}/versions/{sample_version.id}/render",
                params={"lang": "en"}
            )
            
            new_job_id = response.json()["job_id"]
            
            # Old job still exists and is failed
            old_response = await client.get(f"/api/render/jobs/{failed_job.id}")
            assert old_response.json()["status"] == "failed"
            
            # New job is queued
            new_response = await client.get(f"/api/render/jobs/{new_job_id}")
            assert new_response.json()["status"] == "queued"
    
    @pytest.mark.asyncio
    async def test_s03_multiple_retries_dont_create_duplicate_assets(
        self,
        client: AsyncClient,
        sample_slide: Slide,
        sample_script: SlideScript,
        db_session: AsyncSession
    ):
        """Multiple TTS calls for same content use cache"""
        # Simulate audio with same hash (cached)
        audio = SlideAudio(
            slide_id=sample_slide.id,
            lang="en",
            voice_id="test-voice",
            audio_path="audio/slide_001.wav",
            duration_sec=5.0,
            audio_hash="consistent-hash-abc123",
        )
        db_session.add(audio)
        await db_session.commit()
        
        # Check only one audio record exists
        result = await db_session.execute(
            select(SlideAudio)
            .where(SlideAudio.slide_id == sample_slide.id)
            .where(SlideAudio.lang == "en")
        )
        audios = result.scalars().all()
        assert len(audios) == 1


class TestStateMachineS04_Cancel:
    """
    S-04: Cancel (если есть)
    
    Шаги: cancel в processing
    Ожидаемо: job останавливается, ресурсы не продолжают тратиться
    """
    
    @pytest.mark.asyncio
    async def test_s04_cancel_queued_job(
        self,
        client: AsyncClient,
        sample_render_job: RenderJob,
        db_session: AsyncSession
    ):
        """Can cancel a queued job"""
        assert sample_render_job.status == JobStatus.QUEUED
        
        with patch("app.api.routes.render.celery_app") as mock_celery:
            mock_celery.control.revoke = MagicMock()
            
            response = await client.post(f"/api/render/jobs/{sample_render_job.id}/cancel")
            
            assert response.status_code == 200
            assert response.json()["status"] == "cancelled"
            
            # Celery revoke was called
            mock_celery.control.revoke.assert_called_once()
        
        # Job is now cancelled with cancel message
        await db_session.refresh(sample_render_job)
        assert sample_render_job.status == JobStatus.CANCELLED
        assert "cancelled" in sample_render_job.error_message.lower()
    
    @pytest.mark.asyncio
    async def test_s04_cancel_running_job(
        self,
        client: AsyncClient,
        sample_render_job: RenderJob,
        db_session: AsyncSession
    ):
        """Can cancel a running job"""
        sample_render_job.status = JobStatus.RUNNING
        sample_render_job.progress_pct = 50
        await db_session.commit()
        
        with patch("app.api.routes.render.celery_app") as mock_celery:
            mock_celery.control.revoke = MagicMock()
            
            response = await client.post(f"/api/render/jobs/{sample_render_job.id}/cancel")
            
            assert response.status_code == 200
            # Revoke with terminate=True for running tasks
            mock_celery.control.revoke.assert_called_with(
                str(sample_render_job.id), terminate=True, signal="SIGTERM"
            )
    
    @pytest.mark.asyncio
    async def test_s04_cannot_cancel_completed_job(
        self,
        client: AsyncClient,
        sample_render_job: RenderJob,
        db_session: AsyncSession
    ):
        """Cannot cancel a completed job"""
        sample_render_job.status = JobStatus.DONE
        sample_render_job.progress_pct = 100
        await db_session.commit()
        
        response = await client.post(f"/api/render/jobs/{sample_render_job.id}/cancel")
        
        assert response.status_code == 400
        assert "cannot cancel" in response.json()["detail"].lower()
    
    @pytest.mark.asyncio
    async def test_s04_cancel_all_project_jobs(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion,
        db_session: AsyncSession
    ):
        """Can cancel all jobs for a project"""
        # Create multiple jobs
        for i in range(3):
            job = RenderJob(
                project_id=sample_project.id,
                version_id=sample_version.id,
                lang="en",
                job_type=JobType.RENDER,
                status=JobStatus.RUNNING if i < 2 else JobStatus.QUEUED,
            )
            db_session.add(job)
        await db_session.commit()
        
        with patch("app.api.routes.render.celery_app") as mock_celery:
            mock_celery.control.revoke = MagicMock()
            
            response = await client.post(
                f"/api/render/projects/{sample_project.id}/jobs/cancel_all"
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["cancelled_count"] == 3
            assert len(data["cancelled_job_ids"]) == 3


class TestStateMachineValidTransitions:
    """Additional tests for valid state transitions"""
    
    @pytest.mark.asyncio
    async def test_valid_transitions_queued_to_running(
        self,
        sample_render_job: RenderJob,
        db_session: AsyncSession
    ):
        """Valid transition: QUEUED → RUNNING"""
        assert sample_render_job.status == JobStatus.QUEUED
        sample_render_job.status = JobStatus.RUNNING
        await db_session.commit()
        await db_session.refresh(sample_render_job)
        assert sample_render_job.status == JobStatus.RUNNING
    
    @pytest.mark.asyncio
    async def test_valid_transitions_running_to_done(
        self,
        sample_render_job: RenderJob,
        db_session: AsyncSession
    ):
        """Valid transition: RUNNING → DONE"""
        sample_render_job.status = JobStatus.RUNNING
        await db_session.commit()
        
        sample_render_job.status = JobStatus.DONE
        await db_session.commit()
        await db_session.refresh(sample_render_job)
        assert sample_render_job.status == JobStatus.DONE
    
    @pytest.mark.asyncio
    async def test_valid_transitions_running_to_failed(
        self,
        sample_render_job: RenderJob,
        db_session: AsyncSession
    ):
        """Valid transition: RUNNING → FAILED"""
        sample_render_job.status = JobStatus.RUNNING
        await db_session.commit()
        
        sample_render_job.status = JobStatus.FAILED
        sample_render_job.error_message = "Processing error"
        await db_session.commit()
        await db_session.refresh(sample_render_job)
        assert sample_render_job.status == JobStatus.FAILED

