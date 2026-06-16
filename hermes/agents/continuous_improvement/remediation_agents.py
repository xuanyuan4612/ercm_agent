"""
持续改善模块 — Agent 实现

Agent:
  improvement-issue-ingest-agent    — 问题录入校验
  rectification-plan-review-agent   — 整改计划初审
  rectification-evidence-review-agent — 整改证据复核
  reminder-escalation-agent          — 催办升级建议
  closure-acceptance-agent           — 关闭验收
  improvement-knowledge-agent        — 经验沉淀

统一问题数据契约: RemediationIssueRecord (36字段)

参照: doc/agents/08-continuous-improvement-agents.md
"""

from __future__ import annotations

import json
import time
from typing import Any

from hermes.agents.base import BaseStageAgent
from hermes.core.logging import get_logger
from hermes.schemas.agents.common import Confidence
from hermes.schemas.agents.continuous_improvement import (
    ClosureAcceptanceOutput,
    EvidenceReviewOutput,
    IssueIngestOutput,
    KnowledgePrecipitationOutput,
    PlanReviewOutput,
    RemediationAgentInput,
    RemediationAgentOutput,
    RemediationOperation,
    ReminderEscalationOutput,
)

logger = get_logger(__name__)


class ImprovementIssueIngestAgent(BaseStageAgent):
    """问题录入校验 Agent — 校验上游问题字段完整性、去重、责任归属"""

    agent_id = "improvement-issue-ingest-agent"
    agent_name = "问题录入校验 Agent"
    module = "continuous_improvement"
    stage = "issue_ingest"
    kb_types = ["improvement_case", "audit_issue_history", "common"]
    role_description = "整改问题管理专家，擅长校验问题数据完整性和去重"

    async def run(
        self,
        db_session,
        issues: list[dict],
        kb_context: str = "",
    ) -> IssueIngestOutput:
        """校验问题数据"""
        start_time = time.monotonic()

        messages = [
            {"role": "system", "content": (
                "你是整改问题管理专家。校验上游推送的问题清单：字段完整性、是否存在重复问题、"
                "责任部门是否明确、证据引用是否充分。来源不明或证据缺失的问题必须标记为阻断下发。"
            )},
            {"role": "user", "content": json.dumps({
                "issues": issues,
                "kb_context": kb_context,
            }, ensure_ascii=False)},
        ]

        try:
            response = await self._invoke_llm(messages, temperature=0.2, max_tokens=4096)
            data = self._extract_json(response)
            return IssueIngestOutput(
                field_issues=data.get("field_issues", []),
                duplicate_issues=data.get("duplicate_issues", []),
                completeness_score=data.get("completeness_score", 0.0),
                suggested_responsibility=data.get("suggested_responsibility", {}),
                missing_items=data.get("missing_items", []),
                can_dispatch=data.get("can_dispatch", True),
                blocking_reasons=data.get("blocking_reasons", []),
                confidence=self._safe_confidence(data.get("confidence")),
            )
        except Exception as e:
            logger.error("issue_ingest_failed", error=str(e))
            return IssueIngestOutput(
                can_dispatch=False,
                blocking_reasons=[f"问题校验失败: {str(e)[:200]}"],
                confidence=Confidence.UNABLE,
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


class RectificationPlanReviewAgent(BaseStageAgent):
    """整改计划初审 Agent — 初审整改计划合理性"""

    agent_id = "rectification-plan-review-agent"
    agent_name = "整改计划初审 Agent"
    module = "continuous_improvement"
    stage = "plan_review"
    kb_types = ["improvement_case", "rectification_template", "policy_and_process", "common"]
    role_description = "整改督导员，擅长判断整改计划是否对准问题根因"

    async def run(
        self,
        db_session,
        agent_input: RemediationAgentInput,
        kb_context: str = "",
    ) -> RemediationAgentOutput:
        """初审整改计划"""
        start_time = time.monotonic()

        messages = [
            {"role": "system", "content": (
                "你是整改督导员。初审整改计划是否对准问题根因、措施是否可执行、时间是否合理。"
                "措施必须对应问题根因和验收标准，否则标记为待修改。"
            )},
            {"role": "user", "content": json.dumps({
                "issue_data": agent_input.issue_data,
                "remediation_plan": agent_input.remediation_plan,
                "plan_deadline": agent_input.plan_deadline,
                "previous_review_count": agent_input.previous_review_count,
                "kb_context": kb_context,
            }, ensure_ascii=False)},
        ]

        try:
            response = await self._invoke_llm(messages, temperature=0.2, max_tokens=4096)
            data = self._extract_json(response)
            return RemediationAgentOutput(
                ai_plan_review=data.get("ai_plan_review"),
                suggested_actions=data.get("suggested_actions", []),
                escalation_needed=agent_input.previous_review_count >= 3,
                confidence=self._safe_confidence(data.get("confidence")),
                processing_time_ms=self._elapsed_ms(start_time),
            )
        except Exception as e:
            logger.error("plan_review_failed", error=str(e))
            return RemediationAgentOutput(
                confidence=Confidence.UNABLE,
                processing_time_ms=self._elapsed_ms(start_time),
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


class RectificationEvidenceReviewAgent(BaseStageAgent):
    """整改证据复核 Agent — 初审整改证据真实性和完整性"""

    agent_id = "rectification-evidence-review-agent"
    agent_name = "整改证据复核 Agent"
    module = "continuous_improvement"
    stage = "evidence_review"
    kb_types = ["improvement_case", "rectification_template", "policy_and_process", "common"]
    role_description = "整改证据审查专家，擅长判断整改证据与计划的一致性"

    async def run(
        self,
        db_session,
        agent_input: RemediationAgentInput,
        kb_context: str = "",
    ) -> RemediationAgentOutput:
        """复核整改证据"""
        start_time = time.monotonic()

        messages = [
            {"role": "system", "content": (
                "你是整改证据审查专家。初审整改证据的真实性、完整性、前后对比和闭环充分性。"
                "证据不足必须输出退回重改建议和待补充材料清单。返回退回原因时需明确哪些要求未满足。"
            )},
            {"role": "user", "content": json.dumps({
                "issue_data": agent_input.issue_data,
                "remediation_plan": agent_input.remediation_plan,
                "evidence": agent_input.remediation_evidence,
                "kb_context": kb_context,
            }, ensure_ascii=False)},
        ]

        try:
            response = await self._invoke_llm(messages, temperature=0.2, max_tokens=4096)
            data = self._extract_json(response)
            return RemediationAgentOutput(
                ai_evidence_review=data.get("ai_evidence_review"),
                suggested_actions=data.get("suggested_actions", []),
                confidence=self._safe_confidence(data.get("confidence")),
                processing_time_ms=self._elapsed_ms(start_time),
            )
        except Exception as e:
            logger.error("evidence_review_failed", error=str(e))
            return RemediationAgentOutput(
                confidence=Confidence.UNABLE,
                processing_time_ms=self._elapsed_ms(start_time),
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


class ReminderEscalationAgent(BaseStageAgent):
    """催办升级建议 Agent — 生成催办话术和升级风险提示"""

    agent_id = "reminder-escalation-agent"
    agent_name = "催办升级建议 Agent"
    module = "continuous_improvement"
    stage = "reminder_escalation"
    kb_types = ["improvement_case", "common"]
    role_description = "整改催办协调员，擅长风险评估和升级决策"

    async def run(
        self,
        db_session,
        agent_input: RemediationAgentInput,
        kb_context: str = "",
    ) -> RemediationAgentOutput:
        """生成催办升级建议"""
        start_time = time.monotonic()

        messages = [
            {"role": "system", "content": (
                "你是整改催办协调员。根据逾期状态和风险等级，生成催办话术和升级路径建议。"
                "Agent只能生成文案和建议，不能直接发送高风险升级通知。"
            )},
            {"role": "user", "content": json.dumps({
                "issue_data": agent_input.issue_data,
                "plan_deadline": agent_input.plan_deadline,
                "previous_review_count": agent_input.previous_review_count,
                "kb_context": kb_context,
            }, ensure_ascii=False)},
        ]

        try:
            response = await self._invoke_llm(messages, temperature=0.3, max_tokens=2048)
            data = self._extract_json(response)
            return RemediationAgentOutput(
                suggested_actions=data.get("suggested_actions", []),
                overdue_risk=data.get("overdue_risk", False),
                overdue_days=data.get("overdue_days"),
                escalation_needed=data.get("escalation_needed", False),
                confidence=self._safe_confidence(data.get("confidence")),
                processing_time_ms=self._elapsed_ms(start_time),
            )
        except Exception as e:
            logger.error("reminder_failed", error=str(e))
            return RemediationAgentOutput(
                confidence=Confidence.UNABLE,
                processing_time_ms=self._elapsed_ms(start_time),
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


class ClosureAcceptanceAgent(BaseStageAgent):
    """关闭验收 Agent — 汇总计划+证据+复核记录，建议是否允许关闭"""

    agent_id = "closure-acceptance-agent"
    agent_name = "关闭验收 Agent"
    module = "continuous_improvement"
    stage = "closure_acceptance"
    kb_types = ["improvement_case", "rectification_template", "common"]
    role_description = "整改验收专家，擅长判断整改是否真正闭环"

    async def run(
        self,
        db_session,
        agent_input: RemediationAgentInput,
        review_history: list[dict] | None = None,
        kb_context: str = "",
    ) -> RemediationAgentOutput:
        """关闭验收"""
        start_time = time.monotonic()

        messages = [
            {"role": "system", "content": (
                "你是整改验收专家。汇总整改计划、证据、复核记录和整改效果，建议是否允许关闭。"
                "关闭必须由审计跟进人确认。你只能建议关闭或建议保留风险。"
            )},
            {"role": "user", "content": json.dumps({
                "issue_data": agent_input.issue_data,
                "remediation_plan": agent_input.remediation_plan,
                "review_history": review_history or [],
                "kb_context": kb_context,
            }, ensure_ascii=False)},
        ]

        try:
            response = await self._invoke_llm(messages, temperature=0.2, max_tokens=4096)
            data = self._extract_json(response)
            return RemediationAgentOutput(
                ai_plan_review=data.get("acceptance_summary"),
                suggested_actions=data.get("suggested_actions", []),
                confidence=self._safe_confidence(data.get("confidence")),
                processing_time_ms=self._elapsed_ms(start_time),
            )
        except Exception as e:
            logger.error("closure_acceptance_failed", error=str(e))
            return RemediationAgentOutput(
                confidence=Confidence.UNABLE,
                processing_time_ms=self._elapsed_ms(start_time),
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


class ImprovementKnowledgeAgent(BaseStageAgent):
    """经验沉淀 Agent — 从已闭环问题中抽取知识库候选条目"""

    agent_id = "improvement-knowledge-agent"
    agent_name = "经验沉淀 Agent"
    module = "continuous_improvement"
    stage = "knowledge_precipitation"
    kb_types = ["improvement_case", "audit_issue_history", "policy_and_process", "common"]
    role_description = "知识管理专家，擅长从案例中提炼通用规则和最佳实践"

    async def run(
        self,
        db_session,
        closed_issues: list[dict],
        kb_context: str = "",
    ) -> KnowledgePrecipitationOutput:
        """经验沉淀"""
        start_time = time.monotonic()

        messages = [
            {"role": "system", "content": (
                "你是知识管理专家。从已闭环整改问题中抽取制度缺陷、流程改进点、"
                "相似问题标签和知识库候选条目。入库必须经过业务owner审核。"
            )},
            {"role": "user", "content": json.dumps({
                "closed_issues": closed_issues,
                "kb_context": kb_context,
            }, ensure_ascii=False)},
        ]

        try:
            response = await self._invoke_llm(messages, temperature=0.3, max_tokens=4096)
            data = self._extract_json(response)
            return KnowledgePrecipitationOutput(
                knowledge_candidates=data.get("knowledge_candidates", []),
                rule_optimization_suggestions=data.get("rule_optimization_suggestions", []),
                similarity_tags=data.get("similarity_tags", []),
                process_improvement_points=data.get("process_improvement_points", []),
                confidence=self._safe_confidence(data.get("confidence")),
            )
        except Exception as e:
            logger.error("knowledge_precipitation_failed", error=str(e))
            return KnowledgePrecipitationOutput(
                confidence=Confidence.UNABLE,
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
