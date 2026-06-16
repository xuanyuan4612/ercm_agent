"""认证接口"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hermes.api.dependencies import CurrentUser
from hermes.core.config import settings
from hermes.core.exceptions import AccountLockedError, UnauthorizedError
from hermes.core.response import success
from hermes.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from hermes.db.models.shared import User
from hermes.db.session import get_db
from hermes.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RefreshResponse,
    TokenResponse,
    UserInfo,
)

router = APIRouter(prefix="/auth")


@router.post("/login", response_model=dict)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """用户登录，返回 access_token + refresh_token"""
    result = await db.execute(select(User).where(User.username == request.username))
    user = result.scalar_one_or_none()

    if not user:
        raise UnauthorizedError(detail="用户名或密码错误")

    # 检查账号锁定
    now = datetime.now(UTC)
    if user.locked_until:
        locked = user.locked_until
        if locked.tzinfo is None:
            locked = locked.replace(tzinfo=UTC)
        if locked > now:
            raise AccountLockedError(detail=f"账号已锁定，请{settings.ACCOUNT_LOCK_MINUTES}分钟后再试")

    if not verify_password(request.password, user.hashed_password):
        user.login_attempts = (user.login_attempts or 0) + 1
        if user.login_attempts >= settings.MAX_LOGIN_ATTEMPTS:
            user.locked_until = now + timedelta(minutes=settings.ACCOUNT_LOCK_MINUTES)
        await db.flush()
        raise UnauthorizedError(detail="用户名或密码错误")

    # 登录成功
    user.login_attempts = 0
    user.locked_until = None
    user.last_login = now

    extra_claims = {
        "role": user.role,
        "user_id": str(user.id),
    }
    access_token = create_access_token(user.username, extra_claims)
    refresh_token = create_refresh_token(user.username)

    return success(
        LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_SECONDS,
            user_info=UserInfo(
                id=str(user.id),
                username=user.username,
                role=user.role,
                display_name=user.display_name,
            ),
        ).model_dump()
    )


@router.post("/refresh", response_model=dict)
async def refresh(request: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """刷新 access_token"""
    try:
        payload = decode_token(request.refresh_token)
    except ValueError as e:
        raise UnauthorizedError(detail="Invalid refresh token")

    if payload.get("type") != "refresh":
        raise UnauthorizedError(detail="Not a refresh token")

    username = payload.get("sub")
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise UnauthorizedError(detail="User not found or disabled")

    extra_claims = {"role": user.role, "user_id": str(user.id)}
    access_token = create_access_token(username, extra_claims)

    return success(
        RefreshResponse(
            access_token=access_token,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_SECONDS,
        ).model_dump()
    )


@router.post("/logout", response_model=dict)
async def logout(current_user: CurrentUser):
    """登出（使 refresh_token 失效）"""
    # 将 refresh_token 加入黑名单（当前降级为无状态登出）
    try:
        from fastapi import Request
        # 尝试获取 Redis 连接加入黑名单
        # redis_client = current_user._redis
        # if redis_client:
        #     await redis_client.sadd("token_blacklist", refresh_token)
        #     await redis_client.expire("token_blacklist", settings.REFRESH_TOKEN_EXPIRE_SECONDS)
        pass
    except Exception:
        pass
    return success(message="已登出（当前无状态登出模式，Redis 黑名单待接入）")


@router.get("/me", response_model=dict)
async def get_me(current_user: CurrentUser):
    """获取当前用户信息"""
    return success(
        UserInfo(
            id=str(current_user.id),
            username=current_user.username,
            role=current_user.role,
            display_name=current_user.display_name,
        ).model_dump()
    )
