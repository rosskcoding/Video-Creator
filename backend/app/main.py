"""
FastAPI Application Entry Point
"""
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.core.config import settings
from app.api import router as api_router
from app.api.routes.auth import verify_session


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    # Startup
    print(f"🚀 Starting {settings.APP_NAME}")
    print(f"📁 Data directory: {settings.DATA_DIR}")
    
    # Ensure data directory exists
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)

    # NOTE: Database schema is managed by Alembic migrations.
    # Run `alembic upgrade head` before starting the app.
    # Do NOT use create_all here as it can cause schema drift.
    
    yield
    
    # Shutdown
    print("👋 Shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    description="Multilingual Voiceover Video Platform",
    version="1.1.0",
    lifespan=lifespan,
)

# CORS middleware - origins from env variable (comma-separated)
cors_origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(api_router, prefix="/api")


# === Restricted Static File Serving ===
# Instead of exposing entire DATA_DIR, we serve only slides via explicit routes
# with path traversal protection

# Pattern to validate UUID
UUID_PATTERN = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE
)

# Patterns for static asset filenames.
#
# - Slides: legacy PPTX slides are 001.png, 002.png, ... (numeric)
#          user-added slides use slide_<uuid>.png to avoid collisions on reorder/delete.
# - Audio:  legacy is slide_001.wav, slide_002.wav, ...
#          new TTS uses slide_<uuid>.wav for the same reason.
UUID_FILENAME_PART = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
SLIDE_FILENAME_PATTERN = re.compile(
    rf"^(?:\d{{3}}|slide_{UUID_FILENAME_PART})\.png$",
    re.IGNORECASE,
)
AUDIO_FILENAME_PATTERN = re.compile(
    rf"^slide_(?:\d{{3}}|{UUID_FILENAME_PART})\.wav$",
    re.IGNORECASE,
)

# Allowed language codes for audio paths (prevent path traversal)
LANG_CODE_PATTERN = re.compile(r'^[a-z]{2}(-[A-Z]{2})?$')


def validate_uuid(value: str) -> str:
    """Validate string is a valid UUID format"""
    if not UUID_PATTERN.match(value):
        raise HTTPException(status_code=400, detail="Invalid ID format")
    return value


@app.get("/static/slides/{project_id}/{version_id}/{filename}")
async def serve_slide_image(
    project_id: str,
    version_id: str,
    filename: str,
    _: str = Depends(verify_session),
):
    """
    Serve slide images with path traversal protection.
    Only serves PNG files from the slides directory.
    Requires authentication.
    """
    # Validate UUIDs
    safe_project_id = validate_uuid(project_id)
    safe_version_id = validate_uuid(version_id)
    
    # Validate filename format (only allow 001.png, 002.png, etc.)
    if not SLIDE_FILENAME_PATTERN.match(filename):
        raise HTTPException(status_code=400, detail="Invalid filename format")
    
    # Build path
    slides_dir = (
        settings.DATA_DIR / safe_project_id / "versions" / safe_version_id / "slides"
    ).resolve()
    
    file_path = slides_dir / filename
    resolved_path = file_path.resolve()
    
    # Verify path is within slides_dir (prevent traversal)
    if not resolved_path.is_relative_to(slides_dir):
        raise HTTPException(status_code=400, detail="Invalid file path")
    
    if not resolved_path.exists():
        raise HTTPException(status_code=404, detail="Slide not found")
    
    return FileResponse(
        path=resolved_path,
        media_type="image/png",
        filename=filename,
    )


@app.get("/static/audio/{project_id}/{version_id}/{lang}/{filename}")
async def serve_slide_audio(
    project_id: str,
    version_id: str,
    lang: str,
    filename: str,
    _: str = Depends(verify_session),
):
    """
    Serve slide audio files with path traversal protection.
    Only serves WAV files from the audio directory.
    Requires authentication.
    """
    # Validate UUIDs
    safe_project_id = validate_uuid(project_id)
    safe_version_id = validate_uuid(version_id)
    
    # Validate language code format
    if not LANG_CODE_PATTERN.match(lang):
        raise HTTPException(status_code=400, detail="Invalid language code format")
    
    # Validate filename format (only allow slide_001.wav, slide_002.wav, etc.)
    if not AUDIO_FILENAME_PATTERN.match(filename):
        raise HTTPException(status_code=400, detail="Invalid filename format")
    
    # Build path
    audio_dir = (
        settings.DATA_DIR / safe_project_id / "versions" / safe_version_id / "audio" / lang
    ).resolve()
    
    file_path = audio_dir / filename
    resolved_path = file_path.resolve()
    
    # Verify path is within audio_dir (prevent traversal)
    if not resolved_path.is_relative_to(audio_dir):
        raise HTTPException(status_code=400, detail="Invalid file path")
    
    if not resolved_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    
    return FileResponse(
        path=resolved_path,
        media_type="audio/wav",
        filename=filename,
    )


@app.get("/static/music/{project_id}/corporate.mp3")
async def serve_project_music(
    project_id: str,
    _: str = Depends(verify_session),
):
    """
    Serve project's corporate music file with path traversal protection.
    Only serves the corporate.mp3 file from the music directory.
    Requires authentication.
    """
    # Validate UUID
    safe_project_id = validate_uuid(project_id)
    
    # Build path
    music_dir = (settings.DATA_DIR / safe_project_id / "music").resolve()
    
    file_path = music_dir / "corporate.mp3"
    resolved_path = file_path.resolve()
    
    # Verify path is within music_dir (prevent traversal)
    if not resolved_path.is_relative_to(music_dir):
        raise HTTPException(status_code=400, detail="Invalid file path")
    
    if not resolved_path.exists():
        raise HTTPException(status_code=404, detail="Music file not found")
    
    return FileResponse(
        path=resolved_path,
        media_type="audio/mpeg",
        filename="corporate.mp3",
        headers={
            # Avoid stale preview after replacing the file (same URL).
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "app": settings.APP_NAME}

