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
from typing import Any, AsyncGenerator, Callable, Optional

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

async def create_http_trace(
    method: str,
    path: str,
    user_id: str | None = None,
    user_role: str | None = None,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> dict[str, Any] | None:
    """为 HTTP 请求创建 Langfuse trace。

    Returns:
        包含 trace 信息的字典，或 None（Langfuse 未配置时）
    """
    client = get_langfuse()
    if client is None:
        return None

    trace_id = str(uuid.uuid4())
    set_trace_context(trace_id)

    # 使用 propagate_attributes 将用户/请求信息附加到后续 span
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

    # 使用 start_as_current_observation 创建顶层 trace（span type）
    trace_name = f"HTTP {method} {path}"
    client.start_as_current_observation(
        as_type="span",
        name=trace_name,
        input={
            "method": method,
            "path": path,
            "user_id": user_id,
            "client_ip": client_ip,
        },
    )

    return {
        "trace_id": trace_id,
        "trace_name": trace_name,
    }


async def finalize_http_trace(
    trace_info: dict[str, Any] | None,
    status_code: int,
    response_body: Any = None,
    error: str | None = None,
) -> None:
    """完成 HTTP 请求 trace。

    Args:
        trace_info: create_http_trace 返回的 trace 信息
        status_code: HTTP 状态码
        response_body: 响应体（可选）
        error: 错误信息（可选）
    """
    client = get_langfuse()
    if client is None or trace_info is None:
        return

    level = "ERROR" if error else "DEFAULT"
    client.update_current_span(
        output={"status_code": status_code, "response": response_body},
        level=level,
        status_message=error,
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


async def create_agent_observation(
    agent_name: str,
    stage: str,
    input_data: dict[str, Any],
    trace_id: str | None = None,
) -> Any:
    """为 Agent 推理创建子 span。

    Args:
        agent_name: Agent 名称
        stage: 工作流阶段
        input_data: Agent 输入
        trace_id: 关联的 trace ID

    Returns:
        当前 observation 上下文
    """
    client = get_langfuse()
    if client is None:
        return None

    obs_name = f"agent.{agent_name}.{stage}"
    return client.start_as_current_observation(
        as_type="agent",
        name=obs_name,
        input=input_data,
    )


async def finalize_agent_observation(
    observation: Any,
    output: dict[str, Any],
    error: str | None = None,
) -> None:
    """完成 Agent 推理 span。"""
    client = get_langfuse()
    if client is None or observation is None:
        return

    level = "ERROR" if error else "DEFAULT"
    client.update_current_span(
        output=output,
        level=level,
        status_message=error,
    )


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
    "create_http_trace",
    "finalize_http_trace",
    "create_agent_observation",
    "finalize_agent_observation",
    "flush",
    "shutdown",
]
