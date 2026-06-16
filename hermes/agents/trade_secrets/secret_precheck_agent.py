"""
定密预审 Agent (secret-precheck-agent)

角色：保密评审预审专家
阶段：保密员定密建议/预审

核心任务：
  1. 检查定密材料完整性
  2. 生成预审建议（含建议密级、范围、期限和依据）
  3. 输出格式与《商业秘密信息表》一致

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
    SecrecyPrecheckOutput,
    SecrecyReviewAgentInput,
)

logger = get_logger(__name__)


class SecretPrecheckAgent(BaseStageAgent):
    """定密预审 Agent — 保密评审预审专家"""

    agent_id = "secret-precheck-agent"
    agent_name = "定密预审 Agent"
    module = "trade_secrets"
    stage = "secret_precheck"
    kb_types = ["trade_secret_policy", "historical_secret_review", "trade_secret_cases", "common"]
    role_description = "保密评审预审专家，擅长检查定密材料完整性和合理性"

    def __init__(self) -> None:
        super().__init__()
        self._prompt_version = "v1.0"

    async def run(
        self,
        db_session,
        review_input: SecrecyReviewAgentInput,
        kb_context: str = "",
    ) -> SecrecyPrecheckOutput:
        """执行定密预审"""
        start_time = time.monotonic()

        messages = [
            {"role": "system", "content": (
                "你是保密评审预审专家。根据定密信息表和前期已定密信息，检查材料的完整性和初步合理性，"
                "输出预审建议。你的建议必须给出制度或案例依据，不得无依据地建议密级。"
            )},
            {"role": "user", "content": json.dumps({
                "secrecy_info_table": review_input.secrecy_info_table,
                "classified_files": review_input.classified_file_list,
                "previous_reviews": review_input.previous_reviews or [],
                "kb_context": kb_context,
            }, ensure_ascii=False)},
        ]

        try:
            response = await self._invoke_llm(messages, temperature=0.2, max_tokens=4096)
            return self._parse_response(response, start_time)
        except Exception as e:
            logger.error("secret_precheck_failed", error=str(e))
            return SecrecyPrecheckOutput(
                pre_review_report={},
                confidence=Confidence.UNABLE,
            )

    def _parse_response(self, response: str, start_time: float) -> SecrecyPrecheckOutput:
        try:
            data = self._extract_json(response)
            return SecrecyPrecheckOutput(
                pre_review_report=data.get("pre_review_report", {}),
                completeness_check=data.get("completeness_check", {}),
                suggested_secrecy_level=data.get("suggested_secrecy_level", ""),
                suggested_secrecy_scope=data.get("suggested_secrecy_scope", ""),
                suggested_duration=data.get("suggested_duration", ""),
                missing_items=data.get("missing_items", []),
                policy_basis=data.get("policy_basis", []),
                confidence=self._safe_confidence(data.get("confidence")),
            )
        except Exception as e:
            logger.warning("secret_precheck_parse_failed", error=str(e))
            return SecrecyPrecheckOutput(
                pre_review_report={},
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
