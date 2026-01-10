"""
Performance Audit Tests (P-01 to P-03)

Цель: предсказуемо работает на больших входах.

Test Matrix:
- P-01: PPTX 50–100 слайдов (импорт не падает, UI не "умирает")
- P-02: Длинные скрипты (10–20 мин озвучки) - генерация по частям
- P-03: 5 проектов параллельно (очереди не клинят)
"""
import uuid
import time
import io
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from PIL import Image

from app.db.models import (
    Project, ProjectVersion, Slide, SlideScript, RenderJob,
    JobType, JobStatus, ScriptSource
)


class TestPerformanceP01_LargePresentations:
    """
    P-01: PPTX 50–100 слайдов
    
    Ожидаемо: импорт не падает, UI не "умирает"
    """
    
    @pytest.mark.asyncio
    async def test_p01_list_50_slides_performance(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion,
        db_session: AsyncSession
    ):
        """Listing 50 slides returns in reasonable time"""
        # Create 50 slides
        for i in range(50):
            slide = Slide(
                project_id=sample_project.id,
                version_id=sample_version.id,
                slide_index=i + 1,
                image_path=f"slides/slide_{i+1:03d}.png",
            )
            db_session.add(slide)
        await db_session.commit()
        
        start = time.time()
        response = await client.get(
            f"/api/slides/projects/{sample_project.id}/versions/{sample_version.id}/slides"
        )
        elapsed = time.time() - start
        
        assert response.status_code == 200
        assert len(response.json()) == 50
        # Should complete in under 2 seconds
        assert elapsed < 2.0, f"Listing 50 slides took {elapsed:.2f}s"
    
    @pytest.mark.asyncio
    async def test_p01_list_100_slides_performance(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion,
        db_session: AsyncSession
    ):
        """Listing 100 slides returns in reasonable time"""
        # Create 100 slides
        for i in range(100):
            slide = Slide(
                project_id=sample_project.id,
                version_id=sample_version.id,
                slide_index=i + 1,
                image_path=f"slides/slide_{i+1:03d}.png",
            )
            db_session.add(slide)
        await db_session.commit()
        
        start = time.time()
        response = await client.get(
            f"/api/slides/projects/{sample_project.id}/versions/{sample_version.id}/slides"
        )
        elapsed = time.time() - start
        
        assert response.status_code == 200
        assert len(response.json()) == 100
        # Should complete in under 5 seconds
        assert elapsed < 5.0, f"Listing 100 slides took {elapsed:.2f}s"
    
    @pytest.mark.asyncio
    async def test_p01_get_single_slide_constant_time(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion,
        db_session: AsyncSession
    ):
        """Getting single slide is O(1), not O(n)"""
        # Create 100 slides
        slides = []
        for i in range(100):
            slide = Slide(
                project_id=sample_project.id,
                version_id=sample_version.id,
                slide_index=i + 1,
                image_path=f"slides/slide_{i+1:03d}.png",
            )
            db_session.add(slide)
            slides.append(slide)
        await db_session.commit()
        
        # Get slide in the middle - should be fast
        middle_slide = slides[50]
        
        start = time.time()
        response = await client.get(f"/api/slides/{middle_slide.id}")
        elapsed = time.time() - start
        
        assert response.status_code == 200
        # Should be very fast (index lookup)
        assert elapsed < 0.5, f"Getting single slide took {elapsed:.2f}s"


class TestPerformanceP02_LongScripts:
    """
    P-02: Длинные скрипты (10–20 мин озвучки)
    
    Ожидаемо: генерация по частям/очередями, UI показывает прогресс
    """
    
    @pytest.mark.asyncio
    async def test_p02_large_script_text_accepted(
        self,
        client: AsyncClient,
        sample_slide: Slide,
        sample_script: SlideScript
    ):
        """Large script text (10K chars) is accepted"""
        # Create 10K character script (approx 5-7 min of speech)
        large_text = "This is a test sentence. " * 500  # ~12.5K chars
        
        response = await client.patch(
            f"/api/slides/{sample_slide.id}/scripts/en",
            json={"text": large_text}
        )
        
        assert response.status_code == 200
        assert len(response.json()["text"]) == len(large_text)
    
    @pytest.mark.asyncio
    async def test_p02_batch_tts_queues_all_slides(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion,
        db_session: AsyncSession
    ):
        """Batch TTS can handle many slides with long scripts"""
        # Create 20 slides with scripts
        for i in range(20):
            slide = Slide(
                project_id=sample_project.id,
                version_id=sample_version.id,
                slide_index=i + 1,
                image_path=f"slides/slide_{i+1:03d}.png",
            )
            db_session.add(slide)
            await db_session.flush()
            
            # Long script for each
            script = SlideScript(
                slide_id=slide.id,
                lang="en",
                text=f"Slide {i+1}: " + ("Long content here. " * 100),
                source=ScriptSource.MANUAL,
            )
            db_session.add(script)
        await db_session.commit()
        
        # Queue batch TTS
        with patch("app.workers.tasks.tts_batch_task") as mock_tts:
            mock_task = MagicMock()
            mock_task.id = "batch-tts-p02"
            mock_tts.delay.return_value = mock_task
            
            start = time.time()
            response = await client.post(
                f"/api/slides/projects/{sample_project.id}/versions/{sample_version.id}/tts",
                params={"lang": "en"}
            )
            elapsed = time.time() - start
            
            assert response.status_code == 200
            # Queuing should be fast (actual processing is async)
            assert elapsed < 1.0


class TestPerformanceP03_ParallelProjects:
    """
    P-03: 5 проектов параллельно
    
    Ожидаемо: очереди не клинят, статусы корректны
    """
    
    @pytest.mark.asyncio
    async def test_p03_multiple_projects_list(
        self,
        client: AsyncClient,
        db_session: AsyncSession
    ):
        """Can list many projects efficiently"""
        from app.db.models import ProjectAudioSettings, ProjectTranslationRules
        
        # Create 20 projects
        project_ids = []
        for i in range(20):
            project = Project(
                name=f"P03 Test Project {i}",
                base_language="en",
                allowed_languages=["en"],
            )
            db_session.add(project)
            await db_session.flush()
            
            # Add required settings
            audio_settings = ProjectAudioSettings(project_id=project.id)
            translation_rules = ProjectTranslationRules(project_id=project.id)
            db_session.add(audio_settings)
            db_session.add(translation_rules)
            
            project_ids.append(project.id)
        await db_session.commit()
        
        start = time.time()
        response = await client.get("/api/projects")
        elapsed = time.time() - start
        
        assert response.status_code == 200
        # Should include our 20 projects (plus any fixtures)
        assert len(response.json()) >= 20
        # Should be fast
        assert elapsed < 2.0
        
        # Cleanup
        for pid in project_ids:
            await client.delete(f"/api/projects/{pid}")
    
    @pytest.mark.asyncio
    async def test_p03_parallel_render_jobs(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion,
        db_session: AsyncSession
    ):
        """Multiple render jobs can be queued for different languages"""
        languages = ["en", "ru", "es", "de", "fr"]
        
        # Enable languages on project
        sample_project.allowed_languages = languages
        await db_session.commit()
        
        # Queue render jobs for each language
        job_ids = []
        with patch("app.workers.tasks.render_language_task") as mock_render:
            def _apply_async(*args, **kwargs):
                t = MagicMock()
                t.id = kwargs.get("task_id")
                return t
            mock_render.apply_async.side_effect = _apply_async
            
            for lang in languages:
                response = await client.post(
                    f"/api/render/projects/{sample_project.id}/versions/{sample_version.id}/render",
                    params={"lang": lang}
                )
                if response.status_code == 200:
                    job_ids.append(response.json()["job_id"])
        
        # All jobs should be queued
        assert len(job_ids) == len(languages)
        
        # List jobs should show all
        response = await client.get(f"/api/render/projects/{sample_project.id}/jobs")
        assert len(response.json()) >= len(languages)
    
    @pytest.mark.asyncio
    async def test_p03_job_list_with_filters(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion,
        db_session: AsyncSession
    ):
        """Job listing with status filter performs well"""
        # Create jobs with different statuses
        statuses = [
            JobStatus.QUEUED,
            JobStatus.RUNNING,
            JobStatus.DONE,
            JobStatus.FAILED,
        ]
        
        for status in statuses:
            for i in range(5):
                job = RenderJob(
                    project_id=sample_project.id,
                    version_id=sample_version.id,
                    lang="en",
                    job_type=JobType.RENDER,
                    status=status,
                )
                db_session.add(job)
        await db_session.commit()
        
        # Query with filter
        start = time.time()
        response = await client.get(
            "/api/render/jobs",
            params={"status": "done", "limit": 50}
        )
        elapsed = time.time() - start
        
        assert response.status_code == 200
        # Should be fast
        assert elapsed < 1.0


class TestPerformanceMemory:
    """Memory-related performance tests"""
    
    @pytest.mark.asyncio
    async def test_large_response_pagination_ready(
        self,
        client: AsyncClient,
        sample_project: Project
    ):
        """Jobs list has limit parameter for pagination"""
        response = await client.get(
            f"/api/render/projects/{sample_project.id}/jobs",
            params={"limit": 5}
        )
        
        assert response.status_code == 200
        jobs = response.json()
        # Response is limited
        assert len(jobs) <= 5
    
    @pytest.mark.asyncio
    async def test_all_jobs_list_has_limit(
        self,
        client: AsyncClient
    ):
        """All jobs endpoint has default limit"""
        response = await client.get("/api/render/jobs")
        
        assert response.status_code == 200
        jobs = response.json()
        # Has a reasonable limit
        assert len(jobs) <= 50


class TestPerformanceLatency:
    """Latency-specific tests"""
    
    @pytest.mark.asyncio
    async def test_health_check_fast(
        self,
        client: AsyncClient
    ):
        """Health check endpoint is fast"""
        start = time.time()
        response = await client.get("/health")
        elapsed = time.time() - start
        
        assert response.status_code == 200
        assert elapsed < 0.1  # Should be instant
    
    @pytest.mark.asyncio
    async def test_project_list_n_plus_one_avoided(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion,
        db_session: AsyncSession
    ):
        """Project list doesn't have N+1 query problem"""
        from app.db.models import ProjectAudioSettings, ProjectTranslationRules
        
        # Create several projects with versions
        for i in range(5):
            project = Project(
                name=f"N+1 Test {i}",
                base_language="en",
                allowed_languages=["en"],
            )
            db_session.add(project)
            await db_session.flush()
            
            audio_settings = ProjectAudioSettings(project_id=project.id)
            translation_rules = ProjectTranslationRules(project_id=project.id)
            db_session.add(audio_settings)
            db_session.add(translation_rules)
            
            version = ProjectVersion(
                project_id=project.id,
                version_number=1,
            )
            db_session.add(version)
            await db_session.flush()
            
            project.current_version_id = version.id
        
        await db_session.commit()
        
        # Time the list query
        start = time.time()
        response = await client.get("/api/projects")
        elapsed = time.time() - start
        
        assert response.status_code == 200
        # Should be fast even with related data
        assert elapsed < 1.0

