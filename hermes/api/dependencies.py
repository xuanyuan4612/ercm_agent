"""
FastAPI 共享依赖：认证、RBAC 权限过滤
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hermes.core.exceptions import (
    AccountLockedError,
    CrossClientForbiddenError,
    ForbiddenError,
    TokenExpiredError,
    UnauthorizedError,
)
from hermes.core.security import decode_token
from hermes.db.models.shared import User
from hermes.db.session import get_db


async def get_current_user(
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    db: AsyncSession = Depends(get_db),
) -> User:
    """从 JWT Bearer Token 解析当前用户。"""
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError(detail="Missing or invalid Authorization header")

    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = decode_token(token)
    except ValueError as e:
        raise TokenExpiredError(detail=str(e))

    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedError(detail="Token missing subject claim")

    result = await db.execute(select(User).where(User.username == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise UnauthorizedError(detail=f"User {user_id} not found")
    if not user.is_active:
        raise ForbiddenError(detail="User account is disabled")
    if user.locked_until:
        from datetime import UTC, datetime
        now = datetime.now(UTC)
        locked = user.locked_until
        if locked.tzinfo is None:
            locked = locked.replace(tzinfo=UTC)
        if locked > now:
            raise AccountLockedError()

    # 将用户信息存入 request.state 供后续使用
    request.state.user = user
    request.state.user_id = str(user.id)
    request.state.role = user.role
    return user


def require_role(*allowed_roles: str):
    """RBAC 角色守卫工厂。"""

    async def _check(user: User = Depends(get_current_user)) -> User:
        if allowed_roles and user.role not in allowed_roles:
            raise ForbiddenError(detail=f"Role '{user.role}' not allowed")
        return user

    return _check


def check_client_access(user: User, resource_client: str) -> None:
    """检查用户是否有权限访问特定事业部的数据。

    规则：
    - group: 全量可见
    - ecovacs / tineco: 仅可见自己事业部的数据
    """
    if user.role == "group":
        return
    if user.role != resource_client:
        raise CrossClientForbiddenError(
            detail=f"User role '{user.role}' cannot access client '{resource_client}' data"
        )


# 常用依赖别名
CurrentUser = Annotated[User, Depends(get_current_user)]
GroupRoleRequired = Annotated[User, Depends(require_role("group"))]
