"""
Render Service Client - calls the Node.js Puppeteer-based renderer

EPIC B Enhancement:
- Added segment caching support
- Cache lookup before rendering
- Cache storage after successful render
"""
import httpx
from pathlib import Path
from typing import List, Optional, Any
import logging
import uuid
from datetime import datetime

from app.core.config import settings

logger = logging.getLogger(__name__)

# Renderer version for cache invalidation
RENDERER_VERSION = "2.0"  # Bumped for EPIC B stream capture


class RenderServiceClient:
    """HTTP client for the browser-based render service."""
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        self.base_url = base_url or settings.RENDER_SERVICE_URL
        self.timeout = timeout or settings.RENDER_SERVICE_TIMEOUT_SEC
    
    async def health_check(self) -> bool:
        """Check if render service is healthy."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code == 200
        except Exception as e:
            logger.warning(f"Render service health check failed: {e}")
            return False
    
    async def render_slide(
        self,
        slide_id: str,
        slide_image_url: str,
        layers: List[dict],
        duration: float,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        output_format: str = "webm",
        render_key: Optional[str] = None,
        lang: str = "en",
    ) -> dict:
        """
        Render a single slide with animated layers.
        
        Args:
            slide_id: UUID of the slide
            slide_image_url: Full URL to slide background image
            layers: List of SlideLayer dicts (already resolved to time-based triggers)
            duration: Total slide duration in seconds
            width: Output video width
            height: Output video height
            fps: Frames per second
            output_format: "webm" or "mp4"
            render_key: Hash for caching
            lang: Language for text content
        
        Returns:
            dict with outputPath, duration, frames
        """
        payload = {
            "slideId": slide_id,
            "slideImageUrl": slide_image_url,
            "layers": layers,
            "duration": duration,
            "width": width,
            "height": height,
            "fps": fps,
            "format": output_format,
            "renderKey": render_key,
            "lang": lang,
        }
        
        logger.info(f"Requesting slide render: {slide_id}, duration={duration}s, layers={len(layers)}")
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/render",
                json=payload,
            )
            response.raise_for_status()
            return response.json()
    
    async def render_batch(
        self,
        slides: List[dict],
        concurrency: Optional[int] = None,
    ) -> dict:
        """
        Render multiple slides (parallelized inside render-service).
        
        Args:
            slides: List of slide render requests
            concurrency: Optional concurrency hint for render-service
        
        Returns:
            dict with results array
        """
        logger.info(f"Requesting batch render: {len(slides)} slides")
        
        # Increase timeout for batch
        # NOTE: render-service can parallelize, but we keep a generous timeout to avoid
        # spurious failures on slower machines.
        batch_timeout = self.timeout * max(1, len(slides))
        
        async with httpx.AsyncClient(timeout=batch_timeout) as client:
            response = await client.post(
                f"{self.base_url}/render-batch",
                json={"slides": slides, "concurrency": concurrency},
            )
            response.raise_for_status()
            return response.json()
    
    def get_output_path(self, filename: str) -> Path:
        """Get full path to rendered output file."""
        return settings.RENDER_OUTPUT_DIR / filename
    
    async def render_preview(
        self,
        slide_id: str,
        slide_image_url: str,
        layers: List[dict],
        width: int = 1920,
        height: int = 1080,
        lang: str = "en",
    ) -> dict:
        """
        Render a single PNG preview with all layers applied.
        
        Args:
            slide_id: UUID of the slide
            slide_image_url: Filesystem path to slide background image
            layers: List of SlideLayer dicts
            width: Output image width
            height: Output image height
            lang: Language for text content
        
        Returns:
            dict with outputPath
        """
        payload = {
            "slideId": slide_id,
            "slideImageUrl": slide_image_url,
            "layers": layers,
            "width": width,
            "height": height,
            "lang": lang,
        }
        
        logger.info(f"Requesting slide preview: {slide_id}, layers={len(layers)}")
        
        async with httpx.AsyncClient(timeout=60) as client:  # 60 sec timeout for preview
            response = await client.post(
                f"{self.base_url}/render-preview",
                json=payload,
            )
            response.raise_for_status()
            return response.json()


# === EPIC B: Render Cache Functions ===

async def check_render_cache(
    db,
    slide_id: str,
    lang: str,
    render_key: str,
    fps: int = 30,
    width: int = 1920,
    height: int = 1080,
) -> Optional[dict]:
    """
    Check if a cached segment exists for the given parameters.
    
    Returns:
        Cache entry dict with segment_path if found, None otherwise
    """
    from sqlalchemy import select
    from app.db.models import RenderCache
    from app.core.paths import to_absolute_path, file_exists
    
    result = await db.execute(
        select(RenderCache)
        .where(RenderCache.slide_id == uuid.UUID(slide_id))
        .where(RenderCache.lang == lang)
        .where(RenderCache.render_key == render_key)
        .where(RenderCache.fps == fps)
        .where(RenderCache.width == width)
        .where(RenderCache.height == height)
        .where(RenderCache.renderer_version == RENDERER_VERSION)
    )
    cache_entry = result.scalar_one_or_none()
    
    if cache_entry:
        # Verify the cached file still exists
        segment_path = to_absolute_path(cache_entry.segment_path)
        if file_exists(segment_path):
            # Update last_accessed_at
            cache_entry.last_accessed_at = datetime.utcnow()
            await db.flush()
            
            logger.info(f"Render cache HIT for slide {slide_id}, lang {lang}")
            return {
                "segment_path": str(segment_path),
                "duration_sec": cache_entry.duration_sec,
                "frame_count": cache_entry.frame_count,
                "cached": True,
            }
        else:
            # Stale cache entry - delete it
            await db.delete(cache_entry)
            await db.flush()
            logger.info(f"Render cache STALE for slide {slide_id} - file missing")
    
    logger.info(f"Render cache MISS for slide {slide_id}, lang {lang}")
    return None


async def store_render_cache(
    db,
    slide_id: str,
    lang: str,
    render_key: str,
    segment_path: str,
    duration_sec: float,
    frame_count: int,
    fps: int = 30,
    width: int = 1920,
    height: int = 1080,
    render_time_ms: Optional[int] = None,
    file_size_bytes: Optional[int] = None,
) -> None:
    """
    Store a rendered segment in the cache.
    """
    from app.db.models import RenderCache
    from app.core.paths import to_relative_path
    
    # Use relative path for storage
    relative_path = to_relative_path(segment_path)
    
    cache_entry = RenderCache(
        id=uuid.uuid4(),
        slide_id=uuid.UUID(slide_id),
        lang=lang,
        render_key=render_key,
        fps=fps,
        width=width,
        height=height,
        renderer_version=RENDERER_VERSION,
        segment_path=relative_path,
        duration_sec=duration_sec,
        frame_count=frame_count,
        render_time_ms=render_time_ms,
        file_size_bytes=file_size_bytes,
    )
    db.add(cache_entry)
    await db.flush()
    
    logger.info(f"Render cache STORE for slide {slide_id}, lang {lang}")


async def cleanup_old_cache_entries(
    db,
    max_age_days: int = 30,
    max_entries: int = 1000,
) -> int:
    """
    Cleanup old cache entries to prevent unbounded growth.
    
    Removes entries that:
    - Haven't been accessed in max_age_days
    - Exceed max_entries (oldest first)
    
    Returns count of deleted entries.
    """
    from sqlalchemy import select, delete, func
    from app.db.models import RenderCache
    from app.core.paths import to_absolute_path
    from datetime import timedelta
    
    deleted_count = 0
    cutoff_date = datetime.utcnow() - timedelta(days=max_age_days)
    
    # Delete entries older than cutoff
    result = await db.execute(
        select(RenderCache)
        .where(RenderCache.last_accessed_at < cutoff_date)
    )
    old_entries = result.scalars().all()
    
    for entry in old_entries:
        # Try to delete the cached file
        try:
            segment_path = to_absolute_path(entry.segment_path)
            if segment_path.exists():
                segment_path.unlink()
        except Exception as e:
            logger.warning(f"Failed to delete cached segment: {e}")
        
        await db.delete(entry)
        deleted_count += 1
    
    # Check total count and delete oldest if over limit
    count_result = await db.execute(select(func.count(RenderCache.id)))
    total_count = count_result.scalar() or 0
    
    if total_count > max_entries:
        excess = total_count - max_entries
        result = await db.execute(
            select(RenderCache)
            .order_by(RenderCache.last_accessed_at.asc())
            .limit(excess)
        )
        excess_entries = result.scalars().all()
        
        for entry in excess_entries:
            try:
                segment_path = to_absolute_path(entry.segment_path)
                if segment_path.exists():
                    segment_path.unlink()
            except Exception:
                pass
            await db.delete(entry)
            deleted_count += 1
    
    if deleted_count > 0:
        await db.flush()
        logger.info(f"Cleaned up {deleted_count} render cache entries")
    
    return deleted_count


# Singleton instance
_client: Optional[RenderServiceClient] = None


def get_render_service_client() -> RenderServiceClient:
    """Get or create render service client singleton."""
    global _client
    if _client is None:
        _client = RenderServiceClient()
    return _client

