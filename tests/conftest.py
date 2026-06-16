"""pytest 共享 fixtures"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# 在导入 hermes 模块之前设置测试环境变量，避免触发真实 .env 加载
# 注意：不要覆盖 .env 文件中已有的数据库密码等关键配置，
# 因为 pydantic-settings 优先使用 OS 环境变量而非 .env 文件值。
# DB_PASSWORD 等关键字段由 .env 文件提供（如果有的话），
# 这里只为单元测试中没有 .env 文件的情况提供 fallback。

# 集成测试需要通过 API handler 的 get_db() 访问测试数据库，
# 所以必须将 DB_NAME 指向测试库，确保与 db_session fixture 同库
_need_test_db = os.getenv("TEST_DB_AVAILABLE", "").lower() in ("1", "true", "yes")
if _need_test_db:
    os.environ["DB_NAME"] = f"{os.getenv('TEST_DB_NAME', os.getenv('DB_NAME', 'hermes') + '_test')}"

os.environ.setdefault("REDIS_PASSWORD", "test")
os.environ.setdefault("RABBITMQ_PASSWORD", "test")
os.environ.setdefault("MINIO_SECRET_KEY", "test")
os.environ.setdefault("LLM_API_KEY", "test")
os.environ.setdefault("LLM_BACKUP_API_KEY", "test")
os.environ.setdefault("EMBEDDING_API_KEY", "test")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-unit-tests-at-least-32-chars!!")
os.environ.setdefault("ENCRYPTION_KEY", "jxmHOG1FgZJDFrKsVgOW0lQioiZ-M9S_VG3DRaRWM_c=")
# DB_PASSWORD 不使用 setdefault —— 让 .env 文件的值生效，
# 单元测试通过 _build_settings(DB_PASSWORD="test") 显式传入

from hermes.core.config import settings  # noqa: E402


def _build_test_db_url() -> str:
    """构建测试数据库 URL（若未配置则跳过集成测试）。

    当 TEST_DB_AVAILABLE=1 时，模块顶部已设置 DB_NAME 指向测试库，
    这里直接使用 settings.database_url 即可。
    """
    return settings.database_url


TEST_DB_URL = _build_test_db_url()


def _db_available() -> bool:
    """检查测试数据库是否可用。"""
    return os.getenv("TEST_DB_AVAILABLE", "").lower() in ("1", "true", "yes")


@pytest.fixture(scope="session")
def event_loop():
    """为整个测试会话创建事件循环（全局 engine 的 pool 依赖单一 loop）。"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """为每个测试函数提供独立的数据库会话。

    需要 PostgreSQL 测试数据库可用；未设置 TEST_DB_AVAILABLE=1 时跳过。
    """
    if not _db_available():
        pytest.skip("TEST_DB_AVAILABLE is not set — skipping integration test")

    # 确保所有 ORM 模型已在 Base.metadata 中注册
    import hermes.db.models  # noqa: F401
    from hermes.db.models import Base

    engine = create_async_engine(TEST_DB_URL, echo=False, pool_size=5, pool_pre_ping=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    _async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with _async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ── 集成测试共享 fixtures ─────────────────────────────────────────

@pytest.fixture
async def client(db_session: AsyncSession):
    """创建测试 HTTP 客户端（需要 db_session fixture）。"""
    from httpx import ASGITransport, AsyncClient

    from hermes.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def auth_headers(client, db_session: AsyncSession):
    """创建测试用户并返回认证头。"""
    from hermes.core.security import hash_password
    from hermes.db.models.shared import User

    user = User(
        username="test_user_api",
        hashed_password=hash_password("TestPass123!"),
        display_name="API测试用户",
        department="测试部",
        role="ecovacs",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    resp = await client.post("/api/v1/auth/login", json={
        "username": "test_user_api",
        "password": "TestPass123!",
    })
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def group_auth_headers(client, db_session: AsyncSession):
    """创建 group 角色管理员并返回认证头。"""
    from hermes.core.security import hash_password
    from hermes.db.models.shared import User

    user = User(
        username="group_admin_test",
        hashed_password=hash_password("AdminPass123!"),
        display_name="管理员",
        department="风控部",
        role="group",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    resp = await client.post("/api/v1/auth/login", json={
        "username": "group_admin_test",
        "password": "AdminPass123!",
    })
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}
