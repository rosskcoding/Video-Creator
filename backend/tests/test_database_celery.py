import pytest


@pytest.mark.asyncio
async def test_celery_engine_and_session_factory_are_singletons_and_disposable():
    """
    Celery DB helper should NOT create a new engine per task.
    We keep a singleton engine (NullPool) + session factory and dispose it on shutdown.
    """
    from sqlalchemy import text

    from app.db import database as db

    # Ensure clean slate (in case previous tests initialized the singleton)
    await db.dispose_celery_engine()

    engine1 = db._get_celery_engine()
    engine2 = db._get_celery_engine()
    assert engine1 is engine2

    sf1 = db._get_celery_session_factory()
    sf2 = db._get_celery_session_factory()
    assert sf1 is sf2

    # Ensure the context manager yields a working session
    async with db.get_celery_db() as session:
        res = await session.execute(text("SELECT 1"))
        assert res.scalar_one() == 1

    # Dispose should reset singletons
    await db.dispose_celery_engine()
    engine3 = db._get_celery_engine()
    assert engine3 is not engine1

    # Cleanup
    await db.dispose_celery_engine()


