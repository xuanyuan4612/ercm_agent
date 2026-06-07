"""
处罚执行 Agent (enforcement-agent)

角色：执行协调员
阶段：[4.5] 处罚执行 + 跟踪

核心任务：
  1. 处罚公告生成（脱敏）
  2. 协议/合同生成
  3. A2A 任务分发（龟宝/西塞罗/波特）
  4. 黑名单维护（MDM 同步）
  5. OA 系统同步

状态机：IDLE → DOC_GENERATE → A2A_DISPATCH → SYNC_EXTERNAL → COMPLETE

A2A 目标：
- guibao (龟宝): 员工处罚跟踪
- cicero (西塞罗): 法务协议审核
- porter (波特): 供应商扣款/财务冻结
"""

from __future__ import annotations

import json
import time
from typing import Any

from hermes.agents.integrity.schemas import (
    A2ATaskItem,
    Confidence,
    EnforcementAgentInput,
    EnforcementAgentOutput,
    PenaltyAnnouncement,
)
from hermes.agents.llm_adapter import llm_adapter
from hermes.agents.prompt_manager import prompt_manager
from hermes.core.exceptions import AIServiceUnavailableError
from hermes.core.logging import get_logger

logger = get_logger(__name__)

# A2A 目标 Agent 配置
A2A_TARGETS = {
    "guibao": {
        "name": "龟宝",
        "description": "HR 员工管理智能体",
        "commands": ["initiate_penalty_tracking", "transfer_hr_case", "query_penalty_status"],
    },
    "cicero": {
        "name": "西塞罗",
        "description": "法务智能体",
        "commands": ["push_civil_case", "submit_agreement_review", "query_legal_opinion"],
    },
    "porter": {
        "name": "波特",
        "description": "财务智能体",
        "commands": ["initiate_supplier_deduction", "query_deduction_status"],
    },
}


class EnforcementAgent:
    """处罚执行 Agent — 执行协调员

    职责：
    1. 生成处罚公告（文本脱敏，按发布范围控制可见性）
    2. 生成协议/合同文档
    3. 根据追责类型分发 A2A 任务：
       - 员工处罚 → 龟宝 (HR)
       - 民事追责 → 西塞罗 (法务)
       - 供应商/财务 → 波特 (财务)
    4. 黑名单维护 (MDM 同步)
    5. OA 同步 (任务中心)
    """

    def __init__(self) -> None:
        self.agent_id = "enforcement-agent"
        self.agent_name = "处罚执行 Agent"
        self.role = "执行协调员"
        self.kb_types = ["enforcement", "common"]

    async def run(
        self,
        enforcement_input: EnforcementAgentInput,
        kb_context: str = "",
    ) -> EnforcementAgentOutput:
        """执行处罚

        Args:
            enforcement_input: 处罚执行输入（追责意见、涉及人员）
            kb_context: 知识库检索（黑名单制度、公告模板、协议模板、组织架构）

        Returns:
            EnforcementAgentOutput
        """
        start_time = time.monotonic()
        retry_count = 0

        variables = {
            "case_info": _format_enforcement_input(enforcement_input),
            "kb_context": kb_context or "（无相关知识库内容）",
            "disposition_context": json.dumps(enforcement_input.disposition_context, ensure_ascii=False),
        }

        prompt_text = prompt_manager.render(
            module="integrity",
            stage="enforcement",
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
                return self._parse_response(response, enforcement_input.task_id, start_time, retry_count)
            except AIServiceUnavailableError as e:
                retry_count = attempt
                logger.warning("enforcement_llm_retry", attempt=attempt + 1, error=str(e))
                if attempt < 2:
                    await _sleep_backoff(attempt)
            except Exception as e:
                logger.error("enforcement_unexpected_error", error=str(e))
                break

        return self._fallback_output(enforcement_input.task_id, start_time, "LLM 服务不可用")

    def _parse_response(
        self, response: str, task_id: str, start_time: float, retry_count: int
    ) -> EnforcementAgentOutput:
        processing_time_ms = int((time.monotonic() - start_time) * 1000)

        try:
            data = _extract_json(response)

            # 处罚公告
            announcements = []
            for a in data.get("penalty_announcements", []):
                announcements.append(PenaltyAnnouncement(
                    title=a.get("title", "处罚公告"),
                    content=a.get("content", ""),
                    publish_scope=a.get("publish_scope", "内部"),
                    publish_date=a.get("publish_date"),
                ))

            # A2A 任务
            a2a_tasks = []
            a2a_task_ids = []
            for t in data.get("a2a_tasks", []):
                target = t.get("target_agent", "")
                command = t.get("command", "")
                if target in A2A_TARGETS and command in A2A_TARGETS[target]["commands"]:
                    a2a_tasks.append(A2ATaskItem(
                        target_agent=target,
                        command=command,
                        payload=t.get("payload", {}),
                        priority=t.get("priority", "normal"),
                    ))
                    a2a_task_ids.append(f"a2a-{target}-{task_id}")

            return EnforcementAgentOutput(
                penalty_announcements=announcements,
                agreement_doc_ids=data.get("agreement_doc_ids", []),
                a2a_tasks=a2a_tasks,
                a2a_task_ids=a2a_task_ids,
                blacklist_updates=data.get("blacklist_updates", []),
                sync_tasks=data.get("sync_tasks", []),
                confidence=_safe_confidence(data.get("confidence", "medium")),
                processing_time_ms=processing_time_ms,
                kb_sources=data.get("kb_sources", []),
                retry_count=retry_count,
            )
        except Exception as e:
            logger.warning("enforcement_json_parse_failed", error=str(e))
            return self._fallback_output(task_id, start_time, f"JSON 解析失败: {e}")

    def _fallback_output(self, task_id: str, start_time: float, reason: str) -> EnforcementAgentOutput:
        return EnforcementAgentOutput(
            confidence=Confidence.UNABLE,
            processing_time_ms=int((time.monotonic() - start_time) * 1000),
        )

    def get_a2a_routing(self, penalty_type: str) -> str:
        """根据处罚类型确定 A2A 路由

        - 员工纪律处分 → guibao (龟宝)
        - 法务/协议/合同 → cicero (西塞罗)
        - 供应商/财务扣款 → porter (波特)
        """
        if any(kw in penalty_type for kw in ["员工", "人事", "纪律"]):
            return "guibao"
        if any(kw in penalty_type for kw in ["法务", "合同", "协议", "诉讼"]):
            return "cicero"
        if any(kw in penalty_type for kw in ["供应商", "财务", "扣款", "冻结"]):
            return "porter"
        return "guibao"


# ── 辅助函数 ────────────────────────────────────────────────────────

def _format_enforcement_input(enforcement_input: EnforcementAgentInput) -> str:
    lines = [
        f"案件编号: {enforcement_input.task_id}",
        f"事业部: {enforcement_input.client.value}",
        f"追责意见数: {len(enforcement_input.penalty_opinions)}",
        f"涉及人员数: {len(enforcement_input.involved_personnel)}",
        "",
        "--- 追责意见 ---",
    ]
    for i, p in enumerate(enforcement_input.penalty_opinions, 1):
        lines.append(f"{i}. 对象: {p.target_person}, 类型: {p.penalty_type}")
        lines.append(f"   详情: {p.penalty_detail}")
        lines.append(f"   依据: {p.legal_basis}")
    lines.append("")
    lines.append("--- 涉及人员 ---")
    for i, person in enumerate(enforcement_input.involved_personnel, 1):
        if isinstance(person, dict):
            lines.append(f"{i}. {person.get('name', '未知')} - {person.get('role', '未知')}")
    return "\n".join(lines)


def _parse_system_user(prompt_text: str) -> list[dict]:
    if "[System]" in prompt_text and "[User]" in prompt_text:
        system_part = prompt_text.split("[User]")[0].replace("[System]\n", "").strip()
        user_part = prompt_text.split("[User]")[1].strip()
        return [
            {"role": "system", "content": system_part},
            {"role": "user", "content": user_part},
        ]
    return [
        {"role": "system", "content": "你是赫尔墨斯风控系统的处罚执行协调员。"},
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
