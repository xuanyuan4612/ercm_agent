"""
Langfuse 分布式追踪中间件

为每个 HTTP 请求自动创建 Langfuse trace，包含：
- 请求元数据（method, path, client IP, user agent）
- 用户信息（user_id, role）
- 响应状态码和耗时
- 错误详情

所有 span 自动挂载到当前 trace，形成完整的调用链。
"""

from __future__ import annotations

import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from hermes.core.logging import get_logger
from hermes.core.observability import (
    create_http_trace,
    finalize_http_trace,
    flush,
    get_langfuse,
    set_trace_context,
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

    每个 HTTP 请求自动创建一个 Langfuse trace，
    将请求上下文信息（用户、IP、路径等）注入 span 元数据。
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

        # 获取或创建 session_id（使用 trace_id 作为 session_id 的近似）
        trace_id = getattr(request.state, "trace_id", None)
        if trace_id:
            set_trace_context(trace_id)

        # 创建 HTTP trace
        start_time = time.monotonic()
        trace_info = await create_http_trace(
            method=request.method,
            path=request.url.path,
            user_id=str(user_id) if user_id else None,
            user_role=user_role,
            client_ip=client_ip,
            user_agent=user_agent,
        )

        error: str | None = None
        response = None
        try:
            response = await call_next(request)
        except Exception as exc:
            error = str(exc)
            status_code = 500
            raise
        else:
            status_code = response.status_code
        finally:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)

            # 完成 trace
            await finalize_http_trace(
                trace_info=trace_info,
                status_code=status_code,
                response_body=None,  # 不记录完整响应体以保护数据
                error=error,
            )

            # 在响应头中返回 trace 信息
            if trace_info and response is not None:
                response.headers["X-Trace-ID"] = trace_info.get("trace_id", "")

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
