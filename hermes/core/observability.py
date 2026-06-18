"""
可观测性模块：Langfuse 分布式追踪

提供统一的 Langfuse 追踪能力：
- FastAPI HTTP 请求追踪（中间件）
- LangChain/LangGraph LLM 调用追踪（CallbackHandler）
- 自定义函数追踪（@observe 装饰器）
- Agent 推理过程追踪

架构：
    Trace (HTTP request)
    ├── Span: auth.login
    ├── Span: cases.create_case
    │   ├── Generation: LLM intake analysis
    │   ├── Span: knowledge_search
    │   └── Span: human_approval
    └── Span: workflow.resume

使用方式：
    from hermes.core.observability import observe, get_langfuse_handler, trace_context
"""

from __future__ import annotations

import contextvars
import uuid
from typing import Any

from langfuse import Langfuse, get_client, observe, propagate_attributes
from langfuse.langchain import CallbackHandler

from hermes.core.config import settings
from hermes.core.logging import get_logger

logger = get_logger(__name__)

# ── 全局 Langfuse 客户端（延迟初始化） ───────────────────────────

_langfuse_client: Langfuse | None = None


def get_langfuse() -> Langfuse | None:
    """获取 Langfuse 客户端实例（已配置则返回，未配置返回 None）。"""
    global _langfuse_client
    if _langfuse_client is not None:
        return _langfuse_client
    if not _is_configured():
        return None
    _langfuse_client = Langfuse(
        public_key=settings.LANGFUSE_PUBLIC_KEY,
        secret_key=settings.LANGFUSE_SECRET_KEY.get_secret_value(),
        host=settings.LANGFUSE_BASE_URL,
    )
    logger.info("langfuse_initialized", host=settings.LANGFUSE_BASE_URL)
    return _langfuse_client


def _is_configured() -> bool:
    """检查 Langfuse 是否已配置。"""
    return bool(
        settings.LANGFUSE_PUBLIC_KEY
        and settings.LANGFUSE_SECRET_KEY.get_secret_value()
    )


# ── LangChain Callback Handler ────────────────────────────────────

def get_langfuse_handler(
    trace_id: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> CallbackHandler | None:
    """获取 Langfuse LangChain CallbackHandler。

    将 Handler 传入 LangChain/LangGraph 的 callbacks 参数即可实现 LLM 调用自动追踪。

    Args:
        trace_id: 关联的 trace ID（可选，自动从上下文获取）
        session_id: 用户会话 ID
        user_id: 用户标识
        metadata: 附加元数据

    Returns:
        CallbackHandler 实例，若 Langfuse 未配置则返回 None

    Example:
        handler = get_langfuse_handler(user_id="admin")
        llm = ChatOpenAI(callbacks=[handler])
        response = await llm.ainvoke(messages)
    """
    if not _is_configured():
        return None

    trace_context = {}
    if trace_id:
        trace_context["trace_id"] = trace_id
    if session_id:
        trace_context["session_id"] = session_id
    if user_id:
        trace_context["user_id"] = user_id

    return CallbackHandler(
        public_key=settings.LANGFUSE_PUBLIC_KEY,
        trace_context=trace_context if trace_context else None,
    )


# ── Trace 上下文管理 ─────────────────────────────────────────────

_current_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "langfuse_trace_id", default=None
)
_current_session_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "langfuse_session_id", default=None
)


def set_trace_context(trace_id: str, session_id: str | None = None) -> None:
    """设置当前协程的 trace 上下文。"""
    _current_trace_id.set(trace_id)
    if session_id:
        _current_session_id.set(session_id)


def get_trace_id() -> str | None:
    """获取当前协程的 trace ID。"""
    return _current_trace_id.get()


def get_session_id() -> str | None:
    """获取当前协程的 session ID。"""
    return _current_session_id.get()


# ── HTTP 请求追踪 ────────────────────────────────────────────────

def start_http_span(
    method: str,
    path: str,
    user_id: str | None = None,
    user_role: str | None = None,
    client_ip: str | None = None,
    user_agent: str | None = None,
):
    """为 HTTP 请求创建 Langfuse span（返回 context manager，需用 with 进入）。

    用法:
        with start_http_span("GET", "/api/v1/cases", user_id="admin") as span:
            response = await handle_request()
            span.update(output={"status_code": response.status_code})

    Returns:
        _AgnosticContextManager，或 None（Langfuse 未配置时）
    """
    client = get_langfuse()
    if client is None:
        return None

    trace_id = str(uuid.uuid4())
    set_trace_context(trace_id)

    # 将用户/请求信息附加到后续 span
    propagate_attributes(
        user_id=user_id or "anonymous",
        session_id=_current_session_id.get(),
        metadata={
            "method": method,
            "path": path,
            "user_role": user_role or "unknown",
            "client_ip": client_ip or "unknown",
        },
        tags=["hermes", "api"],
    )

    trace_name = f"HTTP {method} {path}"
    return client.start_as_current_observation(
        as_type="span",
        name=trace_name,
        input={
            "method": method,
            "path": path,
            "user_id": user_id,
            "client_ip": client_ip,
        },
    )


def flush() -> None:
    """刷新 Langfuse 缓冲区（确保所有数据已发送）。"""
    client = get_langfuse()
    if client:
        client.flush()


async def shutdown() -> None:
    """关闭 Langfuse 客户端。"""
    client = get_langfuse()
    if client:
        client.flush()
        client.shutdown()
    global _langfuse_client
    _langfuse_client = None
    logger.info("langfuse_shutdown")


# ── Agent 推理追踪 ───────────────────────────────────────────────


def start_agent_span(
    agent_name: str,
    stage: str,
    input_data: dict[str, Any],
    trace_id: str | None = None,
):
    """为 Agent 推理创建子 span（返回 context manager，需用 with 进入）。

    用法:
        with start_agent_span("intake-agent", "intake", input_data) as span:
            result = await agent.run()
            span.update(output=result.model_dump())
    """
    client = get_langfuse()
    if client is None:
        return None

    obs_name = f"agent.{agent_name}.{stage}"
    return client.start_as_current_observation(
        as_type="span",
        name=obs_name,
        input=input_data,
    )


# ── 评分（人工反馈 / 评估）───────────────────────────────────────


def tag_current_span(tags: list[str] | None = None, metadata: dict[str, Any] | None = None) -> None:
    """为当前活跃 span 添加 tag 或 metadata（用于在 API 端点中补充上下文）。

    用法（在 request handler 中调用）:
        tag_current_span(tags=["client:ecovacs"], metadata={"case_id": str(case.id)})
    """
    client = get_langfuse()
    if client is None:
        return
    try:
        update_kwargs: dict[str, Any] = {}
        if tags:
            update_kwargs["metadata"] = {"tags": tags}
        if metadata:
            existing = update_kwargs.get("metadata", {})
            existing.update(metadata)
            update_kwargs["metadata"] = existing
        if update_kwargs:
            client.update_current_span(**update_kwargs)
    except Exception as e:
        logger.warning("langfuse_tag_span_failed", error=str(e))


def create_score(
    trace_id: str,
    name: str,
    value: float | int,
    data_type: str = "NUMERIC",
    comment: str | None = None,
) -> None:
    """创建 Langfuse score（人工反馈或自动评估）。

    用法:
        create_score(trace_id, "human-approval", 1, data_type="BOOLEAN", comment="通过")

    Args:
        trace_id: 关联的 trace ID
        name: 评分名称（小写+连字符，如 "human-approval", "user-thumbs"）
        value: 评分值（NUMERIC: 0-1 float, BOOLEAN: 0/1, CATEGORICAL: string）
        data_type: 数据类型 ("NUMERIC" | "BOOLEAN" | "CATEGORICAL")
        comment: 可选评语
    """
    client = get_langfuse()
    if client is None:
        return
    try:
        client.create_score(
            trace_id=trace_id,
            name=name,
            value=value,
            data_type=data_type,
            comment=comment,
        )
    except Exception as e:
        logger.warning("langfuse_score_failed", name=name, error=str(e))


# ── 重新导出常用函数 ────────────────────────────────────────────

__all__ = [
    "Langfuse",
    "observe",
    "propagate_attributes",
    "get_client",
    "get_langfuse",
    "get_langfuse_handler",
    "set_trace_context",
    "get_trace_id",
    "get_session_id",
    "start_http_span",
    "start_agent_span",
    "tag_current_span",
    "create_score",
    "flush",
    "shutdown",
]
