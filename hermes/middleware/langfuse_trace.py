"""
Langfuse 分布式追踪中间件

为每个 HTTP 请求自动创建 Langfuse trace span，使用 context manager
（with）正确激活 span。所有下游 span（LLM 调用、agent 推理等）
自动挂载到当前 trace 下，形成完整的调用链。

Langfuse v4 SDK 要求 start_as_current_observation 返回的 context manager
必须用 with 进入，否则 span 不会被激活。
"""

from __future__ import annotations

import time
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from hermes.core.logging import get_logger
from hermes.core.observability import (
    get_langfuse,
    set_trace_context,
    start_http_span,
)

logger = get_logger(__name__)

# 不需要追踪的路径
_SKIP_TRACE_PREFIXES = (
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
)


class LangfuseTraceMiddleware(BaseHTTPMiddleware):
    """Langfuse HTTP 请求追踪中间件。

    每个 HTTP 请求自动创建一个 Langfuse span，
    将请求上下文信息（用户、IP、路径等）注入 span 元数据。
    span 通过 context manager 正确激活，下游所有操作自动挂载为此 span 的子节点。
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 跳过非业务请求
        if any(request.url.path.startswith(p) for p in _SKIP_TRACE_PREFIXES):
            return await call_next(request)

        if get_langfuse() is None:
            return await call_next(request)

        # 提取请求上下文
        user_id = getattr(request.state, "user_id", None)
        user_role = getattr(request.state, "role", None)
        client_ip = _get_client_ip(request)
        user_agent = request.headers.get("user-agent", "")

        # 获取或创建 session_id
        trace_id = getattr(request.state, "trace_id", None)
        if trace_id:
            set_trace_context(trace_id)

        # 创建 span（context manager），若不配置则跳过
        span_ctx = start_http_span(
            method=request.method,
            path=request.url.path,
            user_id=str(user_id) if user_id else None,
            user_role=user_role,
            client_ip=client_ip,
            user_agent=user_agent,
        )
        if span_ctx is None:
            return await call_next(request)

        start_time = time.monotonic()

        # with 进入 span context —— 这才是激活 span 的关键步骤
        with span_ctx as span:
            error: str | None = None
            status_code = 200
            try:
                response = await call_next(request)
                status_code = response.status_code
            except Exception as exc:
                error = str(exc)
                status_code = 500
                span.update(
                    level="ERROR",
                    status_message=error[:1000],
                )
                raise
            finally:
                duration_ms = int((time.monotonic() - start_time) * 1000)
                span.update(
                    output={
                        "status_code": status_code,
                        "duration_ms": duration_ms,
                    },
                )

            # 在响应头中返回 trace 信息
            if span.trace_id:
                response.headers["X-Trace-ID"] = span.trace_id

            return response


def _get_client_ip(request: Request) -> str:
    """提取客户端真实 IP（考虑反向代理）。"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip
    client = request.client
    if client:
        return client.host
    return "unknown"
