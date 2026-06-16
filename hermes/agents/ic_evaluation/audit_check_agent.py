"""
审计检查 Agent (audit-check-agent) ⭐ 跨模块共享

角色：审计执行师（15年审计实务经验）
阶段：设计缺陷评估 + 执行缺陷评估

核心任务：
  1. 设计缺陷评估：制度文档逐一比对风控矩阵，识别制度缺失/冲突/过时/模糊
  2. 执行缺陷评估：根据穿行测试结果和数据分析，判断控制执行有效性
  3. 自动评分并输出缺陷清单

共享范围：内控评价 + 专项审计 + 离任审计

参照: doc/agents/03-internal-control-evaluation-agents.md §三
"""

from __future__ import annotations

import json
import time
from typing import Any

from hermes.agents.base import BaseStageAgent
from hermes.agents.prompt_manager import prompt_manager
from hermes.core.logging import get_logger
from hermes.schemas.agents.common import Confidence
from hermes.schemas.agents.ic_evaluation import (
    AuditCheckAgentInput,
    AuditCheckAgentOutput,
    CheckType,
    Deficiency,
)

logger = get_logger(__name__)


class AuditCheckAgent(BaseStageAgent):
    """审计检查 Agent — 审计执行师 ⭐"""

    agent_id = "audit-check-agent"
    agent_name = "审计检查 Agent"
    module = "ic_evaluation"
    stage = "audit_check"
    kb_types = ["control_matrix", "deficiency_rating", "audit_plan", "common"]
    role_description = "有15年审计实务经验的审计执行师，精通内控测试和缺陷评估"

    def __init__(self) -> None:
        super().__init__()
        self._prompt_version = "v1.0"

    async def run(
        self,
        db_session,
        check_input: AuditCheckAgentInput,
        kb_context: str = "",
    ) -> AuditCheckAgentOutput:
        """执行审计检查（设计缺陷或执行缺陷评估）"""
        start_time = time.monotonic()

        stage_name = "design_deficiency" if check_input.check_type == CheckType.DESIGN else "execution_deficiency"

        prompt_text = prompt_manager.render(
            module="ic_evaluation",
            stage=stage_name,
            variables={
                "audit_type": check_input.audit_type.value,
                "check_type": check_input.check_type.value,
                "kb_context": kb_context,
                "scoring_criteria": json.dumps(check_input.scoring_criteria, ensure_ascii=False),
                "policy_docs": json.dumps(check_input.policy_documents or [], ensure_ascii=False),
                "test_results": json.dumps(check_input.execution_test_results or [], ensure_ascii=False),
            },
        )

        messages = self._parse_prompt_to_messages(prompt_text)

        try:
            response = await self._invoke_llm(
                messages,
                temperature=0.2,
                max_tokens=8192,
            )
            return self._parse_response(response, start_time)
        except Exception as e:
            logger.error("audit_check_agent_failed", error=str(e))
            return AuditCheckAgentOutput(
                deficiencies=[],
                total_score=0.0,
                score_breakdown={"error": str(e)[:200]},
                confidence=Confidence.UNABLE,
                processing_time_ms=self._elapsed_ms(start_time),
            )

    def _parse_response(self, response: str, start_time: float) -> AuditCheckAgentOutput:
        processing_time_ms = self._elapsed_ms(start_time)
        try:
            data = self._extract_json(response)
            deficiencies = []
            for d in data.get("deficiencies", []):
                deficiencies.append(Deficiency(
                    deficiency_id=d.get("deficiency_id", ""),
                    deficiency_type=d.get("deficiency_type", ""),
                    deficiency_category=d.get("deficiency_category", ""),
                    description=d.get("description", ""),
                    related_policy=d.get("related_policy"),
                    related_control=d.get("related_control", ""),
                    business_cycle=d.get("business_cycle", ""),
                    severity_score=d.get("severity_score", 0.0),
                    impact_assessment=d.get("impact_assessment", ""),
                    suggestion=d.get("suggestion", ""),
                    responsible_dept=d.get("responsible_dept", ""),
                ))

            return AuditCheckAgentOutput(
                deficiencies=deficiencies,
                total_score=data.get("total_score", 0.0),
                score_breakdown=data.get("score_breakdown", {}),
                working_paper_doc_id=data.get("working_paper_doc_id"),
                confidence=self._safe_confidence(data.get("confidence")),
                processing_time_ms=processing_time_ms,
            )
        except Exception as e:
            logger.warning("audit_check_parse_failed", error=str(e))
            return AuditCheckAgentOutput(
                deficiencies=[],
                total_score=0.0,
                score_breakdown={"parse_error": str(e)[:200]},
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
            {"role": "system", "content": "你是赫尔墨斯风控系统的审计执行师。"},
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
