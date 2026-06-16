"""
速率限制中间件

三层限流策略：
- 全局：1000 req/s（Nginx 层实现，此处为应用层补充）
- 用户：100 req/min per user（Redis 计数器）
- LLM：50 req/s 令牌桶（LLM Adapter 内实现）
"""

from __future__ import annotations

import time
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from hermes.core.config import settings
from hermes.core.exceptions import RateLimitError
from hermes.core.logging import get_logger

logger = get_logger(__name__)

# 不需要限流的路径
_SKIP_PREFIXES = (
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """用户级速率限制中间件

    使用**滑动窗口 + 内存计数器**（生产环境应改用 Redis）。

    限制：100 req/min per user（可配置）。
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        # 内存计数器: {user_key: [(timestamp, ...)]}
        self._windows: dict[str, list[float]] = {}
        self._window_seconds: float = 60.0  # 1 分钟窗口
        self._max_requests: int = settings.RATE_LIMIT_USER_RPM

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 跳过非业务请求
        if any(request.url.path.startswith(p) for p in _SKIP_PREFIXES):
            return await call_next(request)

        user_id = getattr(request.state, "user_id", None)
        client_ip = _get_client_ip(request)
        key = f"user:{user_id}" if user_id else f"ip:{client_ip}"

        if self._is_rate_limited(key):
            logger.warning("rate_limit_exceeded", key=key, path=request.url.path)
            raise RateLimitError(
                detail=f"超过 {self._max_requests} req/min 限制，请稍后再试"
            )

        self._record_request(key)
        return await call_next(request)

    def _is_rate_limited(self, key: str) -> bool:
        """检查是否超出速率限制（滑动窗口）。"""
        now = time.monotonic()
        cutoff = now - self._window_seconds

        window = self._windows.get(key, [])
        # 清理过期记录
        window = [t for t in window if t > cutoff]
        self._windows[key] = window

        return len(window) >= self._max_requests

    def _record_request(self, key: str) -> None:
        """记录一次请求。"""
        now = time.monotonic()
        if key not in self._windows:
            self._windows[key] = []
        self._windows[key].append(now)

        # 定期清理内存（简单策略：保留最近 1000 个 key）
        if len(self._windows) > 1000:
            # 删除最久未访问的 key
            oldest = min(self._windows.keys(), key=lambda k: self._windows[k][-1] if self._windows[k] else 0)
            del self._windows[oldest]


def _get_client_ip(request: Request) -> str:
    """提取客户端 IP"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = request.client
    if client:
        return client.host
    return "unknown"
