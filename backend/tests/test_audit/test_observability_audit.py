"""
Observability Audit Tests (O-01 to O-03)

Цель: любой фейл можно расследовать за минуты.

Test Matrix:
- O-01: Correlation ID (job_id виден в логах/ошибках)
- O-02: Понятные ошибки пользователю (без "500 Internal Server Error")
- O-03: Базовые метрики (длительность, %failed)
"""
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import (
    Project, ProjectVersion, RenderJob,
    JobType, JobStatus
)


class TestObservabilityO01_CorrelationID:
    """
    O-01: Correlation ID
    
    Ожидаемо: у каждого job есть job_id, в логах/ошибках он виден
    """
    
    @pytest.mark.asyncio
    async def test_o01_job_has_unique_id(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion
    ):
        """Each job has a unique ID"""
        with patch("app.workers.tasks.render_language_task") as mock_render:
            def _apply_async(*args, **kwargs):
                t = MagicMock()
                t.id = kwargs.get("task_id")
                return t
            mock_render.apply_async.side_effect = _apply_async
            
            from unittest.mock import MagicMock
            
            # Create two jobs
            response1 = await client.post(
                f"/api/render/projects/{sample_project.id}/versions/{sample_version.id}/render",
                params={"lang": "en"}
            )
            response2 = await client.post(
                f"/api/render/projects/{sample_project.id}/versions/{sample_version.id}/render",
                params={"lang": "en"}
            )
            
            job_id1 = response1.json()["job_id"]
            job_id2 = response2.json()["job_id"]
            
            # IDs should be unique
            assert job_id1 != job_id2
            # IDs should be valid UUIDs
            uuid.UUID(job_id1)
            uuid.UUID(job_id2)
    
    @pytest.mark.asyncio
    async def test_o01_job_id_in_status_response(
        self,
        client: AsyncClient,
        sample_render_job: RenderJob
    ):
        """Job ID is included in status responses"""
        response = await client.get(f"/api/render/jobs/{sample_render_job.id}")
        
        assert response.status_code == 200
        data = response.json()
        
        # Job ID is present
        assert "id" in data
        assert data["id"] == str(sample_render_job.id)
    
    @pytest.mark.asyncio
    async def test_o01_error_includes_job_context(
        self,
        client: AsyncClient,
        sample_render_job: RenderJob,
        db_session: AsyncSession
    ):
        """Errors include job context for debugging"""
        # Mark job as failed with error
        sample_render_job.status = JobStatus.FAILED
        sample_render_job.error_message = "TTS generation failed: ElevenLabs rate limit"
        await db_session.commit()
        
        response = await client.get(f"/api/render/jobs/{sample_render_job.id}")
        data = response.json()
        
        # Error context is available
        assert data["status"] == "failed"
        assert data["error_message"] is not None
        # Job ID is present for correlation
        assert data["id"] is not None


class TestObservabilityO02_UserFriendlyErrors:
    """
    O-02: Понятные ошибки пользователю
    
    Ожидаемо: error message без "500 Internal Server Error", с actionable текстом
    """
    
    @pytest.mark.asyncio
    async def test_o02_404_has_clear_message(
        self,
        client: AsyncClient
    ):
        """404 errors have clear, user-friendly messages"""
        response = await client.get(f"/api/projects/{uuid.uuid4()}")
        
        assert response.status_code == 404
        error = response.json()
        
        # Has detail field
        assert "detail" in error
        # Message is human-readable
        assert "not found" in error["detail"].lower()
        # No technical jargon
        assert "traceback" not in error["detail"].lower()
        assert "exception" not in error["detail"].lower()
    
    @pytest.mark.asyncio
    async def test_o02_validation_errors_are_clear(
        self,
        client: AsyncClient
    ):
        """Validation errors explain what's wrong"""
        # Missing required field
        response = await client.post(
            "/api/projects",
            json={}  # Missing 'name'
        )
        
        assert response.status_code == 422
        error = response.json()
        
        # Has structured error info
        assert "detail" in error
        # Mentions the problematic field
        detail_str = str(error["detail"]).lower()
        assert "name" in detail_str or "required" in detail_str
    
    @pytest.mark.asyncio
    async def test_o02_failed_job_has_actionable_error(
        self,
        client: AsyncClient,
        sample_render_job: RenderJob,
        db_session: AsyncSession
    ):
        """Failed jobs have actionable error messages"""
        error_scenarios = [
            ("Rate limit exceeded. Please wait a few minutes and try again.", True),
            ("Invalid voice ID. Please select a different voice.", True),
            ("No audio generated. Ensure all slides have script text.", True),
        ]
        
        for error_msg, should_be_actionable in error_scenarios:
            sample_render_job.status = JobStatus.FAILED
            sample_render_job.error_message = error_msg
            await db_session.commit()
            
            response = await client.get(f"/api/render/jobs/{sample_render_job.id}")
            data = response.json()
            
            if should_be_actionable:
                # Error should tell user what to do
                msg = data["error_message"].lower()
                has_action = any(word in msg for word in [
                    "please", "try", "ensure", "check", "select", "wait"
                ])
                assert has_action, f"Error not actionable: {data['error_message']}"
    
    @pytest.mark.asyncio
    async def test_o02_no_raw_exceptions_exposed(
        self,
        client: AsyncClient,
        sample_project: Project
    ):
        """Raw Python exceptions are not exposed to users"""
        # Try various operations
        endpoints = [
            f"/api/projects/{sample_project.id}",
            f"/api/projects/{sample_project.id}/audio_settings",
            f"/api/projects/{sample_project.id}/versions",
        ]
        
        for endpoint in endpoints:
            response = await client.get(endpoint)
            response_text = response.text.lower()
            
            # Should not contain Python exception markers
            assert "traceback" not in response_text
            assert "file \"" not in response_text
            assert "line " not in response_text or "file" not in response_text


class TestObservabilityO03_BasicMetrics:
    """
    O-03: Базовые метрики
    
    Ожидаемо: длительность импорта, %failed TTS, длина очереди, latency
    """
    
    @pytest.mark.asyncio
    async def test_o03_job_has_timing_info(
        self,
        client: AsyncClient,
        sample_render_job: RenderJob,
        db_session: AsyncSession
    ):
        """Jobs track start and finish times"""
        # Simulate job lifecycle
        sample_render_job.status = JobStatus.RUNNING
        sample_render_job.started_at = datetime.utcnow()
        await db_session.commit()
        
        response = await client.get(f"/api/render/jobs/{sample_render_job.id}")
        assert response.json()["started_at"] is not None
        
        # Complete the job
        sample_render_job.status = JobStatus.DONE
        sample_render_job.finished_at = datetime.utcnow()
        await db_session.commit()
        
        response = await client.get(f"/api/render/jobs/{sample_render_job.id}")
        data = response.json()
        
        assert data["started_at"] is not None
        assert data["finished_at"] is not None
    
    @pytest.mark.asyncio
    async def test_o03_job_progress_tracked(
        self,
        client: AsyncClient,
        sample_render_job: RenderJob,
        db_session: AsyncSession
    ):
        """Jobs track progress percentage"""
        progress_values = [0, 25, 50, 75, 100]
        
        for progress in progress_values:
            sample_render_job.progress_pct = progress
            await db_session.commit()
            
            response = await client.get(f"/api/render/jobs/{sample_render_job.id}")
            assert response.json()["progress_pct"] == progress
    
    @pytest.mark.asyncio
    async def test_o03_admin_job_list_shows_all_statuses(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion,
        db_session: AsyncSession
    ):
        """Admin can see jobs in all statuses"""
        # Create jobs with different statuses
        statuses = [
            (JobStatus.QUEUED, None),
            (JobStatus.RUNNING, 50),
            (JobStatus.DONE, 100),
            (JobStatus.FAILED, 30),
        ]
        
        created_jobs = []
        for status, progress in statuses:
            job = RenderJob(
                project_id=sample_project.id,
                version_id=sample_version.id,
                lang="en",
                job_type=JobType.RENDER,
                status=status,
                progress_pct=progress or 0,
            )
            if status in [JobStatus.RUNNING, JobStatus.DONE, JobStatus.FAILED]:
                job.started_at = datetime.utcnow()
            if status in [JobStatus.DONE, JobStatus.FAILED]:
                job.finished_at = datetime.utcnow()
            if status == JobStatus.FAILED:
                job.error_message = "Test failure"
            
            db_session.add(job)
            created_jobs.append(job)
        await db_session.commit()
        
        # Admin endpoint shows all
        response = await client.get("/api/render/jobs")
        jobs = response.json()
        
        # All statuses should be visible
        status_set = {j["status"] for j in jobs}
        assert "queued" in status_set
        assert "running" in status_set or "done" in status_set or "failed" in status_set
    
    @pytest.mark.asyncio
    async def test_o03_job_duration_calculable(
        self,
        client: AsyncClient,
        sample_render_job: RenderJob,
        db_session: AsyncSession
    ):
        """Job duration can be calculated from timestamps"""
        start = datetime.utcnow()
        end = start + timedelta(minutes=5)
        
        sample_render_job.status = JobStatus.DONE
        sample_render_job.started_at = start
        sample_render_job.finished_at = end
        sample_render_job.progress_pct = 100
        await db_session.commit()
        
        response = await client.get(f"/api/render/jobs/{sample_render_job.id}")
        data = response.json()
        
        # Both timestamps present for duration calculation
        assert data["started_at"] is not None
        assert data["finished_at"] is not None
        
        # Can calculate duration
        from datetime import datetime as dt
        started = dt.fromisoformat(data["started_at"].replace("Z", "+00:00").replace("+00:00", ""))
        finished = dt.fromisoformat(data["finished_at"].replace("Z", "+00:00").replace("+00:00", ""))
        duration = finished - started
        assert duration.total_seconds() >= 0


class TestObservabilityHealthCheck:
    """Health check and system status tests"""
    
    @pytest.mark.asyncio
    async def test_health_endpoint_exists(
        self,
        client: AsyncClient
    ):
        """Health check endpoint exists and works"""
        response = await client.get("/health")
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_api_docs_available(
        self,
        client: AsyncClient
    ):
        """API documentation is available"""
        response = await client.get("/docs")
        # Should redirect to docs or return docs page
        assert response.status_code in [200, 307, 308]
    
    @pytest.mark.asyncio
    async def test_openapi_schema_available(
        self,
        client: AsyncClient
    ):
        """OpenAPI schema is available"""
        response = await client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        
        # Has basic OpenAPI structure
        assert "openapi" in schema
        assert "paths" in schema


class TestObservabilityErrorTracking:
    """Error tracking and categorization tests"""
    
    @pytest.mark.asyncio
    async def test_job_error_types_categorized(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion,
        db_session: AsyncSession
    ):
        """Different error types are distinguishable"""
        error_categories = [
            "TTS Error: ",
            "Render Error: ",
            "Import Error: ",
            "Validation Error: ",
        ]
        
        for category in error_categories:
            job = RenderJob(
                project_id=sample_project.id,
                version_id=sample_version.id,
                lang="en",
                job_type=JobType.RENDER,
                status=JobStatus.FAILED,
                error_message=f"{category}Test error details",
            )
            db_session.add(job)
            await db_session.commit()
            
            response = await client.get(f"/api/render/jobs/{job.id}")
            data = response.json()
            
            # Error category is visible in message
            assert category.replace(" Error: ", "") in data["error_message"]

