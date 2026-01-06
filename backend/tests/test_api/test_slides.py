"""
Tests for Slide and Script management API routes
"""
import uuid
import pytest
from unittest.mock import patch, MagicMock

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import (
    Project, ProjectVersion, Slide, SlideScript, SlideAudio,
    ScriptSource
)


class TestSlidesAPI:
    """Tests for slides endpoints"""
    
    @pytest.mark.asyncio
    async def test_get_slides_empty(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion
    ):
        """Test getting slides when none exist"""
        response = await client.get(
            f"/api/slides/projects/{sample_project.id}/versions/{sample_version.id}/slides"
        )
        
        assert response.status_code == 200
        assert response.json() == []
    
    @pytest.mark.asyncio
    async def test_get_slides(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion,
        sample_slide: Slide
    ):
        """Test getting slides list"""
        response = await client.get(
            f"/api/slides/projects/{sample_project.id}/versions/{sample_version.id}/slides"
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert len(data) == 1
        assert data[0]["slide_index"] == 1
        assert data[0]["notes_text"] == "Speaker notes for slide 1"
    
    @pytest.mark.asyncio
    async def test_get_single_slide(
        self,
        client: AsyncClient,
        sample_slide: Slide
    ):
        """Test getting a single slide with scripts and audio"""
        response = await client.get(f"/api/slides/{sample_slide.id}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["slide_index"] == 1
        assert "scripts" in data
        assert "audio_files" in data
    
    @pytest.mark.asyncio
    async def test_get_slide_not_found(self, client: AsyncClient):
        """Test getting a non-existent slide"""
        fake_id = uuid.uuid4()
        response = await client.get(f"/api/slides/{fake_id}")
        
        assert response.status_code == 404


class TestScriptsAPI:
    """Tests for scripts endpoints"""
    
    @pytest.mark.asyncio
    async def test_get_slide_scripts_empty(
        self,
        client: AsyncClient,
        sample_slide: Slide
    ):
        """Test getting scripts when none exist"""
        response = await client.get(f"/api/slides/{sample_slide.id}/scripts")
        
        assert response.status_code == 200
        assert response.json() == []
    
    @pytest.mark.asyncio
    async def test_get_slide_scripts(
        self,
        client: AsyncClient,
        sample_slide: Slide,
        sample_script: SlideScript
    ):
        """Test getting scripts list"""
        response = await client.get(f"/api/slides/{sample_slide.id}/scripts")
        
        assert response.status_code == 200
        data = response.json()
        
        assert len(data) == 1
        assert data[0]["lang"] == "en"
        assert data[0]["text"] == "This is the script text for slide 1"
    
    @pytest.mark.asyncio
    async def test_update_script_existing(
        self,
        client: AsyncClient,
        sample_slide: Slide,
        sample_script: SlideScript
    ):
        """Test updating an existing script"""
        response = await client.patch(
            f"/api/slides/{sample_slide.id}/scripts/en",
            json={"text": "Updated script text"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["text"] == "Updated script text"
        assert data["source"] == "manual"
    
    @pytest.mark.asyncio
    async def test_update_script_create_new(
        self,
        client: AsyncClient,
        sample_slide: Slide
    ):
        """Test creating a new script via update"""
        response = await client.patch(
            f"/api/slides/{sample_slide.id}/scripts/ru",
            json={"text": "Русский текст"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["lang"] == "ru"
        assert data["text"] == "Русский текст"
    
    @pytest.mark.asyncio
    async def test_update_script_slide_not_found(self, client: AsyncClient):
        """Test updating script for non-existent slide"""
        fake_id = uuid.uuid4()
        response = await client.patch(
            f"/api/slides/{fake_id}/scripts/en",
            json={"text": "Test"}
        )
        
        assert response.status_code == 404


class TestLanguageManagement:
    """Tests for language management endpoints"""
    
    @pytest.mark.asyncio
    async def test_add_language(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion,
        sample_slide: Slide
    ):
        """Test adding a new language"""
        response = await client.post(
            f"/api/slides/projects/{sample_project.id}/versions/{sample_version.id}/languages/add",
            params={"lang": "ru"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["lang"] == "ru"
        assert data["slides_count"] == 1
        assert data["scripts_created"] == 1
    
    @pytest.mark.asyncio
    async def test_add_language_already_exists(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion,
        sample_slide: Slide,
        sample_script: SlideScript
    ):
        """Test adding language when it already exists"""
        response = await client.post(
            f"/api/slides/projects/{sample_project.id}/versions/{sample_version.id}/languages/add",
            params={"lang": "en"}  # Already exists from sample_script
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["scripts_created"] == 0  # No new scripts created
    
    @pytest.mark.asyncio
    async def test_add_language_no_slides(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion
    ):
        """Test adding language when no slides exist"""
        response = await client.post(
            f"/api/slides/projects/{sample_project.id}/versions/{sample_version.id}/languages/add",
            params={"lang": "ru"}
        )
        
        assert response.status_code == 404


class TestImportNotes:
    """Tests for speaker notes import"""
    
    @pytest.mark.asyncio
    async def test_import_speaker_notes(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion,
        sample_slide: Slide
    ):
        """Test importing speaker notes as scripts"""
        response = await client.post(
            f"/api/slides/projects/{sample_project.id}/versions/{sample_version.id}/import_notes",
            params={"lang": "en"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["lang"] == "en"
        assert data["imported_count"] == 1
        
        # Verify script was created with notes text
        scripts_response = await client.get(f"/api/slides/{sample_slide.id}/scripts")
        scripts = scripts_response.json()
        
        assert len(scripts) == 1
        assert scripts[0]["text"] == "Speaker notes for slide 1"
        assert scripts[0]["source"] == "imported_notes"


class TestTranslation:
    """Tests for translation endpoint"""
    
    @pytest.mark.asyncio
    async def test_translate_all_slides(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion,
        sample_slide: Slide,
        sample_script: SlideScript
    ):
        """Test triggering batch translation"""
        mock_task = MagicMock()
        mock_task.id = "translate-task-123"
        
        with patch(
            "app.workers.tasks.translate_batch_task"
        ) as mock_translate:
            mock_translate.delay.return_value = mock_task
            
            response = await client.post(
                f"/api/slides/projects/{sample_project.id}/versions/{sample_version.id}/translate",
                params={"target_lang": "ru"}
            )
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["task_id"] == "translate-task-123"
            assert data["target_lang"] == "ru"
            assert data["status"] == "queued"
    
    @pytest.mark.asyncio
    async def test_translate_project_not_found(self, client: AsyncClient):
        """Test translation for non-existent project"""
        fake_project_id = uuid.uuid4()
        fake_version_id = uuid.uuid4()
        
        with patch("app.workers.tasks.translate_batch_task"):
            response = await client.post(
                f"/api/slides/projects/{fake_project_id}/versions/{fake_version_id}/translate",
                params={"target_lang": "ru"}
            )
        
        assert response.status_code == 404


class TestTTSGeneration:
    """Tests for TTS generation endpoints"""
    
    @pytest.mark.asyncio
    async def test_generate_slide_tts(
        self,
        client: AsyncClient,
        sample_slide: Slide
    ):
        """Test TTS generation for single slide"""
        mock_task = MagicMock()
        mock_task.id = "tts-task-123"
        
        with patch("app.workers.tasks.tts_slide_task") as mock_tts:
            mock_tts.delay.return_value = mock_task
            
            response = await client.post(
                f"/api/slides/{sample_slide.id}/tts",
                params={"lang": "en"}
            )
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["task_id"] == "tts-task-123"
            assert data["slide_id"] == str(sample_slide.id)
            assert data["lang"] == "en"
    
    @pytest.mark.asyncio
    async def test_generate_slide_tts_not_found(self, client: AsyncClient):
        """Test TTS for non-existent slide"""
        fake_id = uuid.uuid4()
        
        with patch("app.workers.tasks.tts_slide_task"):
            response = await client.post(
                f"/api/slides/{fake_id}/tts",
                params={"lang": "en"}
            )
        
        assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_generate_version_tts(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion
    ):
        """Test batch TTS for version"""
        mock_task = MagicMock()
        mock_task.id = "tts-batch-123"
        
        with patch("app.workers.tasks.tts_batch_task") as mock_tts:
            mock_tts.delay.return_value = mock_task
            
            response = await client.post(
                f"/api/slides/projects/{sample_project.id}/versions/{sample_version.id}/tts",
                params={"lang": "en"}
            )
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["task_id"] == "tts-batch-123"
    
    @pytest.mark.asyncio
    async def test_generate_version_tts_version_not_found(self, client: AsyncClient):
        """Test batch TTS for non-existent version"""
        fake_project_id = uuid.uuid4()
        fake_version_id = uuid.uuid4()
        
        with patch("app.workers.tasks.tts_batch_task"):
            response = await client.post(
                f"/api/slides/projects/{fake_project_id}/versions/{fake_version_id}/tts",
                params={"lang": "en"}
            )
        
        assert response.status_code == 404


class TestSlideWithAudio:
    """Tests for slides with audio files"""
    
    @pytest.mark.asyncio
    async def test_get_slide_with_audio(
        self,
        client: AsyncClient,
        sample_slide: Slide,
        db_session: AsyncSession
    ):
        """Test getting slide with associated audio files"""
        # Create an audio file
        audio = SlideAudio(
            slide_id=sample_slide.id,
            lang="en",
            provider="elevenlabs",
            voice_id="test-voice",
            audio_path="/tmp/audio.mp3",
            duration_sec=5.5,
            audio_hash="abc123"
        )
        db_session.add(audio)
        await db_session.commit()
        
        response = await client.get(f"/api/slides/{sample_slide.id}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["audio_files"]) == 1
        assert data["audio_files"][0]["lang"] == "en"
        assert data["audio_files"][0]["duration_sec"] == 5.5

