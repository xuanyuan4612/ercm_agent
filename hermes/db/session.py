"""
赫尔墨斯（Hermes）数据库引擎与会话管理

基于 SQLAlchemy 2.0 async + asyncpg + pgvector。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from hermes.core.config import settings

# 异步引擎（用于 API 运行时）
engine = create_async_engine(
    settings.database_url,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    echo=settings.DB_ECHO,
    pool_pre_ping=True,
    pool_recycle=3600,
)

# 会话工厂
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """所有 ORM 模型基类"""

    pass


async def get_db() -> AsyncSession:
    """FastAPI 依赖注入：获取数据库会话。"""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_db_nocommit() -> AsyncSession:
    """FastAPI 依赖注入：获取只读会话（用于复杂查询，不自动提交）。"""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
