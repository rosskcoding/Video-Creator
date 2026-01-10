import uuid
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.db.models import Slide, RenderCache


@pytest.mark.asyncio
async def test_store_and_check_render_cache_hit(db_session: AsyncSession, sample_slide: Slide):
    from app.adapters.render_service import store_render_cache, check_render_cache, RENDERER_VERSION

    slide_id = str(sample_slide.id)
    lang = "en"
    render_key = "rk-test-123"

    # Create a fake segment file under DATA_DIR
    seg_abs = Path(settings.DATA_DIR) / "cache_test" / f"{uuid.uuid4()}.webm"
    seg_abs.parent.mkdir(parents=True, exist_ok=True)
    seg_abs.write_bytes(b"fake-video")

    await store_render_cache(
        db=db_session,
        slide_id=slide_id,
        lang=lang,
        render_key=render_key,
        segment_path=str(seg_abs),
        duration_sec=3.0,
        frame_count=90,
        fps=30,
        width=1920,
        height=1080,
        render_time_ms=123,
        file_size_bytes=seg_abs.stat().st_size,
    )
    await db_session.commit()

    hit = await check_render_cache(
        db=db_session,
        slide_id=slide_id,
        lang=lang,
        render_key=render_key,
        fps=30,
        width=1920,
        height=1080,
    )
    assert hit is not None
    assert hit["cached"] is True
    assert hit["segment_path"] == str(seg_abs)
    assert hit["duration_sec"] == pytest.approx(3.0)
    assert hit["frame_count"] == 90

    # Sanity: record exists with correct renderer_version
    res = await db_session.execute(select(RenderCache).where(RenderCache.renderer_version == RENDERER_VERSION))
    assert res.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_check_render_cache_miss_deletes_stale_entry(db_session: AsyncSession, sample_slide: Slide):
    from app.adapters.render_service import store_render_cache, check_render_cache

    slide_id = str(sample_slide.id)
    lang = "en"
    render_key = "rk-missing-file"

    # Point to a path under DATA_DIR but do NOT create the file
    seg_abs = Path(settings.DATA_DIR) / "cache_test" / f"{uuid.uuid4()}.webm"
    seg_abs.parent.mkdir(parents=True, exist_ok=True)

    await store_render_cache(
        db=db_session,
        slide_id=slide_id,
        lang=lang,
        render_key=render_key,
        segment_path=str(seg_abs),
        duration_sec=1.0,
        frame_count=30,
    )
    await db_session.commit()

    miss = await check_render_cache(
        db=db_session,
        slide_id=slide_id,
        lang=lang,
        render_key=render_key,
    )
    assert miss is None
    await db_session.commit()

    res = await db_session.execute(select(RenderCache).where(RenderCache.render_key == render_key))
    assert res.scalar_one_or_none() is None


