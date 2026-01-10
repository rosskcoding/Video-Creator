from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings


def _default_data_dir() -> Path:
    """
    Compute default DATA_DIR when env var is not set.

    - In containers we usually mount to /data/projects.
    - In local dev we default to <repo_root>/data/projects to avoid requiring root perms.
    """
    docker_path = Path("/data/projects")
    if docker_path.exists():
        return docker_path

    # backend/app/core/config.py -> repo_root is 3 levels up from `backend/`
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "data" / "projects"


def _default_render_output_dir() -> Path:
    """
    Default shared output directory for render-service generated clips.

    - In Docker images we use /app/output
    - In local dev we use <repo_root>/tmp/render-service-out
    """
    docker_path = Path("/app/output")
    if docker_path.exists() or Path("/app").exists():
        return docker_path

    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "tmp" / "render-service-out"


class Settings(BaseSettings):
    """Application settings with defaults from ТЗ"""
    
    # App
    APP_NAME: str = "Presenter Platform"
    ENV: Literal["dev", "prod"] = "dev"
    DEBUG: bool = False
    
    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/presenter"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # APIs
    OPENAI_API_KEY: str = ""
    ELEVENLABS_API_KEY: str = ""
    
    # Storage
    DATA_DIR: Path = Field(default_factory=_default_data_dir)
    
    # Auth (single admin)
    ADMIN_USERNAME: str = "login"
    ADMIN_PASSWORD: str = "Superman2026!"
    SECRET_KEY: str = "change-me-in-production-very-secret-key"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 1 week
    
    # TTS defaults
    DEFAULT_VOICE_ID: str = "iBcRJa9DRdlJlVihC0V6"
    DEFAULT_TTS_MODEL: str = "eleven_flash_v2_5"
    
    # Translation defaults  
    TRANSLATION_MODEL: str = "gpt-4o"
    
    # === VIDEO OUTPUT CONSTANTS ===
    VIDEO_WIDTH: int = 1920
    VIDEO_HEIGHT: int = 1080
    VIDEO_FPS: int = 30
    VIDEO_CODEC: str = "libx264"
    AUDIO_CODEC: str = "aac"
    AUDIO_BITRATE: str = "192k"
    
    # === TIMING CONSTANTS ===
    PRE_PADDING_SEC: float = 3.0
    POST_PADDING_SEC: float = 3.0
    FIRST_SLIDE_HOLD_SEC: float = 1.0
    LAST_SLIDE_HOLD_SEC: float = 1.0
    TRANSITION_TYPE: str = "fade"
    TRANSITION_DURATION_SEC: float = 0.5
    
    # === AUDIO MIX CONSTANTS ===
    TARGET_LUFS: int = -14
    DEFAULT_VOICE_GAIN_DB: float = 0.0
    DEFAULT_MUSIC_GAIN_DB: float = -22.0
    DUCKING_ENABLED: bool = True
    DUCKING_STRENGTH: str = "default"  # light | default | strong
    
    # === LIMITS (unlimited = -1) ===
    MAX_SLIDES: int = -1
    MAX_TOTAL_DURATION_SEC: int = -1
    MAX_LANGUAGES: int = -1
    
    # Celery task timeouts
    TTS_TASK_TIMEOUT_SEC: int = 180  # 3 min
    RENDER_TASK_TIMEOUT_SEC: int = 3600  # 1 hour
    CONVERT_TASK_TIMEOUT_SEC: int = 600  # 10 min
    
    # HTTP client timeouts (seconds)
    TTS_HTTP_TIMEOUT_SEC: int = 60  # ElevenLabs API timeout
    TRANSLATE_HTTP_TIMEOUT_SEC: int = 120  # OpenAI API timeout (batch translations can be slow)
    
    # Render service (Puppeteer-based)
    RENDER_SERVICE_URL: str = "http://localhost:3001"  # Docker: http://render-service:3001
    RENDER_OUTPUT_DIR: Path = Field(default_factory=_default_render_output_dir)
    RENDER_SERVICE_TIMEOUT_SEC: int = 600  # 10 min per slide
    RENDER_SERVICE_BATCH_CONCURRENCY: int = 3  # Hint for /render-batch parallelism
    USE_RENDER_SERVICE: bool = False  # Enable browser-based render with animations

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @model_validator(mode="after")
    def _validate_prod_settings(self) -> "Settings":
        if self.ENV == "prod":
            if self.DEBUG:
                raise ValueError("DEBUG must be false when ENV=prod")

            # Prevent shipping default credentials/secrets to production.
            if not self.ADMIN_PASSWORD or self.ADMIN_PASSWORD in ("admin", "Superman2026!"):
                raise ValueError("ADMIN_PASSWORD must be changed when ENV=prod")
            
            if not self.ADMIN_USERNAME or self.ADMIN_USERNAME == "login":
                raise ValueError("ADMIN_USERNAME must be changed when ENV=prod")

            if (
                not self.SECRET_KEY
                or self.SECRET_KEY == "change-me-in-production-very-secret-key"
                or len(self.SECRET_KEY) < 32
            ):
                raise ValueError("SECRET_KEY must be set to a strong value (>= 32 chars) when ENV=prod")

            # Avoid accidentally allowing localhost origins in production.
            if "localhost" in self.CORS_ORIGINS or "127.0.0.1" in self.CORS_ORIGINS:
                raise ValueError("CORS_ORIGINS must not include localhost when ENV=prod")

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

