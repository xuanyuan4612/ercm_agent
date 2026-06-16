"""
风险规则 Agent (risk-rule-agent)

角色：风控规则师（精通SQL和业务风险场景识别）
阶段：[6.1] 风险规则清单生成

核心任务：
  1. 根据业务场景自动生成三级风险场景 → 计算规则 → 可执行SQL语句
  2. SQL语法校验 + 测试环境验证
  3. 人工审核通过后入库形成风险清单知识库

参照: doc/agents/02-risk-monitoring-agents.md §二
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Optional

from hermes.agents.base import BaseStageAgent
from hermes.agents.prompt_manager import prompt_manager
from hermes.agents.rag_engine import KB_TYPE_MAP
from hermes.core.logging import get_logger
from hermes.schemas.agents.common import Confidence
from hermes.schemas.agents.risk_monitoring import (
    RiskRule,
    RiskRuleAgentInput,
    RiskRuleAgentOutput,
    RuleGenerationMode,
)

logger = get_logger(__name__)


class RiskRuleAgent(BaseStageAgent):
    """风险规则 Agent — 风控规则师"""

    agent_id = "risk-rule-agent"
    agent_name = "风险规则 Agent"
    module = "risk_monitoring"
    stage = "risk_rule"
    kb_types = ["risk_rules", "database_schema", "risk_cases", "common"]
    role_description = "资深风控规则师，精通企业风险场景识别和SQL数据分析"

    def __init__(self) -> None:
        super().__init__()
        self._prompt_version = "v1.0"

    async def run(
        self,
        db_session,
        rule_input: RiskRuleAgentInput,
        kb_context: str = "",
    ) -> RiskRuleAgentOutput:
        """执行风险规则生成"""
        start_time = time.monotonic()

        # 构建 Prompt
        prompt_text = prompt_manager.render(
            module="risk_monitoring",
            stage="risk_rule",
            variables={
                "mode": rule_input.mode.value,
                "scenario": rule_input.manual_scenario or "",
                "db_schema": kb_context or str(rule_input.db_schema_context),
                "historical_cases": json.dumps(rule_input.historical_cases, ensure_ascii=False),
            },
        )

        messages = self._parse_prompt_to_messages(prompt_text)

        try:
            response = await self._invoke_llm(
                messages,
                temperature=0.4,
                max_tokens=8192,
            )
            return self._parse_response(response, start_time)
        except Exception as e:
            logger.error("risk_rule_agent_failed", error=str(e))
            return RiskRuleAgentOutput(
                rules=[],
                sql_validation_results=[],
                generation_rationale=f"规则生成失败: {str(e)[:200]}",
                confidence=Confidence.UNABLE,
                processing_time_ms=self._elapsed_ms(start_time),
            )

    def _parse_response(self, response: str, start_time: float) -> RiskRuleAgentOutput:
        """解析 LLM 响应"""
        processing_time_ms = self._elapsed_ms(start_time)

        try:
            data = self._extract_json(response)
            rules = []
            for r in data.get("rules", []):
                rules.append(RiskRule(
                    business_unit=r.get("business_unit", ""),
                    channel=r.get("channel"),
                    business_format=r.get("business_format"),
                    business_cycle=r.get("business_cycle", ""),
                    department=r.get("department", ""),
                    position=r.get("position"),
                    personnel_info=r.get("personnel_info"),
                    level1_scenario=r.get("level1_scenario", ""),
                    level2_scenario=r.get("level2_scenario", ""),
                    level3_scenario=r.get("level3_scenario", ""),
                    sql_statement=r.get("sql_statement", ""),
                    risk_level=r.get("risk_level", "中"),
                    threshold=r.get("threshold"),
                    monitor_frequency=r.get("monitor_frequency", "daily"),
                    monitor_business_unit=r.get("monitor_business_unit", ""),
                    use_external_data=r.get("use_external_data", False),
                ))

            return RiskRuleAgentOutput(
                rules=rules,
                sql_validation_results=data.get("sql_validation_results", []),
                generation_rationale=data.get("generation_rationale", ""),
                confidence=self._safe_confidence(data.get("confidence")),
                processing_time_ms=processing_time_ms,
            )
        except Exception as e:
            logger.warning("risk_rule_parse_failed", error=str(e))
            return RiskRuleAgentOutput(
                rules=[],
                sql_validation_results=[],
                generation_rationale="JSON解析失败，请人工审核原始输出",
                confidence=Confidence.LOW,
                processing_time_ms=processing_time_ms,
            )

    # ── 辅助方法 ──
    @staticmethod
    def _parse_prompt_to_messages(prompt_text: str) -> list[dict]:
        if "[System]" in prompt_text and "[User]" in prompt_text:
            system_part = prompt_text.split("[User]")[0].replace("[System]\n", "").strip()
            user_part = prompt_text.split("[User]")[1].strip()
            return [
                {"role": "system", "content": system_part},
                {"role": "user", "content": user_part},
            ]
        return [
            {"role": "system", "content": "你是赫尔墨斯风控系统的风控规则师。"},
            {"role": "user", "content": prompt_text},
        ]

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
