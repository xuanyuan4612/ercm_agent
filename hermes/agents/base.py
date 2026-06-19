"""
Stage Agent 基类

所有模块的 Stage Agent 继承此基类，遵守统一的输入输出契约。

生产约束：
- Stage Agent 只在对应阶段内生成结构化建议和证据引用
- 不直接修改业务终态，不绕过人工守门
- 模型调用必须经过 Model Gateway
- 检索必须经过 RAG Orchestrator

参照: doc/agents/00-agent-architecture.md §四
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from hermes.agents.llm_adapter import llm_adapter
from hermes.agents.profiles import ModuleAgentProfile
from hermes.agents.rag_engine import RAGOrchestrator
from hermes.core.logging import get_logger
from hermes.core.observability import observe

logger = get_logger(__name__)


class StageAgentInput(BaseModel):
    """Stage Agent 统一输入契约"""
    case_id: str = ""
    module: str = ""
    stage: str = ""
    workflow_thread_id: str = ""
    workflow_state_version: int = 0
    business_context: dict = {}
    human_modified_context: dict = {}
    evidence_refs: list[str] = []
    knowledge_scope: list[str] = []
    allowed_tools: list[str] = []
    tenant_scope: dict = {}
    schema_version: str = "1.0"
    trace_id: str = ""


class StageAgentOutput(BaseModel):
    """Stage Agent 统一输出契约"""
    stage_output: dict = {}
    conclusion: str = ""
    risk_level: str = "unknown"
    confidence: float = 0.0
    evidence_refs: list[str] = []
    knowledge_refs: list[str] = []
    uncertainties: list[str] = []
    recommended_actions: list[str] = []
    human_review_required: bool = True
    tool_calls: list[dict] = []
    model_usage: dict = {}


class BaseStageAgent(ABC):
    """Stage Agent 基类

    所有模块的 Stage Agent 必须继承此类并实现 run() 方法。

    子类需要定义:
        agent_id: str      — Agent 唯一标识
        agent_name: str    — Agent 显示名称
        module: str        — 所属模块
        stage: str         — 对应工作流阶段
        kb_types: list[str]— 使用的知识库类型列表
        role_description: str — 角色描述（用于 Prompt）
    """

    agent_id: str = ""
    agent_name: str = ""
    module: str = ""
    stage: str = ""
    kb_types: list[str] = []
    role_description: str = ""
    _prompt_version: str = "v1.0"

    def __init__(self, profile: ModuleAgentProfile | None = None) -> None:
        self.profile = profile
        self._rag_engine: RAGOrchestrator | None = None

    @abstractmethod
    async def run(self, **kwargs: Any) -> Any:
        """执行 Agent 推理

        子类必须实现此方法，返回结构化的阶段输出。
        """
        ...

    @observe(as_type="retriever", name="agent.knowledge_search")
    async def _search_kb(
        self,
        db_session,
        query: str,
        kb_types: list[str] | None = None,
        top_k: int = 5,
    ) -> list[dict]:
        """知识库检索（Langfuse 追踪：retriever span）"""
        if self._rag_engine is None:
            self._rag_engine = RAGOrchestrator(db_session)
        kb = kb_types or self.kb_types
        return await self._rag_engine.search(query, kb, top_k)

    async def _get_retrieval_context(
        self,
        db_session,
        query: str,
        kb_types: list[str] | None = None,
        top_k: int = 5,
    ) -> str:
        """获取格式化后的检索上下文"""
        if self._rag_engine is None:
            self._rag_engine = RAGOrchestrator(db_session)
        kb = kb_types or self.kb_types
        return await self._rag_engine._get_context_async(query, kb, top_k)

    @observe(as_type="generation", name="agent.llm_invoke")
    async def _invoke_llm(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        retries: int = 2,
    ) -> str:
        """调用 LLM（含重试和降级，Langfuse 追踪：generation span）"""
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                response = await llm_adapter.invoke(
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    trace_name=f"{self.agent_id}.{self.stage}",
                )
                return response
            except Exception as e:
                last_error = e
                logger.warning(
                    f"{self.agent_id}_llm_retry",
                    attempt=attempt + 1,
                    error=str(e),
                )
                if attempt < retries:
                    await self._sleep_backoff(attempt)

        raise last_error or RuntimeError(f"{self.agent_id}: LLM 调用全部失败")

    @staticmethod
    async def _sleep_backoff(attempt: int) -> None:
        """指数退避等待"""
        import asyncio
        delays = [2, 4]  # seconds
        delay = delays[attempt] if attempt < len(delays) else 4
        await asyncio.sleep(delay)

    @staticmethod
    def _elapsed_ms(start_time: float) -> int:
        """计算从 start_time 到现在的毫秒数"""
        return int((time.monotonic() - start_time) * 1000)

    def _build_output(
        self,
        stage_output: dict,
        conclusion: str = "",
        risk_level: str = "unknown",
        confidence: float = 0.0,
        **kwargs: Any,
    ) -> StageAgentOutput:
        """构建统一输出"""
        return StageAgentOutput(
            stage_output=stage_output,
            conclusion=conclusion,
            risk_level=risk_level,
            confidence=confidence,
            **kwargs,
        )
