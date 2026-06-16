"""
问题清单 Agent (exit-issue-agent)

角色：离任审计问题识别专家
阶段：问题清单生成

核心任务：
  1. 识别个人问题（商业秘密泄露、个人报销、样机使用、关联公司）
  2. 识别业务问题（流程漏洞、制度缺陷、经济损失）
  3. 生成双轨问题清单和证据链

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
    ExitIssueAgentOutput,
    ExitIssueItem,
)

logger = get_logger(__name__)


class ExitIssueAgent(BaseStageAgent):
    """问题清单 Agent — 离任审计问题识别专家"""

    agent_id = "exit-issue-agent"
    agent_name = "问题清单 Agent"
    module = "exit_audit"
    stage = "issue_list"
    kb_types = ["ea_plan", "personal_risk_case", "business_audit_case", "behavioral_risk_history", "common"]
    role_description = "离任审计问题识别专家，擅长区分个人问题与业务问题"

    def __init__(self) -> None:
        super().__init__()
        self._prompt_version = "v1.0"

    async def run(
        self,
        db_session,
        agent_input: ExitAuditAgentInput,
        materials: list[dict] | None = None,
        interview_summaries: list[dict] | None = None,
        behavioral_warnings: list[dict] | None = None,
        tianyancha_relations: list[dict] | None = None,
        kb_context: str = "",
    ) -> ExitIssueAgentOutput:
        """生成离任审计问题清单"""
        start_time = time.monotonic()

        messages = [
            {"role": "system", "content": (
                "你是离任审计问题识别专家。根据被审计人的岗位职责、任职期间、收集的资料、访谈纪要和风险预警，"
                "识别个人问题和业务问题。个人问题包括：商业秘密泄露、个人报销违规、样机私用、关联公司利益冲突。"
                "业务问题包括：流程漏洞、制度缺陷、经济损失。"
            )},
            {"role": "user", "content": json.dumps({
                "departing_person": {
                    "name": agent_input.departing_person_name,
                    "position": agent_input.position,
                    "department": agent_input.department,
                    "tenure_years": agent_input.tenure_years,
                    "audit_period_years": agent_input.audit_period_years,
                },
                "position_duties": agent_input.position_duties,
                "materials": materials or [],
                "interview_summaries": interview_summaries or [],
                "behavioral_warnings": behavioral_warnings or [],
                "tianyancha_relations": tianyancha_relations or [],
                "kb_context": kb_context,
            }, ensure_ascii=False)},
        ]

        try:
            response = await self._invoke_llm(messages, temperature=0.3, max_tokens=4096)
            return self._parse_response(response, start_time)
        except Exception as e:
            logger.error("exit_issue_failed", error=str(e))
            return ExitIssueAgentOutput(
                personal_issues=[],
                business_issues=[],
                confidence=Confidence.UNABLE,
                processing_time_ms=self._elapsed_ms(start_time),
            )

    def _parse_response(self, response: str, start_time: float) -> ExitIssueAgentOutput:
        processing_time_ms = self._elapsed_ms(start_time)
        try:
            data = self._extract_json(response)
            personal = [ExitIssueItem(**i) for i in data.get("personal_issues", [])]
            business = [ExitIssueItem(**i) for i in data.get("business_issues", [])]

            return ExitIssueAgentOutput(
                personal_issues=personal,
                business_issues=business,
                total_personal_issue_count=len(personal),
                total_business_issue_count=len(business),
                audit_opinion_table=data.get("audit_opinion_table", {}),
                confidence=self._safe_confidence(data.get("confidence")),
                processing_time_ms=processing_time_ms,
            )
        except Exception as e:
            logger.warning("exit_issue_parse_failed", error=str(e))
            return ExitIssueAgentOutput(
                personal_issues=[],
                business_issues=[],
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
