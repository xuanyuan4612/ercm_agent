"""管理后台接口（仅 group 角色）"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hermes.api.dependencies import GroupRoleRequired
from hermes.core.config import settings
from hermes.core.logging import get_logger
from hermes.core.response import paginated, success
from hermes.core.security import hash_password
from hermes.db.models.shared import AuditLog, User
from hermes.db.session import get_db

logger = get_logger(__name__)

router = APIRouter(prefix="/admin")


class CreateUserRequest(BaseModel):
    """创建用户请求"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    password: str = Field(..., min_length=settings.PASSWORD_MIN_LENGTH, description="密码")
    display_name: str = Field(..., min_length=1, max_length=100, description="显示名称")
    department: str = Field(..., max_length=100, description="部门")
    email: str | None = Field(None, description="邮箱")
    role: str = Field(default="ecovacs", description="角色: group/ecovacs/tineco")

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        allowed = {"group", "ecovacs", "tineco"}
        if v not in allowed:
            raise ValueError(f"角色必须为 {allowed} 之一")
        return v


# ── 用户管理 ───────────────────────────────────────────────────

@router.get("/users")
async def list_users(
    current_user: GroupRoleRequired,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """用户列表"""
    count_q = select(func.count()).select_from(User)
    total = (await db.execute(count_q)).scalar() or 0

    result = await db.execute(
        select(User)
        .order_by(User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    users = result.scalars().all()

    return paginated(
        items=[{
            "id": str(u.id),
            "username": u.username,
            "display_name": u.display_name,
            "department": u.department,
            "email": u.email,
            "role": u.role,
            "is_active": u.is_active,
            "last_login": u.last_login.isoformat() if u.last_login else None,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        } for u in users],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/users")
async def create_user(
    request: CreateUserRequest,
    current_user: GroupRoleRequired,
    db: AsyncSession = Depends(get_db),
):
    """创建用户（hashed password 存储）"""
    # 检查用户名是否已存在
    result = await db.execute(select(User).where(User.username == request.username))
    existing = result.scalar_one_or_none()
    if existing:
        from hermes.core.exceptions import ConflictError
        raise ConflictError(detail=f"用户名 {request.username} 已存在")

    hashed_pw = hash_password(request.password)
    user = User(
        username=request.username,
        hashed_password=hashed_pw,
        display_name=request.display_name,
        department=request.department,
        email=request.email,
        role=request.role,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    logger.info("user_created", username=request.username, role=request.role,
                operator=current_user.username)

    return success({
        "id": str(user.id),
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "is_active": user.is_active,
    })


@router.put("/users/{user_id}")
async def update_user(
    user_id: uuid.UUID,
    current_user: GroupRoleRequired,
    db: AsyncSession = Depends(get_db),
):
    """更新用户信息"""
    return success(message="用户更新功能待实现")


@router.patch("/users/{user_id}/status")
async def toggle_user_status(
    user_id: uuid.UUID,
    current_user: GroupRoleRequired,
    db: AsyncSession = Depends(get_db),
):
    """启用/禁用用户"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        from hermes.core.exceptions import NotFoundError
        raise NotFoundError(message="用户不存在")

    user.is_active = not user.is_active
    await db.flush()
    return success({"id": str(user.id), "is_active": user.is_active})


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: uuid.UUID,
    current_user: GroupRoleRequired,
    db: AsyncSession = Depends(get_db),
):
    """软删除用户"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        from hermes.core.exceptions import NotFoundError
        raise NotFoundError(message="用户不存在")

    user.is_active = False
    await db.flush()
    return success(message=f"用户 {user.username} 已禁用")


# ── 审计日志 ───────────────────────────────────────────────────

@router.get("/audit-logs")
async def list_audit_logs(
    current_user: GroupRoleRequired,
    db: AsyncSession = Depends(get_db),
    operator: str | None = Query(None),
    operation: str | None = Query(None),
    target_table: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """审计日志查询（只读，不可删除）"""
    query = select(AuditLog)
    if operator:
        query = query.where(AuditLog.operator_id == operator)
    if operation:
        query = query.where(AuditLog.operation == operation)
    if target_table:
        query = query.where(AuditLog.target_table == target_table)
    if start_date:
        query = query.where(AuditLog.created_at >= start_date)
    if end_date:
        query = query.where(AuditLog.created_at <= end_date)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    query = query.order_by(AuditLog.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    logs = result.scalars().all()

    return paginated(
        items=[{
            "id": str(log_entry.id),
            "operator_id": log_entry.operator_id,
            "operation": log_entry.operation,
            "target_table": log_entry.target_table,
            "target_id": str(log_entry.target_id) if log_entry.target_id else None,
            "ip_address": str(log_entry.ip_address) if log_entry.ip_address else None,
            "changes": log_entry.changes,
            "created_at": log_entry.created_at.isoformat() if log_entry.created_at else None,
        } for log_entry in logs],
        total=total,
        page=page,
        page_size=page_size,
    )
