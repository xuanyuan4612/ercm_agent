"""
制度比对 Agent (secret-policy-compare-agent)

角色：制度比对专家
阶段：预审/评审共用

核心任务：
  1. 比对内部制度、保密规则、知识产权制度和历史定密口径
  2. 识别合规性冲突和不一致
  3. 输出待人工确认的制度冲突项

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
    SecrecyPolicyCompareOutput,
    SecrecyReviewAgentInput,
)

logger = get_logger(__name__)


class SecretPolicyCompareAgent(BaseStageAgent):
    """制度比对 Agent — 制度比对专家"""

    agent_id = "secret-policy-compare-agent"
    agent_name = "制度比对 Agent"
    module = "trade_secrets"
    stage = "policy_compare"
    kb_types = ["trade_secret_policy", "ip_policy", "ic_policy", "historical_secret_review", "common"]
    role_description = "制度比对专家，擅长跨制度体系的合规性分析"

    def __init__(self) -> None:
        super().__init__()
        self._prompt_version = "v1.0"

    async def run(
        self,
        db_session,
        review_input: SecrecyReviewAgentInput,
        internal_policies: list[dict] | None = None,
        kb_context: str = "",
    ) -> SecrecyPolicyCompareOutput:
        """执行制度比对"""
        start_time = time.monotonic()

        messages = [
            {"role": "system", "content": (
                "你是制度比对专家。将定密信息与内部制度、历史定密口径逐一比对，"
                "识别合规性冲突。制度冲突不得自动裁决，必须标记为待人工确认。"
            )},
            {"role": "user", "content": json.dumps({
                "secrecy_info_table": review_input.secrecy_info_table,
                "previous_reviews": review_input.previous_reviews or [],
                "internal_policies": internal_policies or [],
                "kb_context": kb_context,
            }, ensure_ascii=False)},
        ]

        try:
            response = await self._invoke_llm(messages, temperature=0.2, max_tokens=4096)
            return self._parse_response(response, start_time)
        except Exception as e:
            logger.error("policy_compare_failed", error=str(e))
            return SecrecyPolicyCompareOutput(
                compliance_result="比对失败",
                confidence=Confidence.UNABLE,
            )

    def _parse_response(self, response: str, start_time: float) -> SecrecyPolicyCompareOutput:
        try:
            data = self._extract_json(response)
            return SecrecyPolicyCompareOutput(
                compliance_result=data.get("compliance_result", ""),
                conflicts=data.get("conflicts", []),
                inconsistencies=data.get("inconsistencies", []),
                pending_human_review=data.get("pending_human_review", []),
                confidence=self._safe_confidence(data.get("confidence")),
            )
        except Exception as e:
            logger.warning("policy_compare_parse_failed", error=str(e))
            return SecrecyPolicyCompareOutput(
                compliance_result="解析失败",
                confidence=Confidence.LOW,
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
