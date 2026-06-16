"""
专项审计报告 Agent (special-audit-report-agent)

角色：审计报告撰写师
阶段：出具报告

核心任务：生成审计报告初稿、整改建议和问题清单摘要

参照: doc/agents/04-special-audit-agents.md
"""

from __future__ import annotations

import json
import time
from typing import Any

from hermes.agents.base import BaseStageAgent
from hermes.core.logging import get_logger
from hermes.schemas.agents.common import Confidence
from hermes.schemas.agents.special_audit import (
    SpecialAuditReportInput,
    SpecialAuditReportOutput,
)

logger = get_logger(__name__)


class SpecialAuditReportAgent(BaseStageAgent):
    """专项审计报告 Agent — 审计报告撰写师"""

    agent_id = "special-audit-report-agent"
    agent_name = "专项审计报告 Agent"
    module = "special_audit"
    stage = "audit_report"
    kb_types = ["sa_history", "audit_plan", "improvement_suggestion", "common"]
    role_description = "审计报告撰写师，擅长撰写结构严谨、结论清晰的审计报告"

    def __init__(self) -> None:
        super().__init__()
        self._prompt_version = "v1.0"

    async def run(
        self,
        db_session,
        report_input: SpecialAuditReportInput,
        kb_context: str = "",
    ) -> SpecialAuditReportOutput:
        """生成专项审计报告"""
        start_time = time.monotonic()

        messages = [
            {"role": "system", "content": "你是审计报告撰写师。根据已确认的审计问题和工作底稿，生成审计报告初稿。"},
            {"role": "user", "content": json.dumps({
                "audit_objective": report_input.audit_objective,
                "confirmed_issues": [i.model_dump() for i in report_input.confirmed_issues],
                "audit_plan_summary": report_input.audit_plan_summary,
                "project_info": report_input.project_info,
                "kb_context": kb_context,
            }, ensure_ascii=False)},
        ]

        try:
            response = await self._invoke_llm(messages, temperature=0.3, max_tokens=8192)
            return self._parse_response(response, start_time)
        except Exception as e:
            logger.error("audit_report_failed", error=str(e))
            return SpecialAuditReportOutput(
                report_title="审计报告生成失败",
                report_content={"error": str(e)[:200]},
                confidence=Confidence.UNABLE,
                processing_time_ms=self._elapsed_ms(start_time),
            )

    def _parse_response(self, response: str, start_time: float) -> SpecialAuditReportOutput:
        processing_time_ms = self._elapsed_ms(start_time)
        try:
            data = self._extract_json(response)
            return SpecialAuditReportOutput(
                report_title=data.get("report_title", ""),
                report_content=data.get("report_content", {}),
                issue_summary_list=data.get("issue_summary_list", []),
                remediation_suggestions=data.get("remediation_suggestions", []),
                report_doc_id=data.get("report_doc_id"),
                confidence=self._safe_confidence(data.get("confidence")),
                processing_time_ms=processing_time_ms,
            )
        except Exception as e:
            logger.warning("audit_report_parse_failed", error=str(e))
            return SpecialAuditReportOutput(
                report_title="报告解析失败",
                report_content={},
                confidence=Confidence.LOW,
                processing_time_ms=processing_time_ms,
            )

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
