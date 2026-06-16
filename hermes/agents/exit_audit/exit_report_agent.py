"""
离任审计报告 Agent (exit-report-agent)

角色：离任审计报告撰写师
阶段：出具报告

核心任务：生成离任审计报告初稿和问题汇总

参照: doc/agents/05-exit-audit-agents.md
"""

from __future__ import annotations

import json
import time
from typing import Any

from hermes.agents.base import BaseStageAgent
from hermes.core.logging import get_logger
from hermes.schemas.agents.common import Confidence
from hermes.schemas.agents.exit_audit import (
    ExitAuditAgentInput,
    ExitReportAgentOutput,
)

logger = get_logger(__name__)


class ExitReportAgent(BaseStageAgent):
    """离任审计报告 Agent — 离任审计报告撰写师"""

    agent_id = "exit-report-agent"
    agent_name = "离任审计报告 Agent"
    module = "exit_audit"
    stage = "exit_report"
    kb_types = ["ea_plan", "personal_risk_case", "business_audit_case", "common"]
    role_description = "离任审计报告撰写师，擅长撰写客观、全面的离任审计报告"

    def __init__(self) -> None:
        super().__init__()
        self._prompt_version = "v1.0"

    async def run(
        self,
        db_session,
        agent_input: ExitAuditAgentInput,
        confirmed_issues: list[dict] | None = None,
        kb_context: str = "",
    ) -> ExitReportAgentOutput:
        """生成离任审计报告"""
        start_time = time.monotonic()

        messages = [
            {"role": "system", "content": "你是离任审计报告撰写师。根据确认的问题和审计资料，生成离任审计报告初稿。"},
            {"role": "user", "content": json.dumps({
                "departing_person": {
                    "name": agent_input.departing_person_name,
                    "position": agent_input.position,
                    "department": agent_input.department,
                    "tenure_years": agent_input.tenure_years,
                    "audit_period_years": agent_input.audit_period_years,
                },
                "confirmed_issues": confirmed_issues or [],
                "kb_context": kb_context,
            }, ensure_ascii=False)},
        ]

        try:
            response = await self._invoke_llm(messages, temperature=0.3, max_tokens=4096)
            return self._parse_response(response, start_time)
        except Exception as e:
            logger.error("exit_report_failed", error=str(e))
            return ExitReportAgentOutput(
                report_title="离任审计报告生成失败",
                confidence=Confidence.UNABLE,
                processing_time_ms=self._elapsed_ms(start_time),
            )

    def _parse_response(self, response: str, start_time: float) -> ExitReportAgentOutput:
        processing_time_ms = self._elapsed_ms(start_time)
        try:
            data = self._extract_json(response)
            return ExitReportAgentOutput(
                report_title=data.get("report_title", ""),
                personal_issue_summary=data.get("personal_issue_summary", ""),
                business_issue_summary=data.get("business_issue_summary", ""),
                overall_assessment=data.get("overall_assessment", ""),
                report_doc_id=data.get("report_doc_id"),
                confidence=self._safe_confidence(data.get("confidence")),
                processing_time_ms=processing_time_ms,
            )
        except Exception as e:
            logger.warning("exit_report_parse_failed", error=str(e))
            return ExitReportAgentOutput(
                report_title="报告解析失败",
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
