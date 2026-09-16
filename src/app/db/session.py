from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings


def build_engine(database_url: str | None = None) -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        database_url or settings.database_url,
        echo=settings.db_echo,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
    )


engine: AsyncEngine = build_engine()
async_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped session."""
    async with async_session_factory() as session:
        yield session


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Context manager for use outside of FastAPI's DI (workers, scripts)."""
    async with async_session_factory() as session:
        yield session
