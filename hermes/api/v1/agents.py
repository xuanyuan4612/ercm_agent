"""Agent 模块 Profile 查询接口"""

from __future__ import annotations

from fastapi import APIRouter

from hermes.agents.profiles import MODULE_PROFILES, get_profile
from hermes.api.dependencies import CurrentUser
from hermes.core.response import success

router = APIRouter(prefix="/agents")


@router.get("/profiles")
async def list_agent_profiles(current_user: CurrentUser):
    """获取所有模块 Agent Profile 列表"""
    profiles = [p.to_dict() for p in MODULE_PROFILES.values()]
    return success(profiles)


@router.get("/profiles/{module}")
async def get_agent_profile(module: str, current_user: CurrentUser):
    """获取单个模块 Agent Profile"""
    profile = get_profile(module)
    return success(profile.to_dict() if profile else None)
