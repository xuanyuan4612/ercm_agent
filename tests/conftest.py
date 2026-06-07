"""pytest 共享 fixtures"""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from hermes.core.config import settings
from hermes.db.models import Base

# 使用测试数据库（需要单独配置环境变量或在 CI 中启动临时 PG）
TEST_DB_URL = settings.database_url.replace(settings.DB_NAME, f"{settings.DB_NAME}_test")


@pytest.fixture(scope="session")
def event_loop():
    """为整个测试会话创建事件循环"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """为每个测试函数提供独立的数据库会话"""
    engine = create_async_engine(TEST_DB_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()
