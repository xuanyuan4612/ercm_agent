"""
问题确认 Agent (exit-issue-confirm-agent)

角色：离任审计问题确认专家
阶段：问题确认

核心任务：汇总反馈并判断问题成立性、责任归属和整改方向

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
    ExitIssueConfirmOutput,
    ExitIssueItem,
)

logger = get_logger(__name__)


class ExitIssueConfirmAgent(BaseStageAgent):
    """问题确认 Agent — 离任审计问题确认专家"""

    agent_id = "exit-issue-confirm-agent"
    agent_name = "问题确认 Agent"
    module = "exit_audit"
    stage = "issue_confirm"
    kb_types = ["ea_plan", "personal_risk_case", "business_audit_case", "common"]
    role_description = "离任审计问题确认专家，擅长判断问题责任归属和整改方向"

    def __init__(self) -> None:
        super().__init__()
        self._prompt_version = "v1.0"

    async def run(
        self,
        db_session,
        agent_input: ExitAuditAgentInput,
        draft_issues: list[dict] | None = None,
        feedback: list[dict] | None = None,
        supplementary_evidence: list[str] | None = None,
        kb_context: str = "",
    ) -> ExitIssueConfirmOutput:
        """确认离任审计问题"""
        start_time = time.monotonic()

        messages = [
            {"role": "system", "content": "你是离任审计问题确认专家。根据反馈和补充证据，确认每个问题的成立性和责任归属。"},
            {"role": "user", "content": json.dumps({
                "departing_person": agent_input.departing_person_name,
                "draft_issues": draft_issues or [],
                "feedback": feedback or [],
                "supplementary_evidence": supplementary_evidence or [],
                "kb_context": kb_context,
            }, ensure_ascii=False)},
        ]

        try:
            response = await self._invoke_llm(messages, temperature=0.3, max_tokens=4096)
            return self._parse_response(response, start_time)
        except Exception as e:
            logger.error("exit_confirm_failed", error=str(e))
            return ExitIssueConfirmOutput(
                confirmed_issues=[],
                confidence=Confidence.UNABLE,
                processing_time_ms=self._elapsed_ms(start_time),
            )

    def _parse_response(self, response: str, start_time: float) -> ExitIssueConfirmOutput:
        processing_time_ms = self._elapsed_ms(start_time)
        try:
            data = self._extract_json(response)
            return ExitIssueConfirmOutput(
                confirmed_issues=[ExitIssueItem(**i) for i in data.get("confirmed_issues", [])],
                issue_confirmations=data.get("issue_confirmations", []),
                responsibility_assessment=data.get("responsibility_assessment", {}),
                remediation_directions=data.get("remediation_directions", []),
                confidence=self._safe_confidence(data.get("confidence")),
                processing_time_ms=processing_time_ms,
            )
        except Exception as e:
            logger.warning("exit_confirm_parse_failed", error=str(e))
            return ExitIssueConfirmOutput(
                confirmed_issues=[],
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
