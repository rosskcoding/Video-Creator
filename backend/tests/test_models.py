"""
Tests for database models
"""
import uuid
from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import (
    Project, ProjectVersion, ProjectAudioSettings, ProjectTranslationRules,
    Slide, SlideScript, SlideAudio, AudioAsset, RenderJob,
    GlobalMarker, MarkerPosition, MarkerSource, RenderCache,
    ProjectStatus, ScriptSource, JobType, JobStatus, DuckingStrength, TranslationStyle
)


class TestProjectModel:
    """Tests for Project model"""
    
    @pytest.mark.asyncio
    async def test_create_project(self, db_session: AsyncSession):
        """Test creating a project"""
        project = Project(
            name="Test Project",
            base_language="en"
        )
        db_session.add(project)
        await db_session.commit()
        
        assert project.id is not None
        assert isinstance(project.id, uuid.UUID)
        assert project.name == "Test Project"
        assert project.base_language == "en"
        assert project.created_at is not None
        assert project.updated_at is not None
    
    @pytest.mark.asyncio
    async def test_project_default_values(self, db_session: AsyncSession):
        """Test project default values"""
        project = Project(name="Defaults Test")
        db_session.add(project)
        await db_session.commit()
        
        assert project.base_language == "en"
        assert project.current_version_id is None
    
    @pytest.mark.asyncio
    async def test_project_relationships(self, db_session: AsyncSession):
        """Test project relationships"""
        project = Project(name="Relations Test")
        db_session.add(project)
        await db_session.commit()
        
        # Add audio settings
        audio_settings = ProjectAudioSettings(project_id=project.id)
        db_session.add(audio_settings)
        
        # Add translation rules
        translation_rules = ProjectTranslationRules(project_id=project.id)
        db_session.add(translation_rules)
        
        await db_session.commit()
        await db_session.refresh(project)
        
        assert project.audio_settings is not None
        assert project.translation_rules is not None


class TestProjectVersionModel:
    """Tests for ProjectVersion model"""
    
    @pytest.mark.asyncio
    async def test_create_version(self, db_session: AsyncSession, sample_project: Project):
        """Test creating a version"""
        version = ProjectVersion(
            project_id=sample_project.id,
            version_number=1,
            status=ProjectStatus.DRAFT,
            comment="Initial version"
        )
        db_session.add(version)
        await db_session.commit()
        
        assert version.id is not None
        assert version.version_number == 1
        assert version.status == ProjectStatus.DRAFT
        assert version.comment == "Initial version"
    
    @pytest.mark.asyncio
    async def test_version_status_transitions(self, db_session: AsyncSession, sample_project: Project):
        """Test version status changes"""
        version = ProjectVersion(
            project_id=sample_project.id,
            version_number=1,
            status=ProjectStatus.DRAFT
        )
        db_session.add(version)
        await db_session.commit()
        
        # Test status transitions
        for status in [ProjectStatus.READY, ProjectStatus.RENDERING, ProjectStatus.DONE]:
            version.status = status
            await db_session.commit()
            assert version.status == status


class TestSlideModel:
    """Tests for Slide model"""
    
    @pytest.mark.asyncio
    async def test_create_slide(
        self,
        db_session: AsyncSession,
        sample_project: Project,
        sample_version: ProjectVersion
    ):
        """Test creating a slide"""
        slide = Slide(
            project_id=sample_project.id,
            version_id=sample_version.id,
            slide_index=1,
            image_path="/data/slides/001.png",
            notes_text="Speaker notes"
        )
        db_session.add(slide)
        await db_session.commit()
        
        assert slide.id is not None
        assert slide.slide_index == 1
        assert slide.notes_text == "Speaker notes"
    
    @pytest.mark.asyncio
    async def test_slide_ordering(
        self,
        db_session: AsyncSession,
        sample_project: Project,
        sample_version: ProjectVersion
    ):
        """Test slide ordering by index"""
        # Create slides out of order
        for i in [3, 1, 2]:
            slide = Slide(
                project_id=sample_project.id,
                version_id=sample_version.id,
                slide_index=i,
                image_path=f"/data/slides/{i:03d}.png"
            )
            db_session.add(slide)
        
        await db_session.commit()
        
        # Query ordered by slide_index
        result = await db_session.execute(
            select(Slide)
            .where(Slide.version_id == sample_version.id)
            .order_by(Slide.slide_index)
        )
        slides = result.scalars().all()
        
        assert len(slides) == 3
        assert [s.slide_index for s in slides] == [1, 2, 3]


class TestGlobalMarkerModel:
    """Tests for EPIC A marker models"""

    @pytest.mark.asyncio
    async def test_create_global_marker_and_position(self, db_session: AsyncSession, sample_slide: Slide):
        gm = GlobalMarker(slide_id=sample_slide.id, name="Anchor")
        db_session.add(gm)
        await db_session.commit()
        await db_session.refresh(gm)

        assert gm.id is not None
        assert gm.slide_id == sample_slide.id

        pos = MarkerPosition(
            marker_id=gm.id,
            lang="en",
            char_start=0,
            char_end=5,
            time_seconds=1.25,
            source=MarkerSource.WORDCLICK,
        )
        db_session.add(pos)
        await db_session.commit()
        await db_session.refresh(pos)

        assert pos.marker_id == gm.id
        assert pos.lang == "en"
        assert pos.time_seconds == pytest.approx(1.25)


class TestRenderCacheModel:
    """Tests for EPIC B render cache model"""

    @pytest.mark.asyncio
    async def test_create_render_cache_entry(self, db_session: AsyncSession, sample_slide: Slide):
        entry = RenderCache(
            slide_id=sample_slide.id,
            lang="en",
            render_key="rk",
            segment_path="cache/segment.webm",
            duration_sec=3.0,
            frame_count=90,
            fps=30,
            width=1920,
            height=1080,
            renderer_version="2.0",
        )
        db_session.add(entry)
        await db_session.commit()
        await db_session.refresh(entry)

        assert entry.id is not None
        assert entry.slide_id == sample_slide.id
        assert entry.duration_sec == pytest.approx(3.0)


class TestSlideScriptModel:
    """Tests for SlideScript model"""
    
    @pytest.mark.asyncio
    async def test_create_script(self, db_session: AsyncSession, sample_slide: Slide):
        """Test creating a script"""
        script = SlideScript(
            slide_id=sample_slide.id,
            lang="en",
            text="Hello world",
            source=ScriptSource.MANUAL
        )
        db_session.add(script)
        await db_session.commit()
        
        assert script.id is not None
        assert script.lang == "en"
        assert script.source == ScriptSource.MANUAL
    
    @pytest.mark.asyncio
    async def test_script_sources(self, db_session: AsyncSession, sample_slide: Slide):
        """Test different script sources"""
        sources = [
            (ScriptSource.MANUAL, "Manual text"),
            (ScriptSource.IMPORTED_NOTES, "From notes"),
            (ScriptSource.TRANSLATED, "Translated text"),
        ]
        
        for source, text in sources:
            script = SlideScript(
                slide_id=sample_slide.id,
                lang=f"{source.value[:2]}",
                text=text,
                source=source
            )
            db_session.add(script)
        
        await db_session.commit()
        
        result = await db_session.execute(
            select(SlideScript).where(SlideScript.slide_id == sample_slide.id)
        )
        scripts = result.scalars().all()
        
        assert len(scripts) == 3
    
    @pytest.mark.asyncio
    async def test_script_translation_meta(self, db_session: AsyncSession, sample_slide: Slide):
        """Test script translation metadata JSON"""
        script = SlideScript(
            slide_id=sample_slide.id,
            lang="ru",
            text="Привет мир",
            source=ScriptSource.TRANSLATED,
            translation_meta_json={
                "model": "gpt-4o",
                "source_lang": "en",
                "source_checksum": "abc123"
            }
        )
        db_session.add(script)
        await db_session.commit()
        await db_session.refresh(script)
        
        assert script.translation_meta_json["model"] == "gpt-4o"


class TestSlideAudioModel:
    """Tests for SlideAudio model"""
    
    @pytest.mark.asyncio
    async def test_create_audio(self, db_session: AsyncSession, sample_slide: Slide):
        """Test creating slide audio"""
        audio = SlideAudio(
            slide_id=sample_slide.id,
            lang="en",
            provider="elevenlabs",
            voice_id="test-voice-123",
            audio_path="/data/audio/slide_001_en.mp3",
            duration_sec=5.5,
            audio_hash="sha256hash"
        )
        db_session.add(audio)
        await db_session.commit()
        
        assert audio.id is not None
        assert audio.duration_sec == 5.5
        assert audio.provider == "elevenlabs"
    
    @pytest.mark.asyncio
    async def test_multiple_audio_per_slide(self, db_session: AsyncSession, sample_slide: Slide):
        """Test multiple audio files for different languages"""
        for lang in ["en", "ru", "es"]:
            audio = SlideAudio(
                slide_id=sample_slide.id,
                lang=lang,
                provider="elevenlabs",
                voice_id=f"voice-{lang}",
                audio_path=f"/data/audio/slide_001_{lang}.mp3",
                duration_sec=5.0,
                audio_hash=f"hash-{lang}"
            )
            db_session.add(audio)
        
        await db_session.commit()
        
        result = await db_session.execute(
            select(SlideAudio).where(SlideAudio.slide_id == sample_slide.id)
        )
        audio_files = result.scalars().all()
        
        assert len(audio_files) == 3


class TestAudioSettingsModel:
    """Tests for ProjectAudioSettings model"""
    
    @pytest.mark.asyncio
    async def test_create_audio_settings(self, db_session: AsyncSession, sample_project: Project):
        """Test creating audio settings"""
        # Audio settings already created by sample_project fixture
        result = await db_session.execute(
            select(ProjectAudioSettings).where(ProjectAudioSettings.project_id == sample_project.id)
        )
        settings = result.scalar_one()
        
        assert settings is not None
        assert settings.background_music_enabled is False  # Default
        assert settings.ducking_strength == DuckingStrength.DEFAULT
    
    @pytest.mark.asyncio
    async def test_audio_settings_ducking_strengths(self, db_session: AsyncSession):
        """Test different ducking strength values"""
        project = Project(name="Ducking Test")
        db_session.add(project)
        await db_session.commit()
        
        for strength in DuckingStrength:
            settings = ProjectAudioSettings(
                project_id=project.id,
                ducking_strength=strength
            )
            # Just test that the value is accepted
            assert settings.ducking_strength == strength


class TestTranslationRulesModel:
    """Tests for ProjectTranslationRules model"""
    
    @pytest.mark.asyncio
    async def test_translation_rules_json_fields(self, db_session: AsyncSession, sample_project: Project):
        """Test JSON fields in translation rules"""
        result = await db_session.execute(
            select(ProjectTranslationRules).where(ProjectTranslationRules.project_id == sample_project.id)
        )
        rules = result.scalar_one()
        
        # Update with complex data
        rules.do_not_translate = ["IFRS", "ESG", "KPI"]
        rules.preferred_translations = [
            {"term": "revenue", "lang": "ru", "translation": "выручка"},
            {"term": "profit", "lang": "ru", "translation": "прибыль"}
        ]
        rules.style = TranslationStyle.FORMAL
        rules.extra_rules = "Use formal business language"
        
        await db_session.commit()
        await db_session.refresh(rules)
        
        assert "IFRS" in rules.do_not_translate
        assert len(rules.preferred_translations) == 2
        assert rules.style == TranslationStyle.FORMAL


class TestRenderJobModel:
    """Tests for RenderJob model"""
    
    @pytest.mark.asyncio
    async def test_create_render_job(
        self,
        db_session: AsyncSession,
        sample_project: Project,
        sample_version: ProjectVersion
    ):
        """Test creating render job"""
        job = RenderJob(
            project_id=sample_project.id,
            version_id=sample_version.id,
            lang="en",
            job_type=JobType.RENDER,
            status=JobStatus.QUEUED
        )
        db_session.add(job)
        await db_session.commit()
        
        assert job.id is not None
        assert job.progress_pct == 0
        assert job.status == JobStatus.QUEUED
    
    @pytest.mark.asyncio
    async def test_job_status_transitions(
        self,
        db_session: AsyncSession,
        sample_project: Project,
        sample_version: ProjectVersion
    ):
        """Test job status transitions"""
        job = RenderJob(
            project_id=sample_project.id,
            version_id=sample_version.id,
            lang="en",
            job_type=JobType.RENDER,
            status=JobStatus.QUEUED
        )
        db_session.add(job)
        await db_session.commit()
        
        # Simulate job progression
        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        await db_session.commit()
        assert job.status == JobStatus.RUNNING
        
        job.progress_pct = 50
        await db_session.commit()
        assert job.progress_pct == 50
        
        job.status = JobStatus.DONE
        job.progress_pct = 100
        job.finished_at = datetime.utcnow()
        job.output_video_path = "/data/exports/video.mp4"
        await db_session.commit()
        
        assert job.status == JobStatus.DONE
        assert job.finished_at > job.started_at
    
    @pytest.mark.asyncio
    async def test_job_types(
        self,
        db_session: AsyncSession,
        sample_project: Project,
        sample_version: ProjectVersion
    ):
        """Test different job types"""
        for job_type in JobType:
            job = RenderJob(
                project_id=sample_project.id,
                version_id=sample_version.id,
                job_type=job_type,
                status=JobStatus.QUEUED
            )
            db_session.add(job)
        
        await db_session.commit()
        
        result = await db_session.execute(
            select(RenderJob).where(RenderJob.project_id == sample_project.id)
        )
        jobs = result.scalars().all()
        
        assert len(jobs) == len(JobType)


class TestCascadeDeletes:
    """Tests for cascade delete behavior"""
    
    @pytest.mark.asyncio
    async def test_project_cascade_delete(self, db_session: AsyncSession):
        """Test that deleting project cascades to related entities"""
        # Create project with all related entities
        project = Project(name="Cascade Test")
        db_session.add(project)
        await db_session.flush()
        
        audio_settings = ProjectAudioSettings(project_id=project.id)
        translation_rules = ProjectTranslationRules(project_id=project.id)
        db_session.add_all([audio_settings, translation_rules])
        
        version = ProjectVersion(
            project_id=project.id,
            version_number=1,
            status=ProjectStatus.DRAFT
        )
        db_session.add(version)
        await db_session.flush()
        
        slide = Slide(
            project_id=project.id,
            version_id=version.id,
            slide_index=1,
            image_path="/test.png"
        )
        db_session.add(slide)
        await db_session.commit()
        
        project_id = project.id
        
        # Delete project
        await db_session.delete(project)
        await db_session.commit()
        
        # Verify cascaded deletes
        result = await db_session.execute(
            select(ProjectVersion).where(ProjectVersion.project_id == project_id)
        )
        assert result.scalar_one_or_none() is None
    
    @pytest.mark.asyncio
    async def test_version_cascade_delete(
        self,
        db_session: AsyncSession,
        sample_project: Project,
        sample_version: ProjectVersion
    ):
        """Test that deleting version cascades to slides and jobs"""
        # Create slide
        slide = Slide(
            project_id=sample_project.id,
            version_id=sample_version.id,
            slide_index=1,
            image_path="/test.png"
        )
        db_session.add(slide)
        
        # Create render job
        job = RenderJob(
            project_id=sample_project.id,
            version_id=sample_version.id,
            job_type=JobType.RENDER,
            status=JobStatus.QUEUED
        )
        db_session.add(job)
        await db_session.commit()
        
        version_id = sample_version.id
        
        # Delete version
        await db_session.delete(sample_version)
        await db_session.commit()
        
        # Verify cascaded deletes
        result = await db_session.execute(
            select(Slide).where(Slide.version_id == version_id)
        )
        assert result.scalar_one_or_none() is None


class TestEnums:
    """Tests for enum values"""
    
    def test_project_status_values(self):
        """Test ProjectStatus enum values"""
        assert ProjectStatus.DRAFT.value == "draft"
        assert ProjectStatus.READY.value == "ready"
        assert ProjectStatus.RENDERING.value == "rendering"
        assert ProjectStatus.DONE.value == "done"
        assert ProjectStatus.FAILED.value == "failed"
    
    def test_script_source_values(self):
        """Test ScriptSource enum values"""
        assert ScriptSource.MANUAL.value == "manual"
        assert ScriptSource.IMPORTED_NOTES.value == "imported_notes"
        assert ScriptSource.TRANSLATED.value == "translated"
    
    def test_job_type_values(self):
        """Test JobType enum values"""
        assert JobType.CONVERT.value == "convert"
        assert JobType.TTS.value == "tts"
        assert JobType.RENDER.value == "render"
        assert JobType.PREVIEW.value == "preview"
    
    def test_job_status_values(self):
        """Test JobStatus enum values"""
        assert JobStatus.QUEUED.value == "queued"
        assert JobStatus.RUNNING.value == "running"
        assert JobStatus.DONE.value == "done"
        assert JobStatus.FAILED.value == "failed"
    
    def test_ducking_strength_values(self):
        """Test DuckingStrength enum values"""
        assert DuckingStrength.LIGHT.value == "light"
        assert DuckingStrength.DEFAULT.value == "default"
        assert DuckingStrength.STRONG.value == "strong"
    
    def test_translation_style_values(self):
        """Test TranslationStyle enum values"""
        assert TranslationStyle.FORMAL.value == "formal"
        assert TranslationStyle.NEUTRAL.value == "neutral"
        assert TranslationStyle.FRIENDLY.value == "friendly"

