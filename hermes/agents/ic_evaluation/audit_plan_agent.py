"""
审计方案 Agent (audit-plan-agent) ⭐ 跨模块共享

角色：审计规划师（10年审计经验，熟悉各类审计方法论）
阶段：审计方案生成

核心任务：
  1. 根据审计类型/目的/重点/范围自动生成标准化审计方案
  2. 方案包含5部分：项目基本信息、评价依据、审计范围、审计实施细则、缺陷认定标准
  3. 支持内控评价(ic_evaluation)、专项审计(special_audit)、离任审计(exit_audit)三种审计类型

共享范围：内控评价 + 专项审计 + 离任审计

参照: doc/agents/03-internal-control-evaluation-agents.md §二
"""

from __future__ import annotations

import json
import time
from typing import Any

from hermes.agents.base import BaseStageAgent
from hermes.agents.prompt_manager import prompt_manager
from hermes.core.logging import get_logger
from hermes.schemas.agents.common import AuditType, Confidence
from hermes.schemas.agents.ic_evaluation import (
    AuditPlan,
    AuditPlanAgentInput,
    AuditPlanAgentOutput,
)

logger = get_logger(__name__)


class AuditPlanAgent(BaseStageAgent):
    """审计方案 Agent — 审计规划师 ⭐"""

    agent_id = "audit-plan-agent"
    agent_name = "审计方案 Agent"
    module = "ic_evaluation"
    stage = "audit_plan"
    kb_types = ["audit_plan", "sa_plan", "ea_plan", "control_matrix", "common"]
    role_description = "有10年审计经验的审计规划师，精通COSO内控框架和各类审计方法论"

    def __init__(self) -> None:
        super().__init__()
        self._prompt_version = "v1.0"

    async def run(
        self,
        db_session,
        plan_input: AuditPlanAgentInput,
        kb_context: str = "",
        similar_plans_context: str = "",
    ) -> AuditPlanAgentOutput:
        """生成审计方案"""
        start_time = time.monotonic()

        prompt_text = prompt_manager.render(
            module="ic_evaluation",
            stage="audit_plan",
            variables={
                "audit_type": plan_input.audit_type.value,
                "audit_objective": plan_input.audit_objective,
                "audit_focus": json.dumps(plan_input.audit_focus, ensure_ascii=False),
                "audit_period": plan_input.audit_period,
                "audited_entity": plan_input.audited_entity,
                "project_leader": plan_input.project_leader,
                "kb_context": kb_context,
                "similar_plans": similar_plans_context,
                "business_cycles": json.dumps(plan_input.business_cycles or [], ensure_ascii=False),
                "departing_person_info": json.dumps(plan_input.departing_person_info or {}, ensure_ascii=False),
            },
        )

        messages = self._parse_prompt_to_messages(prompt_text)

        try:
            response = await self._invoke_llm(
                messages,
                temperature=0.3,
                max_tokens=8192,
            )
            return self._parse_response(response, start_time)
        except Exception as e:
            logger.error("audit_plan_agent_failed", error=str(e))
            return AuditPlanAgentOutput(
                audit_plan=AuditPlan(),
                plan_rationale=f"方案生成失败: {str(e)[:200]}",
                confidence=Confidence.UNABLE,
                processing_time_ms=self._elapsed_ms(start_time),
            )

    def _parse_response(self, response: str, start_time: float) -> AuditPlanAgentOutput:
        processing_time_ms = self._elapsed_ms(start_time)
        try:
            data = self._extract_json(response)
            plan = AuditPlan(
                project_basic_info=data.get("project_basic_info", {}),
                evaluation_basis=data.get("evaluation_basis", []),
                audit_scope=data.get("audit_scope", {}),
                audit_implementation_rules=data.get("audit_implementation_rules", []),
                deficiency_criteria=data.get("deficiency_criteria", {}),
                sampling_strategy=data.get("sampling_strategy"),
                timeline=data.get("timeline", {}),
                personnel_assignment=data.get("personnel_assignment", {}),
                referenced_historical_plans=data.get("referenced_historical_plans", []),
                confidence=self._safe_confidence(data.get("confidence")),
            )
            return AuditPlanAgentOutput(
                audit_plan=plan,
                plan_rationale=data.get("plan_rationale", ""),
                similar_plans_referenced=data.get("similar_plans_referenced", []),
                confidence=self._safe_confidence(data.get("confidence")),
                processing_time_ms=processing_time_ms,
                kb_sources=data.get("kb_sources", []),
            )
        except Exception as e:
            logger.warning("audit_plan_parse_failed", error=str(e))
            return AuditPlanAgentOutput(
                audit_plan=AuditPlan(),
                plan_rationale="JSON解析失败，请人工审核",
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
            {"role": "system", "content": "你是赫尔墨斯风控系统的审计规划师。"},
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
