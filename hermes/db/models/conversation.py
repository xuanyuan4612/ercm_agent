"""
会话与意图路由数据模型

三张表：
  - conversation_sessions: 对话会话
  - conversation_messages: 对话消息
  - intent_decisions: 意图识别决策（审计留痕）

参照: doc/superpowers/specs/2026-06-20-conversation-gateway-agent-design.md §三
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hermes.db.session import Base


class ConversationSession(Base):
    """对话会话"""

    __tablename__ = "conversation_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    client_scope: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="'[]'::jsonb"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    related_case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    related_module: Mapped[str | None] = mapped_column(String(50), nullable=True)
    context_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # 关系
    messages: Mapped[list["ConversationMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<ConversationSession {self.id} user={self.user_id} status={self.status}>"


class ConversationMessage(Base):
    """对话消息"""

    __tablename__ = "conversation_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversation_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    page_context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    attachment_refs: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # 关系
    session: Mapped["ConversationSession"] = relationship(back_populates="messages")
    intent_decision: Mapped["IntentDecision | None"] = relationship(
        back_populates="message", uselist=False
    )

    def __repr__(self) -> str:
        return f"<ConversationMessage {self.id} role={self.role}>"


class IntentDecision(Base):
    """意图识别决策"""

    __tablename__ = "intent_decisions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversation_sessions.id"), nullable=False, index=True
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversation_messages.id"), nullable=False
    )
    intent_type: Mapped[str] = mapped_column(String(30), nullable=False)
    operation: Mapped[str | None] = mapped_column(String(50), nullable=True)
    module: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    slots: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    missing_fields: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    permission_result: Mapped[str] = mapped_column(
        String(10), nullable=False, default="allowed", server_default="allowed"
    )
    denied_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    requires_confirmation: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default="false"
    )
    risk_level: Mapped[str] = mapped_column(
        String(10), nullable=False, default="low", server_default="low"
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    executed_action_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # 关系
    message: Mapped["ConversationMessage"] = relationship(back_populates="intent_decision")

    def __repr__(self) -> str:
        return (
            f"<IntentDecision {self.id} intent={self.intent_type}"
            f" op={self.operation} module={self.module}>"
        )
