import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.db.models import Slide, SlideMarkers, GlobalMarker, MarkerPosition, NormalizedScript


@pytest.mark.asyncio
async def test_update_marker_timings_updates_by_char_start(
    db_session: AsyncSession,
    sample_slide: Slide,
):
    """_update_marker_timings should set marker.timeSeconds using word_timings charStart match."""
    from app.workers.tasks import _update_marker_timings

    slide_id = sample_slide.id

    db_session.add(
        SlideMarkers(
            slide_id=slide_id,
            lang="en",
            markers=[
                {
                    "id": "m1",
                    "name": "Anchor",
                    "charStart": 0,
                    "charEnd": 5,
                    "wordText": "Hello",
                    "timeSeconds": 0,
                }
            ],
        )
    )
    await db_session.commit()

    word_timings = [
        {"charStart": 0, "charEnd": 5, "startTime": 1.23, "endTime": 1.5, "word": "Hello"},
        {"charStart": 6, "charEnd": 11, "startTime": 2.0, "endTime": 2.5, "word": "world"},
    ]

    updated = await _update_marker_timings(db_session, slide_id, "en", word_timings)
    assert updated == 1
    await db_session.commit()

    orm_result = await db_session.execute(
        select(SlideMarkers)
        .where(SlideMarkers.slide_id == slide_id)
        .where(SlideMarkers.lang == "en")
    )
    markers_record = orm_result.scalar_one()
    assert markers_record.markers[0]["timeSeconds"] == pytest.approx(1.23)


@pytest.mark.asyncio
async def test_update_marker_timings_fallbacks_to_word_text(
    db_session: AsyncSession,
    sample_slide: Slide,
):
    """_update_marker_timings should fall back to matching by wordText when charStart doesn't match."""
    from app.workers.tasks import _update_marker_timings

    slide_id = sample_slide.id

    db_session.add(
        SlideMarkers(
            slide_id=slide_id,
            lang="en",
            markers=[
                {
                    "id": "m1",
                    "name": "Anchor",
                    "charStart": 999,  # doesn't exist in timings
                    "charEnd": 1000,
                    "wordText": "Hello",
                    "timeSeconds": 0,
                }
            ],
        )
    )
    await db_session.commit()

    word_timings = [
        {"charStart": 0, "charEnd": 5, "startTime": 0.75, "endTime": 1.0, "word": "hello"},
    ]

    updated = await _update_marker_timings(db_session, slide_id, "en", word_timings)
    assert updated == 1
    await db_session.commit()

    orm_result = await db_session.execute(
        select(SlideMarkers)
        .where(SlideMarkers.slide_id == slide_id)
        .where(SlideMarkers.lang == "en")
    )
    markers_record = orm_result.scalar_one()
    assert markers_record.markers[0]["timeSeconds"] == pytest.approx(0.75)


def test_resolve_trigger_prefers_marker_id():
    """_resolve_trigger should resolve word trigger via markerId + apply voice_offset_sec."""
    from app.workers.tasks import _resolve_trigger

    markers = [{"id": "m1", "timeSeconds": 2.5, "wordText": "hello"}]
    trigger = {"type": "word", "markerId": "m1", "wordText": "hello"}

    resolved = _resolve_trigger(
        trigger=trigger,
        normalized_script=None,
        markers=markers,
        audio_duration=10.0,
        voice_offset_sec=1.0,
    )

    assert resolved["type"] == "time"
    assert resolved["seconds"] == pytest.approx(3.5)
    assert resolved.get("_resolved_via") == "markerId"


def test_asset_url_to_filesystem_path_security(sample_project):
    """_asset_url_to_filesystem_path should enforce DATA_DIR confinement and block traversal."""
    from app.workers.tasks import _asset_url_to_filesystem_path

    pid = str(sample_project.id)
    filename = "safe.png"

    ok = _asset_url_to_filesystem_path(f"/static/assets/{pid}/{filename}", project_id=pid)
    assert ok is not None
    assert ok.startswith(str(settings.DATA_DIR.resolve()))
    assert ok.endswith(f"{pid}/assets/{filename}")

    # Path traversal via URL segments should be rejected
    bad = _asset_url_to_filesystem_path(f"/static/assets/{pid}/../passwd", project_id=pid)
    assert bad is None

    bad2 = _asset_url_to_filesystem_path("/static/assets/../x.png", project_id=pid)
    assert bad2 is None

    # Absolute path outside DATA_DIR should be rejected
    bad3 = _asset_url_to_filesystem_path("/etc/passwd", project_id=pid)
    assert bad3 is None

    # Absolute path inside DATA_DIR is allowed
    inside = str(settings.DATA_DIR / pid / "assets" / filename)
    ok2 = _asset_url_to_filesystem_path(inside, project_id=pid)
    assert ok2 is not None
    assert ok2.startswith(str(settings.DATA_DIR.resolve()))


@pytest.mark.asyncio
async def test_update_marker_timings_updates_global_marker_position_via_token(
    db_session: AsyncSession,
    sample_slide: Slide,
):
    """_update_marker_timings should update MarkerPosition.time_seconds using ⟦M:uuid⟧ token anchoring."""
    import uuid as _uuid

    from app.workers.tasks import _update_marker_timings
    from app.adapters.marker_tokens import format_marker_token

    slide_id = sample_slide.id
    marker_id = _uuid.uuid4()
    token = format_marker_token(str(marker_id))
    token_len = len(token)

    db_session.add(GlobalMarker(id=marker_id, slide_id=slide_id, name="Test"))
    db_session.add(
        MarkerPosition(
            id=_uuid.uuid4(),
            marker_id=marker_id,
            lang="en",
            char_start=0,
            char_end=5,
            time_seconds=None,
        )
    )

    # Normalized text contains token; anchor word is immediately after token.
    normalized_text = f"{token}Hello world"
    db_session.add(
        NormalizedScript(
            slide_id=slide_id,
            lang="en",
            raw_text=normalized_text,
            normalized_text=normalized_text,
            word_timings=None,
        )
    )
    await db_session.commit()

    word_timings = [
        {"charStart": token_len, "charEnd": token_len + 5, "startTime": 1.75, "endTime": 2.0, "word": "Hello"},
        {"charStart": token_len + 6, "charEnd": token_len + 11, "startTime": 2.2, "endTime": 2.4, "word": "world"},
    ]

    updated = await _update_marker_timings(db_session, slide_id, "en", word_timings)
    assert updated >= 1
    await db_session.commit()

    orm_result = await db_session.execute(
        select(MarkerPosition)
        .where(MarkerPosition.marker_id == marker_id)
        .where(MarkerPosition.lang == "en")
    )
    pos = orm_result.scalar_one()
    assert pos.time_seconds == pytest.approx(1.75)


@pytest.mark.asyncio
async def test_resolve_scene_triggers_uses_global_marker_positions(
    db_session: AsyncSession,
    sample_slide: Slide,
    sample_project,
):
    """_resolve_scene_triggers should resolve marker triggers via GlobalMarker/MarkerPosition (EPIC A)."""
    import uuid as _uuid

    from app.workers.tasks import _resolve_scene_triggers
    from app.db.models import SlideScene

    slide_id = sample_slide.id

    marker_id = _uuid.uuid4()
    db_session.add(GlobalMarker(id=marker_id, slide_id=slide_id, name="Anchor"))
    db_session.add(
        MarkerPosition(
            id=_uuid.uuid4(),
            marker_id=marker_id,
            lang="en",
            char_start=0,
            char_end=5,
            time_seconds=2.0,
        )
    )

    scene = SlideScene(
        id=_uuid.uuid4(),
        slide_id=slide_id,
        canvas_width=1920,
        canvas_height=1080,
        layers=[
            {
                "id": "layer-1",
                "type": "text",
                "name": "T",
                "position": {"x": 0, "y": 0},
                "size": {"width": 100, "height": 50},
                "zIndex": 0,
                "text": {"baseContent": "Hi"},
                "animation": {
                    "entrance": {
                        "type": "fadeIn",
                        "duration": 0.5,
                        "delay": 0,
                        "easing": "easeOut",
                        "trigger": {"type": "marker", "markerId": str(marker_id)},
                    }
                },
            }
        ],
        schema_version=1,
    )
    db_session.add(scene)
    await db_session.commit()

    resolved_layers = await _resolve_scene_triggers(
        db=db_session,
        slide_id=slide_id,
        scene=scene,
        lang="en",
        slide_duration=5.0,
        voice_offset_sec=1.0,
        project_id=str(sample_project.id),
    )

    assert resolved_layers[0]["animation"]["entrance"]["trigger"]["type"] == "time"
    # timeSeconds(2.0) + voice_offset_sec(1.0)
    assert resolved_layers[0]["animation"]["entrance"]["trigger"]["seconds"] == pytest.approx(3.0)


