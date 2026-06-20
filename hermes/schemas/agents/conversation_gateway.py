"""
conversation-gateway-agent 输入输出 Schema

参照: doc/agents/09-conversation-gateway-agent.md §七〜八
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════
# 意图分类枚举
# ═══════════════════════════════════════════════════════════════


class IntentType(StrEnum):
    """顶层意图类型"""
    OPERATION = "operation_intent"       # 创建案件、查询状态、查询风险
    STAGE = "stage_intent"               # 审批辅助（守门页内）
    KNOWLEDGE = "knowledge_intent"       # 知识库问答
    DOCUMENT = "document_intent"         # 文档生成/重写
    NAVIGATION = "navigation_intent"     # 导航（打开案件、查看任务）
    UNSUPPORTED = "unsupported_intent"   # 不支持或转人工


class OperationType(StrEnum):
    """具体操作（MVP 6 种 + 预留扩展）"""
    CREATE_CASE = "create_case"
    QUERY_CASE_STATUS = "query_case_status"
    QUERY_RISK = "query_risk"
    KNOWLEDGE_QA = "knowledge_qa"
    APPROVAL_ASSIST = "approval_assist"
    DOCUMENT_REWRITE_DRAFT = "document_rewrite_draft"


class RouteDecisionType(StrEnum):
    """路由结果类型"""
    ASK_USER = "ask_user"
    ANSWER_WITH_RAG = "answer_with_rag"
    PREVIEW_ACTION = "preview_action"
    HANDOFF_TO_API = "handoff_to_api"
    HANDOFF_TO_WORKFLOW = "handoff_to_workflow"
    HANDOFF_TO_STAGE_AGENT = "handoff_to_stage_agent"
    DENY = "deny"
    HUMAN_INTERVENTION = "human_intervention"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ═══════════════════════════════════════════════════════════════
# 输入 Schema
# ═══════════════════════════════════════════════════════════════


class PageContext(BaseModel):
    """页面上下文"""
    route: str | None = None           # 当前路由，如 /cases/create
    case_id: str | None = None         # 关联案件 ID
    module: str | None = None          # 当前模块
    stage: str | None = None           # 当前阶段


class AttachmentRef(BaseModel):
    """附件引用"""
    file_id: str
    file_name: str
    parsed_status: str = "pending"     # pending / completed / failed


class UserPermissions(BaseModel):
    """用户权限快照（由 API 层注入）"""
    role: str = "viewer"
    client_scope: list[str] = Field(default_factory=list)
    allowed_modules: list[str] = Field(default_factory=list)


class GatewayAgentInput(BaseModel):
    """入口 Agent 输入契约"""
    session_id: str
    user_id: str
    message: str
    page_context: PageContext = Field(default_factory=PageContext)
    draft_context: dict[str, Any] = Field(default_factory=dict)
    attachment_refs: list[AttachmentRef] = Field(default_factory=list)
    user_permissions: UserPermissions = Field(default_factory=UserPermissions)


# ═══════════════════════════════════════════════════════════════
# 输出 Schema
# ═══════════════════════════════════════════════════════════════


class IntentResult(BaseModel):
    """意图识别结果"""
    intent_type: IntentType = IntentType.UNSUPPORTED
    operation: OperationType | None = None
    module: str | None = None           # integrity_supervision / risk_monitoring / ...
    stage: str | None = None
    confidence: float = 0.0
    risk_level: RiskLevel = RiskLevel.LOW


class ProposedAction(BaseModel):
    """下一步动作建议"""
    type: RouteDecisionType = RouteDecisionType.ASK_USER
    operation: OperationType | None = None
    requires_user_confirmation: bool = False
    api_preview: dict[str, Any] | None = None   # {method, path, body}


class SafetyResult(BaseModel):
    """安全校验结果"""
    permission_result: str = "allowed"           # allowed / denied
    prompt_injection_detected: bool = False
    denied_reason: str | None = None
    requires_hitl: bool = False


class GatewayAgentOutput(BaseModel):
    """入口 Agent 输出契约"""
    reply: str                                      # 面向用户的中文回复
    intent: IntentResult = Field(default_factory=IntentResult)
    slots: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    proposed_action: ProposedAction = Field(default_factory=ProposedAction)
    safety: SafetyResult = Field(default_factory=SafetyResult)
    audit: dict[str, Any] = Field(default_factory=dict)
