from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import DATABASE_URL
from . import db_models

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(db_models.Base.metadata.create_all)
        # Migration: gait-Spalte in frames (für bestehende DBs)
        await conn.execute(text(
            "ALTER TABLE frames ADD COLUMN IF NOT EXISTS gait VARCHAR"
        ))
        # Migration G2: stockmass_cm in videos (für bestehende DBs)
        await conn.execute(text(
            "ALTER TABLE videos ADD COLUMN IF NOT EXISTS stockmass_cm INTEGER"
        ))
