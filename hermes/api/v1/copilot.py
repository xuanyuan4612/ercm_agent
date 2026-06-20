"""
对话入口（Copilot）API

端点:
  POST /api/v1/copilot/sessions              创建会话
  POST /api/v1/copilot/sessions/{id}/messages  发送消息
  POST /api/v1/copilot/sessions/{id}/confirm   确认动作
  GET  /api/v1/copilot/sessions/{id}           查询会话

参照: doc/agents/09-conversation-gateway-agent.md §十三
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hermes.agents.conversation_gateway import ConversationGatewayAgent
from hermes.api.dependencies import CurrentUser, get_db
from hermes.core.logging import get_logger
from hermes.core.response import success
from hermes.db.models import (
    ConversationMessage,
    ConversationSession,
    IntentDecision,
    User,
)
from hermes.schemas.agents.conversation_gateway import (
    AttachmentRef,
    GatewayAgentInput,
    GatewayAgentOutput,
    PageContext,
    UserPermissions,
)

router = APIRouter(prefix="/copilot")
logger = get_logger(__name__)

# 全局单例
_gateway_agent = ConversationGatewayAgent()


# ═══════════════════════════════════════════════════════════════
# 请求/响应模型
# ═══════════════════════════════════════════════════════════════


class CreateSessionRequest(BaseModel):
    page_context: dict[str, Any] = Field(default_factory=dict)
    related_case_id: str | None = None
    related_module: str | None = None


class SendMessageRequest(BaseModel):
    message: str
    page_context: dict[str, Any] = Field(default_factory=dict)
    draft_context: dict[str, Any] = Field(default_factory=dict)
    attachment_refs: list[dict[str, str]] = Field(default_factory=list)


class ConfirmActionRequest(BaseModel):
    message_id: str
    action_id: str | None = None
    confirm: bool = True


# ═══════════════════════════════════════════════════════════════
# API 端点
# ═══════════════════════════════════════════════════════════════


@router.post("/sessions")
async def create_session(
    body: CreateSessionRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """创建对话会话"""
    session = ConversationSession(
        user_id=current_user.id,
        client_scope=_derive_client_scope(current_user),
        context_snapshot=body.page_context,
        related_case_id=body.related_case_id,
        related_module=body.related_module,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    logger.info(
        "copilot_session_created",
        session_id=str(session.id),
        user_id=str(current_user.id),
    )
    return success({
        "session_id": str(session.id),
        "status": session.status,
    })


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """查询会话详情（含消息历史）"""
    session = await _get_session(db, session_id, current_user)

    # 查询消息
    result = await db.execute(
        select(ConversationMessage)
        .where(ConversationMessage.session_id == session.id)
        .order_by(ConversationMessage.created_at)
    )
    messages = result.scalars().all()

    return success({
        "session_id": str(session.id),
        "status": session.status,
        "related_case_id": str(session.related_case_id) if session.related_case_id else None,
        "related_module": session.related_module,
        "created_at": session.created_at.isoformat(),
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
    })


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: str,
    body: SendMessageRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """发送消息，返回 Agent 意图识别与路由结果"""
    session = await _get_session(db, session_id, current_user)

    if session.status != "active":
        raise HTTPException(status_code=400, detail=f"会话状态为 {session.status}，无法发送消息")

    # 1. 保存用户消息
    user_msg = ConversationMessage(
        session_id=session.id,
        role="user",
        content=body.message,
        page_context=body.page_context,
        attachment_refs=body.attachment_refs,
    )
    db.add(user_msg)
    await db.flush()

    # 2. 构建 Agent 输入（client_scope 从 role 推导）
    client_scope = _derive_client_scope(current_user)

    agent_input = GatewayAgentInput(
        session_id=session_id,
        user_id=str(current_user.id),
        message=body.message,
        page_context=PageContext(**body.page_context),
        draft_context=body.draft_context,
        attachment_refs=[
            AttachmentRef(**ref) for ref in body.attachment_refs
        ],
        user_permissions=UserPermissions(
            role=current_user.role or "viewer",
            client_scope=client_scope,
            allowed_modules=_resolve_allowed_modules(current_user),
        ),
    )

    # 3. 调用 Agent
    try:
        output: GatewayAgentOutput = await _gateway_agent.run(agent_input)
    except Exception as e:
        logger.exception("gateway_agent_error", session_id=session_id, error=str(e))
        raise HTTPException(status_code=500, detail="意图识别失败，请稍后重试")

    # 4. 保存 assistant 消息
    assistant_msg = ConversationMessage(
        session_id=session.id,
        role="assistant",
        content=output.reply,
    )
    db.add(assistant_msg)
    await db.flush()

    # 5. 保存意图决策
    intent = IntentDecision(
        session_id=session.id,
        message_id=assistant_msg.id,
        intent_type=output.intent.intent_type.value,
        operation=output.intent.operation.value if output.intent.operation else None,
        module=output.intent.module,
        confidence=output.intent.confidence,
        slots=output.slots,
        missing_fields=output.missing_fields,
        permission_result=output.safety.permission_result,
        denied_reason=output.safety.denied_reason,
        requires_confirmation=output.proposed_action.requires_user_confirmation,
        risk_level=output.intent.risk_level.value,
    )
    db.add(intent)

    # 6. 更新 session 关联模块
    if output.intent.module and not session.related_module:
        session.related_module = output.intent.module

    await db.commit()

    return success(output.model_dump())


@router.post("/sessions/{session_id}/confirm")
async def confirm_action(
    session_id: str,
    body: ConfirmActionRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """用户确认执行动作"""
    session = await _get_session(db, session_id, current_user)

    if not body.confirm:
        return success({
            "status": "cancelled",
            "message": "已取消该操作。",
        })

    # 查找对应的 intent_decision
    result = await db.execute(
        select(IntentDecision)
        .where(
            IntentDecision.message_id == body.message_id,
            IntentDecision.session_id == session.id,
        )
        .order_by(IntentDecision.created_at.desc())
        .limit(1)
    )
    intent = result.scalar_one_or_none()

    if not intent:
        raise HTTPException(status_code=404, detail="未找到对应的意图决策")

    if not intent.requires_confirmation:
        raise HTTPException(status_code=400, detail="该操作不需要确认")

    # 标记已确认
    intent.confirmed_at = func.now()

    # 根据 operation 类型，调用对应的业务 API
    # （当前只记录确认，实际执行由 API 层在后续阶段完成）
    await db.commit()

    logger.info(
        "copilot_action_confirmed",
        session_id=session_id,
        intent_id=str(intent.id),
        operation=intent.operation,
    )

    return success({
        "status": "confirmed",
        "operation": intent.operation,
        "module": intent.module,
        "message": f"已确认 {intent.operation} 操作，正在交给业务系统处理。",
    })


# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════


async def _get_session(
    db: AsyncSession, session_id: str, current_user: CurrentUser
) -> ConversationSession:
    """获取并校验会话归属"""
    try:
        sid = UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的 session_id")

    result = await db.execute(
        select(ConversationSession).where(ConversationSession.id == sid)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    if str(session.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="无权访问此会话")

    return session


def _derive_client_scope(user: Any) -> list[str]:
    """从用户 role 推导数据权限范围"""
    role = getattr(user, "role", "viewer")
    if role == "group":
        return ["group", "ecovacs", "tineco"]
    return [role]


def _resolve_allowed_modules(user: Any) -> list[str]:
    """根据用户角色和权限推导可访问模块"""
    base_modules = ["integrity_supervision", "risk_monitoring", "knowledge"]
    role = getattr(user, "role", "viewer")

    if role in ("group", "admin"):
        return base_modules + [
            "internal_control_evaluation",
            "special_audit",
            "exit_audit",
            "trade_secrets",
            "behavioral_risk",
            "continuous_improvement",
        ]
    return base_modules

