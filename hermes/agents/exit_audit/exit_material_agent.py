"""
资料清单 Agent (exit-material-agent)

角色：离任审计资料协调员
阶段：资料清单生成

核心任务：
  1. 根据被审计人岗位职责生成资料需求清单
  2. 标记系统自动取数 vs 人工上传
  3. 匹配责任人、系统来源和截止时间

参照: doc/agents/05-exit-audit-agents.md
"""

from __future__ import annotations

import json
import time
from typing import Any

from hermes.agents.base import BaseStageAgent
from hermes.core.logging import get_logger
from hermes.schemas.agents.common import Confidence
from hermes.schemas.agents.exit_audit import (
    ExitAuditAgentInput,
    ExitMaterialAgentOutput,
)

logger = get_logger(__name__)


class ExitMaterialAgent(BaseStageAgent):
    """资料清单 Agent — 离任审计资料协调员"""

    agent_id = "exit-material-agent"
    agent_name = "资料清单 Agent"
    module = "exit_audit"
    stage = "material_list"
    kb_types = ["ea_plan", "position_duty", "common"]
    role_description = "离任审计资料协调员，擅长根据岗位职责精准识别所需的各类资料"

    def __init__(self) -> None:
        super().__init__()
        self._prompt_version = "v1.0"

    async def run(
        self,
        db_session,
        agent_input: ExitAuditAgentInput,
        kb_context: str = "",
        available_systems: list[str] | None = None,
    ) -> ExitMaterialAgentOutput:
        """生成资料需求清单"""
        start_time = time.monotonic()

        systems = available_systems or []
        messages = [
            {"role": "system", "content": "你是离任审计资料协调员。根据被审计人岗位职责和系统清单，生成资料需求清单。"},
            {"role": "user", "content": json.dumps({
                "departing_person": {
                    "name": agent_input.departing_person_name,
                    "position": agent_input.position,
                    "department": agent_input.department,
                    "tenure_years": agent_input.tenure_years,
                    "audit_period_years": agent_input.audit_period_years,
                },
                "position_duties": agent_input.position_duties,
                "available_systems": systems,
                "kb_context": kb_context,
            }, ensure_ascii=False)},
        ]

        try:
            response = await self._invoke_llm(messages, temperature=0.3, max_tokens=4096)
            return self._parse_response(response, systems, start_time)
        except Exception as e:
            logger.error("exit_material_failed", error=str(e))
            return ExitMaterialAgentOutput(
                material_requirements=[],
                system_data_requests=[],
                manual_upload_items=[],
                missing_systems_flag=True,
                missing_system_notes=f"资料清单生成失败: {str(e)[:200]}",
                confidence=Confidence.UNABLE,
                processing_time_ms=self._elapsed_ms(start_time),
            )

    def _parse_response(
        self, response: str, available_systems: list[str], start_time: float
    ) -> ExitMaterialAgentOutput:
        processing_time_ms = self._elapsed_ms(start_time)
        try:
            data = self._extract_json(response)
            return ExitMaterialAgentOutput(
                material_requirements=data.get("material_requirements", []),
                system_data_requests=data.get("system_data_requests", []),
                manual_upload_items=data.get("manual_upload_items", []),
                missing_systems_flag=data.get("missing_systems_flag", False),
                missing_system_notes=data.get("missing_system_notes", ""),
                confidence=self._safe_confidence(data.get("confidence")),
                processing_time_ms=processing_time_ms,
            )
        except Exception as e:
            logger.warning("exit_material_parse_failed", error=str(e))
            return ExitMaterialAgentOutput(
                material_requirements=[],
                missing_systems_flag=True,
                missing_system_notes="JSON解析失败",
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
