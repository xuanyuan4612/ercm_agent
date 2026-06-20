"""API v1 路由聚合"""

from fastapi import APIRouter

from hermes.api.v1 import (
    admin,
    agents,
    approval,
    auth,
    cases,
    copilot,
    documents,
    knowledge,
    risk_monitor,
    webhooks,
    websocket,
    workflow,
)

api_router = APIRouter()

# Agent 模块 Profile
api_router.include_router(agents.router, tags=["agents"])
# 对话入口（Copilot）
api_router.include_router(copilot.router, tags=["copilot"])
# 认证
api_router.include_router(auth.router, tags=["auth"])
# 案件管理
api_router.include_router(cases.router, tags=["cases"])
# 工作流
api_router.include_router(workflow.router, tags=["workflow"])
# 守门审批
api_router.include_router(approval.router, tags=["approval"])
# 文档管理
api_router.include_router(documents.router, tags=["documents"])
# 知识库
api_router.include_router(knowledge.router, tags=["knowledge"])
# 风险监控
api_router.include_router(risk_monitor.router, tags=["risk-monitor"])
# 外部 Webhook
api_router.include_router(webhooks.router, tags=["webhooks"])
# 管理后台
api_router.include_router(admin.router, tags=["admin"])

# WebSocket 独立注册（不用 include_router，直接用 add_websocket_route）
# 在 main.py 中注册或通过 include_router 的 websocket 支持
api_router.include_router(websocket.router, tags=["websocket"])
