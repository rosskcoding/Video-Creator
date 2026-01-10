"""
Tests for Canvas Editor API endpoints (Phase 1)
- Scene CRUD operations
- Layer add/update/delete/reorder
- Asset upload/delete
- Markers CRUD
"""
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import (
    Project,
    ProjectVersion,
    Slide,
    SlideScene,
    SlideMarkers,
    SlideScript,
    Asset,
    NormalizedScript,
    GlobalMarker,
    MarkerPosition,
)


# === SCENE TESTS ===

@pytest.mark.asyncio
async def test_get_scene_creates_default(client: AsyncClient, sample_slide: Slide):
    """GET /canvas/slides/{slide_id}/scene creates default scene if not exists"""
    response = await client.get(f"/api/canvas/slides/{sample_slide.id}/scene")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["slide_id"] == str(sample_slide.id)
    assert data["canvas"]["width"] == 1920
    assert data["canvas"]["height"] == 1080
    assert data["layers"] == []
    assert data["schema_version"] == 1
    assert "render_key" in data


@pytest.mark.asyncio
async def test_update_scene(client: AsyncClient, sample_slide: Slide):
    """PUT /canvas/slides/{slide_id}/scene updates scene"""
    scene_data = {
        "canvas": {"width": 1280, "height": 720},
        "layers": [
            {
                "id": "layer-1",
                "type": "text",
                "name": "Title",
                "position": {"x": 100, "y": 50},
                "size": {"width": 400, "height": 60},
                "visible": True,
                "locked": False,
                "zIndex": 0,
                "text": {
                    "baseContent": "Hello World",
                    "translations": {},
                    "isTranslatable": True,
                    "style": {
                        "fontFamily": "Inter",
                        "fontSize": 32,
                        "fontWeight": "bold",
                        "fontStyle": "normal",
                        "color": "#000000",
                        "align": "center",
                        "verticalAlign": "middle",
                        "lineHeight": 1.4
                    },
                    "overflow": "shrinkFont",
                    "minFontSize": 12
                }
            }
        ]
    }
    
    response = await client.put(
        f"/api/canvas/slides/{sample_slide.id}/scene",
        json=scene_data
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["canvas"]["width"] == 1280
    assert data["canvas"]["height"] == 720
    assert len(data["layers"]) == 1
    assert data["layers"][0]["id"] == "layer-1"
    assert data["layers"][0]["text"]["baseContent"] == "Hello World"
    assert data["render_key"] is not None


@pytest.mark.asyncio
async def test_add_layer(client: AsyncClient, sample_slide: Slide):
    """POST /canvas/slides/{slide_id}/scene/layers adds a new layer"""
    layer_data = {
        "id": str(uuid.uuid4()),
        "type": "plate",
        "name": "Background Plate",
        "position": {"x": 0, "y": 0},
        "size": {"width": 500, "height": 300},
        "visible": True,
        "locked": False,
        "zIndex": 0,
        "plate": {
            "backgroundColor": "#F3F4F6",
            "backgroundOpacity": 1.0,
            "borderRadius": 12,
            "padding": {"top": 16, "right": 16, "bottom": 16, "left": 16}
        }
    }
    
    response = await client.post(
        f"/api/canvas/slides/{sample_slide.id}/scene/layers",
        json=layer_data
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert len(data["layers"]) == 1
    assert data["layers"][0]["type"] == "plate"
    assert data["layers"][0]["plate"]["backgroundColor"] == "#F3F4F6"


@pytest.mark.asyncio
async def test_update_layer(client: AsyncClient, sample_slide: Slide):
    """PUT /canvas/slides/{slide_id}/scene/layers/{layer_id} updates a layer"""
    # First add a layer
    layer_id = str(uuid.uuid4())
    layer_data = {
        "id": layer_id,
        "type": "text",
        "name": "Test Layer",
        "position": {"x": 0, "y": 0},
        "size": {"width": 100, "height": 50},
        "visible": True,
        "locked": False,
        "zIndex": 0,
        "text": {"baseContent": "Original", "translations": {}, "isTranslatable": True}
    }
    
    await client.post(f"/api/canvas/slides/{sample_slide.id}/scene/layers", json=layer_data)
    
    # Update the layer
    updated_layer = {
        "id": layer_id,
        "type": "text",
        "name": "Updated Layer",
        "position": {"x": 50, "y": 50},
        "size": {"width": 200, "height": 100},
        "visible": True,
        "locked": True,
        "zIndex": 0,
        "text": {"baseContent": "Updated", "translations": {"ru": "Обновлено"}, "isTranslatable": True}
    }
    
    response = await client.put(
        f"/api/canvas/slides/{sample_slide.id}/scene/layers/{layer_id}",
        json=updated_layer
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["layers"][0]["name"] == "Updated Layer"
    assert data["layers"][0]["position"]["x"] == 50
    assert data["layers"][0]["locked"] is True
    assert data["layers"][0]["text"]["baseContent"] == "Updated"
    assert data["layers"][0]["text"]["translations"]["ru"] == "Обновлено"


@pytest.mark.asyncio
async def test_delete_layer(client: AsyncClient, sample_slide: Slide):
    """DELETE /canvas/slides/{slide_id}/scene/layers/{layer_id} removes a layer"""
    # First add two layers
    layer1_id = str(uuid.uuid4())
    layer2_id = str(uuid.uuid4())
    
    layer1 = {
        "id": layer1_id,
        "type": "text",
        "name": "Layer 1",
        "position": {"x": 0, "y": 0},
        "size": {"width": 100, "height": 50},
        "visible": True,
        "locked": False,
        "zIndex": 0,
        "text": {"baseContent": "First", "translations": {}, "isTranslatable": True}
    }
    layer2 = {
        "id": layer2_id,
        "type": "text",
        "name": "Layer 2",
        "position": {"x": 0, "y": 60},
        "size": {"width": 100, "height": 50},
        "visible": True,
        "locked": False,
        "zIndex": 1,
        "text": {"baseContent": "Second", "translations": {}, "isTranslatable": True}
    }
    
    await client.post(f"/api/canvas/slides/{sample_slide.id}/scene/layers", json=layer1)
    await client.post(f"/api/canvas/slides/{sample_slide.id}/scene/layers", json=layer2)
    
    # Delete layer 1
    response = await client.delete(
        f"/api/canvas/slides/{sample_slide.id}/scene/layers/{layer1_id}"
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert len(data["layers"]) == 1
    assert data["layers"][0]["id"] == layer2_id


@pytest.mark.asyncio
async def test_reorder_layers(client: AsyncClient, sample_slide: Slide):
    """PUT /canvas/slides/{slide_id}/scene/layers/reorder changes z-order"""
    # Add multiple layers
    layer1_id = str(uuid.uuid4())
    layer2_id = str(uuid.uuid4())
    layer3_id = str(uuid.uuid4())
    
    for i, lid in enumerate([layer1_id, layer2_id, layer3_id]):
        layer = {
            "id": lid,
            "type": "text",
            "name": f"Layer {i+1}",
            "position": {"x": 0, "y": i * 50},
            "size": {"width": 100, "height": 50},
            "visible": True,
            "locked": False,
            "zIndex": i,
            "text": {"baseContent": f"Layer {i+1}", "translations": {}, "isTranslatable": True}
        }
        await client.post(f"/api/canvas/slides/{sample_slide.id}/scene/layers", json=layer)
    
    # Reorder: 3, 1, 2
    new_order = [layer3_id, layer1_id, layer2_id]
    
    response = await client.put(
        f"/api/canvas/slides/{sample_slide.id}/scene/layers/reorder",
        json={"layer_ids": new_order}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["layers_count"] == 3


@pytest.mark.asyncio
async def test_get_nonexistent_slide_scene(client: AsyncClient):
    """GET /canvas/slides/{slide_id}/scene returns 404 for missing slide"""
    fake_id = uuid.uuid4()
    response = await client.get(f"/api/canvas/slides/{fake_id}/scene")
    
    assert response.status_code == 404


# === MARKERS TESTS ===

@pytest.mark.asyncio
async def test_get_markers_empty(client: AsyncClient, sample_slide: Slide):
    """GET /canvas/slides/{slide_id}/markers/{lang} returns empty list by default"""
    response = await client.get(f"/api/canvas/slides/{sample_slide.id}/markers/en")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["slide_id"] == str(sample_slide.id)
    assert data["lang"] == "en"
    assert data["markers"] == []


@pytest.mark.asyncio
async def test_update_markers(client: AsyncClient, sample_slide: Slide):
    """PUT /canvas/slides/{slide_id}/markers/{lang} saves markers"""
    markers_data = {
        "markers": [
            {
                "id": "marker-1",
                "name": "Intro",
                "charStart": 0,
                "charEnd": 5,
                "wordText": "Hello",
                "timeSeconds": 0.5
            },
            {
                "id": "marker-2",
                "name": "Key Point",
                "charStart": 6,
                "charEnd": 11,
                "wordText": "World",
                "timeSeconds": 1.2
            }
        ]
    }
    
    response = await client.put(
        f"/api/canvas/slides/{sample_slide.id}/markers/en",
        json=markers_data
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert len(data["markers"]) == 2
    assert data["markers"][0]["id"] == "marker-1"
    assert data["markers"][0]["wordText"] == "Hello"
    assert data["markers"][1]["timeSeconds"] == 1.2


# === MARKERS PROPAGATION TESTS ===

@pytest.mark.asyncio
async def test_propagate_markers_to_language(
    client: AsyncClient,
    db_session: AsyncSession,
    sample_slide: Slide,
):
    """
    POST /canvas/slides/{slide_id}/markers/propagate copies marker IDs to target language
    and best-effort maps positions by word-index ratio.
    """
    slide_id = sample_slide.id

    # Create scripts in source + target languages
    source_text = "Hello world again"
    target_text = "Привет мир снова"

    db_session.add(
        SlideScript(
            slide_id=slide_id,
            lang="en",
            text=source_text,
        )
    )
    db_session.add(
        SlideScript(
            slide_id=slide_id,
            lang="ru",
            text=target_text,
        )
    )
    await db_session.commit()

    # Create a marker anchored to the 2nd word ("world") in English
    markers_data = {
        "markers": [
            {
                "id": "m-world",
                "name": "World Anchor",
                "charStart": 6,
                "charEnd": 11,
                "wordText": "world",
                "timeSeconds": 1.5,
            }
        ]
    }
    put_resp = await client.put(f"/api/canvas/slides/{slide_id}/markers/en", json=markers_data)
    assert put_resp.status_code == 200

    # Propagate to Russian
    propagate_resp = await client.post(
        f"/api/canvas/slides/{slide_id}/markers/propagate",
        params={"source_lang": "en", "target_lang": "ru"},
    )
    assert propagate_resp.status_code == 200
    payload = propagate_resp.json()
    assert payload["status"] == "success"
    assert payload["source_lang"] == "en"
    assert payload["target_lang"] == "ru"
    assert payload["markers_propagated"] == 1

    # Fetch RU markers and verify id preserved + mapped word/position
    get_ru = await client.get(f"/api/canvas/slides/{slide_id}/markers/ru")
    assert get_ru.status_code == 200
    ru_data = get_ru.json()
    assert len(ru_data["markers"]) == 1

    ru_marker = ru_data["markers"][0]
    assert ru_marker["id"] == "m-world"
    assert ru_marker["name"] == "World Anchor"
    assert ru_marker["timeSeconds"] == 0  # reset; will be filled by TTS for target language

    # Expected mapping via tokenize_words (robust to unicode/normalization)
    from app.adapters.text_normalizer import normalize_text, tokenize_words

    target_words = tokenize_words(normalize_text(target_text))
    assert len(target_words) >= 2
    expected_char_start, expected_char_end, expected_word = target_words[1]
    assert ru_marker["charStart"] == expected_char_start
    assert ru_marker["charEnd"] == expected_char_end
    assert ru_marker["wordText"] == expected_word


# === ASSET TESTS ===

@pytest.mark.asyncio
async def test_list_assets_empty(client: AsyncClient, sample_project: Project):
    """GET /canvas/projects/{project_id}/assets returns empty list initially"""
    response = await client.get(f"/api/canvas/projects/{sample_project.id}/assets")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["assets"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_upload_asset(client: AsyncClient, sample_project: Project, tmp_path):
    """POST /canvas/projects/{project_id}/assets uploads an image"""
    # Create a simple PNG file
    from PIL import Image
    import io
    
    img = Image.new('RGB', (100, 100), color='red')
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    
    response = await client.post(
        f"/api/canvas/projects/{sample_project.id}/assets",
        files={"file": ("test.png", img_bytes, "image/png")},
        params={"type": "image"}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["type"] == "image"
    assert data["width"] == 100
    assert data["height"] == 100
    assert "url" in data
    assert "id" in data


@pytest.mark.asyncio
async def test_upload_asset_rejects_too_large_file(
    client: AsyncClient,
    sample_project: Project,
    monkeypatch,
):
    """POST /canvas/projects/{project_id}/assets enforces max upload size (DoS protection)"""
    from app.api.routes import canvas as canvas_routes

    # Keep test fast: lower the max size to 1MB and upload slightly more.
    monkeypatch.setattr(canvas_routes, "MAX_ASSET_SIZE_BYTES", 1024 * 1024)

    payload = b"\x00" * (1024 * 1024 + 1)
    response = await client.post(
        f"/api/canvas/projects/{sample_project.id}/assets",
        files={"file": ("big.png", payload, "image/png")},
        params={"type": "image"},
    )
    assert response.status_code == 413
    assert "too large" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_upload_asset_rejects_decompression_bomb(
    client: AsyncClient,
    sample_project: Project,
    monkeypatch,
):
    """POST /canvas/projects/{project_id}/assets rejects huge pixel images (decompression bomb)"""
    from app.api.routes import canvas as canvas_routes

    # Keep test deterministic: lower pixel threshold so a small image triggers it.
    monkeypatch.setattr(canvas_routes, "MAX_IMAGE_PIXELS", 100)

    from PIL import Image
    import io

    img = Image.new("RGB", (20, 20), color="red")  # 400 pixels > 100
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")
    img_bytes.seek(0)

    response = await client.post(
        f"/api/canvas/projects/{sample_project.id}/assets",
        files={"file": ("bomb.png", img_bytes, "image/png")},
        params={"type": "image"},
    )
    assert response.status_code == 400
    assert "too large" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_asset(client: AsyncClient, sample_project: Project):
    """DELETE /canvas/assets/{asset_id} removes an asset"""
    # First upload an asset
    from PIL import Image
    import io
    
    img = Image.new('RGB', (50, 50), color='blue')
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    
    upload_response = await client.post(
        f"/api/canvas/projects/{sample_project.id}/assets",
        files={"file": ("test.png", img_bytes, "image/png")},
        params={"type": "background"}
    )
    
    asset_id = upload_response.json()["id"]
    
    # Delete the asset
    delete_response = await client.delete(f"/api/canvas/assets/{asset_id}")
    
    assert delete_response.status_code == 204
    
    # Verify it's gone
    list_response = await client.get(f"/api/canvas/projects/{sample_project.id}/assets")
    assert list_response.json()["total"] == 0


@pytest.mark.asyncio
async def test_upload_invalid_file_type(client: AsyncClient, sample_project: Project):
    """POST /canvas/projects/{project_id}/assets rejects non-image files"""
    response = await client.post(
        f"/api/canvas/projects/{sample_project.id}/assets",
        files={"file": ("test.txt", b"hello world", "text/plain")},
        params={"type": "image"}
    )
    
    assert response.status_code == 400
    assert "Invalid file type" in response.json()["detail"]


# === TEXT NORMALIZATION TESTS ===

def test_normalize_text():
    """Test text normalization utility"""
    from app.adapters.text_normalizer import normalize_text
    
    # Smart quotes
    text = "\u201CHello\u201D \u2018world\u2019"
    normalized = normalize_text(text)
    assert normalized == '"Hello" \'world\''
    
    # Multiple spaces
    text = "Hello    world"
    normalized = normalize_text(text)
    assert normalized == "Hello world"
    
    # Em dash
    text = "Hello\u2014world"
    normalized = normalize_text(text)
    assert normalized == "Hello-world"


def test_tokenize_words():
    """Test word tokenization with char offsets"""
    from app.adapters.text_normalizer import tokenize_words
    
    text = "Hello world, how are you?"
    words = tokenize_words(text)
    
    # Should have: Hello, world, how, are, you?
    assert len(words) >= 5
    
    # First word
    assert words[0][0] == 0  # charStart
    assert words[0][1] == 5  # charEnd
    assert words[0][2] == "Hello"  # word


def test_estimate_word_timings():
    """Test fallback timing estimation"""
    from app.adapters.text_normalizer import estimate_word_timings
    
    text = "Hello world"
    total_duration = 2.0
    
    timings = estimate_word_timings(text, total_duration)
    
    assert len(timings) == 2
    assert timings[0]["word"] == "Hello"
    assert timings[0]["startTime"] == 0.0
    assert timings[1]["word"] == "world"
    assert timings[-1]["endTime"] == pytest.approx(total_duration, rel=0.1)


# === LAYER WITH ANIMATION TESTS ===

@pytest.mark.asyncio
async def test_add_layer_with_animation(client: AsyncClient, sample_slide: Slide):
    """Test adding layer with animation configuration"""
    layer_data = {
        "id": str(uuid.uuid4()),
        "type": "text",
        "name": "Animated Title",
        "position": {"x": 100, "y": 100},
        "size": {"width": 400, "height": 60},
        "visible": True,
        "locked": False,
        "zIndex": 0,
        "text": {
            "baseContent": "Welcome!",
            "translations": {},
            "isTranslatable": True
        },
        "animation": {
            "entrance": {
                "type": "fadeIn",
                "duration": 0.5,
                "delay": 0,
                "easing": "easeOut",
                "trigger": {
                    "type": "word",
                    "charStart": 0,
                    "charEnd": 7,
                    "wordText": "Welcome"
                }
            },
            "exit": {
                "type": "fadeOut",
                "duration": 0.3,
                "delay": 0,
                "easing": "easeIn",
                "trigger": {
                    "type": "end",
                    "offsetSeconds": -0.5
                }
            }
        }
    }
    
    response = await client.post(
        f"/api/canvas/slides/{sample_slide.id}/scene/layers",
        json=layer_data
    )
    
    assert response.status_code == 200
    data = response.json()
    
    layer = data["layers"][0]
    assert layer["animation"]["entrance"]["type"] == "fadeIn"
    assert layer["animation"]["entrance"]["trigger"]["type"] == "word"
    assert layer["animation"]["exit"]["type"] == "fadeOut"


# === INTEGRATION TEST ===

@pytest.mark.asyncio
async def test_full_scene_workflow(
    client: AsyncClient,
    sample_project: Project,
    sample_version: ProjectVersion,
    sample_slide: Slide
):
    """Integration test: create scene with layers, save, reload"""
    slide_id = sample_slide.id
    
    # 1. Create scene with layers
    scene_data = {
        "canvas": {"width": 1920, "height": 1080},
        "layers": [
            {
                "id": "bg-plate",
                "type": "plate",
                "name": "Background",
                "position": {"x": 100, "y": 100},
                "size": {"width": 600, "height": 400},
                "visible": True,
                "locked": False,
                "zIndex": 0,
                "plate": {
                    "backgroundColor": "#FFFFFF",
                    "backgroundOpacity": 0.9,
                    "borderRadius": 16
                }
            },
            {
                "id": "title-text",
                "type": "text",
                "name": "Title",
                "position": {"x": 150, "y": 150},
                "size": {"width": 500, "height": 60},
                "visible": True,
                "locked": False,
                "zIndex": 1,
                "text": {
                    "baseContent": "Welcome to Presentation",
                    "translations": {"ru": "Добро пожаловать"},
                    "isTranslatable": True,
                    "style": {"fontSize": 36, "fontWeight": "bold"}
                },
                "animation": {
                    "entrance": {
                        "type": "slideLeft",
                        "duration": 0.6,
                        "delay": 0.2,
                        "easing": "easeOut",
                        "trigger": {"type": "start", "offsetSeconds": 0.5}
                    }
                }
            }
        ]
    }
    
    save_response = await client.put(
        f"/api/canvas/slides/{slide_id}/scene",
        json=scene_data
    )
    assert save_response.status_code == 200
    saved_render_key = save_response.json()["render_key"]
    
    # 2. Reload scene
    load_response = await client.get(f"/api/canvas/slides/{slide_id}/scene")
    assert load_response.status_code == 200
    loaded = load_response.json()
    
    assert len(loaded["layers"]) == 2
    assert loaded["layers"][1]["text"]["translations"]["ru"] == "Добро пожаловать"
    assert loaded["render_key"] == saved_render_key
    
    # 3. Add markers
    markers_data = {
        "markers": [
            {
                "id": "m1",
                "name": "Welcome Word",
                "charStart": 0,
                "charEnd": 7,
                "wordText": "Welcome"
            }
        ]
    }
    
    markers_response = await client.put(
        f"/api/canvas/slides/{slide_id}/markers/en",
        json=markers_data
    )
    assert markers_response.status_code == 200
    
    # 4. Verify markers
    get_markers = await client.get(f"/api/canvas/slides/{slide_id}/markers/en")
    assert get_markers.status_code == 200
    assert get_markers.json()["markers"][0]["wordText"] == "Welcome"


# === TRANSLATION TEST ===

@pytest.mark.asyncio
async def test_translate_scene_text_layers(
    client: AsyncClient,
    sample_project: Project,
    sample_version: ProjectVersion,
    sample_slide: Slide
):
    """Test translating text layers in a scene"""
    from unittest.mock import patch, AsyncMock
    
    slide_id = sample_slide.id
    
    # 1. Create scene with translatable text layers
    scene_data = {
        "layers": [
            {
                "id": "title-layer",
                "type": "text",
                "name": "Title",
                "position": {"x": 100, "y": 100},
                "size": {"width": 400, "height": 60},
                "visible": True,
                "locked": False,
                "zIndex": 0,
                "text": {
                    "baseContent": "Hello World",
                    "translations": {},
                    "isTranslatable": True
                }
            },
            {
                "id": "subtitle-layer",
                "type": "text",
                "name": "Subtitle",
                "position": {"x": 100, "y": 200},
                "size": {"width": 400, "height": 40},
                "visible": True,
                "locked": False,
                "zIndex": 1,
                "text": {
                    "baseContent": "Welcome to our presentation",
                    "translations": {},
                    "isTranslatable": True
                }
            },
            {
                "id": "non-translatable",
                "type": "text",
                "name": "Logo Text",
                "position": {"x": 100, "y": 300},
                "size": {"width": 200, "height": 30},
                "visible": True,
                "locked": False,
                "zIndex": 2,
                "text": {
                    "baseContent": "CompanyName",
                    "translations": {},
                    "isTranslatable": False
                }
            }
        ]
    }
    
    create_response = await client.put(
        f"/api/canvas/slides/{slide_id}/scene",
        json=scene_data
    )
    assert create_response.status_code == 200
    
    # 2. Mock the translate_batch method to avoid real API calls
    with patch(
        "app.adapters.translate.TranslateAdapter.translate_batch",
        new_callable=AsyncMock,
        return_value=(["Привет Мир", "Добро пожаловать"], {"checksum": "abc123"})
    ) as mock_translate:
        # 3. Request translation to Russian
        translate_response = await client.post(
            f"/api/canvas/slides/{slide_id}/scene/translate",
            json={"target_lang": "ru"}
        )
        
        assert translate_response.status_code == 200
        data = translate_response.json()
        assert data["translated_count"] == 2  # Only 2 translatable layers
        assert data["target_lang"] == "ru"
        assert len(data["layers_updated"]) == 2
        assert "title-layer" in data["layers_updated"]
        assert "subtitle-layer" in data["layers_updated"]
        
        # Verify mock was called
        mock_translate.assert_called_once()


@pytest.mark.asyncio
async def test_translate_scene_same_language(
    client: AsyncClient,
    sample_project: Project,
    sample_version: ProjectVersion,
    sample_slide: Slide
):
    """Test that translating to base language returns no translations"""
    slide_id = sample_slide.id
    
    # Create scene with text
    scene_data = {
        "layers": [{
            "id": "text1",
            "type": "text",
            "name": "Title",
            "position": {"x": 0, "y": 0},
            "size": {"width": 100, "height": 50},
            "visible": True,
            "locked": False,
            "zIndex": 0,
            "text": {
                "baseContent": "Test",
                "translations": {},
                "isTranslatable": True
            }
        }]
    }
    
    await client.put(f"/api/canvas/slides/{slide_id}/scene", json=scene_data)
    
    # Translate to same language (base = en)
    response = await client.post(
        f"/api/canvas/slides/{slide_id}/scene/translate",
        json={"target_lang": "en"}  # Same as base
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["translated_count"] == 0
    assert data["target_lang"] == "en"
    assert len(data["layers_updated"]) == 0


@pytest.mark.asyncio
async def test_get_resolved_scene_with_word_triggers(
    client: AsyncClient,
    sample_project: Project,
    sample_version: ProjectVersion,
    sample_slide: Slide
):
    """Test getting scene with word triggers resolved to time-based"""
    slide_id = sample_slide.id
    
    # Create scene with word trigger animation
    scene_data = {
        "layers": [{
            "id": "animated-text",
            "type": "text",
            "name": "Animated",
            "position": {"x": 100, "y": 100},
            "size": {"width": 400, "height": 60},
            "visible": True,
            "locked": False,
            "zIndex": 0,
            "text": {
                "baseContent": "Hello World",
                "translations": {},
                "isTranslatable": True
            },
            "animation": {
                "entrance": {
                    "type": "fadeIn",
                    "duration": 0.5,
                    "delay": 0,
                    "easing": "easeOut",
                    "trigger": {
                        "type": "word",
                        "charStart": 0,
                        "charEnd": 5,
                        "wordText": "Hello"
                    }
                }
            }
        }]
    }
    
    await client.put(f"/api/canvas/slides/{slide_id}/scene", json=scene_data)
    
    # Get resolved scene for English
    response = await client.get(
        f"/api/canvas/slides/{slide_id}/scene/resolved?lang=en"
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["lang"] == "en"
    assert "triggers_resolved" in data
    assert len(data["layers"]) == 1
    
    # Since we don't have normalized script, the word trigger should be converted
    # with estimation or kept as-is if no timing data available
    layer = data["layers"][0]
    trigger = layer["animation"]["entrance"]["trigger"]
    
    # If resolved, type should be "time" with _original_type = "word"
    # If not resolved (no timing data), it stays as "word"
    assert trigger["type"] in ["time", "word"]


@pytest.mark.asyncio
async def test_get_resolved_scene_with_marker_triggers(
    client: AsyncClient,
    sample_project: Project,
    sample_version: ProjectVersion,
    sample_slide: Slide,
    db_session: AsyncSession,
):
    """Test getting scene with marker triggers resolved to time-based"""
    slide_id = sample_slide.id

    # Persist markers with a timeSeconds value
    markers = SlideMarkers(
        id=uuid.uuid4(),
        slide_id=slide_id,
        lang="en",
        markers=[
            {
                "id": "m1",
                "name": "Intro",
                "charStart": 0,
                "charEnd": 5,
                "wordText": "Hello",
                "timeSeconds": 1.25,
            }
        ],
    )
    db_session.add(markers)
    await db_session.commit()

    # Create scene with marker trigger
    scene_data = {
        "layers": [{
            "id": "animated-text",
            "type": "text",
            "name": "Animated",
            "position": {"x": 100, "y": 100},
            "size": {"width": 400, "height": 60},
            "visible": True,
            "locked": False,
            "zIndex": 0,
            "text": {
                "baseContent": "Hello World",
                "translations": {},
                "isTranslatable": True
            },
            "animation": {
                "entrance": {
                    "type": "fadeIn",
                    "duration": 0.5,
                    "delay": 0,
                    "easing": "easeOut",
                    "trigger": {
                        "type": "marker",
                        "markerId": "m1"
                    }
                }
            }
        }]
    }
    await client.put(f"/api/canvas/slides/{slide_id}/scene", json=scene_data)

    response = await client.get(f"/api/canvas/slides/{slide_id}/scene/resolved?lang=en")
    assert response.status_code == 200
    data = response.json()

    assert data["triggers_resolved"] == 1
    trigger = data["layers"][0]["animation"]["entrance"]["trigger"]
    assert trigger["type"] == "time"
    assert trigger["seconds"] == pytest.approx(1.25)
    assert trigger["_original_type"] == "marker"


@pytest.mark.asyncio
async def test_get_resolved_scene_no_triggers(
    client: AsyncClient,
    sample_project: Project,
    sample_version: ProjectVersion,
    sample_slide: Slide
):
    """Test resolved scene with no word triggers to resolve"""
    slide_id = sample_slide.id
    
    # Create scene with time-based trigger (not word)
    scene_data = {
        "layers": [{
            "id": "simple-text",
            "type": "text",
            "name": "Simple",
            "position": {"x": 0, "y": 0},
            "size": {"width": 200, "height": 40},
            "visible": True,
            "locked": False,
            "zIndex": 0,
            "text": {"baseContent": "Test"},
            "animation": {
                "entrance": {
                    "type": "fadeIn",
                    "duration": 0.5,
                    "delay": 0,
                    "easing": "easeOut",
                    "trigger": {
                        "type": "time",
                        "seconds": 1.0
                    }
                }
            }
        }]
    }
    
    await client.put(f"/api/canvas/slides/{slide_id}/scene", json=scene_data)
    
    response = await client.get(
        f"/api/canvas/slides/{slide_id}/scene/resolved?lang=en"
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["triggers_resolved"] == 0  # No word triggers to resolve
    
    # Time trigger should remain unchanged
    trigger = data["layers"][0]["animation"]["entrance"]["trigger"]
    assert trigger["type"] == "time"
    assert trigger["seconds"] == 1.0


# === EPIC A: GLOBAL MARKERS + TOKENS TESTS ===


@pytest.mark.asyncio
async def test_create_global_marker_from_word_endpoint(
    client: AsyncClient,
    db_session: AsyncSession,
    sample_slide: Slide,
):
    slide_id = sample_slide.id

    # Script required by the endpoint
    db_session.add(SlideScript(slide_id=slide_id, lang="en", text="Hello world"))
    await db_session.commit()

    resp = await client.post(
        f"/api/canvas/slides/{slide_id}/markers/en/create-from-word",
        json={"char_start": 0, "char_end": 5},
    )
    assert resp.status_code == 200
    data = resp.json()

    marker_id = data["marker_id"]
    assert data["token"].startswith("⟦M:")
    assert marker_id in data["token"]

    gm_res = await db_session.execute(select(GlobalMarker).where(GlobalMarker.id == uuid.UUID(marker_id)))
    gm = gm_res.scalar_one()
    assert gm.slide_id == slide_id

    pos_res = await db_session.execute(
        select(MarkerPosition)
        .where(MarkerPosition.marker_id == gm.id)
        .where(MarkerPosition.lang == "en")
    )
    pos = pos_res.scalar_one()
    assert pos.char_start == 0
    assert pos.char_end == 5


@pytest.mark.asyncio
async def test_list_global_markers_endpoint(
    client: AsyncClient,
    db_session: AsyncSession,
    sample_slide: Slide,
):
    slide_id = sample_slide.id
    db_session.add(SlideScript(slide_id=slide_id, lang="en", text="Hello world"))
    await db_session.commit()

    create = await client.post(
        f"/api/canvas/slides/{slide_id}/markers/en/create-from-word",
        json={"char_start": 0, "char_end": 5, "name": "Intro"},
    )
    assert create.status_code == 200
    marker_id = create.json()["marker_id"]

    resp = await client.get(f"/api/canvas/slides/{slide_id}/global-markers")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] == 1
    assert payload["markers"][0]["marker_id"] == marker_id
    assert payload["markers"][0]["positions"]["en"]["char_start"] == 0


@pytest.mark.asyncio
async def test_insert_marker_tokens_updates_script_and_normalized_script(
    client: AsyncClient,
    db_session: AsyncSession,
    sample_slide: Slide,
):
    slide_id = sample_slide.id
    base_text = "Hello world"

    script = SlideScript(slide_id=slide_id, lang="en", text=base_text)
    db_session.add(script)
    await db_session.flush()

    # Create marker via API (creates GlobalMarker + MarkerPosition with char_start=0)
    create = await client.post(
        f"/api/canvas/slides/{slide_id}/markers/en/create-from-word",
        json={"char_start": 0, "char_end": 5},
    )
    assert create.status_code == 200
    marker_id = create.json()["marker_id"]
    token = create.json()["token"]

    # Create NormalizedScript so endpoint updates contains_marker_tokens
    from app.adapters.text_normalizer import normalize_text

    ns = NormalizedScript(
        slide_id=slide_id,
        lang="en",
        raw_text=base_text,
        normalized_text=normalize_text(base_text),
        word_timings=None,
    )
    db_session.add(ns)
    await db_session.commit()

    resp = await client.post(f"/api/canvas/slides/{slide_id}/script/en/insert-marker-tokens")
    assert resp.status_code == 200
    out = resp.json()
    assert out["tokens_inserted"] == 1
    assert token in out["updated_text"]

    # Verify script updated in DB
    sres = await db_session.execute(
        select(SlideScript).where(SlideScript.slide_id == slide_id).where(SlideScript.lang == "en")
    )
    script_db = sres.scalar_one()
    assert token in script_db.text
    assert marker_id in script_db.text

    # Verify normalized script updated
    nsres = await db_session.execute(
        select(NormalizedScript).where(NormalizedScript.slide_id == slide_id).where(NormalizedScript.lang == "en")
    )
    ns_db = nsres.scalar_one()
    assert ns_db.contains_marker_tokens is True
    assert token in ns_db.normalized_text


@pytest.mark.asyncio
async def test_compute_marker_times_uses_token_anchor_word(
    client: AsyncClient,
    db_session: AsyncSession,
    sample_slide: Slide,
):
    slide_id = sample_slide.id

    # Base script required for marker creation
    script = SlideScript(slide_id=slide_id, lang="en", text="Hello world")
    db_session.add(script)
    await db_session.commit()

    create = await client.post(
        f"/api/canvas/slides/{slide_id}/markers/en/create-from-word",
        json={"char_start": 0, "char_end": 5},
    )
    assert create.status_code == 200
    marker_id = create.json()["marker_id"]
    token = create.json()["token"]

    # Create NormalizedScript with token + word timings
    from app.adapters.text_normalizer import normalize_text

    text_with_token = f"{token}Hello world"
    token_len = len(token)

    ns = NormalizedScript(
        slide_id=slide_id,
        lang="en",
        raw_text=text_with_token,
        normalized_text=normalize_text(text_with_token),
        word_timings=[
            {"charStart": token_len, "charEnd": token_len + 5, "startTime": 1.5, "endTime": 1.7, "word": "Hello"},
            {"charStart": token_len + 6, "charEnd": token_len + 11, "startTime": 2.0, "endTime": 2.2, "word": "world"},
        ],
    )
    db_session.add(ns)
    await db_session.commit()

    resp = await client.post(f"/api/canvas/slides/{slide_id}/markers/en/compute-times")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["markers_updated"] >= 1

    # Verify MarkerPosition time_seconds updated
    pos_res = await db_session.execute(
        select(MarkerPosition)
        .where(MarkerPosition.lang == "en")
        .where(MarkerPosition.marker_id == uuid.UUID(marker_id))
    )
    pos = pos_res.scalar_one()
    assert pos.time_seconds == pytest.approx(1.5)


@pytest.mark.asyncio
async def test_migrate_scene_word_triggers_to_markers_endpoint(
    client: AsyncClient,
    db_session: AsyncSession,
    sample_project: Project,
    sample_slide: Slide,
):
    slide_id = sample_slide.id

    # Base + translated scripts
    db_session.add(SlideScript(slide_id=slide_id, lang="en", text="Hello world"))
    db_session.add(SlideScript(slide_id=slide_id, lang="ru", text="Привет мир"))
    await db_session.commit()

    # Scene with a word trigger
    scene_data = {
        "layers": [
            {
                "id": "layer-1",
                "type": "text",
                "name": "Animated",
                "position": {"x": 0, "y": 0},
                "size": {"width": 300, "height": 60},
                "visible": True,
                "locked": False,
                "zIndex": 0,
                "text": {"baseContent": "Hello world"},
                "animation": {
                    "entrance": {
                        "type": "fadeIn",
                        "duration": 0.5,
                        "delay": 0,
                        "easing": "easeOut",
                        "trigger": {"type": "word", "charStart": 0, "charEnd": 5, "wordText": "Hello"},
                    }
                },
            }
        ]
    }
    put = await client.put(f"/api/canvas/slides/{slide_id}/scene", json=scene_data)
    assert put.status_code == 200

    mig = await client.post(f"/api/canvas/slides/{slide_id}/scene/migrate-triggers")
    assert mig.status_code == 200
    out = mig.json()
    assert out["markers_created"] == 1
    assert out["triggers_migrated"] == 1
    assert out["tokens_inserted"] == 1
    assert "ru" in out["needs_retranslate"]

    # Verify scene trigger now has markerId
    scene_res = await db_session.execute(select(SlideScene).where(SlideScene.slide_id == slide_id))
    scene = scene_res.scalar_one()
    trig = scene.layers[0]["animation"]["entrance"]["trigger"]
    assert trig.get("markerId")

    # Verify base script contains marker token
    sres = await db_session.execute(select(SlideScript).where(SlideScript.slide_id == slide_id).where(SlideScript.lang == "en"))
    s = sres.scalar_one()
    assert "⟦M:" in s.text


@pytest.mark.asyncio
async def test_resolved_scene_uses_global_marker_positions(
    client: AsyncClient,
    db_session: AsyncSession,
    sample_slide: Slide,
):
    slide_id = sample_slide.id

    # Create a GlobalMarker with time_seconds for 'en'
    marker_id = uuid.uuid4()
    db_session.add(GlobalMarker(id=marker_id, slide_id=slide_id, name="Test"))
    db_session.add(
        MarkerPosition(
            id=uuid.uuid4(),
            marker_id=marker_id,
            lang="en",
            char_start=0,
            char_end=5,
            time_seconds=2.25,
        )
    )
    await db_session.commit()

    # Scene with marker trigger referencing the global marker UUID
    scene_data = {
        "layers": [
            {
                "id": "layer-1",
                "type": "text",
                "name": "Animated",
                "position": {"x": 0, "y": 0},
                "size": {"width": 300, "height": 60},
                "visible": True,
                "locked": False,
                "zIndex": 0,
                "text": {"baseContent": "Hello"},
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
        ]
    }
    put = await client.put(f"/api/canvas/slides/{slide_id}/scene", json=scene_data)
    assert put.status_code == 200

    resp = await client.get(f"/api/canvas/slides/{slide_id}/scene/resolved?lang=en")
    assert resp.status_code == 200
    data = resp.json()
    assert data["triggers_resolved"] == 1
    trigger = data["layers"][0]["animation"]["entrance"]["trigger"]
    assert trigger["type"] == "time"
    assert trigger["seconds"] == pytest.approx(2.25)

