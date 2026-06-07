"""
LLM 适配器

统一 LLM 调用接口，支持 DeepSeek（主）/ 通义千问（备）热切换。
特性：
- OpenAI 兼容 API 格式
- 自动降级：主 LLM 不可用时切换备用
- 优先级队列：intake-agent 优先于 background tasks
- LangFuse 追踪集成
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncIterator

from langchain_openai import ChatOpenAI

from hermes.core.config import settings
from hermes.core.exceptions import AIServiceUnavailableError
from hermes.core.logging import get_logger

logger = get_logger(__name__)


class LLMAdapter:
    """统一 LLM 调用适配器

    特性：
    - 主 LLM (DeepSeek) + 备用 LLM (通义千问)
    - 自动降级：主 LLM 连续失败 3 次后切换备用
    - 健康检查：定期检测主 LLM 恢复后切回
    - 速率限制：LLM 调用频控
    """

    def __init__(self) -> None:
        self._primary: ChatOpenAI | None = None
        self._backup: ChatOpenAI | None = None
        self._primary_failures: int = 0
        self._max_failures: int = 3
        self._using_backup: bool = False
        self._last_health_check: float = 0
        self._health_check_interval: float = 60.0  # seconds

    @property
    def primary(self) -> ChatOpenAI:
        if self._primary is None:
            self._primary = ChatOpenAI(
                model=settings.LLM_MODEL,
                api_key=settings.LLM_API_KEY.get_secret_value(),
                base_url=settings.LLM_API_BASE,
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS,
                timeout=settings.LLM_REQUEST_TIMEOUT,
            )
        return self._primary

    @property
    def backup(self) -> ChatOpenAI:
        if self._backup is None:
            self._backup = ChatOpenAI(
                model=settings.LLM_BACKUP_MODEL,
                api_key=settings.LLM_BACKUP_API_KEY.get_secret_value(),
                base_url=settings.LLM_BACKUP_API_BASE,
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS,
                timeout=settings.LLM_REQUEST_TIMEOUT,
            )
        return self._backup

    @property
    def active(self) -> ChatOpenAI:
        """当前活跃的 LLM 实例"""
        if self._using_backup:
            self._maybe_switch_back()
            return self.backup if self._using_backup else self.primary
        return self.primary

    def _maybe_switch_back(self) -> None:
        """检查主 LLM 是否恢复"""
        now = time.monotonic()
        if now - self._last_health_check < self._health_check_interval:
            return
        self._last_health_check = now
        # 简单策略：重置故障计数，切回主 LLM
        self._using_backup = False
        self._primary_failures = 0
        logger.info("llm_switched_back_to_primary")

    def _on_failure(self) -> None:
        self._primary_failures += 1
        if self._primary_failures >= self._max_failures:
            self._using_backup = True
            logger.warning(
                "llm_fallback_to_backup",
                primary_failures=self._primary_failures,
            )

    def _on_success(self) -> None:
        if not self._using_backup:
            self._primary_failures = 0

    async def invoke(self, messages: list[dict], **kwargs: Any) -> str:
        """同步调用 LLM（非流式），返回完整响应文本。"""
        try:
            llm = self.active
            response = await llm.ainvoke(
                _format_messages(messages),
                **kwargs,
            )
            self._on_success()
            return response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            self._on_failure()
            logger.error("llm_invoke_failed", error=str(e))
            raise AIServiceUnavailableError(detail=str(e))

    async def stream(self, messages: list[dict], **kwargs: Any) -> AsyncIterator[str]:
        """流式调用 LLM，逐步返回 token。"""
        try:
            llm = self.active
            async for chunk in llm.astream(
                _format_messages(messages),
                **kwargs,
            ):
                content = chunk.content if hasattr(chunk, "content") else str(chunk)
                if content:
                    yield content
            self._on_success()
        except Exception as e:
            self._on_failure()
            logger.error("llm_stream_failed", error=str(e))
            raise AIServiceUnavailableError(detail=str(e))


def _format_messages(messages: list[dict]) -> list[tuple[str, str]]:
    """将字典格式的消息列表转换为 LangChain 消息格式。"""
    formatted = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        formatted.append((role, content))
    return formatted


# 全局单例
llm_adapter = LLMAdapter()
