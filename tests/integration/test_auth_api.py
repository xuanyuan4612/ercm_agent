"""集成测试：认证 API

需要测试数据库可用（设置 TEST_DB_AVAILABLE=1 环境变量）。
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from hermes.core.security import hash_password
from hermes.db.models.shared import User


@pytest.fixture
async def test_user(db_session: AsyncSession):
    """创建一个测试用户"""
    user = User(
        username="testuser_auth",
        hashed_password=hash_password("TestPass123!"),
        display_name="测试用户",
        department="测试部",
        role="ecovacs",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


class TestLogin:
    """POST /api/v1/auth/login"""

    async def test_login_success(self, client, test_user):
        resp = await client.post("/api/v1/auth/login", json={
            "username": "testuser_auth",
            "password": "TestPass123!",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert "access_token" in data["data"]
        assert "refresh_token" in data["data"]
        assert data["data"]["token_type"] == "bearer"

    async def test_login_wrong_password(self, client, test_user):
        resp = await client.post("/api/v1/auth/login", json={
            "username": "testuser_auth",
            "password": "WrongPassword",
        })
        assert resp.status_code == 401

    async def test_login_nonexistent_user(self, client):
        resp = await client.post("/api/v1/auth/login", json={
            "username": "nobody",
            "password": "test",
        })
        assert resp.status_code == 401

    async def test_login_missing_fields(self, client):
        resp = await client.post("/api/v1/auth/login", json={})
        assert resp.status_code == 422


class TestGetMe:
    """GET /api/v1/auth/me"""

    async def test_get_me_authenticated(self, client, auth_headers):
        resp = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["username"] == "test_user_api"
        assert data["data"]["role"] == "ecovacs"

    async def test_get_me_without_token(self, client):
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401


class TestRefresh:
    """POST /api/v1/auth/refresh"""

    async def test_refresh_token_success(self, client, auth_headers, db_session: AsyncSession):
        # 登录获取 refresh_token
        resp = await client.post("/api/v1/auth/login", json={
            "username": "test_user_api",
            "password": "TestPass123!",
        })
        refresh_token = resp.json()["data"]["refresh_token"]

        resp = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": refresh_token,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data["data"]

    async def test_refresh_invalid_token(self, client):
        resp = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": "invalid-token",
        })
        assert resp.status_code == 401


class TestLogout:
    """POST /api/v1/auth/logout"""

    async def test_logout_success(self, client, auth_headers):
        resp = await client.post("/api/v1/auth/logout", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["message"] == "success"


class TestHealth:
    """GET /health"""

    async def test_health_check(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
