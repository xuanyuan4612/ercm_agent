"""
风险扫描 Agent (risk-scan-agent)

角色：风险扫描分析师（SQL执行 + AI初核异常）
阶段：[6.2] SQL执行 + AI初核异常

核心任务：
  1. 执行已审核通过的风险规则SQL
  2. 聚合SQL结果，调用LLM进行AI初核
  3. 将每条异常分类为 normal/abnormal/uncertain

参照: doc/agents/02-risk-monitoring-agents.md §三 子阶段1
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
    RiskScanAgentInput,
    RiskScanAgentOutput,
)

logger = get_logger(__name__)


class RiskScanAgent(BaseStageAgent):
    """风险扫描 Agent — SQL执行 + AI初核异常"""

    agent_id = "risk-scan-agent"
    agent_name = "风险扫描 Agent"
    module = "risk_monitoring"
    stage = "risk_scan"
    kb_types = ["risk_rules", "database_schema", "risk_cases", "common"]
    role_description = "经验丰富的风险数据分析师，擅长从海量业务数据中识别真正的异常"

    def __init__(self) -> None:
        super().__init__()
        self._prompt_version = "v1.0"

    async def run(
        self,
        db_session,
        scan_input: RiskScanAgentInput,
        kb_context: str = "",
        anomaly_results: list[dict] | None = None,
    ) -> RiskScanAgentOutput:
        """执行SQL扫描 + AI初核异常

        Args:
            db_session: 数据库会话（用于KB检索）
            scan_input: 扫描输入（规则清单 + 数据源 + 执行参数）
            kb_context: 知识库检索上下文
            anomaly_results: SQL执行后的原始异常数据（由Celery Worker预执行）

        Returns:
            RiskScanAgentOutput: 包含AI初核后的异常记录和汇总统计
        """
        start_time = time.monotonic()
        raw_data = anomaly_results or []

        ctx = {
            "task_id": scan_input.task_id,
            "mode": scan_input.execution_mode.value,
            "rules_count": len(scan_input.risk_rules),
            "kb_context": kb_context,
            "anomaly_results": raw_data,
        }

        if not raw_data:
            logger.info(
                "risk_scan_no_data",
                task_id=ctx["task_id"],
                message="无异常数据，跳过AI初核",
            )
            return RiskScanAgentOutput(
                anomaly_records=[],
                anomaly_summary={
                    "total_detected": 0,
                    "ai_filtered_out": 0,
                    "anomaly_confirmed": 0,
                },
                ai_filter_removed_count=0,
                sql_execution_summary={"total_queries": len(scan_input.risk_rules), "succeeded": 0, "failed": 0},
                sentinel_flags={"schema_adaptation_needed": False, "deep_analysis_needed": False},
                confidence=Confidence.MEDIUM,
                processing_time_ms=self._elapsed_ms(start_time),
            )

        # 构建 Prompt
        prompt_text = prompt_manager.render(
            module="risk_monitoring",
            stage="risk_analysis_phase1",
            variables={
                "task_id": ctx["task_id"],
                "kb_context": ctx["kb_context"],
                "anomaly_data": json.dumps(raw_data, ensure_ascii=False),
            },
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "你是风险数据分析师，擅长从业务数据中识别异常模式。"
                    "你能区分正常业务波动（如季节性促销）和真正的风险信号（如新供应商大额订单）。"
                    "对每条数据给出判断：normal（正常业务）/ abnormal（真正异常）/ uncertain（存疑需人工复核）。"
                ),
            },
            {"role": "user", "content": prompt_text},
        ]

        try:
            response = await self._invoke_llm(messages, temperature=0.2, max_tokens=8192)
            data = self._extract_json(response)
            records_raw = data.get("anomaly_records", [])
            removed = data.get("normal_count", 0)

            # 构建结构化的异常记录
            anomaly_records = []
            abnormal_count = 0
            uncertain_count = 0

            for r in records_raw:
                judgment = r.get("ai_initial_judgment", "uncertain")
                if judgment == "abnormal":
                    abnormal_count += 1
                elif judgment == "uncertain":
                    uncertain_count += 1

                anomaly_records.append(AnomalyRecord(
                    rule_id=r.get("rule_id", ""),
                    rule_level3_scenario=r.get("rule_level3_scenario", ""),
                    anomaly_detail=r.get("anomaly_detail", {}),
                    ai_initial_judgment=judgment,
                    ai_judgment_reason=r.get("ai_judgment_reason", ""),
                    anomaly_score=float(r.get("anomaly_score", 0.0)),
                ))

            # 哨兵判定
            total_judged = len(anomaly_records)
            uncertain_ratio = uncertain_count / total_judged if total_judged > 0 else 0.0
            sentinel_flags = {
                "deep_analysis_needed": uncertain_ratio > 0.30,
                "uncertain_ratio": round(uncertain_ratio, 3),
                "abnormal_count": abnormal_count,
                "uncertain_count": uncertain_count,
                "normal_count": removed,
            }

            logger.info(
                "risk_scan_complete",
                task_id=ctx["task_id"],
                total_anomalies=len(anomaly_records),
                abnormal=abnormal_count,
                uncertain=uncertain_count,
                normal_filtered=removed,
                deep_analysis_needed=sentinel_flags["deep_analysis_needed"],
            )

            return RiskScanAgentOutput(
                anomaly_records=anomaly_records,
                anomaly_summary={
                    "total_detected": total_judged + removed,
                    "ai_filtered_out": removed,
                    "anomaly_confirmed": total_judged,
                    "abnormal_count": abnormal_count,
                    "uncertain_count": uncertain_count,
                },
                ai_filter_removed_count=removed,
                sql_execution_summary=data.get("sql_execution_summary", {}),
                sentinel_flags=sentinel_flags,
                confidence=self._safe_confidence(data.get("confidence")),
                processing_time_ms=self._elapsed_ms(start_time),
            )
        except Exception as e:
            logger.error("risk_scan_failed", task_id=ctx["task_id"], error=str(e))
            return RiskScanAgentOutput(
                anomaly_records=[],
                anomaly_summary={"total_detected": 0, "ai_filtered_out": 0, "anomaly_confirmed": 0, "error": str(e)[:200]},
                ai_filter_removed_count=0,
                sql_execution_summary={"error": str(e)[:200]},
                sentinel_flags={"schema_adaptation_needed": True, "error": str(e)[:200]},
                confidence=Confidence.UNABLE,
                processing_time_ms=self._elapsed_ms(start_time),
            )

    # ── 辅助方法 ──

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
    def _safe_confidence(value) -> Confidence:
        if isinstance(value, Confidence):
            return value
        mapping = {"high": Confidence.HIGH, "medium": Confidence.MEDIUM, "low": Confidence.LOW, "unable": Confidence.UNABLE}
        return mapping.get(str(value).lower() if isinstance(value, str) else "", Confidence.MEDIUM)
