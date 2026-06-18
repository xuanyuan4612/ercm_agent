"""
种子数据初始化脚本

创建默认管理员账号（group 角色），用于首次登录并创建其他用户。

运行方式:
    uv run python -m hermes.scripts.seed

环境变量:
    ADMIN_USERNAME: 管理员用户名（默认: admin）
    ADMIN_PASSWORD: 管理员密码（默认: admin123456，首次登录后务必修改！）
    ADMIN_DISPLAY_NAME: 管理员显示名称（默认: 系统管理员）
    ADMIN_DEPARTMENT: 部门（默认: 风控部）
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from sqlalchemy import select

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hermes.core.security import hash_password
from hermes.db.models.shared import User
from hermes.db.session import async_session_factory

DEFAULT_ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_DISPLAY_NAME = os.getenv("ADMIN_DISPLAY_NAME", "系统管理员")
DEFAULT_ADMIN_DEPARTMENT = os.getenv("ADMIN_DEPARTMENT", "风控部")


def _generate_password() -> str:
    """获取管理员密码，优先环境变量，默认 'admin'。"""
    return os.getenv("ADMIN_PASSWORD", "admin")


async def seed() -> None:
    """执行种子数据初始化。"""
    async with async_session_factory() as session:
        # 检查管理员是否已存在
        result = await session.execute(
            select(User).where(User.username == DEFAULT_ADMIN_USERNAME)
        )
        existing = result.scalar_one_or_none()

        if existing:
            print(f"[SKIP] 管理员用户 '{DEFAULT_ADMIN_USERNAME}' 已存在，跳过创建。")
            return

        password = _generate_password()
        admin = User(
            username=DEFAULT_ADMIN_USERNAME,
            hashed_password=hash_password(password),
            display_name=DEFAULT_ADMIN_DISPLAY_NAME,
            department=DEFAULT_ADMIN_DEPARTMENT,
            email=None,
            role="group",
            is_active=True,
        )
        session.add(admin)
        await session.commit()

        print("=" * 62)
        print("  ✅  管理员账号创建成功")
        print("=" * 62)
        print(f"  用户名:   {DEFAULT_ADMIN_USERNAME}")
        print(f"  密码:     {password}")
        print("  角色:     group (超级管理员)")
        print(f"  显示名:   {DEFAULT_ADMIN_DISPLAY_NAME}")
        print(f"  部门:     {DEFAULT_ADMIN_DEPARTMENT}")
        print("=" * 62)
        print("  ⚠️   首次登录后请立即修改密码！")
        print("  ⚠️   请妥善保管此密码，此信息不会再次显示。")
        print("=" * 62)


def main() -> None:
    """入口函数。"""
    asyncio.run(seed())


if __name__ == "__main__":
    main()
