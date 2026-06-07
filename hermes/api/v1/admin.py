"""管理后台接口（仅 group 角色）"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hermes.api.dependencies import GroupRoleRequired
from hermes.core.response import paginated, success
from hermes.db.models.shared import AuditLog, User
from hermes.db.session import get_db

router = APIRouter(prefix="/admin")


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
    current_user: GroupRoleRequired,
    db: AsyncSession = Depends(get_db),
):
    """创建用户"""
    # TODO: 从请求体解析用户信息，哈希密码
    return success(message="用户创建功能待实现")


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
            "id": str(l.id),
            "operator_id": l.operator_id,
            "operation": l.operation,
            "target_table": l.target_table,
            "target_id": str(l.target_id) if l.target_id else None,
            "ip_address": str(l.ip_address) if l.ip_address else None,
            "changes": l.changes,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        } for l in logs],
        total=total,
        page=page,
        page_size=page_size,
    )
