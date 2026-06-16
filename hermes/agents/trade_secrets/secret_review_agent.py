"""
定密评审 Agent (secret-review-agent)

角色：保密评审专家
阶段：定密信息评审

核心任务：
  1. 综合法规、案例、制度、历史评审和横向比对
  2. 生成正式评审建议（密级/范围/期限）
  3. 输出风险和不确定性说明

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
    SecrecyReviewAgentInput,
    SecrecyReviewAgentOutput,
)

logger = get_logger(__name__)


class SecretReviewAgent(BaseStageAgent):
    """定密评审 Agent — 保密评审专家"""

    agent_id = "secret-review-agent"
    agent_name = "定密评审 Agent"
    module = "trade_secrets"
    stage = "secret_review"
    kb_types = [
        "trade_secret_policy", "trade_secret_law", "trade_secret_cases",
        "historical_secret_review", "ic_policy", "common",
    ]
    role_description = "保密评审专家，擅长综合多维信息进行定密评审"

    def __init__(self) -> None:
        super().__init__()
        self._prompt_version = "v1.0"

    async def run(
        self,
        db_session,
        review_input: SecrecyReviewAgentInput,
        precheck_result: dict | None = None,
        policy_compare_result: dict | None = None,
        behavioral_risk_summary: dict | None = None,
        kb_context: str = "",
    ) -> SecrecyReviewAgentOutput:
        """执行定密评审"""
        start_time = time.monotonic()

        messages = [
            {"role": "system", "content": (
                "你是保密评审专家。综合预审报告、制度比对、法规案例、横向比对和风险结果，"
                "生成正式评审建议。最终密级必须由评审小组确认，你只能提供建议和依据。"
            )},
            {"role": "user", "content": json.dumps({
                "secrecy_info_table": review_input.secrecy_info_table,
                "precheck_result": precheck_result or {},
                "policy_compare_result": policy_compare_result or {},
                "peer_department_reviews": review_input.peer_department_reviews or [],
                "behavioral_risk_summary": behavioral_risk_summary or {},
                "kb_context": kb_context,
            }, ensure_ascii=False)},
        ]

        try:
            response = await self._invoke_llm(messages, temperature=0.2, max_tokens=4096)
            return self._parse_response(response, start_time)
        except Exception as e:
            logger.error("secret_review_failed", error=str(e))
            return SecrecyReviewAgentOutput(
                completeness_score=0.0,
                rationality_score=0.0,
                confidence=Confidence.UNABLE,
                processing_time_ms=self._elapsed_ms(start_time),
            )

    def _parse_response(self, response: str, start_time: float) -> SecrecyReviewAgentOutput:
        processing_time_ms = self._elapsed_ms(start_time)
        try:
            data = self._extract_json(response)
            return SecrecyReviewAgentOutput(
                formal_review_report=data.get("formal_review_report"),
                completeness_score=data.get("completeness_score", 0.0),
                rationality_score=data.get("rationality_score", 0.0),
                lateral_comparison=data.get("lateral_comparison"),
                recommendations=data.get("recommendations", []),
                confidence=self._safe_confidence(data.get("confidence")),
                processing_time_ms=processing_time_ms,
            )
        except Exception as e:
            logger.warning("secret_review_parse_failed", error=str(e))
            return SecrecyReviewAgentOutput(
                completeness_score=0.0,
                rationality_score=0.0,
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
