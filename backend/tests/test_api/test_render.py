"""
Tests for Render and Export API routes
"""
import uuid
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Project, ProjectVersion, RenderJob, Slide, SlideScript,
    JobType, JobStatus
)


class TestRenderAPI:
    """Tests for render endpoints"""
    
    @pytest.mark.asyncio
    async def test_render_video_version_not_found(self, client: AsyncClient):
        """Test rendering with non-existent version"""
        fake_project_id = uuid.uuid4()
        fake_version_id = uuid.uuid4()
        
        response = await client.post(
            f"/api/render/projects/{fake_project_id}/versions/{fake_version_id}/render",
            params={"lang": "en"}
        )
        
        assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_render_video_success(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion
    ):
        """Test successful render job creation"""
        with patch("app.workers.tasks.render_language_task") as mock_render:
            # render endpoint uses apply_async with task_id == job_id
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
            data = response.json()
            
            assert "job_id" in data
            assert data["task_id"] == data["job_id"]
            assert data["lang"] == "en"
            assert data["status"] == "queued"
    
    @pytest.mark.asyncio
    async def test_render_all_languages_no_scripts(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion
    ):
        """Test rendering all languages when no scripts exist"""
        with patch("app.workers.tasks.render_language_task"):
            response = await client.post(
                f"/api/render/projects/{sample_project.id}/versions/{sample_version.id}/render_all"
            )
        
        assert response.status_code == 400
        assert "no scripts" in response.json()["detail"].lower()
    
    @pytest.mark.asyncio
    async def test_render_all_languages_success(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion,
        sample_slide: Slide,
        sample_script: SlideScript
    ):
        """Test rendering all languages with scripts"""
        with patch("app.workers.tasks.render_language_task") as mock_render:
            def _apply_async(*args, **kwargs):
                t = MagicMock()
                t.id = kwargs.get("task_id")
                return t

            mock_render.apply_async.side_effect = _apply_async
            
            response = await client.post(
                f"/api/render/projects/{sample_project.id}/versions/{sample_version.id}/render_all"
            )
            
            assert response.status_code == 200
            data = response.json()
            
            assert "jobs" in data
            assert len(data["jobs"]) >= 1
            assert data["languages_count"] >= 1


class TestJobsAPI:
    """Tests for job status endpoints"""
    
    @pytest.mark.asyncio
    async def test_get_job_status(
        self,
        client: AsyncClient,
        sample_render_job: RenderJob
    ):
        """Test getting job status"""
        response = await client.get(f"/api/render/jobs/{sample_render_job.id}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["id"] == str(sample_render_job.id)
        assert data["job_type"] == "render"
        assert data["status"] == "queued"
        assert "progress_pct" in data
    
    @pytest.mark.asyncio
    async def test_get_job_not_found(self, client: AsyncClient):
        """Test getting non-existent job"""
        fake_id = uuid.uuid4()
        response = await client.get(f"/api/render/jobs/{fake_id}")
        
        assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_list_project_jobs_empty(
        self,
        client: AsyncClient,
        sample_project: Project
    ):
        """Test listing jobs when none exist"""
        response = await client.get(f"/api/render/projects/{sample_project.id}/jobs")
        
        assert response.status_code == 200
        assert response.json() == []
    
    @pytest.mark.asyncio
    async def test_list_project_jobs(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_render_job: RenderJob
    ):
        """Test listing project jobs"""
        response = await client.get(f"/api/render/projects/{sample_project.id}/jobs")
        
        assert response.status_code == 200
        data = response.json()
        
        assert len(data) >= 1
        assert data[0]["job_type"] == "render"
    
    @pytest.mark.asyncio
    async def test_list_project_jobs_with_limit(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_render_job: RenderJob,
        db_session: AsyncSession
    ):
        """Test listing jobs with limit parameter"""
        # Create more jobs
        for i in range(5):
            job = RenderJob(
                project_id=sample_project.id,
                version_id=sample_render_job.version_id,
                lang="en",
                job_type=JobType.RENDER,
                status=JobStatus.QUEUED,
            )
            db_session.add(job)
        await db_session.commit()
        
        response = await client.get(
            f"/api/render/projects/{sample_project.id}/jobs",
            params={"limit": 3}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert len(data) <= 3


class TestCancelAllProjectJobsAPI:
    """Tests for cancelling all jobs for a project"""

    @pytest.mark.asyncio
    async def test_cancel_all_project_jobs_none(
        self,
        client: AsyncClient,
        sample_project: Project
    ):
        response = await client.post(f"/api/render/projects/{sample_project.id}/jobs/cancel_all")
        assert response.status_code == 200
        data = response.json()
        assert data["project_id"] == str(sample_project.id)
        assert data["cancelled_count"] == 0

    @pytest.mark.asyncio
    async def test_cancel_all_project_jobs_success(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_render_job: RenderJob,
        db_session: AsyncSession
    ):
        # Make job cancellable
        sample_render_job.status = JobStatus.RUNNING
        await db_session.commit()

        with patch("app.api.routes.render.celery_app") as mock_celery:
            mock_celery.control.revoke = MagicMock()

            response = await client.post(
                f"/api/render/projects/{sample_project.id}/jobs/cancel_all"
            )

            assert response.status_code == 200
            data = response.json()
            assert data["cancelled_count"] == 1
            assert str(sample_render_job.id) in data["cancelled_job_ids"]
            mock_celery.control.revoke.assert_called_with(
                str(sample_render_job.id), terminate=True, signal="SIGTERM"
            )

        # Verify DB update
        await db_session.refresh(sample_render_job)
        assert sample_render_job.status == JobStatus.FAILED
        assert "project cancel" in (sample_render_job.error_message or "").lower()


class TestExportsAPI:
    """Tests for exports endpoints"""
    
    @pytest.mark.asyncio
    async def test_list_exports_empty(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion
    ):
        """Test listing exports when none exist"""
        response = await client.get(
            f"/api/render/projects/{sample_project.id}/versions/{sample_version.id}/exports"
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["exports"] == []
    
    @pytest.mark.asyncio
    async def test_list_exports_with_files(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion,
        tmp_path
    ):
        """Test listing exports when files exist"""
        # Mock settings.DATA_DIR
        with patch("app.api.routes.render.settings") as mock_settings:
            # Create export directory structure
            exports_dir = tmp_path / str(sample_project.id) / "versions" / str(sample_version.id) / "exports" / "en"
            exports_dir.mkdir(parents=True)
            
            # Create export files
            (exports_dir / "deck_en.mp4").write_bytes(b"video data" * 1000)
            (exports_dir / "deck_en.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nHello")
            
            mock_settings.DATA_DIR = tmp_path
            
            response = await client.get(
                f"/api/render/projects/{sample_project.id}/versions/{sample_version.id}/exports"
            )
            
            assert response.status_code == 200
            data = response.json()
            
            assert len(data["exports"]) == 1
            assert data["exports"][0]["lang"] == "en"
            assert len(data["exports"][0]["files"]) == 2
    
    @pytest.mark.asyncio
    async def test_list_exports_filter_by_lang(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion,
        tmp_path,
        db_session: AsyncSession
    ):
        """Test filtering exports by language"""
        with patch("app.api.routes.render.settings") as mock_settings:
            # Create export directories for multiple languages
            for lang in ["en", "ru", "es"]:
                exports_dir = tmp_path / str(sample_project.id) / "versions" / str(sample_version.id) / "exports" / lang
                exports_dir.mkdir(parents=True)
                (exports_dir / f"deck_{lang}.mp4").write_bytes(b"video")
            
            mock_settings.DATA_DIR = tmp_path

            # Enable languages on the project (per-project allowlist)
            sample_project.allowed_languages = ["en", "ru", "es"]
            await db_session.commit()
            
            response = await client.get(
                f"/api/render/projects/{sample_project.id}/versions/{sample_version.id}/exports",
                params={"lang": "ru"}
            )
            
            assert response.status_code == 200
            data = response.json()
            
            assert len(data["exports"]) == 1
            assert data["exports"][0]["lang"] == "ru"


class TestDownloadExport:
    """Tests for download endpoint"""
    
    @pytest.mark.asyncio
    async def test_download_export_not_found(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion
    ):
        """Test downloading non-existent file"""
        with patch("app.api.routes.render.settings") as mock_settings:
            mock_settings.DATA_DIR = Path("/nonexistent")
            
            response = await client.get(
                f"/api/render/projects/{sample_project.id}/versions/{sample_version.id}/download/en/deck_en.mp4"
            )
            
            assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_download_export_success(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion,
        tmp_path
    ):
        """Test successful file download"""
        with patch("app.api.routes.render.settings") as mock_settings:
            # Create export file
            exports_dir = tmp_path / str(sample_project.id) / "versions" / str(sample_version.id) / "exports" / "en"
            exports_dir.mkdir(parents=True)
            
            video_file = exports_dir / "deck_en.mp4"
            video_file.write_bytes(b"video content")
            
            mock_settings.DATA_DIR = tmp_path
            
            response = await client.get(
                f"/api/render/projects/{sample_project.id}/versions/{sample_version.id}/download/en/deck_en.mp4"
            )
            
            assert response.status_code == 200
            assert response.headers["content-type"] == "video/mp4"
    
    @pytest.mark.asyncio
    async def test_download_srt_content_type(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion,
        tmp_path
    ):
        """Test correct content type for SRT files"""
        with patch("app.api.routes.render.settings") as mock_settings:
            exports_dir = tmp_path / str(sample_project.id) / "versions" / str(sample_version.id) / "exports" / "en"
            exports_dir.mkdir(parents=True)
            
            srt_file = exports_dir / "deck_en.srt"
            srt_file.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello")
            
            mock_settings.DATA_DIR = tmp_path
            
            response = await client.get(
                f"/api/render/projects/{sample_project.id}/versions/{sample_version.id}/download/en/deck_en.srt"
            )
            
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/plain; charset=utf-8"


class TestJobStatusUpdates:
    """Tests for job with different statuses"""
    
    @pytest.mark.asyncio
    async def test_job_with_progress(
        self,
        client: AsyncClient,
        sample_render_job: RenderJob,
        db_session: AsyncSession
    ):
        """Test job with progress updates"""
        sample_render_job.status = JobStatus.RUNNING
        sample_render_job.progress_pct = 50
        await db_session.commit()
        
        response = await client.get(f"/api/render/jobs/{sample_render_job.id}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "running"
        assert data["progress_pct"] == 50
    
    @pytest.mark.asyncio
    async def test_job_with_error(
        self,
        client: AsyncClient,
        sample_render_job: RenderJob,
        db_session: AsyncSession
    ):
        """Test failed job with error message"""
        sample_render_job.status = JobStatus.FAILED
        sample_render_job.error_message = "Render failed: out of memory"
        await db_session.commit()
        
        response = await client.get(f"/api/render/jobs/{sample_render_job.id}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "failed"
        assert "out of memory" in data["error_message"]
    
    @pytest.mark.asyncio
    async def test_completed_job_with_output(
        self,
        client: AsyncClient,
        sample_render_job: RenderJob,
        db_session: AsyncSession
    ):
        """Test completed job with output download URLs"""
        sample_render_job.status = JobStatus.DONE
        sample_render_job.progress_pct = 100
        sample_render_job.output_video_path = "/data/exports/deck_en.mp4"
        sample_render_job.output_srt_path = "/data/exports/deck_en.srt"
        await db_session.commit()
        
        response = await client.get(f"/api/render/jobs/{sample_render_job.id}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "done"
        assert data["progress_pct"] == 100
        assert data["download_video_url"] is not None
        assert "deck_en.mp4" in data["download_video_url"]
        assert data["download_srt_url"] is not None
        assert "deck_en.srt" in data["download_srt_url"]

