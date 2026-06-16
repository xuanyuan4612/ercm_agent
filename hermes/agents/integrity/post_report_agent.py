"""
报案协助 Agent (post-report-agent)

角色：报案协助专家
阶段：[4.6] 报案后续协助

核心任务：
  1. 整理报案所需材料清单
  2. 生成报案书草稿（或补充）
  3. 提供报案后续协助建议（证据补充、司法鉴定、律师对接等）

参照: doc/agents/01-integrity-supervision-agents.md
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Optional

from hermes.agents.integrity.schemas import (
    Client,
    Confidence,
    PostReportInput,
    PostReportOutput,
)
from hermes.agents.llm_adapter import llm_adapter
from hermes.agents.prompt_manager import prompt_manager
from hermes.core.exceptions import AIServiceUnavailableError
from hermes.core.logging import get_logger

logger = get_logger(__name__)


class PostReportAgent:
    """报案协助 Agent — 报案后续协助专家

    职责：
    1. 整理刑事报案所需材料清单
    2. 生成或补充报案书草稿
    3. 提供后续协助建议（证据补充、司法鉴定、律师对接等）

    降级：
    - LLM 不可用 → 返回骨架输出，建议人工准备报案材料
    """

    def __init__(self) -> None:
        self.agent_id = "post-report-agent"
        self.agent_name = "报案协助 Agent"
        self.role = "报案协助专家"
        self.kb_types = ["disposition", "common", "law_and_regulation"]
        self._prompt_version = "v1.0"

    async def run(
        self,
        post_input: PostReportInput,
        kb_context: str = "",
    ) -> PostReportOutput:
        """执行报案协助分析

        Args:
            post_input: 报案协助输入
            kb_context: 知识库检索上下文

        Returns:
            PostReportOutput: 结构化输出
        """
        start_time = time.monotonic()

        # 构建 Prompt
        prompt_text = prompt_manager.render(
            module="integrity",
            stage="post_report",
            variables={
                "task_id": post_input.task_id,
                "case_conclusion": json.dumps(post_input.case_conclusion, ensure_ascii=False),
                "disposition_path": post_input.disposition_path.value,
                "kb_context": kb_context or "（无相关知识库检索结果）",
            },
        )

        messages = self._parse_prompt_to_messages(prompt_text)

        retry_count = 0
        last_error: Optional[Exception] = None

        for attempt in range(3):
            try:
                response = await llm_adapter.invoke(
                    messages,
                    temperature=0.3,
                    max_tokens=4096,
                )
                return self._parse_response(response, post_input.task_id, start_time, retry_count)
            except AIServiceUnavailableError as e:
                last_error = e
                retry_count = attempt
                logger.warning("post_report_llm_retry", attempt=attempt + 1, error=str(e))
                if attempt < 2:
                    await self._sleep_backoff(attempt)
            except Exception as e:
                last_error = e
                logger.error("post_report_unexpected_error", error=str(e))
                break

        logger.error("post_report_all_llm_failed", task_id=post_input.task_id, error=str(last_error))
        return self._fallback_output(post_input.task_id, start_time, str(last_error))

    def _parse_response(
        self,
        response: str,
        task_id: str,
        start_time: float,
        retry_count: int,
    ) -> PostReportOutput:
        """解析 LLM 响应为结构化输出"""
        processing_time_ms = int((time.monotonic() - start_time) * 1000)

        try:
            data = self._extract_json(response)
            return PostReportOutput(
                material_checklist=data.get("material_checklist", []),
                prosecution_letter=data.get("prosecution_letter", ""),
                follow_up_suggestions=data.get("follow_up_suggestions", []),
                evidence_supplement_needed=data.get("evidence_supplement_needed", False),
                evidence_supplement_items=data.get("evidence_supplement_items", []),
                forensic_identification_needed=data.get("forensic_identification_needed", False),
                estimated_timeline=data.get("estimated_timeline", ""),
                legal_counsel_recommendation=data.get("legal_counsel_recommendation", ""),
                confidence=self._safe_confidence(data.get("confidence")),
                confidence_reason=data.get("confidence_reason", ""),
                processing_time_ms=processing_time_ms,
                kb_sources=data.get("kb_sources", []),
                retry_count=retry_count,
            )
        except Exception as parse_err:
            logger.warning("post_report_json_parse_failed", error=str(parse_err), task_id=task_id)
            return PostReportOutput(
                material_checklist=[],
                prosecution_letter="（JSON 解析失败，以下为原始输出摘要）\n" + response[:1000],
                follow_up_suggestions=["需人工审核原始输出"],
                confidence=Confidence.LOW,
                confidence_reason="LLM 输出格式异常，已降级解析",
                processing_time_ms=processing_time_ms,
                retry_count=retry_count,
            )

    def _fallback_output(
        self, task_id: str, start_time: float, error_msg: str
    ) -> PostReportOutput:
        """LLM 完全不可用时的降级输出"""
        return PostReportOutput(
            material_checklist=[
                "报案书（含案件事实、证据摘要、法律适用）",
                "涉案金额统计表",
                "关键证据复印件/副本",
                "涉案人员身份信息",
                "公司营业执照副本",
                "授权委托书",
            ],
            prosecution_letter="（AI 服务暂时不可用，建议人工撰写报案书）",
            follow_up_suggestions=[
                "人工准备报案材料",
                "联系法务部门确认报案策略",
                "确认管辖公安机关",
            ],
            evidence_supplement_needed=True,
            evidence_supplement_items=["需人工补充完整证据链"],
            confidence=Confidence.UNABLE,
            confidence_reason=f"LLM 调用全部失败: {error_msg[:200]}",
            processing_time_ms=int((time.monotonic() - start_time) * 1000),
        )

    # ── 辅助方法 ──
    @staticmethod
    def _parse_prompt_to_messages(prompt_text: str) -> list[dict]:
        if "[System]" in prompt_text and "[User]" in prompt_text:
            system_part = prompt_text.split("[User]")[0].replace("[System]\n", "").strip()
            user_part = prompt_text.split("[User]")[1].strip()
            return [
                {"role": "system", "content": system_part},
                {"role": "user", "content": user_part},
            ]
        return [
            {"role": "system", "content": "你是赫尔墨斯风控系统的报案协助专家。"},
            {"role": "user", "content": prompt_text},
        ]

    @staticmethod
    def _extract_json(text: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:]) if len(lines) > 1 else text
            if text.endswith("```"):
                text = text[:-3]
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        raise ValueError("No JSON found in response")

    @staticmethod
    def _safe_confidence(value: Any) -> Confidence:
        if isinstance(value, Confidence):
            return value
        mapping = {"high": Confidence.HIGH, "medium": Confidence.MEDIUM, "low": Confidence.LOW, "unable": Confidence.UNABLE}
        return mapping.get(str(value).lower(), Confidence.MEDIUM)

    @staticmethod
    async def _sleep_backoff(attempt: int) -> None:
        import asyncio
        delays = [2, 4]
        delay = delays[attempt] if attempt < len(delays) else 4
        await asyncio.sleep(delay)
