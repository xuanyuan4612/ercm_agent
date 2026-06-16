"""
访谈 Agent (interview-agent) ⭐ 跨模块共享

角色：访谈协调师（精通审计访谈方法论和问卷设计）
阶段：访谈计划 + 问卷生成 + 结论完整性分析

核心任务：
  1. 匹配访谈人员 → 生成访谈计划
  2. 生成结构化访谈问卷（每人定制）
  3. 分析访谈结论完整性，判断是否需要补充提问

共享范围：内控评价 + 专项审计 + 离任审计 + 廉洁监察（最广泛共享的Agent）

参照: doc/agents/03-internal-control-evaluation-agents.md §四
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
    InterviewAgentInput,
    InterviewAgentOutput,
    InterviewQuestionnaire,
)

logger = get_logger(__name__)


class InterviewAgent(BaseStageAgent):
    """访谈 Agent — 访谈协调师 ⭐"""

    agent_id = "interview-agent"
    agent_name = "访谈 Agent"
    module = "ic_evaluation"
    stage = "interview"
    kb_types = ["interview_template", "position_duty", "common"]
    role_description = "专业审计访谈协调师，精通FCPA、IIA审计访谈标准和心理学沟通技巧"

    def __init__(self) -> None:
        super().__init__()
        self._prompt_version = "v1.0"

    async def run(
        self,
        db_session,
        interview_input: InterviewAgentInput,
        kb_context: str = "",
        interview_results: list[dict] | None = None,
    ) -> InterviewAgentOutput:
        """执行访谈任务（计划/问卷/结论分析）"""
        start_time = time.monotonic()

        # 如果提供了访谈结果，执行结论分析
        if interview_results:
            return await self._analyze_conclusions(interview_input, interview_results, kb_context, start_time)

        # 否则生成访谈计划和问卷
        prompt_text = prompt_manager.render(
            module="ic_evaluation",
            stage="interview_plan",
            variables={
                "calling_module": interview_input.calling_module,
                "audit_plan_summary": interview_input.audit_plan_summary,
                "target_departments": json.dumps(interview_input.target_departments, ensure_ascii=False),
                "target_positions": json.dumps(interview_input.target_positions, ensure_ascii=False),
                "question_focus_areas": json.dumps(interview_input.question_focus_areas, ensure_ascii=False),
                "kb_context": kb_context,
            },
        )

        messages = self._parse_prompt_to_messages(prompt_text)

        try:
            response = await self._invoke_llm(
                messages,
                temperature=0.5,  # 问卷需要灵活性和口语化
                max_tokens=4096,
            )
            return self._parse_plan_response(response, start_time)
        except Exception as e:
            logger.error("interview_agent_failed", error=str(e))
            return InterviewAgentOutput(
                interview_plan={},
                questionnaires=[],
                confidence=Confidence.UNABLE,
                processing_time_ms=self._elapsed_ms(start_time),
            )

    async def _analyze_conclusions(
        self,
        interview_input: InterviewAgentInput,
        interview_results: list[dict],
        kb_context: str,
        start_time: float,
    ) -> InterviewAgentOutput:
        """访谈后结论完整性分析"""
        messages = [
            {"role": "system", "content": "你擅长分析访谈记录的完整性，判断是否有遗漏或矛盾。"},
            {"role": "user", "content": json.dumps({
                "audit_plan_summary": interview_input.audit_plan_summary,
                "interview_results": interview_results,
                "kb_context": kb_context,
            }, ensure_ascii=False)},
        ]

        try:
            response = await self._invoke_llm(messages, temperature=0.3, max_tokens=4096)
            data = self._extract_json(response)

            return InterviewAgentOutput(
                interview_plan={},
                questionnaires=[],
                interview_conclusion_analysis=data.get("conclusion_analysis", ""),
                need_follow_up=data.get("need_follow_up", False),
                follow_up_questions=data.get("follow_up_questions"),
                confidence=self._safe_confidence(data.get("confidence")),
                processing_time_ms=self._elapsed_ms(start_time),
            )
        except Exception as e:
            logger.warning("interview_conclusion_failed", error=str(e))
            return InterviewAgentOutput(
                interview_plan={},
                questionnaires=[],
                interview_conclusion_analysis="结论分析失败",
                need_follow_up=True,
                confidence=Confidence.LOW,
                processing_time_ms=self._elapsed_ms(start_time),
            )

    def _parse_plan_response(self, response: str, start_time: float) -> InterviewAgentOutput:
        """解析访谈计划和问卷响应"""
        processing_time_ms = self._elapsed_ms(start_time)
        try:
            data = self._extract_json(response)
            questionnaires = []
            for q in data.get("questionnaires", []):
                questionnaires.append(InterviewQuestionnaire(
                    target_person=q.get("target_person", ""),
                    position=q.get("position", ""),
                    department=q.get("department", ""),
                    interview_strategy=q.get("interview_strategy", ""),
                    questions=q.get("questions", []),
                    estimated_duration_min=q.get("estimated_duration_min", 30),
                ))

            return InterviewAgentOutput(
                interview_plan=data.get("interview_plan", {}),
                questionnaires=questionnaires,
                confidence=self._safe_confidence(data.get("confidence")),
                processing_time_ms=processing_time_ms,
            )
        except Exception as e:
            logger.warning("interview_parse_failed", error=str(e))
            return InterviewAgentOutput(
                interview_plan={},
                questionnaires=[],
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
            {"role": "system", "content": "你是赫尔墨斯风控系统的审计访谈协调师。"},
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
