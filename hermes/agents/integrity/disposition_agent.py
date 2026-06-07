"""
处置分流 Agent (disposition-agent)

角色：法律顾问
阶段：[4.4] 处置分流 + 追责 + (报案书)

核心任务：
  1. 法律路径分析：刑事责任/民事责任/内部违规
  2. 追责意见生成：处罚类型、依据、对象
  3. 分流路由：不追责→END | 刑事→报案书 | 民事→西塞罗 | 内部→追责意见
  4. 生成报案书（刑事路径）

状态机：IDLE → LEGAL_ANALYZE → DISPOSITION_DECIDE → PENDING_APPROVAL
"""

from __future__ import annotations

import json
import time
from typing import Any

from hermes.agents.integrity.schemas import (
    Confidence,
    DispositionAgentInput,
    DispositionAgentOutput,
    DispositionType,
    LegalAnalysis,
    PenaltyOpinion,
)
from hermes.agents.llm_adapter import llm_adapter
from hermes.agents.prompt_manager import prompt_manager
from hermes.core.exceptions import AIServiceUnavailableError
from hermes.core.logging import get_logger

logger = get_logger(__name__)


class DispositionAgent:
    """处置分流 Agent — 法律顾问

    职责：
    1. 分析案件结论的法律性质（刑事/民事/内部）
    2. 评估适用法律和制度依据
    3. 生成追责意见（处罚对象、类型、依据、生效日期）
    4. 刑事案件生成报案书
    5. 民事案件准备西塞罗推送信息
    6. 内部案件生成整改建议

    路由：
    - 不追责 → END
    - 刑事 → 报案书生成 + 后续移交给执法部门
    - 民事 → A2A→西塞罗
    - 内部 → 追责意见 → enforcement-agent
    """

    def __init__(self) -> None:
        self.agent_id = "disposition-agent"
        self.agent_name = "处置分流 Agent"
        self.role = "法律顾问"
        self.kb_types = ["disposition", "common"]

    async def run(
        self,
        disposition_input: DispositionAgentInput,
        kb_context: str = "",
    ) -> DispositionAgentOutput:
        """执行处置分流分析

        Args:
            disposition_input: 处置输入（含案件结论、证据汇总）
            kb_context: 知识库检索（制度文件、追责流程、组织架构）

        Returns:
            DispositionAgentOutput
        """
        start_time = time.monotonic()
        retry_count = 0

        # 序列化案件结论
        conclusion_json = disposition_input.case_conclusion.model_dump_json(indent=2)

        variables = {
            "case_info": _format_disposition_input(disposition_input),
            "kb_context": kb_context or "（无相关知识库内容）",
            "case_conclusion": conclusion_json,
            "intake_context": json.dumps(disposition_input.intake_context, ensure_ascii=False),
            "investigation_context": json.dumps(disposition_input.investigation_context, ensure_ascii=False),
        }

        prompt_text = prompt_manager.render(
            module="integrity",
            stage="disposition",
            variables=variables,
        )

        messages = _parse_system_user(prompt_text)

        for attempt in range(3):
            try:
                response = await llm_adapter.invoke(
                    messages,
                    temperature=0.3,
                    max_tokens=4096,
                )
                return self._parse_response(response, disposition_input.task_id, start_time, retry_count)
            except AIServiceUnavailableError as e:
                retry_count = attempt
                logger.warning("disposition_llm_retry", attempt=attempt + 1, error=str(e))
                if attempt < 2:
                    await _sleep_backoff(attempt)
            except Exception as e:
                logger.error("disposition_unexpected_error", error=str(e))
                break

        return self._fallback_output(disposition_input.task_id, start_time, "LLM 服务不可用")

    def _parse_response(
        self, response: str, task_id: str, start_time: float, retry_count: int
    ) -> DispositionAgentOutput:
        processing_time_ms = int((time.monotonic() - start_time) * 1000)

        try:
            data = _extract_json(response)

            # 法律分析
            legal_data = data.get("legal_analysis", {})
            legal_analysis = LegalAnalysis(
                applicable_laws=legal_data.get("applicable_laws", []),
                criminal_liability=legal_data.get("criminal_liability"),
                civil_liability=legal_data.get("civil_liability"),
                internal_violation=legal_data.get("internal_violation"),
                recommended_path=DispositionType(legal_data.get("recommended_path", "内部")),
            )

            # 追责意见
            penalty_opinions = []
            for p in data.get("penalty_opinions", []):
                penalty_opinions.append(PenaltyOpinion(
                    target_person=p.get("target_person", ""),
                    penalty_type=p.get("penalty_type", ""),
                    penalty_detail=p.get("penalty_detail", ""),
                    legal_basis=p.get("legal_basis", ""),
                    effective_date=p.get("effective_date"),
                ))

            disposition_type = DispositionType(data.get("disposition_type", "内部"))

            return DispositionAgentOutput(
                disposition_type=disposition_type,
                disposition_reason=data.get("disposition_reason", ""),
                legal_analysis=legal_analysis,
                penalty_opinions=penalty_opinions,
                prosecution_letter=data.get("prosecution_letter"),
                civil_case_summary=data.get("civil_case_summary"),
                internal_remediation=data.get("internal_remediation"),
                involved_personnel=data.get("involved_personnel", []),
                confidence=_safe_confidence(data.get("confidence", "medium")),
                confidence_reason=data.get("confidence_reason", ""),
                disposition_report_doc_id=data.get("disposition_report_doc_id"),
                prosecution_letter_doc_id=data.get("prosecution_letter_doc_id"),
                processing_time_ms=processing_time_ms,
                kb_sources=data.get("kb_sources", []),
                retry_count=retry_count,
                downstream_context=_build_downstream(data, task_id, disposition_type),
            )
        except Exception as e:
            logger.warning("disposition_json_parse_failed", error=str(e))
            return self._fallback_output(task_id, start_time, f"JSON 解析失败: {e}")

    def _fallback_output(self, task_id: str, start_time: float, reason: str) -> DispositionAgentOutput:
        return DispositionAgentOutput(
            disposition_type=DispositionType.INTERNAL,
            disposition_reason=f"AI 服务异常: {reason}，默认建议内部处理，请人工确认",
            legal_analysis=LegalAnalysis(
                applicable_laws=[],
                recommended_path=DispositionType.INTERNAL,
            ),
            confidence=Confidence.UNABLE,
            confidence_reason=reason,
            processing_time_ms=int((time.monotonic() - start_time) * 1000),
        )

    def route_after_disposition(self, disposition_type: DispositionType) -> str:
        """根据处置类型返回路由目标"""
        routing = {
            DispositionType.NO_ACTION: "end",
            DispositionType.CRIMINAL: "prosecution",
            DispositionType.CIVIL: "cicero_a2a",
            DispositionType.INTERNAL: "enforcement",
        }
        return routing.get(disposition_type, "end")


# ── 辅助函数 ────────────────────────────────────────────────────────

def _format_disposition_input(disposition_input: DispositionAgentInput) -> str:
    conclusion = disposition_input.case_conclusion
    lines = [
        f"案件编号: {disposition_input.task_id}",
        f"事业部: {disposition_input.client.value}",
        f"结论摘要: {conclusion.conclusion_summary}",
        f"舞弊类型: {conclusion.fraud_type}",
        f"涉案金额: {conclusion.estimated_total_amount or '未确定'}",
    ]
    if conclusion.confirmed_facts:
        lines.append("已确认事实:")
        for f in conclusion.confirmed_facts[:10]:
            lines.append(f"  - {f}")
    if conclusion.involved_parties:
        lines.append("涉及方:")
        for p in conclusion.involved_parties:
            lines.append(f"  - {p.name} ({p.role}), 涉及程度: {p.involvement_level}")
    return "\n".join(lines)


def _build_downstream(data: dict, task_id: str, disposition_type: DispositionType) -> dict:
    return {
        "protocol_version": "1.0",
        "source_agent": "disposition-agent",
        "target_agent": "enforcement-agent",
        "case_ref": task_id,
        "disposition_type": disposition_type.value,
        "penalty_opinions": data.get("penalty_opinions", []),
        "involved_personnel": data.get("involved_personnel", []),
        "internal_remediation": data.get("internal_remediation"),
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
        {"role": "system", "content": "你是赫尔墨斯风控系统的法律顾问。"},
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
