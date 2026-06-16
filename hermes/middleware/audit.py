"""
审计日志中间件

等保二级要求：全量操作记录（仅追加、不可删除、保留 >= 6 个月）。
每个请求自动记录：操作人、IP、User-Agent、请求路径、操作类型。
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from hermes.core.logging import get_logger

logger = get_logger(__name__)

# 不需要审计的路径前缀
_SKIP_PREFIXES = (
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/ws",  # WebSocket 单独处理
)


class AuditMiddleware(BaseHTTPMiddleware):
    """请求审计中间件

    对每个 HTTP 请求自动生成 trace_id、记录耗时，并将审计事件写入
    audit_log 表（通过后台任务异步写入，避免阻塞请求主链路）。
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 跳过非业务请求
        if any(request.url.path.startswith(p) for p in _SKIP_PREFIXES):
            return await call_next(request)

        # 生成 trace_id
        trace_id = str(uuid.uuid4())
        request.state.trace_id = trace_id

        # 记录请求开始
        start_time = time.monotonic()

        # 提取用户信息（由认证中间件设置）
        operator_id = getattr(request.state, "user_id", None)
        operator_role = getattr(request.state, "role", None)

        response = await call_next(request)

        # 计算耗时
        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        # 提取审计信息
        audit_event = {
            "trace_id": trace_id,
            "operator_id": str(operator_id) if operator_id else "anonymous",
            "operator_role": operator_role or "unknown",
            "method": request.method,
            "path": request.url.path,
            "query_string": str(request.url.query) if request.url.query else None,
            "status_code": response.status_code,
            "elapsed_ms": elapsed_ms,
            "client_ip": _get_client_ip(request),
            "user_agent": request.headers.get("user-agent", ""),
        }

        # 审计日志写入（当前为 structlog 异步输出，数据库持久化待接入）
        # 生产环境：入队到 Celery audit 任务异步写入 PostgreSQL audit_logs 表
        # app.send_task("hermes.tasks.audit.write", args=[audit_event], queue="hermes.audit")
        logger.info("audit_event", **audit_event)

        # 在响应头中返回 trace_id，方便前端问题排查
        response.headers["X-Trace-ID"] = trace_id

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
