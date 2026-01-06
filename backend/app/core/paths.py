"""
Path utilities for converting between:
- Absolute filesystem paths
- Relative paths (stored in DB)
- URLs (returned by API)

All paths stored in DB should be relative to DATA_DIR.
Example: "{project_id}/versions/{version_id}/audio/{lang}/slide_{id}.wav"
"""
from pathlib import Path
from typing import Optional

from app.core.config import settings


def to_relative_path(absolute_path: Path | str) -> str:
    """
    Convert absolute filesystem path to relative path for DB storage.
    
    Args:
        absolute_path: Absolute path like /data/projects/{project}/versions/{version}/...
        
    Returns:
        Relative path like "{project}/versions/{version}/..."
    """
    path = Path(absolute_path)
    try:
        return str(path.relative_to(settings.DATA_DIR))
    except ValueError:
        # Already relative or different base - return as-is
        return str(path)


def to_absolute_path(relative_path: str) -> Path:
    """
    Convert relative DB path to absolute filesystem path.
    
    Args:
        relative_path: Path stored in DB, relative to DATA_DIR
        
    Returns:
        Absolute Path object
    """
    path = Path(relative_path)
    if path.is_absolute():
        return path
    return settings.DATA_DIR / path


def file_exists(relative_path: str) -> bool:
    """Check if file exists given a relative path from DB."""
    return to_absolute_path(relative_path).exists()


def slide_image_url(relative_path: str) -> str:
    """
    Convert slide image relative path to URL.
    
    Args:
        relative_path: e.g. "{project_id}/versions/{version_id}/slides/001.png"
        
    Returns:
        URL like "/static/slides/{project_id}/{version_id}/001.png"
    """
    parts = Path(relative_path).parts
    # Expected: (project_id, "versions", version_id, "slides", filename)
    if len(parts) >= 5 and parts[1] == "versions" and parts[3] == "slides":
        project_id = parts[0]
        version_id = parts[2]
        filename = parts[4]
        return f"/static/slides/{project_id}/{version_id}/{filename}"
    # Fallback - try to extract from path pattern
    return ""


def slide_audio_url(relative_path: str) -> str:
    """
    Convert slide audio relative path to URL.
    
    Args:
        relative_path: e.g. "{project_id}/versions/{version_id}/audio/{lang}/slide_001.wav"
        
    Returns:
        URL like "/static/audio/{project_id}/{version_id}/{lang}/slide_001.wav"
    """
    parts = Path(relative_path).parts
    # Expected: (project_id, "versions", version_id, "audio", lang, filename)
    if len(parts) >= 6 and parts[1] == "versions" and parts[3] == "audio":
        project_id = parts[0]
        version_id = parts[2]
        lang = parts[4]
        filename = parts[5]
        return f"/static/audio/{project_id}/{version_id}/{lang}/{filename}"
    # Fallback
    return ""


def migrate_absolute_to_relative(absolute_path: Optional[str]) -> Optional[str]:
    """
    Helper for migrating existing absolute paths to relative.
    Returns None if input is None.
    """
    if not absolute_path:
        return None
    return to_relative_path(absolute_path)

