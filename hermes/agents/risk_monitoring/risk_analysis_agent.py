"""
风险分析 Agent (risk-analysis-agent)

角色：风险分析师（15年审计+数据分析经验）
阶段：[6.2] 异常数据生成 → [6.3] 主体合并 → [6.4] 风险定性

核心任务：
  1. 执行规则SQL → AI初核异常
  2. 按主体合并重复预警
  3. 自动判定风险类型/等级/处置建议

参照: doc/agents/02-risk-monitoring-agents.md §三
"""

from __future__ import annotations

import json
import time

from hermes.agents.base import BaseStageAgent
from hermes.agents.prompt_manager import prompt_manager
from hermes.core.logging import get_logger
from hermes.schemas.agents.common import Confidence
from hermes.schemas.agents.risk_monitoring import (
    AnomalyRecord,
    MergedEntityRisk,
    RiskAnalysisAgentInput,
    RiskAnalysisAgentOutput,
    RiskClassification,
)

logger = get_logger(__name__)


class RiskAnalysisAgent(BaseStageAgent):
    """风险分析 Agent — 风险分析师"""

    agent_id = "risk-analysis-agent"
    agent_name = "风险分析 Agent"
    module = "risk_monitoring"
    stage = "risk_analysis"
    kb_types = ["risk_rules", "risk_cases", "disposition_feedback", "common"]
    role_description = "经验丰富的风险数据分析师，擅长从海量业务数据中识别真正的异常"

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
        """执行风险分析（三子阶段）"""
        start_time = time.monotonic()

        ctx = {
            "task_id": analysis_input.task_id,
            "mode": analysis_input.execution_mode.value,
            "rules_count": len(analysis_input.risk_rules),
            "kb_context": kb_context,
            "anomaly_results": anomaly_results or [],
        }

        # 子阶段1: AI初核
        anomaly_records, filter_removed = await self._sub_phase1(analysis_input, ctx)

        # 子阶段2: 主体合并
        merged_entities, merge_rationale = await self._sub_phase2(anomaly_records, ctx)

        # 子阶段3: 风险定性
        classifications = await self._sub_phase3(merged_entities, ctx)

        return RiskAnalysisAgentOutput(
            anomaly_records=[AnomalyRecord(**a) for a in anomaly_records],
            anomaly_summary=self._build_anomaly_summary(anomaly_records, filter_removed),
            ai_filter_removed_count=filter_removed,
            merged_entities=[MergedEntityRisk(**m) for m in merged_entities],
            entity_merge_rationale=merge_rationale,
            risk_classifications=[RiskClassification(**c) for c in classifications],
            confidence=Confidence.MEDIUM,
            processing_time_ms=self._elapsed_ms(start_time),
        )

    async def _sub_phase1(self, analysis_input: RiskAnalysisAgentInput, ctx: dict) -> tuple[list[dict], int]:
        """子阶段1: 异常初核"""
        prompt_text = prompt_manager.render(
            module="risk_monitoring",
            stage="risk_analysis_phase1",
            variables={
                "task_id": ctx["task_id"],
                "kb_context": ctx["kb_context"],
                "anomaly_data": json.dumps(ctx["anomaly_results"], ensure_ascii=False),
            },
        )

        messages = [
            {"role": "system", "content": "你是风险数据分析师，擅长从业务数据中识别异常模式。"},
            {"role": "user", "content": prompt_text},
        ]

        try:
            response = await self._invoke_llm(messages, temperature=0.2, max_tokens=8192)
            data = self._extract_json(response)
            records = data.get("anomaly_records", [])
            removed = data.get("normal_count", 0)
            return records, removed
        except Exception as e:
            logger.warning("risk_phase1_failed", error=str(e))
            return [], 0

    async def _sub_phase2(self, anomaly_records: list[dict], ctx: dict) -> tuple[list[dict], str]:
        """子阶段2: 主体合并"""
        if not anomaly_records:
            return [], "无异常数据，跳过主体合并"

        messages = [
            {"role": "system", "content": "你擅长从散乱的异常记录中识别出同一分析主体。"},
            {"role": "user", "content": json.dumps({"anomaly_records": anomaly_records}, ensure_ascii=False)},
        ]

        try:
            response = await self._invoke_llm(messages, temperature=0.2, max_tokens=4096)
            data = self._extract_json(response)
            return data.get("merged_entities", []), data.get("rationale", "")
        except Exception as e:
            logger.warning("risk_phase2_failed", error=str(e))
            return [], ""

    async def _sub_phase3(self, merged_entities: list[dict], ctx: dict) -> list[dict]:
        """子阶段3: 风险定性"""
        if not merged_entities:
            return []

        messages = [
            {"role": "system", "content": "你擅长综合判断风险的性质、等级和影响范围。"},
            {"role": "user", "content": json.dumps({"entities": merged_entities}, ensure_ascii=False)},
        ]

        try:
            response = await self._invoke_llm(messages, temperature=0.3, max_tokens=4096)
            data = self._extract_json(response)
            return data.get("classifications", [])
        except Exception as e:
            logger.warning("risk_phase3_failed", error=str(e))
            return []

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
