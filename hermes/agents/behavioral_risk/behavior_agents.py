"""
行为风险模块 — Agent 实现

Agent:
  behavior-data-quality-agent    — 数据质量检查
  behavior-anomaly-agent         — 行为异常识别
  behavior-risk-report-agent     — 行为风险分析报告
  behavior-management-report-agent — 管理情况报告

参照: doc/agents/07-behavioral-risk-agents.md
"""

from __future__ import annotations

import json
import time
from typing import Any

from hermes.agents.base import BaseStageAgent
from hermes.core.logging import get_logger
from hermes.schemas.agents.behavioral_risk import (
    BehavioralRiskAgentInput,
    BehavioralRiskReportOutput,
    BehaviorAnomalyOutput,
    BehaviorDataQualityOutput,
    BehaviorManagementReportOutput,
)
from hermes.schemas.agents.common import Confidence

logger = get_logger(__name__)


class BehaviorDataQualityAgent(BaseStageAgent):
    """数据质量 Agent — 检查监管系统数据完整性和质量"""

    agent_id = "behavior-data-quality-agent"
    agent_name = "数据质量 Agent"
    module = "behavioral_risk"
    stage = "data_quality"
    kb_types = ["behavior_policy", "employee_lifecycle", "common"]
    role_description = "数据质量检查专家，擅长评估多源数据完整性和一致性"

    async def run(
        self,
        db_session,
        agent_input: BehavioralRiskAgentInput,
        kb_context: str = "",
    ) -> BehaviorDataQualityOutput:
        """检查数据质量"""
        time.monotonic()

        messages = [
            {"role": "system", "content": (
                "你是数据质量检查专家。检查各监管系统的覆盖范围、字段完整性、数据缺失和口径冲突。"
                "当数据缺失可能影响结论时，必须标记为阻断或建议人工确认。"
            )},
            {"role": "user", "content": json.dumps({
                "analysis_scope": agent_input.analysis_scope,
                "data_sources": agent_input.behavioral_data_sources,
                "lifecycle_info": agent_input.employee_lifecycle_info,
                "kb_context": kb_context,
            }, ensure_ascii=False)},
        ]

        try:
            response = await self._invoke_llm(messages, temperature=0.2, max_tokens=4096)
            data = self._extract_json(response)
            return BehaviorDataQualityOutput(
                coverage_report=data.get("coverage_report", {}),
                missing_fields=data.get("missing_fields", []),
                data_integrity_score=data.get("data_integrity_score", 0.0),
                timeliness_score=data.get("timeliness_score", 0.0),
                accuracy_score=data.get("accuracy_score", 0.0),
                caliber_conflicts=data.get("caliber_conflicts", []),
                can_proceed=data.get("can_proceed", True),
                blocking_reasons=data.get("blocking_reasons", []),
                confidence=self._safe_confidence(data.get("confidence")),
            )
        except Exception as e:
            logger.error("data_quality_failed", error=str(e))
            return BehaviorDataQualityOutput(
                can_proceed=False,
                blocking_reasons=[f"数据质量检查失败: {str(e)[:200]}"],
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


class BehaviorAnomalyAgent(BaseStageAgent):
    """行为异常识别 Agent — 识别异常行为模式，生成风险解释"""

    agent_id = "behavior-anomaly-agent"
    agent_name = "行为异常识别 Agent"
    module = "behavioral_risk"
    stage = "behavior_anomaly"
    kb_types = ["behavior_policy", "employee_lifecycle", "trade_secret_policy", "historical_behavior_analysis", "common"]
    role_description = "行为分析专家，擅长跨系统关联和异常模式识别"

    async def run(
        self,
        db_session,
        agent_input: BehavioralRiskAgentInput,
        behavioral_logs: list[dict] | None = None,
        kb_context: str = "",
    ) -> BehaviorAnomalyOutput:
        """识别行为异常"""
        time.monotonic()

        messages = [
            {"role": "system", "content": (
                "你是行为分析专家。从跨系统行为日志中识别异常模式。"
                "异常必须可解释，不允许只给黑箱分数。给出具体的行为类型、涉及人员、证据和风险关联。"
            )},
            {"role": "user", "content": json.dumps({
                "analysis_scope": agent_input.analysis_scope,
                "behavioral_logs": behavioral_logs or [],
                "lifecycle_info": agent_input.employee_lifecycle_info,
                "conflict_of_interest": agent_input.conflict_of_interest_info,
                "trade_secret_info": agent_input.trade_secret_info,
                "historical_analyses": agent_input.historical_analyses,
                "kb_context": kb_context,
            }, ensure_ascii=False)},
        ]

        try:
            response = await self._invoke_llm(messages, temperature=0.3, max_tokens=8192)
            data = self._extract_json(response)
            return BehaviorAnomalyOutput(
                anomaly_behaviors=data.get("anomaly_behaviors", []),
                anomaly_explanations=data.get("anomaly_explanations", []),
                correlation_findings=data.get("correlation_findings", []),
                time_line_analysis=data.get("time_line_analysis"),
                confidence=self._safe_confidence(data.get("confidence")),
            )
        except Exception as e:
            logger.error("behavior_anomaly_failed", error=str(e))
            return BehaviorAnomalyOutput(
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


class BehaviorRiskReportAgent(BaseStageAgent):
    """行为风险报告 Agent — 生成行为风险分析报告"""

    agent_id = "behavior-risk-report-agent"
    agent_name = "行为风险报告 Agent"
    module = "behavioral_risk"
    stage = "risk_report"
    kb_types = ["behavior_policy", "historical_behavior_analysis", "law_and_regulation", "common"]
    role_description = "行为风险报告撰写师，擅长总结行为风险结论"

    async def run(
        self,
        db_session,
        agent_input: BehavioralRiskAgentInput,
        anomaly_results: dict | None = None,
        kb_context: str = "",
    ) -> BehavioralRiskReportOutput:
        """生成行为风险分析报告"""
        start_time = time.monotonic()

        messages = [
            {"role": "system", "content": (
                "你是行为风险报告撰写师。根据异常识别结果和证据，生成行为风险分析报告。"
                "报告不能直接建议处罚或劳动关系处理，只能给出风险线索和人工关注点。"
            )},
            {"role": "user", "content": json.dumps({
                "analysis_scope": agent_input.analysis_scope,
                "anomaly_results": anomaly_results or {},
                "kb_context": kb_context,
            }, ensure_ascii=False)},
        ]

        try:
            response = await self._invoke_llm(messages, temperature=0.3, max_tokens=4096)
            data = self._extract_json(response)
            return BehavioralRiskReportOutput(
                anomaly_findings=data.get("anomaly_findings", []),
                risk_level_assessment=data.get("risk_level_assessment", {}),
                correlation_analysis=data.get("correlation_analysis", ""),
                push_recommendations=data.get("push_recommendations", []),
                human_attention_points=data.get("human_attention_points", []),
                report_doc_id=data.get("report_doc_id"),
                confidence=self._safe_confidence(data.get("confidence")),
                processing_time_ms=self._elapsed_ms(start_time),
            )
        except Exception as e:
            logger.error("behavior_report_failed", error=str(e))
            return BehavioralRiskReportOutput(
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


class BehaviorManagementReportAgent(BaseStageAgent):
    """管理情况报告 Agent — 月度生成行为风险管理报告"""

    agent_id = "behavior-management-report-agent"
    agent_name = "管理情况报告 Agent"
    module = "behavioral_risk"
    stage = "management_report"
    kb_types = ["behavior_policy", "historical_behavior_analysis", "common"]
    role_description = "行为风险管理员，擅长数据分析和优化建议"

    async def run(
        self,
        db_session,
        report_period: str = "",
        monthly_results: list[dict] | None = None,
        kb_context: str = "",
    ) -> BehaviorManagementReportOutput:
        """生成月度管理报告"""
        start_time = time.monotonic()

        messages = [
            {"role": "system", "content": (
                "你是行为风险管理员。根据月度分析结果，生成管理情况报告。"
                "内容包括：监管系统覆盖范围、缺失范围、数据质量评估、高风险行为汇总、高频问题统计、优化建议。"
            )},
            {"role": "user", "content": json.dumps({
                "report_period": report_period,
                "monthly_results": monthly_results or [],
                "kb_context": kb_context,
            }, ensure_ascii=False)},
        ]

        try:
            response = await self._invoke_llm(messages, temperature=0.3, max_tokens=8192)
            data = self._extract_json(response)
            return BehaviorManagementReportOutput(
                coverage_summary=data.get("coverage_summary", {}),
                data_quality_assessment=data.get("data_quality_assessment", {}),
                high_risk_behaviors_summary=data.get("high_risk_behaviors_summary", []),
                high_frequency_issues=data.get("high_frequency_issues", []),
                coverage_gap_analysis=data.get("coverage_gap_analysis", {}),
                optimization_suggestions=data.get("optimization_suggestions", []),
                report_doc_id=data.get("report_doc_id"),
                confidence=self._safe_confidence(data.get("confidence")),
                processing_time_ms=self._elapsed_ms(start_time),
            )
        except Exception as e:
            logger.error("behavior_management_report_failed", error=str(e))
            return BehaviorManagementReportOutput(
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
