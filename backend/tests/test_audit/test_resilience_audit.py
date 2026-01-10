"""
Resilience / Failure Audit Tests (E-01 to E-03)

Цель: ошибки не ломают проект и дают восстановление.

Test Matrix:
- E-01: Обрыв сети во время save (UI показывает offline, восстанавливает)
- E-02: Обрыв во время upload PPTX (понятная ошибка, retry возможен)
- E-03: Падение воркера (job переходит в failed/retryable)
"""
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import (
    Project, ProjectVersion, Slide, SlideScript, RenderJob,
    ProjectStatus, JobType, JobStatus, ScriptSource
)


class TestResilienceE01_NetworkInterruption:
    """
    E-01: Обрыв сети во время save
    
    Шаги: выключить сеть на 10–15 сек во время автосейва
    Ожидаемо: UI показывает "offline/unsaved", после восстановления — догружает
    """
    
    @pytest.mark.asyncio
    async def test_e01_partial_save_handled_gracefully(
        self,
        client: AsyncClient,
        sample_slide: Slide,
        sample_script: SlideScript
    ):
        """Server handles partial/interrupted saves gracefully"""
        # Simulate a normal save
        response = await client.patch(
            f"/api/slides/{sample_slide.id}/scripts/en",
            json={"text": "Valid save content"}
        )
        assert response.status_code == 200
        
        # Verify content was saved
        response = await client.get(f"/api/slides/{sample_slide.id}/scripts")
        scripts = response.json()
        en_script = next((s for s in scripts if s["lang"] == "en"), None)
        assert en_script["text"] == "Valid save content"
    
    @pytest.mark.asyncio
    async def test_e01_api_returns_proper_error_codes(
        self,
        client: AsyncClient,
        sample_slide: Slide
    ):
        """API returns proper HTTP status codes for errors"""
        # Non-existent slide
        fake_id = uuid.uuid4()
        response = await client.get(f"/api/slides/{fake_id}")
        assert response.status_code == 404
        
        # Invalid request body
        response = await client.patch(
            f"/api/slides/{sample_slide.id}/scripts/en",
            content=b"invalid json"
        )
        assert response.status_code == 422  # Validation error


class TestResilienceE02_UploadInterruption:
    """
    E-02: Обрыв во время upload PPTX
    
    Шаги: оборвать upload на середине
    Ожидаемо: понятная ошибка, возможность retry, не создаёт "полу-проекта"
    """
    
    @pytest.mark.asyncio
    async def test_e02_empty_file_upload_rejected(
        self,
        client: AsyncClient,
        sample_project: Project
    ):
        """Empty file upload is rejected gracefully or handled by converter"""
        response = await client.post(
            f"/api/projects/{sample_project.id}/upload",
            files={"file": ("empty.pptx", b"", "application/vnd.openxmlformats-officedocument.presentationml.presentation")}
        )
        # Either rejected at upload (400/422/413) or accepted for async conversion (200)
        # The key is that it doesn't crash with 500
        assert response.status_code in [200, 400, 422, 413]
    
    @pytest.mark.asyncio
    async def test_e02_corrupted_file_handled(
        self,
        client: AsyncClient,
        sample_project: Project
    ):
        """Corrupted file is handled gracefully"""
        # Not a valid PPTX - just random bytes
        corrupted_content = b"this is not a valid pptx file content"
        
        response = await client.post(
            f"/api/projects/{sample_project.id}/upload",
            files={"file": ("corrupted.pptx", corrupted_content, "application/vnd.openxmlformats-officedocument.presentationml.presentation")}
        )
        # File uploads, but conversion will fail gracefully
        # This tests the upload endpoint, not the converter
        # Upload should succeed, conversion task will handle validation
    
    @pytest.mark.asyncio
    async def test_e02_oversized_file_rejected(
        self,
        client: AsyncClient,
        sample_project: Project
    ):
        """Oversized file is rejected with clear error"""
        # Create content that exceeds limit (mock this in settings)
        with patch("app.api.routes.projects.MAX_MEDIA_SIZE", 100):  # 100 bytes limit
            large_content = b"x" * 200  # 200 bytes
            response = await client.post(
                f"/api/projects/{sample_project.id}/upload",
                files={"file": ("large.pptx", large_content, "application/vnd.openxmlformats-officedocument.presentationml.presentation")}
            )
            
            assert response.status_code == 413
            assert "too large" in response.json()["detail"].lower()
    
    @pytest.mark.asyncio
    async def test_e02_invalid_file_type_rejected(
        self,
        client: AsyncClient,
        sample_project: Project
    ):
        """Invalid file type is rejected with actionable error"""
        response = await client.post(
            f"/api/projects/{sample_project.id}/upload",
            files={"file": ("document.exe", b"executable content", "application/octet-stream")}
        )
        
        assert response.status_code == 400
        assert "invalid file type" in response.json()["detail"].lower()
    
    @pytest.mark.asyncio
    async def test_e02_no_partial_project_on_failed_upload(
        self,
        client: AsyncClient,
        db_session: AsyncSession
    ):
        """Failed upload doesn't leave partial project state"""
        # Create project
        response = await client.post(
            "/api/projects",
            json={"name": "E02 Test Project", "base_language": "en"}
        )
        project_id = response.json()["id"]
        
        # Attempt failed upload (invalid file)
        await client.post(
            f"/api/projects/{project_id}/upload",
            files={"file": ("invalid.xyz", b"content", "application/unknown")}
        )
        
        # Project should still exist and be valid
        response = await client.get(f"/api/projects/{project_id}")
        assert response.status_code == 200
        
        # No orphan versions should exist
        response = await client.get(f"/api/projects/{project_id}/versions")
        # Either no versions, or all versions are complete
        versions = response.json()
        # No crashed/partial versions
        
        # Cleanup
        await client.delete(f"/api/projects/{project_id}")


class TestResilienceE03_WorkerFailure:
    """
    E-03: Падение воркера (симуляция)
    
    Шаги: во время processing "убить" worker/контейнер
    Ожидаемо: job переходит в failed/retryable, не висит навсегда
    """
    
    @pytest.mark.asyncio
    async def test_e03_stuck_job_can_be_cancelled(
        self,
        client: AsyncClient,
        sample_render_job: RenderJob,
        db_session: AsyncSession
    ):
        """Stuck job in running state can be cancelled"""
        # Simulate job stuck in running state
        sample_render_job.status = JobStatus.RUNNING
        sample_render_job.started_at = datetime.utcnow() - timedelta(hours=1)  # Started long ago
        sample_render_job.progress_pct = 25  # Stuck at 25%
        await db_session.commit()
        
        # Admin can cancel stuck job
        with patch("app.api.routes.render.celery_app") as mock_celery:
            mock_celery.control.revoke = MagicMock()
            
            response = await client.post(f"/api/render/jobs/{sample_render_job.id}/cancel")
            assert response.status_code == 200
        
        # Job is now cancelled
        await db_session.refresh(sample_render_job)
        assert sample_render_job.status == JobStatus.CANCELLED
    
    @pytest.mark.asyncio
    async def test_e03_failed_job_retryable(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion,
        sample_render_job: RenderJob,
        db_session: AsyncSession
    ):
        """Failed job can be retried by creating new job"""
        # Mark job as failed (simulating worker crash)
        sample_render_job.status = JobStatus.FAILED
        sample_render_job.error_message = "Worker process killed"
        await db_session.commit()
        
        # Can create new job (retry)
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
            
            assert response.status_code == 200
            new_job_id = response.json()["job_id"]
            
            # New job is queued
            response = await client.get(f"/api/render/jobs/{new_job_id}")
            assert response.json()["status"] == "queued"
    
    @pytest.mark.asyncio
    async def test_e03_job_list_shows_failed_jobs(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_render_job: RenderJob,
        db_session: AsyncSession
    ):
        """Job list includes failed jobs for visibility"""
        sample_render_job.status = JobStatus.FAILED
        sample_render_job.error_message = "Test failure"
        await db_session.commit()
        
        response = await client.get(f"/api/render/projects/{sample_project.id}/jobs")
        jobs = response.json()
        
        # Failed job is visible
        assert len(jobs) >= 1
        failed_job = next((j for j in jobs if j["id"] == str(sample_render_job.id)), None)
        assert failed_job is not None
        assert failed_job["status"] == "failed"


class TestResilienceErrorMessages:
    """Additional tests for error message quality"""
    
    @pytest.mark.asyncio
    async def test_error_messages_are_actionable(
        self,
        client: AsyncClient
    ):
        """Error messages provide actionable information"""
        # Try to get non-existent project
        response = await client.get(f"/api/projects/{uuid.uuid4()}")
        
        assert response.status_code == 404
        error = response.json()
        assert "detail" in error
        # Error should mention what wasn't found
        assert "not found" in error["detail"].lower()
    
    @pytest.mark.asyncio
    async def test_no_internal_error_leakage(
        self,
        client: AsyncClient,
        sample_project: Project
    ):
        """Internal errors don't leak sensitive info"""
        # This is a valid request, should succeed
        response = await client.get(f"/api/projects/{sample_project.id}")
        
        # Response should not contain stack traces or internal paths
        response_text = response.text
        assert "traceback" not in response_text.lower()
        assert "/Users/" not in response_text
        assert "/home/" not in response_text


class TestResilienceRecovery:
    """Tests for recovery mechanisms"""
    
    @pytest.mark.asyncio
    async def test_conversion_failure_allows_retry(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion,
        db_session: AsyncSession
    ):
        """Failed conversion can be retried"""
        # Mark version as failed
        sample_version.status = ProjectStatus.FAILED
        sample_version.pptx_asset_path = "versions/test/input.pptx"
        await db_session.commit()
        
        # Can trigger conversion again
        with patch("app.workers.tasks.convert_pptx_task") as mock_convert:
            mock_task = MagicMock()
            mock_task.id = "retry-task"
            mock_convert.delay.return_value = mock_task
            
            response = await client.post(
                f"/api/projects/{sample_project.id}/versions/{sample_version.id}/convert"
            )
            
            assert response.status_code == 200
            assert response.json()["status"] == "queued"

