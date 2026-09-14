from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def database_url() -> str:
    """读取数据库 URL，并在缺失时给出明确错误。"""
    url = get_settings().database_url
    if not url:
        raise RuntimeError("DATABASE_URL is required")
    return url


def async_database_url() -> str:
    """将同步 psycopg URL 转为 asyncpg URL，兼容 Windows Proactor event loop。"""
    url = make_url(database_url())
    if url.drivername in {"postgresql", "postgresql+psycopg"}:
        url = url.set(drivername="postgresql+asyncpg")
    return url.render_as_string(hide_password=False)


@lru_cache
def get_async_engine() -> AsyncEngine:
    return create_async_engine(async_database_url(), pool_pre_ping=True)


@lru_cache
def get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_async_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_async_session() -> AsyncIterator[AsyncSession]:
    """FastAPI 请求级异步数据库会话。"""
    async with get_async_session_factory()() as session:
        yield session


@lru_cache
def get_sync_engine() -> Engine:
    return create_engine(database_url(), pool_pre_ping=True)


@lru_cache
def get_sync_session_factory() -> sessionmaker[Session]:
    """Celery worker 使用的同步会话工厂。"""
    return sessionmaker(
        bind=get_sync_engine(),
        expire_on_commit=False,
    )
