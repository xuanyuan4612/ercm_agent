"""
风险分析 Agent (risk-analysis-agent) — 向后兼容外观类

⚠️ 此 Agent 已重构为外观模式，内部委托给 3 个独立 Agent：
  - risk-scan-agent      → 子阶段1: SQL执行 + AI初核异常
  - risk-merge-agent     → 子阶段2: 主体识别与合并去重
  - risk-classify-agent  → 子阶段3: 风险类型/等级/处置建议判定

新代码应直接使用上述 3 个 Agent 而非此类。

此为向后兼容保留，供已有调用方（如测试、旧 API）继续使用。

参照:
  - doc/agents/02-risk-monitoring-agents.md
  - doc/agents/02b-risk-monitoring-architecture-analysis.md
"""

from __future__ import annotations

import json
import time

from hermes.agents.base import BaseStageAgent
from hermes.core.logging import get_logger
from hermes.schemas.agents.common import Confidence
from hermes.schemas.agents.risk_monitoring import (
    AnomalyRecord,
    MergedEntityRisk,
    RiskAnalysisAgentInput,
    RiskAnalysisAgentOutput,
    RiskClassification,
    RiskClassifyAgentInput,
    RiskMergeAgentInput,
    RiskScanAgentInput,
)

logger = get_logger(__name__)


class RiskAnalysisAgent(BaseStageAgent):
    """风险分析 Agent — 向后兼容外观类

    内部委托给 risk-scan-agent、risk-merge-agent、risk-classify-agent。
    新代码应直接使用上述 3 个独立 Agent。
    """

    agent_id = "risk-analysis-agent"
    agent_name = "风险分析 Agent (兼容外观)"
    module = "risk_monitoring"
    stage = "risk_analysis"
    kb_types = ["risk_rules", "risk_cases", "disposition_feedback", "common"]
    role_description = "经验丰富的风险数据分析师（向后兼容外观，委托给 3 个独立 Agent）"

    def __init__(self) -> None:
        super().__init__()
        self._prompt_version = "v1.0"

    async def run(
        self,
        db_session,
        analysis_input: RiskAnalysisAgentInput,
        kb_context: str = "",
        anomaly_results: list[dict] | None = None,
    ) -> RiskAnalysisAgentOutput:
        """执行风险分析（三子阶段），委托给 3 个独立 Agent

        保留此方法用于向后兼容。新代码应直接调用各个 Agent。
        """
        start_time = time.monotonic()

        # ── 子阶段1: 委托给 risk-scan-agent ──
        scan_output = None
        anomaly_records = []
        filter_removed = 0
        try:
            from hermes.agents.risk_monitoring.risk_scan_agent import RiskScanAgent

            scan_agent = RiskScanAgent()
            scan_input = RiskScanAgentInput(
                task_id=analysis_input.task_id,
                execution_mode=analysis_input.execution_mode,
                risk_rules=analysis_input.risk_rules,
                business_data_sources=analysis_input.business_data_sources,
                external_data_sources=analysis_input.external_data_sources,
                target_business_units=analysis_input.target_business_units,
                execution_date_range=analysis_input.execution_date_range,
            )
            scan_output = await scan_agent.run(
                db_session,
                scan_input,
                kb_context=kb_context,
                anomaly_results=anomaly_results,
            )
            anomaly_records = [r.model_dump() for r in scan_output.anomaly_records]
            filter_removed = scan_output.ai_filter_removed_count
        except Exception as e:
            logger.warning("risk_scan_agent_delegate_failed", error=str(e))

        # ── 子阶段2: 委托给 risk-merge-agent ──
        merged_entities = []
        merge_rationale = ""
        try:
            from hermes.agents.risk_monitoring.risk_merge_agent import RiskMergeAgent

            merge_agent = RiskMergeAgent()
            merge_input = RiskMergeAgentInput(
                task_id=analysis_input.task_id,
                anomaly_records=[AnomalyRecord(**a) for a in anomaly_records],
            )
            merge_output = await merge_agent.run(
                db_session,
                merge_input,
                kb_context=kb_context,
            )
            merged_entities = [m.model_dump() for m in merge_output.merged_entities]
            merge_rationale = merge_output.entity_merge_rationale
        except Exception as e:
            logger.warning("risk_merge_agent_delegate_failed", error=str(e))

        # ── 子阶段3: 委托给 risk-classify-agent ──
        classifications = []
        try:
            from hermes.agents.risk_monitoring.risk_classify_agent import RiskClassifyAgent

            classify_agent = RiskClassifyAgent()
            classify_input = RiskClassifyAgentInput(
                task_id=analysis_input.task_id,
                merged_entities=[MergedEntityRisk(**m) for m in merged_entities],
                anomaly_summary=scan_output.anomaly_summary if scan_output else {},
            )
            classify_output = await classify_agent.run(
                db_session,
                classify_input,
                kb_context=kb_context,
            )
            classifications = [c.model_dump() for c in classify_output.risk_classifications]
        except Exception as e:
            logger.warning("risk_classify_agent_delegate_failed", error=str(e))

        return RiskAnalysisAgentOutput(
            anomaly_records=[AnomalyRecord(**a) for a in anomaly_records],
            anomaly_summary=scan_output.anomaly_summary if scan_output
            else self._build_anomaly_summary(anomaly_records, filter_removed),
            ai_filter_removed_count=filter_removed,
            merged_entities=[MergedEntityRisk(**m) for m in merged_entities],
            entity_merge_rationale=merge_rationale,
            risk_classifications=[RiskClassification(**c) for c in classifications],
            confidence=Confidence.MEDIUM,
            processing_time_ms=self._elapsed_ms(start_time),
        )

    # ── 向后兼容的辅助方法 ──

    @staticmethod
    def _build_anomaly_summary(records: list[dict], removed: int) -> dict:
        return {
            "total_detected": len(records) + removed,
            "ai_filtered_out": removed,
            "anomaly_confirmed": len(records),
        }

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
