"""
管理报告 Agent (secret-management-report-agent)

角色：商业秘密管理报告分析师
阶段：月度/周期报告

核心任务：
  1. 生成商业秘密管理情况报告
  2. 统计分析（进度/数量/趋势）
  3. 风险提示

参照: doc/agents/06-trade-secrets-agents.md
"""

from __future__ import annotations

import json
import time
from typing import Any

from hermes.agents.base import BaseStageAgent
from hermes.core.logging import get_logger
from hermes.schemas.agents.common import Confidence
from hermes.schemas.agents.trade_secrets import (
    MonthlySecrecyReport,
    SecretManagementReportOutput,
)

logger = get_logger(__name__)


class SecretManagementReportAgent(BaseStageAgent):
    """管理报告 Agent — 商业秘密管理报告分析师"""

    agent_id = "secret-management-report-agent"
    agent_name = "管理报告 Agent"
    module = "trade_secrets"
    stage = "management_report"
    kb_types = ["trade_secret_policy", "historical_secret_review", "trade_secret_cases", "common"]
    role_description = "商业秘密管理报告分析师，擅长统计分析和风险趋势判断"

    def __init__(self) -> None:
        super().__init__()
        self._prompt_version = "v1.0"

    async def run(
        self,
        db_session,
        report_period: str = "",
        report_scope: str = "全集团",
        secrecy_ledger: list[dict] | None = None,
        historical_reports: list[dict] | None = None,
        kb_context: str = "",
    ) -> SecretManagementReportOutput:
        """生成月度管理报告"""
        start_time = time.monotonic()

        messages = [
            {"role": "system", "content": (
                "你是商业秘密管理报告分析师。根据定密台账和历史数据，"
                "生成月度管理情况报告，含进度统计、趋势分析和风险提示。"
            )},
            {"role": "user", "content": json.dumps({
                "report_period": report_period,
                "report_scope": report_scope,
                "secrecy_ledger": secrecy_ledger or [],
                "historical_reports": historical_reports or [],
                "kb_context": kb_context,
            }, ensure_ascii=False)},
        ]

        try:
            response = await self._invoke_llm(messages, temperature=0.3, max_tokens=4096)
            return self._parse_response(response, report_period, report_scope, start_time)
        except Exception as e:
            logger.error("secret_report_failed", error=str(e))
            return SecretManagementReportOutput(
                monthly_report=MonthlySecrecyReport(report_period=report_period),
                confidence=Confidence.UNABLE,
                processing_time_ms=self._elapsed_ms(start_time),
            )

    def _parse_response(
        self, response: str, report_period: str, report_scope: str, start_time: float
    ) -> SecretManagementReportOutput:
        processing_time_ms = self._elapsed_ms(start_time)
        try:
            data = self._extract_json(response)
            report_data = data.get("monthly_report", {})
            report_data.setdefault("report_period", report_period)
            report_data.setdefault("report_scope", report_scope)
            report_data.setdefault("generated_at", time.strftime("%Y-%m-%dT%H:%M:%S"))

            return SecretManagementReportOutput(
                monthly_report=MonthlySecrecyReport(**report_data),
                risk_alerts=data.get("risk_alerts", []),
                optimization_suggestions=data.get("optimization_suggestions", []),
                report_doc_id=data.get("report_doc_id"),
                confidence=self._safe_confidence(data.get("confidence")),
                processing_time_ms=processing_time_ms,
            )
        except Exception as e:
            logger.warning("secret_report_parse_failed", error=str(e))
            return SecretManagementReportOutput(
                monthly_report=MonthlySecrecyReport(report_period=report_period),
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
