"""
问题确认 Agent (special-issue-confirm-agent)

角色：审计问题确认专家
阶段：问题确认

核心任务：汇总被审计单位反馈，判断问题是否成立、证据是否充分、整改建议是否合理

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
    ConfirmedIssue,
    SpecialIssueConfirmInput,
    SpecialIssueConfirmOutput,
)

logger = get_logger(__name__)


class SpecialIssueConfirmAgent(BaseStageAgent):
    """问题确认 Agent — 审计问题确认专家"""

    agent_id = "special-issue-confirm-agent"
    agent_name = "问题确认 Agent"
    module = "special_audit"
    stage = "issue_confirm"
    kb_types = ["sa_history", "audit_plan", "improvement_suggestion", "common"]
    role_description = "审计问题确认专家，擅长判断审计问题是否成立及其证据充分性"

    def __init__(self) -> None:
        super().__init__()
        self._prompt_version = "v1.0"

    async def run(
        self,
        db_session,
        confirm_input: SpecialIssueConfirmInput,
        kb_context: str = "",
    ) -> SpecialIssueConfirmOutput:
        """执行问题确认"""
        start_time = time.monotonic()

        messages = [
            {"role": "system", "content": "你是审计问题确认专家。根据被审计单位反馈和证据，判断每个问题是否成立。"},
            {"role": "user", "content": json.dumps({
                "issue_drafts": confirm_input.issue_drafts,
                "auditee_feedback": confirm_input.auditee_feedback,
                "supplementary_evidence": confirm_input.supplementary_evidence,
                "policy_basis": confirm_input.policy_basis,
                "kb_context": kb_context,
            }, ensure_ascii=False)},
        ]

        try:
            response = await self._invoke_llm(messages, temperature=0.3, max_tokens=4096)
            return self._parse_response(response, start_time)
        except Exception as e:
            logger.error("issue_confirm_failed", error=str(e))
            return SpecialIssueConfirmOutput(
                confirmed_issues=[],
                rejected_issues=[],
                uncertain_issues=[],
                adjustment_summary=f"问题确认失败: {str(e)[:200]}",
                confidence=Confidence.UNABLE,
                processing_time_ms=self._elapsed_ms(start_time),
            )

    def _parse_response(self, response: str, start_time: float) -> SpecialIssueConfirmOutput:
        processing_time_ms = self._elapsed_ms(start_time)
        try:
            data = self._extract_json(response)
            confirmed = [ConfirmedIssue(**c) for c in data.get("confirmed_issues", [])]

            return SpecialIssueConfirmOutput(
                confirmed_issues=confirmed,
                rejected_issues=data.get("rejected_issues", []),
                uncertain_issues=data.get("uncertain_issues", []),
                adjustment_summary=data.get("adjustment_summary", ""),
                confidence=self._safe_confidence(data.get("confidence")),
                processing_time_ms=processing_time_ms,
            )
        except Exception as e:
            logger.warning("issue_confirm_parse_failed", error=str(e))
            return SpecialIssueConfirmOutput(
                confirmed_issues=[],
                rejected_issues=[],
                uncertain_issues=[],
                adjustment_summary="JSON解析失败",
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
