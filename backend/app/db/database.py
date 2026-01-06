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
        finally:
            await session.close()


# === Celery-specific session factory ===
# Uses NullPool to avoid connection caching issues with asyncio event loops

def create_celery_session():
    """
    Create a new engine and session factory for Celery tasks.
    Uses NullPool to ensure connections are created fresh for each task
    and don't get stuck in a different event loop.
    """
    celery_engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        future=True,
        poolclass=NullPool,  # No connection pooling - fresh connection each time
    )
    return async_sessionmaker(
        celery_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


@asynccontextmanager
async def get_celery_db():
    """
    Context manager for Celery tasks that creates a fresh session factory.
    Usage:
        async with get_celery_db() as db:
            result = await db.execute(...)
    """
    session_factory = create_celery_session()
    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.close()

