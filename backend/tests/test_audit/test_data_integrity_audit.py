"""
Data Integrity Audit Tests (D-01 to D-04)

Цель: после любых операций связи "слайд ↔ скрипт ↔ аудио ↔ таймлайн" остаются корректными.

Test Matrix:
- D-01: Reorder не ломает привязки
- D-02: Delete слайда с аудио (корректное удаление ассетов)
- D-03: Parallel edits (2 вкладки) - конфликт-резолв
- D-04: Autosave границы (дебаунс, не теряет данные)
"""
import uuid
import asyncio
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import (
    Project, ProjectVersion, Slide, SlideScript, SlideAudio,
    ScriptSource
)


class TestDataIntegrityD01_ReorderPreservesBindings:
    """
    D-01: Reorder не ломает привязки
    
    Шаги: reorder после генерации аудио
    Ожидаемо: аудио остаётся у своего слайда (по slide_id, не по индексу)
    """
    
    @pytest.mark.asyncio
    async def test_d01_audio_stays_with_slide_after_reorder(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion,
        db_session: AsyncSession
    ):
        """Audio files remain bound to their slides after reorder"""
        # Create slides with audio
        slides = []
        for i in range(3):
            slide = Slide(
                project_id=sample_project.id,
                version_id=sample_version.id,
                slide_index=i + 1,
                image_path=f"slides/slide_{i+1:03d}.png",
            )
            db_session.add(slide)
            await db_session.flush()
            
            # Add script
            script = SlideScript(
                slide_id=slide.id,
                lang="en",
                text=f"Script for slide {i + 1}",
                source=ScriptSource.MANUAL,
            )
            db_session.add(script)
            
            # Add audio bound to slide
            audio = SlideAudio(
                slide_id=slide.id,
                lang="en",
                voice_id="test-voice",
                audio_path=f"audio/slide_{i+1}.wav",
                duration_sec=float(i + 2),  # Different durations
                audio_hash=f"hash-{i}",
            )
            db_session.add(audio)
            slides.append(slide)
        
        await db_session.commit()
        
        # Record original audio assignments
        original_audio_durations = {}
        for slide in slides:
            result = await db_session.execute(
                select(SlideAudio)
                .where(SlideAudio.slide_id == slide.id)
            )
            audio = result.scalar_one()
            original_audio_durations[str(slide.id)] = audio.duration_sec
        
        # Reorder: reverse the slides
        new_order = [str(s.id) for s in reversed(slides)]
        response = await client.put(
            f"/api/slides/projects/{sample_project.id}/versions/{sample_version.id}/slides/reorder",
            json={"slide_ids": new_order}
        )
        assert response.status_code == 200
        
        # Verify audio is still bound to same slide (by ID)
        for slide in slides:
            await db_session.refresh(slide)
            result = await db_session.execute(
                select(SlideAudio)
                .where(SlideAudio.slide_id == slide.id)
            )
            audio = result.scalar_one()
            # Duration should match original assignment
            assert audio.duration_sec == original_audio_durations[str(slide.id)]
    
    @pytest.mark.asyncio
    async def test_d01_script_stays_with_slide_after_reorder(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion,
        db_session: AsyncSession
    ):
        """Scripts remain bound to their slides after reorder"""
        slides = []
        for i in range(3):
            slide = Slide(
                project_id=sample_project.id,
                version_id=sample_version.id,
                slide_index=i + 1,
                image_path=f"slides/slide_{i+1:03d}.png",
            )
            db_session.add(slide)
            await db_session.flush()
            
            script = SlideScript(
                slide_id=slide.id,
                lang="en",
                text=f"Unique script content {uuid.uuid4().hex[:8]}",
                source=ScriptSource.MANUAL,
            )
            db_session.add(script)
            slides.append((slide, script.text))
        
        await db_session.commit()
        
        # Reorder
        new_order = [str(s[0].id) for s in reversed(slides)]
        await client.put(
            f"/api/slides/projects/{sample_project.id}/versions/{sample_version.id}/slides/reorder",
            json={"slide_ids": new_order}
        )
        
        # Verify scripts stayed with their slides
        for slide, original_text in slides:
            response = await client.get(f"/api/slides/{slide.id}/scripts")
            scripts = response.json()
            en_script = next((s for s in scripts if s["lang"] == "en"), None)
            assert en_script["text"] == original_text


class TestDataIntegrityD02_DeleteSlideWithAudio:
    """
    D-02: Delete слайда с аудио
    
    Шаги: удалить слайд, на котором уже есть TTS
    Ожидаемо: ассет корректно удаляется/отвязывается, без "сирот"
    """
    
    @pytest.mark.asyncio
    async def test_d02_delete_slide_removes_audio(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion,
        db_session: AsyncSession
    ):
        """Deleting slide also deletes its audio"""
        # Create slide with audio
        slide = Slide(
            project_id=sample_project.id,
            version_id=sample_version.id,
            slide_index=1,
            image_path="slides/slide_001.png",
        )
        db_session.add(slide)
        await db_session.flush()
        
        audio = SlideAudio(
            slide_id=slide.id,
            lang="en",
            voice_id="test-voice",
            audio_path="audio/slide_001.wav",
            duration_sec=5.0,
            audio_hash="hash-123",
        )
        db_session.add(audio)
        await db_session.commit()
        
        audio_id = audio.id
        slide_id = slide.id
        
        # Delete the slide
        response = await client.delete(f"/api/slides/{slide_id}")
        assert response.status_code == 200
        
        # Verify audio was deleted (cascade)
        result = await db_session.execute(
            select(SlideAudio).where(SlideAudio.id == audio_id)
        )
        orphan_audio = result.scalar_one_or_none()
        assert orphan_audio is None
    
    @pytest.mark.asyncio
    async def test_d02_delete_slide_removes_scripts(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion,
        db_session: AsyncSession
    ):
        """Deleting slide also deletes its scripts"""
        slide = Slide(
            project_id=sample_project.id,
            version_id=sample_version.id,
            slide_index=1,
            image_path="slides/slide_001.png",
        )
        db_session.add(slide)
        await db_session.flush()
        
        # Create scripts in multiple languages
        for lang in ["en", "ru", "es"]:
            script = SlideScript(
                slide_id=slide.id,
                lang=lang,
                text=f"Script in {lang}",
                source=ScriptSource.MANUAL,
            )
            db_session.add(script)
        await db_session.commit()
        
        slide_id = slide.id
        
        # Delete the slide
        await client.delete(f"/api/slides/{slide_id}")
        
        # Verify all scripts were deleted
        result = await db_session.execute(
            select(SlideScript).where(SlideScript.slide_id == slide_id)
        )
        orphan_scripts = result.scalars().all()
        assert len(orphan_scripts) == 0
    
    @pytest.mark.asyncio
    async def test_d02_no_orphan_assets_after_delete(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion,
        db_session: AsyncSession
    ):
        """No orphan assets remain after slide deletion"""
        # Create multiple slides with assets
        for i in range(3):
            slide = Slide(
                project_id=sample_project.id,
                version_id=sample_version.id,
                slide_index=i + 1,
                image_path=f"slides/slide_{i+1:03d}.png",
            )
            db_session.add(slide)
            await db_session.flush()
            
            audio = SlideAudio(
                slide_id=slide.id,
                lang="en",
                voice_id="voice",
                audio_path=f"audio/slide_{i+1}.wav",
                duration_sec=5.0,
                audio_hash=f"hash-{i}",
            )
            db_session.add(audio)
        
        await db_session.commit()
        
        # Get slides to delete
        response = await client.get(
            f"/api/slides/projects/{sample_project.id}/versions/{sample_version.id}/slides"
        )
        slides = response.json()
        
        # Delete first slide
        await client.delete(f"/api/slides/{slides[0]['id']}")
        
        # Count remaining audio records
        result = await db_session.execute(
            select(SlideAudio)
            .join(Slide)
            .where(Slide.version_id == sample_version.id)
        )
        remaining_audio = result.scalars().all()
        assert len(remaining_audio) == 2  # Only for remaining slides


class TestDataIntegrityD03_ParallelEdits:
    """
    D-03: Parallel edits (2 вкладки)
    
    Шаги: открыть проект в двух вкладках → править одно поле
    Ожидаемо: либо last-write-wins, либо конфликт-резолв
    """
    
    @pytest.mark.asyncio
    async def test_d03_last_write_wins(
        self,
        client: AsyncClient,
        sample_slide: Slide,
        sample_script: SlideScript
    ):
        """Last write wins in concurrent edit scenario"""
        # Simulate two concurrent edits
        edit1_text = "Edit from tab 1"
        edit2_text = "Edit from tab 2"
        
        # Both "tabs" send updates
        response1 = await client.patch(
            f"/api/slides/{sample_slide.id}/scripts/en",
            json={"text": edit1_text}
        )
        response2 = await client.patch(
            f"/api/slides/{sample_slide.id}/scripts/en",
            json={"text": edit2_text}
        )
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        # Last write should win
        response = await client.get(f"/api/slides/{sample_slide.id}/scripts")
        scripts = response.json()
        en_script = next((s for s in scripts if s["lang"] == "en"), None)
        assert en_script["text"] == edit2_text
    
    @pytest.mark.asyncio
    async def test_d03_concurrent_updates_dont_corrupt(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion,
        db_session: AsyncSession
    ):
        """Concurrent updates don't corrupt data"""
        # Create slide with script
        slide = Slide(
            project_id=sample_project.id,
            version_id=sample_version.id,
            slide_index=1,
            image_path="slides/slide_001.png",
        )
        db_session.add(slide)
        await db_session.flush()
        
        script = SlideScript(
            slide_id=slide.id,
            lang="en",
            text="Initial text",
            source=ScriptSource.MANUAL,
        )
        db_session.add(script)
        await db_session.commit()
        
        # Simulate rapid concurrent updates
        async def update_script(n: int):
            await client.patch(
                f"/api/slides/{slide.id}/scripts/en",
                json={"text": f"Update {n}"}
            )
        
        # Run updates "concurrently" (sequentially in async context)
        for i in range(10):
            await update_script(i)
        
        # Verify data integrity - script exists and has valid content
        response = await client.get(f"/api/slides/{slide.id}/scripts")
        scripts = response.json()
        en_script = next((s for s in scripts if s["lang"] == "en"), None)
        
        assert en_script is not None
        assert "Update" in en_script["text"]  # Some update was saved
        assert en_script["source"] == "manual"


class TestDataIntegrityD04_AutosaveBoundaries:
    """
    D-04: Autosave границы
    
    Шаги: быстро набрать текст 30–60 сек
    Ожидаемо: не шлёт save на каждый символ (дебаунс), не теряет финальную версию
    """
    
    @pytest.mark.asyncio
    async def test_d04_final_content_preserved(
        self,
        client: AsyncClient,
        sample_slide: Slide,
        sample_script: SlideScript
    ):
        """Final content is preserved after rapid updates"""
        # Simulate typing - rapid updates
        incremental_texts = [
            "H",
            "He",
            "Hel",
            "Hell",
            "Hello",
            "Hello ",
            "Hello W",
            "Hello Wo",
            "Hello Wor",
            "Hello Worl",
            "Hello World",
        ]
        
        for text in incremental_texts:
            await client.patch(
                f"/api/slides/{sample_slide.id}/scripts/en",
                json={"text": text}
            )
        
        # Final version should be saved
        response = await client.get(f"/api/slides/{sample_slide.id}/scripts")
        scripts = response.json()
        en_script = next((s for s in scripts if s["lang"] == "en"), None)
        
        assert en_script["text"] == "Hello World"
    
    @pytest.mark.asyncio
    async def test_d04_update_timestamp_reflects_last_change(
        self,
        client: AsyncClient,
        sample_slide: Slide,
        sample_script: SlideScript
    ):
        """Updated timestamp reflects last change"""
        # Get initial timestamp
        response = await client.get(f"/api/slides/{sample_slide.id}/scripts")
        initial_updated_at = response.json()[0]["updated_at"]
        
        # Make update
        await client.patch(
            f"/api/slides/{sample_slide.id}/scripts/en",
            json={"text": "New content"}
        )
        
        # Check timestamp changed
        response = await client.get(f"/api/slides/{sample_slide.id}/scripts")
        new_updated_at = response.json()[0]["updated_at"]
        
        # Timestamp should be different (newer)
        assert new_updated_at >= initial_updated_at


class TestDataIntegrityRelationships:
    """Additional relationship integrity tests"""
    
    @pytest.mark.asyncio
    async def test_slide_script_relationship_intact(
        self,
        sample_slide: Slide,
        sample_script: SlideScript,
        db_session: AsyncSession
    ):
        """Slide-script relationship is intact"""
        await db_session.refresh(sample_slide)
        await db_session.refresh(sample_script)
        
        assert sample_script.slide_id == sample_slide.id
    
    @pytest.mark.asyncio
    async def test_project_version_relationship_intact(
        self,
        sample_project: Project,
        sample_version: ProjectVersion,
        db_session: AsyncSession
    ):
        """Project-version relationship is intact"""
        await db_session.refresh(sample_version)
        
        assert sample_version.project_id == sample_project.id
    
    @pytest.mark.asyncio
    async def test_slide_indices_are_contiguous(
        self,
        client: AsyncClient,
        sample_project: Project,
        sample_version: ProjectVersion,
        db_session: AsyncSession
    ):
        """Slide indices remain contiguous after operations"""
        # Create slides
        for i in range(5):
            slide = Slide(
                project_id=sample_project.id,
                version_id=sample_version.id,
                slide_index=i + 1,
                image_path=f"slides/slide_{i+1:03d}.png",
            )
            db_session.add(slide)
        await db_session.commit()
        
        # Delete middle slide
        response = await client.get(
            f"/api/slides/projects/{sample_project.id}/versions/{sample_version.id}/slides"
        )
        slides = response.json()
        await client.delete(f"/api/slides/{slides[2]['id']}")  # Delete 3rd
        
        # Verify indices are contiguous
        response = await client.get(
            f"/api/slides/projects/{sample_project.id}/versions/{sample_version.id}/slides"
        )
        slides = response.json()
        indices = [s["slide_index"] for s in slides]
        
        assert indices == [1, 2, 3, 4]  # Contiguous after reindex

