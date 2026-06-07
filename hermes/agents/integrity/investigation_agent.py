"""
调查方案 Agent (investigation-agent)

角色：调查策略师 (10年反舞弊调查经验)
阶段：[4.2] 调查方案生成

核心任务：
  1. 匹配类似历史案例，提取关键调查路径
  2. 生成调查方向与方案（目标、范围、方法、数据需求）
  3. 建议访谈人员、访谈策略和数据获取方案
  4. 输出标准化调查方案 Excel

状态机：IDLE → KB_RETRIEVE → PLAN_GENERATE → PENDING_APPROVAL
"""

from __future__ import annotations

import json
import time
from typing import Any

from hermes.agents.integrity.schemas import (
    Confidence,
    DataRequirement,
    InterviewPlan,
    InvestigationAgentInput,
    InvestigationAgentOutput,
    InvestigationPlan,
    TimelinePhase,
)
from hermes.agents.llm_adapter import llm_adapter
from hermes.agents.prompt_manager import prompt_manager
from hermes.core.exceptions import AIServiceUnavailableError
from hermes.core.logging import get_logger

logger = get_logger(__name__)


class InvestigationAgent:
    """调查方案 Agent — 调查策略师

    职责：
    1. 检索历史案例的调查方法、业务系统信息、相关法规
    2. 匹配人员（组织架构 + 案件涉及部门）
    3. 生成结构化调查方案：目标/范围/方法/数据需求/访谈/时间/抽样
    4. 异步生成 Excel 方案文档
    """

    def __init__(self) -> None:
        self.agent_id = "investigation-agent"
        self.agent_name = "调查方案 Agent"
        self.role = "调查策略师"
        self.kb_types = ["investigation", "common"]

    async def run(
        self,
        plan_input: InvestigationAgentInput,
        kb_context: str = "",
        similar_cases_context: str = "",
        personnel_context: str = "",
    ) -> InvestigationAgentOutput:
        """执行调查方案生成

        Args:
            plan_input: 调查方案输入
            kb_context: 知识库检索上下文（历史调查方法、业务系统、法规）
            similar_cases_context: ES 历史相似案例
            personnel_context: 人员匹配结果

        Returns:
            InvestigationAgentOutput
        """
        start_time = time.monotonic()
        retry_count = 0

        # 构建上下文
        variables = {
            "case_info": _format_investigation_input(plan_input),
            "kb_context": kb_context or "（无相关知识库检索结果）",
            "similar_cases": similar_cases_context or "（无相似历史案例）",
            "intake_context": json.dumps(plan_input.intake_context, ensure_ascii=False),
            "personnel_context": personnel_context or "（未匹配到建议访谈人员）",
        }

        prompt_text = prompt_manager.render(
            module="integrity",
            stage="investigation",
            variables=variables,
        )

        messages = _parse_system_user(prompt_text)

        for attempt in range(3):
            try:
                response = await llm_adapter.invoke(
                    messages,
                    temperature=0.5,
                    max_tokens=4096,
                )
                return self._parse_response(response, plan_input.task_id, start_time, retry_count)
            except AIServiceUnavailableError as e:
                retry_count = attempt
                logger.warning("investigation_llm_retry", attempt=attempt + 1, error=str(e))
                if attempt < 2:
                    await _sleep_backoff(attempt)
            except Exception as e:
                logger.error("investigation_unexpected_error", error=str(e))
                break

        return self._fallback_output(plan_input.task_id, start_time, "LLM 服务不可用")

    def _parse_response(
        self, response: str, task_id: str, start_time: float, retry_count: int
    ) -> InvestigationAgentOutput:
        processing_time_ms = int((time.monotonic() - start_time) * 1000)

        try:
            data = _extract_json(response)
            plan_data = data.get("investigation_plan", data)

            # 解析调查方案结构
            timeline = []
            for t in plan_data.get("timeline", []):
                timeline.append(TimelinePhase(
                    name=t.get("name", ""),
                    duration=t.get("duration", ""),
                    tasks=t.get("tasks", []),
                ))

            data_reqs = []
            for d in plan_data.get("data_requirements", []):
                data_reqs.append(DataRequirement(
                    system=d.get("system", ""),
                    data_type=d.get("data_type", ""),
                    time_range=d.get("time_range", ""),
                    purpose=d.get("purpose", ""),
                    filters=d.get("filters"),
                ))

            interview = plan_data.get("interview_plan", {})
            interview_plan = InterviewPlan(
                targets=interview.get("targets", []),
                strategy=interview.get("strategy", ""),
                key_questions=interview.get("key_questions", []),
            )

            investigation_plan = InvestigationPlan(
                investigation_objectives=plan_data.get("investigation_objectives", []),
                investigation_scope=plan_data.get("investigation_scope", ""),
                investigation_methods=plan_data.get("investigation_methods", []),
                data_requirements=data_reqs,
                interview_plan=interview_plan,
                timeline=timeline,
                sampling_strategy=plan_data.get("sampling_strategy"),
                risk_mitigation=plan_data.get("risk_mitigation", []),
            )

            return InvestigationAgentOutput(
                investigation_plan=investigation_plan,
                plan_rationale=data.get("plan_rationale", ""),
                similar_cases_referenced=data.get("similar_cases_referenced", []),
                confidence=_safe_confidence(data.get("confidence", "medium")),
                confidence_reason=data.get("confidence_reason", ""),
                processing_time_ms=processing_time_ms,
                kb_sources=data.get("kb_sources", []),
                retry_count=retry_count,
                downstream_context=_build_downstream(data, task_id, investigation_plan),
            )
        except Exception as e:
            logger.warning("investigation_json_parse_failed", error=str(e))
            return self._fallback_output(task_id, start_time, f"JSON 解析失败: {e}")

    def _fallback_output(self, task_id: str, start_time: float, reason: str) -> InvestigationAgentOutput:
        return InvestigationAgentOutput(
            investigation_plan=InvestigationPlan(
                investigation_objectives=["需人工制定调查目标"],
                investigation_scope="待人工确定",
                investigation_methods=["需人工确定调查方法"],
                data_requirements=[],
                interview_plan=InterviewPlan(targets=[], strategy="待人工确定"),
                timeline=[TimelinePhase(name="调查阶段", duration="待定", tasks=["需人工规划"])],
            ),
            plan_rationale=f"AI 服务异常: {reason}，请人工制定调查方案",
            confidence=Confidence.UNABLE,
            confidence_reason=reason,
            processing_time_ms=int((time.monotonic() - start_time) * 1000),
        )


# ── 辅助函数 ────────────────────────────────────────────────────────

def _format_investigation_input(plan_input: InvestigationAgentInput) -> str:
    lines = [
        f"案件编号: {plan_input.task_id}",
        f"事业部: {plan_input.client.value}",
        f"初判摘要: {plan_input.intake_report_summary}",
        f"调查对象类型: {plan_input.involved_entity_type}",
    ]
    if plan_input.key_facts:
        lines.append("关键事实:")
        for f in plan_input.key_facts:
            lines.append(f"  - {f}")
    if plan_input.suggested_focus:
        lines.append("建议调查方向:")
        for f in plan_input.suggested_focus:
            lines.append(f"  - {f}")
    if plan_input.suggested_interview_targets:
        lines.append(f"建议访谈人员: {', '.join(plan_input.suggested_interview_targets)}")
    if plan_input.case_files:
        lines.append(f"案件文件: {len(plan_input.case_files)} 份")
    return "\n".join(lines)


def _build_downstream(data: dict, task_id: str, plan: InvestigationPlan) -> dict:
    return {
        "protocol_version": "1.0",
        "source_agent": "investigation-agent",
        "target_agent": "analysis-agent",
        "case_ref": task_id,
        "investigation_plan_summary": data.get("plan_rationale", ""),
        "data_requirements": [
            {
                "system": dr.system,
                "data_type": dr.data_type,
                "time_range": dr.time_range,
                "filters": dr.filters,
            }
            for dr in plan.data_requirements
        ],
        "interview_plan": {
            "targets": plan.interview_plan.targets,
            "key_questions": plan.interview_plan.key_questions,
        },
        "analysis_focus": plan.investigation_objectives,
    }


def _parse_system_user(prompt_text: str) -> list[dict]:
    if "[System]" in prompt_text and "[User]" in prompt_text:
        system_part = prompt_text.split("[User]")[0].replace("[System]\n", "").strip()
        user_part = prompt_text.split("[User]")[1].strip()
        return [
            {"role": "system", "content": system_part},
            {"role": "user", "content": user_part},
        ]
    return [
        {"role": "system", "content": "你是赫尔墨斯风控系统的调查策略师。"},
        {"role": "user", "content": prompt_text},
    ]


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


def _safe_confidence(value: Any) -> Confidence:
    if isinstance(value, Confidence):
        return value
    mapping = {"high": Confidence.HIGH, "medium": Confidence.MEDIUM, "low": Confidence.LOW, "unable": Confidence.UNABLE}
    return mapping.get(str(value).lower(), Confidence.MEDIUM)


async def _sleep_backoff(attempt: int) -> None:
    import asyncio
    delays = [2, 4]
    delay = delays[attempt] if attempt < len(delays) else 4
    await asyncio.sleep(delay)
