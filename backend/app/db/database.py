from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import settings


# Main engine for FastAPI (uses connection pooling)
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# === Celery-specific session factory (SINGLETON) ===
# Uses NullPool to avoid connection caching issues with asyncio event loops.
# Engine is created once and reused across all Celery tasks to prevent resource leaks.

_celery_engine = None
_celery_session_factory = None


def _get_celery_engine():
    """
    Get or create singleton Celery engine with NullPool.
    NullPool ensures connections are created fresh for each session
    and don't get stuck in a different event loop.
    """
    global _celery_engine
    if _celery_engine is None:
        _celery_engine = create_async_engine(
            settings.DATABASE_URL,
            echo=False,
            future=True,
            poolclass=NullPool,  # No connection pooling - fresh connection each time
        )
    return _celery_engine


def _get_celery_session_factory():
    """Get or create singleton session factory for Celery tasks."""
    global _celery_session_factory
    if _celery_session_factory is None:
        _celery_session_factory = async_sessionmaker(
            _get_celery_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _celery_session_factory


@asynccontextmanager
async def get_celery_db():
    """
    Context manager for Celery tasks using singleton session factory.
    Usage:
        async with get_celery_db() as db:
            result = await db.execute(...)
    """
    session_factory = _get_celery_session_factory()
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def dispose_celery_engine():
    """
    Dispose the Celery engine on worker shutdown.
    Call this in Celery worker shutdown signal handler.
    """
    global _celery_engine, _celery_session_factory
    if _celery_engine is not None:
        await _celery_engine.dispose()
        _celery_engine = None
        _celery_session_factory = None

