"""
Canvas Editor API Routes
- Scenes (layers, positions, animations)
- Markers
- Assets
- Normalized scripts with word timings
"""
import uuid
import hashlib
import json
import shutil
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Query, Body
from pydantic import BaseModel
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from PIL import Image

from app.db import get_db
from app.db.models import (
    Slide, SlideScene, SlideMarkers, NormalizedScript, Asset, Project, SlideAudio,
    GlobalMarker, MarkerPosition, MarkerSource
)
from app.api.schemas.canvas import (
    SlideSceneCreate, SlideSceneUpdate, SlideSceneRead,
    SlideMarkersCreate, SlideMarkersUpdate, SlideMarkersRead,
    NormalizedScriptRead, WordTiming,
    AssetCreate, AssetRead, AssetListResponse,
    SlideLayer
)
from app.core.config import settings
from app.core.paths import to_relative_path, to_absolute_path

router = APIRouter()

# Allowed image types for assets
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"}


def compute_render_key(layers: list, canvas: dict) -> str:
    """Compute a hash key for caching rendered scenes"""
    content = json.dumps({"layers": layers, "canvas": canvas}, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


# === SCENE ENDPOINTS ===

@router.get("/slides/{slide_id}/scene", response_model=SlideSceneRead)
async def get_slide_scene(
    slide_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get the canvas scene for a slide. Creates default scene if not exists."""
    # Check slide exists
    slide = await db.get(Slide, slide_id)
    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found")
    
    # Get or create scene
    result = await db.execute(
        select(SlideScene).where(SlideScene.slide_id == slide_id)
    )
    scene = result.scalar_one_or_none()
    
    if not scene:
        # Create default scene
        scene = SlideScene(
            id=uuid.uuid4(),
            slide_id=slide_id,
            canvas_width=1920,
            canvas_height=1080,
            layers=[],
            schema_version=1,
            render_key=compute_render_key([], {"width": 1920, "height": 1080})
        )
        db.add(scene)
        await db.commit()
        await db.refresh(scene)
    
    return SlideSceneRead(
        id=scene.id,
        slide_id=scene.slide_id,
        canvas={"width": scene.canvas_width, "height": scene.canvas_height},
        layers=scene.layers or [],
        schema_version=scene.schema_version,
        render_key=scene.render_key,
        created_at=scene.created_at,
        updated_at=scene.updated_at
    )


@router.put("/slides/{slide_id}/scene", response_model=SlideSceneRead)
async def update_slide_scene(
    slide_id: uuid.UUID,
    scene_data: SlideSceneUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update the canvas scene for a slide."""
    # Check slide exists
    slide = await db.get(Slide, slide_id)
    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found")
    
    # Get or create scene
    result = await db.execute(
        select(SlideScene).where(SlideScene.slide_id == slide_id)
    )
    scene = result.scalar_one_or_none()
    
    if not scene:
        # Create with explicit defaults to avoid None values
        scene = SlideScene(
            id=uuid.uuid4(),
            slide_id=slide_id,
            canvas_width=1920,
            canvas_height=1080,
            layers=[],
            schema_version=1,
            render_key=compute_render_key([], {"width": 1920, "height": 1080})
        )
        db.add(scene)
    
    # Update fields
    if scene_data.canvas:
        scene.canvas_width = scene_data.canvas.width
        scene.canvas_height = scene_data.canvas.height
    
    if scene_data.layers is not None:
        # Convert layers to dict for JSON storage.
        # Ensure zIndex is always a number in persisted JSON (None is only used as "auto-assign" input).
        normalized_layers = []
        for i, l in enumerate(scene_data.layers):
            if l.zIndex is None:
                l.zIndex = i
            normalized_layers.append(l.model_dump())
        scene.layers = normalized_layers
    
    # Compute render_key server-side
    scene.render_key = compute_render_key(
        scene.layers,
        {"width": scene.canvas_width, "height": scene.canvas_height}
    )
    scene.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(scene)
    
    return SlideSceneRead(
        id=scene.id,
        slide_id=scene.slide_id,
        canvas={"width": scene.canvas_width, "height": scene.canvas_height},
        layers=scene.layers or [],
        schema_version=scene.schema_version,
        render_key=scene.render_key,
        created_at=scene.created_at,
        updated_at=scene.updated_at
    )


class GeneratePreviewResponse(BaseModel):
    success: bool
    preview_url: str
    slide_id: str


@router.post("/slides/{slide_id}/preview", response_model=GeneratePreviewResponse)
async def generate_slide_preview(
    slide_id: uuid.UUID,
    lang: str = Query("en", description="Language for text layers"),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate a PNG preview of the slide with all canvas layers rendered.
    
    This is called after saving a canvas scene to update the slide thumbnail.
    The preview is saved to the slide's directory and replaces the original PNG.
    """
    from app.adapters.render_service import get_render_service_client
    from app.core.paths import to_absolute_path, to_relative_path, slide_image_url
    import shutil
    
    # Get slide
    slide = await db.get(Slide, slide_id)
    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found")
    
    # Get scene
    result = await db.execute(
        select(SlideScene).where(SlideScene.slide_id == slide_id)
    )
    scene = result.scalar_one_or_none()
    
    layers = scene.layers if scene else []
    
    # Get absolute path to slide image
    slide_image_path = to_absolute_path(slide.image_path)
    if not slide_image_path.exists():
        raise HTTPException(status_code=404, detail="Slide image not found")
    
    # If no layers, just return the original slide image URL
    if not layers:
        return GeneratePreviewResponse(
            success=True,
            preview_url=slide_image_url(slide.image_path),
            slide_id=str(slide_id),
        )
    
    # Sanitize layers for render-service (strict Zod validation):
    # - drop nulls (optional fields must be omitted, not null)
    # - drop UI-only / unsupported keys (anchor, fromState)
    def _sanitize_for_render_service(obj):
        if isinstance(obj, dict):
            cleaned = {}
            for k, v in obj.items():
                if k in {"anchor", "fromState"}:
                    continue
                if v is None:
                    continue
                cleaned[k] = _sanitize_for_render_service(v)
            return cleaned
        if isinstance(obj, list):
            return [_sanitize_for_render_service(i) for i in obj]
        return obj
    
    sanitized_layers = _sanitize_for_render_service(layers)
    # Extra compatibility: render-service schema requires image.assetId (safeIdSchema)
    # Our UI sometimes saves "" for assetId; fill it with the layer id.
    try:
        for l in sanitized_layers:
            if isinstance(l, dict) and l.get("type") == "image":
                img = l.get("image")
                if isinstance(img, dict):
                    if not img.get("assetId"):
                        img["assetId"] = str(l.get("id") or "asset")
                    # Plate accent is currently UI-only; drop it to avoid Zod errors
            if isinstance(l, dict) and l.get("type") == "plate":
                plate = l.get("plate")
                if isinstance(plate, dict) and "accent" in plate:
                    plate.pop("accent", None)
    except Exception:
        pass
    
    # Call render-service to generate preview
    render_client = get_render_service_client()
    
    try:
        result = await render_client.render_preview(
            slide_id=str(slide_id),
            slide_image_url=str(slide_image_path),
            layers=sanitized_layers,
            width=1920,
            height=1080,
            lang=lang,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Preview generation failed: {str(e)}")
    
    # Copy preview to slide's preview path.
    # We version the filename with render_key so the URL changes on each edit (avoids browser cache showing stale preview).
    output_path = Path(result.get("outputPath", ""))
    if not output_path.exists():
        raise HTTPException(status_code=500, detail="Preview file not generated")
    
    slides_dir = slide_image_path.parent
    render_key = (scene.render_key if scene else None) or ""
    if render_key:
        preview_filename = f"slide_{slide_id}_{render_key}.png"
    else:
        preview_filename = f"slide_{slide_id}.png"
    preview_path = slides_dir / preview_filename
    
    # Copy the rendered preview
    shutil.copy2(output_path, preview_path)
    
    # Best-effort cleanup of previous preview file (avoid unbounded growth)
    try:
        if slide.preview_path:
            old_abs = to_absolute_path(slide.preview_path)
            if old_abs.exists() and old_abs != preview_path:
                old_abs.unlink()
    except Exception:
        pass

    # Update slide record with preview path
    slide.preview_path = to_relative_path(preview_path)
    await db.commit()
    
    # Return the preview URL
    preview_url = slide_image_url(slide.preview_path) if slide.preview_path else ""
    
    return GeneratePreviewResponse(
        success=True,
        preview_url=preview_url,
        slide_id=str(slide_id),
    )


@router.post("/slides/{slide_id}/scene/layers", response_model=SlideSceneRead)
async def add_layer(
    slide_id: uuid.UUID,
    layer: SlideLayer,
    db: AsyncSession = Depends(get_db)
):
    """Add a new layer to the scene."""
    result = await db.execute(
        select(SlideScene).where(SlideScene.slide_id == slide_id)
    )
    scene = result.scalar_one_or_none()
    
    if not scene:
        # Create scene first with explicit defaults
        slide = await db.get(Slide, slide_id)
        if not slide:
            raise HTTPException(status_code=404, detail="Slide not found")
        
        scene = SlideScene(
            id=uuid.uuid4(),
            slide_id=slide_id,
            canvas_width=1920,
            canvas_height=1080,
            layers=[],
            schema_version=1,
            render_key=compute_render_key([], {"width": 1920, "height": 1080})
        )
        db.add(scene)
    
    # Add layer
    layers = list(scene.layers or [])
    
    # Ensure unique ID
    if not layer.id:
        layer.id = str(uuid.uuid4())
    
    # Set zIndex if not provided (None means auto-assign, 0 is valid bottom layer)
    if layer.zIndex is None:
        if layers:
            layer.zIndex = max(l.get("zIndex", 0) for l in layers) + 1
        else:
            layer.zIndex = 0
    
    layers.append(layer.model_dump())
    scene.layers = layers
    scene.render_key = compute_render_key(layers, {"width": scene.canvas_width, "height": scene.canvas_height})
    scene.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(scene)
    
    return SlideSceneRead(
        id=scene.id,
        slide_id=scene.slide_id,
        canvas={"width": scene.canvas_width, "height": scene.canvas_height},
        layers=scene.layers or [],
        schema_version=scene.schema_version,
        render_key=scene.render_key,
        created_at=scene.created_at,
        updated_at=scene.updated_at
    )


class ReorderLayersRequest(BaseModel):
    layer_ids: list[str]


@router.put("/slides/{slide_id}/scene/layers/reorder")
async def reorder_layers(
    slide_id: uuid.UUID,
    request: ReorderLayersRequest,
    db: AsyncSession = Depends(get_db)
):
    """Reorder layers by providing ordered list of layer IDs."""
    layer_ids = request.layer_ids
    result = await db.execute(
        select(SlideScene).where(SlideScene.slide_id == slide_id)
    )
    scene = result.scalar_one_or_none()
    
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    
    layers = scene.layers or []
    layers_by_id = {l.get("id"): l for l in layers}
    
    # Reorder and update zIndex
    new_layers = []
    for i, lid in enumerate(layer_ids):
        if lid in layers_by_id:
            layer = layers_by_id[lid]
            layer["zIndex"] = i
            new_layers.append(layer)
    
    # Add any layers not in the list at the end
    for l in layers:
        if l.get("id") not in layer_ids:
            l["zIndex"] = len(new_layers)
            new_layers.append(l)
    
    scene.layers = new_layers
    scene.render_key = compute_render_key(new_layers, {"width": scene.canvas_width, "height": scene.canvas_height})
    scene.updated_at = datetime.utcnow()
    
    await db.commit()
    
    return {"status": "ok", "layers_count": len(new_layers)}


@router.put("/slides/{slide_id}/scene/layers/{layer_id}", response_model=SlideSceneRead)
async def update_layer(
    slide_id: uuid.UUID,
    layer_id: str,
    layer: SlideLayer,
    db: AsyncSession = Depends(get_db)
):
    """Update a specific layer."""
    result = await db.execute(
        select(SlideScene).where(SlideScene.slide_id == slide_id)
    )
    scene = result.scalar_one_or_none()
    
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    
    layers = list(scene.layers or [])
    layer_index = next((i for i, l in enumerate(layers) if l.get("id") == layer_id), None)
    
    if layer_index is None:
        raise HTTPException(status_code=404, detail="Layer not found")
    
    # Update layer
    layer.id = layer_id  # Preserve original ID
    # Preserve existing zIndex if the client omitted it (None).
    existing_layer = layers[layer_index] if layer_index is not None else {}
    if getattr(layer, "zIndex", None) is None:
        try:
            existing_z = existing_layer.get("zIndex")
            layer.zIndex = existing_z if existing_z is not None else layer_index
        except Exception:
            layer.zIndex = layer_index
    layers[layer_index] = layer.model_dump()
    scene.layers = layers
    scene.render_key = compute_render_key(layers, {"width": scene.canvas_width, "height": scene.canvas_height})
    scene.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(scene)
    
    return SlideSceneRead(
        id=scene.id,
        slide_id=scene.slide_id,
        canvas={"width": scene.canvas_width, "height": scene.canvas_height},
        layers=scene.layers or [],
        schema_version=scene.schema_version,
        render_key=scene.render_key,
        created_at=scene.created_at,
        updated_at=scene.updated_at
    )


@router.delete("/slides/{slide_id}/scene/layers/{layer_id}", response_model=SlideSceneRead)
async def delete_layer(
    slide_id: uuid.UUID,
    layer_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete a layer from the scene."""
    result = await db.execute(
        select(SlideScene).where(SlideScene.slide_id == slide_id)
    )
    scene = result.scalar_one_or_none()
    
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    
    layers = [l for l in (scene.layers or []) if l.get("id") != layer_id]
    
    if len(layers) == len(scene.layers or []):
        raise HTTPException(status_code=404, detail="Layer not found")
    
    scene.layers = layers
    scene.render_key = compute_render_key(layers, {"width": scene.canvas_width, "height": scene.canvas_height})
    scene.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(scene)
    
    return SlideSceneRead(
        id=scene.id,
        slide_id=scene.slide_id,
        canvas={"width": scene.canvas_width, "height": scene.canvas_height},
        layers=scene.layers or [],
        schema_version=scene.schema_version,
        render_key=scene.render_key,
        created_at=scene.created_at,
        updated_at=scene.updated_at
    )


# === MARKERS ENDPOINTS ===

@router.get("/slides/{slide_id}/markers/{lang}", response_model=SlideMarkersRead)
async def get_slide_markers(
    slide_id: uuid.UUID,
    lang: str,
    db: AsyncSession = Depends(get_db)
):
    """Get markers for a slide in a specific language."""
    result = await db.execute(
        select(SlideMarkers)
        .where(SlideMarkers.slide_id == slide_id)
        .where(SlideMarkers.lang == lang)
    )
    markers = result.scalar_one_or_none()
    
    if not markers:
        # Return empty markers
        return SlideMarkersRead(
            id=uuid.uuid4(),
            slide_id=slide_id,
            lang=lang,
            markers=[],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
    
    return SlideMarkersRead(
        id=markers.id,
        slide_id=markers.slide_id,
        lang=markers.lang,
        markers=markers.markers or [],
        created_at=markers.created_at,
        updated_at=markers.updated_at
    )


@router.put("/slides/{slide_id}/markers/{lang}", response_model=SlideMarkersRead)
async def update_slide_markers(
    slide_id: uuid.UUID,
    lang: str,
    markers_data: SlideMarkersUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update markers for a slide in a specific language."""
    # Check slide exists
    slide = await db.get(Slide, slide_id)
    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found")
    
    result = await db.execute(
        select(SlideMarkers)
        .where(SlideMarkers.slide_id == slide_id)
        .where(SlideMarkers.lang == lang)
    )
    markers = result.scalar_one_or_none()
    
    if not markers:
        markers = SlideMarkers(
            id=uuid.uuid4(),
            slide_id=slide_id,
            lang=lang,
        )
        db.add(markers)
    
    markers.markers = [m.model_dump() for m in markers_data.markers]
    markers.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(markers)
    
    return SlideMarkersRead(
        id=markers.id,
        slide_id=markers.slide_id,
        lang=markers.lang,
        markers=markers.markers or [],
        created_at=markers.created_at,
        updated_at=markers.updated_at
    )


@router.post("/slides/{slide_id}/markers/propagate")
async def propagate_markers_to_language(
    slide_id: uuid.UUID,
    source_lang: str = Query(..., description="Source language (usually base language)"),
    target_lang: str = Query(..., description="Target language to propagate markers to"),
    db: AsyncSession = Depends(get_db)
):
    """
    Propagate markers from source language to target language.
    
    This is the key to marker-based word trigger resolution for non-base languages:
    - Markers created in base language are copied to target language
    - Marker IDs are preserved to maintain cross-language reference
    - charStart/charEnd are estimated based on word index proportion
    - timeSeconds will be updated when TTS is generated for target language
    
    Use this after translation to set up markers in the target language,
    then generate TTS to get accurate timeSeconds.
    """
    # Validate slide exists
    slide = await db.get(Slide, slide_id)
    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found")
    
    # Get source markers
    result = await db.execute(
        select(SlideMarkers)
        .where(SlideMarkers.slide_id == slide_id)
        .where(SlideMarkers.lang == source_lang)
    )
    source_markers_record = result.scalar_one_or_none()
    
    if not source_markers_record or not source_markers_record.markers:
        raise HTTPException(status_code=404, detail=f"No markers found for source language '{source_lang}'")
    
    source_markers = source_markers_record.markers
    
    # Get source and target scripts for position estimation
    from app.db.models import SlideScript
    from app.adapters.text_normalizer import tokenize_words, normalize_text
    
    result = await db.execute(
        select(SlideScript)
        .where(SlideScript.slide_id == slide_id)
        .where(SlideScript.lang == source_lang)
    )
    source_script = result.scalar_one_or_none()
    
    result = await db.execute(
        select(SlideScript)
        .where(SlideScript.slide_id == slide_id)
        .where(SlideScript.lang == target_lang)
    )
    target_script = result.scalar_one_or_none()
    
    if not target_script or not target_script.text:
        raise HTTPException(status_code=404, detail=f"No script found for target language '{target_lang}'")
    
    # Tokenize target script to estimate marker positions
    target_normalized = normalize_text(target_script.text)
    target_words = tokenize_words(target_normalized)
    
    # Calculate word indices for source markers
    source_normalized = normalize_text(source_script.text) if source_script and source_script.text else ""
    source_words = tokenize_words(source_normalized)
    
    # Build mapping from charStart to word index for source
    source_word_index_map = {}
    for idx, (char_start, char_end, word) in enumerate(source_words):
        source_word_index_map[char_start] = idx
    
    # Propagate markers
    propagated_markers = []
    for marker in source_markers:
        # Preserve marker ID for cross-language reference
        new_marker = {
            "id": marker.get("id"),
            "name": marker.get("name"),
            "timeSeconds": 0,  # Will be updated when TTS is generated
        }
        
        # Estimate position in target language
        source_char_start = marker.get("charStart")
        if source_char_start is not None and source_char_start in source_word_index_map:
            source_word_idx = source_word_index_map[source_char_start]
            
            # Map to target by word index ratio
            if source_words and target_words:
                ratio = source_word_idx / len(source_words)
                target_word_idx = min(int(ratio * len(target_words)), len(target_words) - 1)
                
                if target_word_idx < len(target_words):
                    target_char_start, target_char_end, target_word = target_words[target_word_idx]
                    new_marker["charStart"] = target_char_start
                    new_marker["charEnd"] = target_char_end
                    new_marker["wordText"] = target_word
        
        # Fallback: If we couldn't estimate position, just copy source info
        if "charStart" not in new_marker:
            new_marker["charStart"] = marker.get("charStart")
            new_marker["charEnd"] = marker.get("charEnd")
            new_marker["wordText"] = marker.get("wordText", "")
        
        propagated_markers.append(new_marker)
    
    # Upsert target markers
    result = await db.execute(
        select(SlideMarkers)
        .where(SlideMarkers.slide_id == slide_id)
        .where(SlideMarkers.lang == target_lang)
    )
    target_markers_record = result.scalar_one_or_none()
    
    if target_markers_record:
        target_markers_record.markers = propagated_markers
        target_markers_record.updated_at = datetime.utcnow()
    else:
        target_markers_record = SlideMarkers(
            slide_id=slide_id,
            lang=target_lang,
            markers=propagated_markers,
        )
        db.add(target_markers_record)
    
    await db.commit()
    
    return {
        "status": "success",
        "source_lang": source_lang,
        "target_lang": target_lang,
        "markers_propagated": len(propagated_markers),
    }


# === NORMALIZED SCRIPT ENDPOINTS ===

@router.get("/slides/{slide_id}/script/{lang}/normalized", response_model=NormalizedScriptRead)
async def get_normalized_script(
    slide_id: uuid.UUID,
    lang: str,
    db: AsyncSession = Depends(get_db)
):
    """Get normalized script with word timings for a slide."""
    result = await db.execute(
        select(NormalizedScript)
        .where(NormalizedScript.slide_id == slide_id)
        .where(NormalizedScript.lang == lang)
    )
    script = result.scalar_one_or_none()
    
    if not script:
        raise HTTPException(status_code=404, detail="Normalized script not found")
    
    return NormalizedScriptRead(
        id=script.id,
        slide_id=script.slide_id,
        lang=script.lang,
        raw_text=script.raw_text,
        normalized_text=script.normalized_text,
        tokenization_version=script.tokenization_version,
        word_timings=script.word_timings,
        created_at=script.created_at,
        updated_at=script.updated_at
    )


# === ASSETS ENDPOINTS ===

@router.get("/projects/{project_id}/assets", response_model=AssetListResponse)
async def list_assets(
    project_id: uuid.UUID,
    type: Optional[str] = Query(None, description="Filter by asset type"),
    db: AsyncSession = Depends(get_db)
):
    """List all assets for a project."""
    query = select(Asset).where(Asset.project_id == project_id)
    if type:
        query = query.where(Asset.type == type)
    query = query.order_by(Asset.created_at.desc())
    
    result = await db.execute(query)
    assets = result.scalars().all()
    
    # Build URLs
    asset_reads = []
    for asset in assets:
        asset_url = f"/static/assets/{project_id}/{asset.filename}"
        thumbnail_url = f"/static/assets/{project_id}/thumbs/{asset.filename}" if asset.thumbnail_path else None
        
        asset_reads.append(AssetRead(
            id=asset.id,
            project_id=asset.project_id,
            type=asset.type,
            filename=asset.filename,
            file_path=asset.file_path,
            thumbnail_path=asset.thumbnail_path,
            width=asset.width,
            height=asset.height,
            file_size=asset.file_size,
            url=asset_url,
            thumbnail_url=thumbnail_url,
            created_at=asset.created_at
        ))
    
    return AssetListResponse(assets=asset_reads, total=len(asset_reads))


# Asset upload limits
MAX_ASSET_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB
MAX_IMAGE_PIXELS = 100_000_000  # 100 megapixels (anti-decompression bomb)


@router.post("/projects/{project_id}/assets", response_model=AssetRead)
async def upload_asset(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    type: str = Query("image", description="Asset type: image, background, icon"),
    db: AsyncSession = Depends(get_db)
):
    """Upload a new asset (image, background, icon)."""
    # Validate project exists
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Validate file type
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_IMAGE_TYPES)}"
        )
    
    # Validate asset type
    if type not in ["image", "background", "icon"]:
        raise HTTPException(status_code=400, detail="Invalid asset type")
    
    # Read file with size limit to prevent OOM/DoS
    chunks = []
    total_size = 0
    chunk_size = 64 * 1024  # 64KB chunks
    
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > MAX_ASSET_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size is {MAX_ASSET_SIZE_BYTES // (1024 * 1024)} MB"
            )
        chunks.append(chunk)
    
    content = b"".join(chunks)
    file_size = total_size
    
    # Get image dimensions with decompression bomb protection
    from io import BytesIO
    try:
        # PIL has built-in decompression bomb protection via MAX_IMAGE_PIXELS
        # but we set an explicit limit as well
        Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
        with Image.open(BytesIO(content)) as img:
            # Verify the image can be loaded (triggers decompression)
            img.verify()
        # Re-open after verify (verify() can leave file in bad state)
        with Image.open(BytesIO(content)) as img:
            width, height = img.size
            # Double-check pixel count
            if width * height > MAX_IMAGE_PIXELS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Image dimensions too large. Maximum is {MAX_IMAGE_PIXELS:,} pixels"
                )
    except HTTPException:
        raise
    except Image.DecompressionBombError:
        raise HTTPException(
            status_code=400,
            detail=f"Image dimensions too large (decompression bomb protection)"
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid image file")
    
    # Generate unique filename
    ext = Path(file.filename).suffix.lower() or ".png"
    asset_id = uuid.uuid4()
    filename = f"{asset_id}{ext}"
    
    # Create directories
    assets_dir = settings.DATA_DIR / str(project_id) / "assets"
    thumbs_dir = assets_dir / "thumbs"
    assets_dir.mkdir(parents=True, exist_ok=True)
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    
    # Save file
    file_path = assets_dir / filename
    file_path.write_bytes(content)
    
    # Create thumbnail
    thumb_path = thumbs_dir / filename
    try:
        with Image.open(BytesIO(content)) as img:
            img.thumbnail((200, 200))
            img.save(thumb_path)
    except Exception:
        thumb_path = None
    
    # Create database record
    asset = Asset(
        id=asset_id,
        project_id=project_id,
        type=type,
        filename=filename,
        file_path=to_relative_path(file_path),
        thumbnail_path=to_relative_path(thumb_path) if thumb_path else None,
        width=width,
        height=height,
        file_size=file_size
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    
    asset_url = f"/static/assets/{project_id}/{filename}"
    thumbnail_url = f"/static/assets/{project_id}/thumbs/{filename}" if thumb_path else None
    
    return AssetRead(
        id=asset.id,
        project_id=asset.project_id,
        type=asset.type,
        filename=asset.filename,
        file_path=asset.file_path,
        thumbnail_path=asset.thumbnail_path,
        width=asset.width,
        height=asset.height,
        file_size=asset.file_size,
        url=asset_url,
        thumbnail_url=thumbnail_url,
        created_at=asset.created_at
    )


@router.delete("/assets/{asset_id}", status_code=204)
async def delete_asset(
    asset_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete an asset."""
    asset = await db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # Delete physical files
    if asset.file_path:
        file_path = to_absolute_path(asset.file_path)
        if file_path.exists():
            file_path.unlink()
    
    if asset.thumbnail_path:
        thumb_path = to_absolute_path(asset.thumbnail_path)
        if thumb_path.exists():
            thumb_path.unlink()
    
    await db.delete(asset)
    await db.commit()
    
    return None


# === TRANSLATION ENDPOINTS ===

class TranslateSceneRequest(BaseModel):
    target_lang: str


class TranslateSceneResponse(BaseModel):
    translated_count: int
    target_lang: str
    layers_updated: list[str]  # IDs of translated layers


@router.post("/slides/{slide_id}/scene/translate", response_model=TranslateSceneResponse)
async def translate_scene_text_layers(
    slide_id: uuid.UUID,
    request: TranslateSceneRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Translate all translatable text layers in a scene to target language.
    Uses project's translation rules (glossary, style).
    """
    from app.adapters.translate import TranslateAdapter
    from app.db.models import ProjectTranslationRules
    
    target_lang = request.target_lang.lower().strip()
    
    # Get scene
    result = await db.execute(
        select(SlideScene).where(SlideScene.slide_id == slide_id)
    )
    scene = result.scalar_one_or_none()
    
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    
    # Get slide to find project
    slide = await db.get(Slide, slide_id)
    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found")
    
    # Get project for base language
    project = await db.get(Project, slide.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    base_lang = project.base_language
    
    if target_lang == base_lang:
        return TranslateSceneResponse(
            translated_count=0,
            target_lang=target_lang,
            layers_updated=[]
        )
    
    # Get translation rules
    result = await db.execute(
        select(ProjectTranslationRules).where(ProjectTranslationRules.project_id == project.id)
    )
    rules = result.scalar_one_or_none()
    
    do_not_translate = rules.do_not_translate if rules else []
    preferred_translations = rules.preferred_translations if rules else []
    style = rules.style if rules else "formal"
    extra_rules = rules.extra_rules if rules else None
    
    # Collect translatable text layers
    layers = scene.layers or []
    texts_to_translate = []
    layer_indices = []
    
    for i, layer in enumerate(layers):
        if layer.get("type") == "text":
            text_content = layer.get("text", {})
            if text_content.get("isTranslatable", True):
                base_text = text_content.get("baseContent", "")
                if base_text.strip():
                    # Check if translation already exists
                    translations = text_content.get("translations", {})
                    if target_lang not in translations:
                        texts_to_translate.append(base_text)
                        layer_indices.append(i)
    
    if not texts_to_translate:
        return TranslateSceneResponse(
            translated_count=0,
            target_lang=target_lang,
            layers_updated=[]
        )
    
    # Translate using adapter
    translator = TranslateAdapter()
    results = await translator.translate_batch(
        texts=texts_to_translate,
        source_lang=base_lang,
        target_lang=target_lang,
        do_not_translate=do_not_translate,
        preferred_translations=preferred_translations,
        style=style,
        extra_rules=extra_rules
    )
    # translate_batch historically returned either:
    # - (List[str], meta_dict)  (older mocks/tests)
    # - List[Tuple[str, Dict]]  (current adapter)
    # Be defensive and accept both shapes.
    translated_texts: list[str] = []
    if isinstance(results, tuple) and len(results) == 2 and isinstance(results[0], list):
        translated_texts = results[0]
    elif isinstance(results, list):
        if results and isinstance(results[0], (tuple, list)):
            translated_texts = [r[0] for r in results if r]
        else:
            translated_texts = results
    
    # Update layers with translations
    updated_layer_ids = []
    for idx, translated_text in zip(layer_indices, translated_texts):
        layer = layers[idx]
        text_content = layer.get("text", {})
        translations = text_content.get("translations", {})
        translations[target_lang] = translated_text
        text_content["translations"] = translations
        layer["text"] = text_content
        updated_layer_ids.append(layer.get("id", ""))
    
    # Save scene
    scene.layers = layers
    scene.render_key = compute_render_key(layers, {"width": scene.canvas_width, "height": scene.canvas_height})
    scene.updated_at = datetime.utcnow()
    
    await db.commit()
    
    return TranslateSceneResponse(
        translated_count=len(translated_texts),
        target_lang=target_lang,
        layers_updated=updated_layer_ids
    )


class ResolvedSceneResponse(BaseModel):
    """Scene with word triggers resolved to time-based triggers"""
    id: UUID
    slide_id: UUID
    canvas: dict
    layers: list
    lang: str
    triggers_resolved: int
    schema_version: int
    render_key: Optional[str]
    voice_offset_applied: float = 0.0  # Shows what offset was applied (for debugging)


@router.get("/slides/{slide_id}/scene/resolved", response_model=ResolvedSceneResponse)
async def get_resolved_scene(
    slide_id: uuid.UUID,
    lang: str = Query(..., description="Target language for trigger resolution"),
    voice_offset_sec: float = Query(0.0, description="Voice offset in seconds (pre-padding before audio begins). "
                                    "Apply this to match final render timing. Default 0 for preview."),
    db: AsyncSession = Depends(get_db)
):
    """
    Get scene with triggers resolved to time-based triggers (EPIC A compliant).
    
    EPIC A IMPLEMENTATION:
    This endpoint now uses the GlobalMarker system for deterministic trigger resolution:
    
    1. For 'marker' triggers: Look up GlobalMarker → MarkerPosition for target language
    2. For 'word' triggers: Check if markerId is present (preferred), otherwise fallback
    3. No heuristics like "charStart from base language" - everything goes through markers
    
    The algorithm:
    - marker triggers → GlobalMarker.positions[lang].time_seconds
    - word triggers with markerId → same as marker triggers
    - word triggers without markerId → fallback to word_timings charStart match
    
    Heuristics (character proportion estimation) are REMOVED as per EPIC A requirement.
    """
    from sqlalchemy.orm import selectinload
    
    # Get scene
    result = await db.execute(
        select(SlideScene).where(SlideScene.slide_id == slide_id)
    )
    scene = result.scalar_one_or_none()
    
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    
    # Get slide to find project
    slide = await db.get(Slide, slide_id)
    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found")
    
    # Get project for base language
    project = await db.get(Project, slide.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    target_lang = lang.lower().strip()
    
    layers = list(scene.layers or [])
    triggers_resolved = 0
    
    # Get word timings for the target language
    result = await db.execute(
        select(NormalizedScript)
        .where(NormalizedScript.slide_id == slide_id)
        .where(NormalizedScript.lang == target_lang)
    )
    normalized_script = result.scalar_one_or_none()
    word_timings = normalized_script.word_timings if normalized_script else None
    
    # === EPIC A: Load GlobalMarkers with positions for this language ===
    result = await db.execute(
        select(GlobalMarker)
        .where(GlobalMarker.slide_id == slide_id)
        .options(selectinload(GlobalMarker.positions))
    )
    global_markers = result.scalars().all()
    
    # Build lookup: marker_id -> time_seconds for target language
    marker_times: dict[str, float] = {}
    for marker in global_markers:
        for pos in marker.positions:
            if pos.lang == target_lang and pos.time_seconds is not None:
                marker_times[str(marker.id).lower()] = pos.time_seconds
                break
    
    # Also load legacy SlideMarkers for backward compatibility
    result = await db.execute(
        select(SlideMarkers)
        .where(SlideMarkers.slide_id == slide_id)
        .where(SlideMarkers.lang == target_lang)
    )
    markers_record = result.scalar_one_or_none()
    legacy_markers = markers_record.markers if markers_record else []
    
    # Build legacy marker lookup
    for m in legacy_markers:
        m_id = (m.get("id") or "").lower()
        if m_id and m_id not in marker_times and m.get("timeSeconds") is not None:
            marker_times[m_id] = m.get("timeSeconds")
    
    # Process each layer
    for layer in layers:
        animation = layer.get("animation")
        if not animation:
            continue
        
        for anim_key in ["entrance", "exit"]:
            anim_config = animation.get(anim_key)
            if not anim_config:
                continue
            
            trigger = anim_config.get("trigger", {})
            trigger_type = trigger.get("type")
            resolved_time = None
            resolution_method = None
            
            if trigger_type == "marker":
                # === EPIC A: Direct marker resolution via GlobalMarker ===
                marker_id = (trigger.get("markerId") or "").strip().lower()
                if marker_id and marker_id in marker_times:
                    resolved_time = marker_times[marker_id]
                    resolution_method = "global_marker"
            
            elif trigger_type == "word":
                # === EPIC A: Word triggers should have markerId if properly migrated ===
                marker_id = (trigger.get("markerId") or "").strip().lower()
                
                if marker_id and marker_id in marker_times:
                    # Preferred: use marker-based resolution
                    resolved_time = marker_times[marker_id]
                    resolution_method = "word_via_marker"
                
                elif word_timings:
                    # Fallback: try exact charStart match in word_timings
                    # This works for base language or if positions are correct
                    char_start = trigger.get("charStart")
                    if char_start is not None:
                        for wt in word_timings:
                            if wt.get("charStart") == char_start:
                                resolved_time = wt.get("startTime")
                                resolution_method = "word_timing_exact"
                                break
                
                # NOTE: Character proportion estimation is REMOVED per EPIC A
                # If we can't resolve, the trigger remains unresolved
            
            # Apply resolved time
            if resolved_time is not None:
                trigger["type"] = "time"
                trigger["seconds"] = resolved_time + voice_offset_sec
                trigger["_original_type"] = trigger_type
                trigger["_resolution_method"] = resolution_method
                if trigger_type == "marker":
                    trigger["_original_markerId"] = trigger.get("markerId")
                elif trigger_type == "word":
                    trigger["_original_wordText"] = trigger.get("wordText", "")
                    trigger["_original_markerId"] = trigger.get("markerId")
                anim_config["trigger"] = trigger
                triggers_resolved += 1
    
    return ResolvedSceneResponse(
        id=scene.id,
        slide_id=scene.slide_id,
        canvas={"width": scene.canvas_width, "height": scene.canvas_height},
        layers=layers,
        lang=target_lang,
        triggers_resolved=triggers_resolved,
        schema_version=scene.schema_version,
        render_key=scene.render_key,
        voice_offset_applied=voice_offset_sec
    )


# === GLOBAL MARKERS API (EPIC A) ===

class CreateMarkerFromWordRequest(BaseModel):
    """Request to create a marker from a word selection"""
    char_start: int
    char_end: int
    word_text: Optional[str] = None
    name: Optional[str] = None


class CreateMarkerFromWordResponse(BaseModel):
    """Response after creating a marker"""
    marker_id: str
    name: Optional[str]
    char_start: int
    char_end: int
    time_seconds: Optional[float]
    token: str  # The marker token to insert in text


class GlobalMarkerResponse(BaseModel):
    """Single global marker with positions"""
    marker_id: str
    slide_id: str
    name: Optional[str]
    created_at: datetime
    positions: dict  # {lang: {char_start, char_end, time_seconds}}


class GlobalMarkersListResponse(BaseModel):
    """List of global markers for a slide"""
    markers: list[GlobalMarkerResponse]
    total: int


class ComputeMarkerTimesResponse(BaseModel):
    """Response from computing marker times"""
    markers_updated: int
    lang: str


@router.post("/slides/{slide_id}/markers/{lang}/create-from-word", response_model=CreateMarkerFromWordResponse)
async def create_marker_from_word(
    slide_id: uuid.UUID,
    lang: str,
    request: CreateMarkerFromWordRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a GlobalMarker from a word selection (EPIC A: A5.1).
    
    This is the primary way to create markers:
    1. User selects a word in the Script Editor
    2. Frontend sends char_start/char_end from normalized text
    3. Backend creates GlobalMarker + MarkerPosition for this language
    4. Returns marker_id and token to insert in script
    
    The token (⟦M:uuid⟧) should be inserted into the script text
    so it can be preserved during translation.
    """
    from app.db.models import GlobalMarker, MarkerPosition, MarkerSource, SlideScript
    from app.adapters.marker_tokens import format_marker_token
    from app.adapters.text_normalizer import normalize_text
    
    # Validate slide exists
    slide = await db.get(Slide, slide_id)
    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found")
    
    # Get the script to validate position
    result = await db.execute(
        select(SlideScript)
        .where(SlideScript.slide_id == slide_id)
        .where(SlideScript.lang == lang)
    )
    script = result.scalar_one_or_none()
    
    if not script:
        raise HTTPException(status_code=404, detail=f"Script not found for language '{lang}'")
    
    # Normalize the script text to validate positions
    normalized_text = normalize_text(script.text)
    
    # Validate char positions
    if request.char_start < 0 or request.char_end > len(normalized_text):
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid char positions: {request.char_start}-{request.char_end} "
                   f"for text of length {len(normalized_text)}"
        )
    
    # Extract word text if not provided
    word_text = request.word_text
    if not word_text:
        word_text = normalized_text[request.char_start:request.char_end]
    
    # Create GlobalMarker
    marker_id = uuid.uuid4()
    marker_name = request.name or f"Marker at '{word_text[:20]}'"
    
    global_marker = GlobalMarker(
        id=marker_id,
        slide_id=slide_id,
        name=marker_name,
    )
    db.add(global_marker)
    
    # Create MarkerPosition for this language
    # Try to compute time_seconds from existing word timings
    time_seconds = None
    result = await db.execute(
        select(NormalizedScript)
        .where(NormalizedScript.slide_id == slide_id)
        .where(NormalizedScript.lang == lang)
    )
    normalized_script = result.scalar_one_or_none()
    
    if normalized_script and normalized_script.word_timings:
        # Find matching word timing
        for wt in normalized_script.word_timings:
            if wt.get("charStart") == request.char_start:
                time_seconds = wt.get("startTime")
                break
    
    marker_position = MarkerPosition(
        id=uuid.uuid4(),
        marker_id=marker_id,
        lang=lang,
        char_start=request.char_start,
        char_end=request.char_end,
        time_seconds=time_seconds,
        source=MarkerSource.WORDCLICK,
    )
    db.add(marker_position)
    
    await db.commit()
    
    return CreateMarkerFromWordResponse(
        marker_id=str(marker_id),
        name=marker_name,
        char_start=request.char_start,
        char_end=request.char_end,
        time_seconds=time_seconds,
        token=format_marker_token(str(marker_id)),
    )


@router.get("/slides/{slide_id}/global-markers", response_model=GlobalMarkersListResponse)
async def list_global_markers(
    slide_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    List all global markers for a slide with their positions across languages.
    
    This is useful for:
    - Displaying markers in the UI
    - Debugging marker positions
    - Checking if markers need time recalculation
    """
    from app.db.models import GlobalMarker, MarkerPosition
    from sqlalchemy.orm import selectinload
    
    # Get all markers for this slide with their positions
    result = await db.execute(
        select(GlobalMarker)
        .where(GlobalMarker.slide_id == slide_id)
        .options(selectinload(GlobalMarker.positions))
        .order_by(GlobalMarker.created_at)
    )
    markers = result.scalars().all()
    
    response_markers = []
    for marker in markers:
        positions = {}
        for pos in marker.positions:
            positions[pos.lang] = {
                "char_start": pos.char_start,
                "char_end": pos.char_end,
                "time_seconds": pos.time_seconds,
                "source": pos.source.value,
            }
        
        response_markers.append(GlobalMarkerResponse(
            marker_id=str(marker.id),
            slide_id=str(marker.slide_id),
            name=marker.name,
            created_at=marker.created_at,
            positions=positions,
        ))
    
    return GlobalMarkersListResponse(
        markers=response_markers,
        total=len(response_markers),
    )


@router.post("/slides/{slide_id}/markers/{lang}/compute-times", response_model=ComputeMarkerTimesResponse)
async def compute_marker_times(
    slide_id: uuid.UUID,
    lang: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Compute time_seconds for all markers in a language (EPIC A: A5.3).
    
    This should be called after TTS generation to update marker timings.
    It uses the word_timings from NormalizedScript to find accurate times.
    
    Algorithm for each marker:
    1. Find marker token position in normalized text
    2. Find anchor word (first word to the right, or last word before)
    3. Set time_seconds = anchor word startTime
    """
    from app.db.models import GlobalMarker, MarkerPosition
    from app.adapters.marker_tokens import compute_marker_time_from_word_timings
    from sqlalchemy.orm import selectinload
    
    # Get normalized script with word timings
    result = await db.execute(
        select(NormalizedScript)
        .where(NormalizedScript.slide_id == slide_id)
        .where(NormalizedScript.lang == lang)
    )
    normalized_script = result.scalar_one_or_none()
    
    if not normalized_script or not normalized_script.word_timings:
        raise HTTPException(
            status_code=404, 
            detail=f"No word timings found for language '{lang}'. Generate TTS first."
        )
    
    # Get all global markers for this slide
    result = await db.execute(
        select(GlobalMarker)
        .where(GlobalMarker.slide_id == slide_id)
        .options(selectinload(GlobalMarker.positions))
    )
    markers = result.scalars().all()
    
    updated_count = 0
    
    for marker in markers:
        # Find position for this language
        position = next((p for p in marker.positions if p.lang == lang), None)
        
        if not position:
            # No position for this language - try to create one from normalized text
            # by looking for the marker token
            time_seconds = compute_marker_time_from_word_timings(
                normalized_script.normalized_text,
                str(marker.id),
                normalized_script.word_timings
            )
            
            if time_seconds is not None:
                # Create new position
                from app.db.models import MarkerSource
                new_position = MarkerPosition(
                    id=uuid.uuid4(),
                    marker_id=marker.id,
                    lang=lang,
                    char_start=None,  # Unknown from token
                    char_end=None,
                    time_seconds=time_seconds,
                    source=MarkerSource.AUTO,
                )
                db.add(new_position)
                updated_count += 1
        else:
            # Update existing position
            # First try token-based lookup
            time_seconds = compute_marker_time_from_word_timings(
                normalized_script.normalized_text,
                str(marker.id),
                normalized_script.word_timings
            )
            
            # If no token found, try char_start matching
            if time_seconds is None and position.char_start is not None:
                for wt in normalized_script.word_timings:
                    if wt.get("charStart") == position.char_start:
                        time_seconds = wt.get("startTime")
                        break
            
            if time_seconds is not None:
                position.time_seconds = time_seconds
                position.updated_at = datetime.utcnow()
                updated_count += 1
    
    await db.commit()
    
    return ComputeMarkerTimesResponse(
        markers_updated=updated_count,
        lang=lang,
    )


class InsertMarkerTokensResponse(BaseModel):
    """Response from inserting marker tokens"""
    tokens_inserted: int
    updated_text: str


@router.post("/slides/{slide_id}/script/{lang}/insert-marker-tokens", response_model=InsertMarkerTokensResponse)
async def insert_marker_tokens(
    slide_id: uuid.UUID,
    lang: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Insert marker tokens into script text for all GlobalMarkers (EPIC A: A6.2).
    
    This endpoint:
    1. Gets all GlobalMarkers for this slide with positions in this language
    2. Inserts ⟦M:uuid⟧ tokens at the marker positions
    3. Updates the SlideScript with the new text
    4. Updates NormalizedScript.contains_marker_tokens flag
    
    Use this to prepare a base language script before translation,
    or to update a translated script with missing tokens.
    """
    from app.db.models import GlobalMarker, MarkerPosition, SlideScript
    from app.adapters.marker_tokens import format_marker_token, contains_marker_tokens
    from app.adapters.text_normalizer import normalize_text
    from sqlalchemy.orm import selectinload
    
    # Get script
    result = await db.execute(
        select(SlideScript)
        .where(SlideScript.slide_id == slide_id)
        .where(SlideScript.lang == lang)
    )
    script = result.scalar_one_or_none()
    
    if not script:
        raise HTTPException(status_code=404, detail=f"Script not found for language '{lang}'")
    
    # Get all markers with positions for this language
    result = await db.execute(
        select(GlobalMarker)
        .where(GlobalMarker.slide_id == slide_id)
        .options(selectinload(GlobalMarker.positions))
    )
    markers = result.scalars().all()
    
    # Collect positions to insert (marker_id, position)
    insertions = []
    for marker in markers:
        position = next((p for p in marker.positions if p.lang == lang), None)
        if position and position.char_start is not None:
            # Check if token already exists in text
            token = format_marker_token(str(marker.id))
            if token not in script.text:
                insertions.append((str(marker.id), position.char_start))
    
    if not insertions:
        return InsertMarkerTokensResponse(
            tokens_inserted=0,
            updated_text=script.text,
        )
    
    # Sort by position descending to insert without shifting issues
    insertions.sort(key=lambda x: x[1], reverse=True)
    
    updated_text = script.text
    for marker_id, pos in insertions:
        token = format_marker_token(marker_id)
        updated_text = updated_text[:pos] + token + updated_text[pos:]
    
    # Update script
    script.text = updated_text
    
    # Update normalized script if exists
    result = await db.execute(
        select(NormalizedScript)
        .where(NormalizedScript.slide_id == slide_id)
        .where(NormalizedScript.lang == lang)
    )
    normalized_script = result.scalar_one_or_none()
    
    if normalized_script:
        normalized_script.raw_text = updated_text
        normalized_script.normalized_text = normalize_text(updated_text)
        normalized_script.contains_marker_tokens = contains_marker_tokens(updated_text)
        normalized_script.updated_at = datetime.utcnow()
    
    await db.commit()
    
    return InsertMarkerTokensResponse(
        tokens_inserted=len(insertions),
        updated_text=updated_text,
    )


class MigrateTriggersResponse(BaseModel):
    """Response from migrating word triggers to markers"""
    markers_created: int
    triggers_migrated: int
    tokens_inserted: int
    needs_retranslate: List[str]


@router.post("/slides/{slide_id}/scene/migrate-triggers", response_model=MigrateTriggersResponse)
async def migrate_word_triggers_to_markers(
    slide_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Migrate existing word triggers to GlobalMarkers (EPIC A: A7).
    
    This endpoint upgrades a scene to use the EPIC A marker system:
    1. Scans the scene for layers with word-type triggers
    2. Creates a GlobalMarker for each unique word trigger
    3. Creates MarkerPosition for the base language
    4. Updates the trigger to use markerId
    5. Inserts marker tokens into the base language script
    6. Flags translated scripts that need re-translation
    
    Call this once per slide to upgrade existing projects.
    After migration, translated scripts should be re-translated to preserve marker tokens.
    """
    from app.workers.tasks import migrate_word_triggers_to_markers as migrate_func
    
    # Get slide to find project and base language
    slide = await db.get(Slide, slide_id)
    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found")
    
    project = await db.get(Project, slide.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Run migration
    result = await migrate_func(
        db=db,
        slide_id=slide_id,
        base_lang=project.base_language,
    )
    
    await db.commit()
    
    return MigrateTriggersResponse(
        markers_created=result["markers_created"],
        triggers_migrated=result["triggers_migrated"],
        tokens_inserted=result["tokens_inserted"],
        needs_retranslate=result["needs_retranslate"],
    )

