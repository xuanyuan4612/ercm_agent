"""
工具系统

Agent 可用的工具集合：
- kb_search: 知识库检索
- es_search: Elasticsearch 全文检索
- audio_transcribe_query: 查询已完成语音转文字结果
- doc_generate: Word/Excel 文档生成 (Celery 异步)
- a2a_send: 发送 A2A 任务到外部智能体 (Celery 异步)
- sql_analyze: 业务数据 SQL 查询分析 (Celery 异步)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from hermes.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class Tool:
    """工具定义"""

    name: str
    description: str
    func: Callable
    parameters: dict[str, Any] = field(default_factory=dict)
    is_async: bool = False  # True = 异步任务，返回 task_id


class ToolRegistry:
    """工具注册中心

    每个 Agent 注册自己需要的工具集合。
    按使用频率和延迟特性分级管理。
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool
        logger.info("tool_registered", name=tool.name, is_async=tool.is_async)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[dict[str, Any]]:
        """返回工具列表描述（用于 LLM function calling）"""
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            }
            for t in self._tools.values()
        ]

    async def execute(self, name: str, **kwargs: Any) -> Any:
        """执行工具调用"""
        tool = self._tools.get(name)
        if not tool:
            raise ValueError(f"Tool '{name}' not found in registry")
        try:
            if tool.is_async:
                # 异步工具：返回 task_id，由 Celery 后台执行
                result = await tool.func(**kwargs)
                return {"task_id": result.get("task_id"), "status": "queued"}
            result = await tool.func(**kwargs) if asyncio_iscoroutine(tool.func) else tool.func(**kwargs)
            return result
        except Exception as e:
            logger.error("tool_execution_failed", name=name, error=str(e))
            raise


def asyncio_iscoroutine(fn: Callable) -> bool:
    import asyncio
    return asyncio.iscoroutinefunction(fn)


# 全局工具注册中心
tool_registry = ToolRegistry()
