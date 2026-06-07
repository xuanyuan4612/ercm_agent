"""
分析报告 Agent (analysis-agent)

角色：数据分析师 (15年审计+数据分析经验)
阶段：[4.3] 多维分析 + 案件报告撰写

核心任务：
  1. 多维数据碰撞分析（SQL + ES + PGVector + 音频）
  2. 证据链构建（交叉验证，≥2 独立来源）
  3. 案件结论生成（确认事实、无法确认主张、涉案金额）
  4. 廉洁监察报告撰写（标准模板）

状态机：IDLE → DATA_GATHER → MULTI_SOURCE_ANALYSIS → CONCLUSION_GENERATE → PENDING_APPROVAL
"""

from __future__ import annotations

import json
import time
from typing import Any

from hermes.agents.integrity.schemas import (
    AnalysisAgentInput,
    AnalysisAgentOutput,
    CaseConclusion,
    Confidence,
    EvidenceChainItem,
    EvidenceSufficiency,
    InvolvedParty,
)
from hermes.agents.llm_adapter import llm_adapter
from hermes.agents.prompt_manager import prompt_manager
from hermes.core.exceptions import AIServiceUnavailableError
from hermes.core.logging import get_logger

logger = get_logger(__name__)


class AnalysisAgent:
    """分析报告 Agent — 数据分析师

    职责：
    1. 数据收集：SQL查询 + ES全文检索 + PGVector相似证据 + 音频分析（4路并行）
    2. 多源分析：交叉比对，发现矛盾/印证关系
    3. 证据链构建：串联证据，分级（直接/间接/证言/推测）
    4. 报告生成：案件结论 + 廉洁监察报告

    关键原则：
    - 交叉验证：任何结论需 ≥2 独立来源
    - 证据强度：直接 > 间接 > 证言 > 推测
    - "无法确认"也是合法结论
    """

    def __init__(self) -> None:
        self.agent_id = "analysis-agent"
        self.agent_name = "分析报告 Agent"
        self.role = "数据分析师"
        self.kb_types = ["analysis", "common"]

    async def run(
        self,
        analysis_input: AnalysisAgentInput,
        kb_context: str = "",
        evidence_context: str = "",
    ) -> AnalysisAgentOutput:
        """执行多维分析

        Args:
            analysis_input: 分析输入（含调查方案、碳基上传数据、访谈、走访）
            kb_context: 知识库检索上下文（历史报告、模板）
            evidence_context: ES/PGVector 检索的证据上下文

        Returns:
            AnalysisAgentOutput
        """
        start_time = time.monotonic()
        retry_count = 0

        # 汇总多源数据为上下文注入
        sql_text = _format_list_section("SQL分析结果", analysis_input.sql_analysis_results)
        system_text = _format_list_section("智能体分析结果", analysis_input.system_analysis_results)
        manual_text = _format_list_section("人工上传数据", analysis_input.manual_upload_results)
        interview_text = _format_list_section("访谈记录", analysis_input.interview_transcripts)
        interview_summary_text = _format_list_section("访谈纪要", analysis_input.interview_summaries)
        site_visit_text = _format_list_section("现场走访", analysis_input.site_visit_reports)

        variables = {
            "case_info": _format_analysis_input(analysis_input),
            "kb_context": kb_context or "（无相关知识库内容）",
            "investigation_context": json.dumps(analysis_input.investigation_context, ensure_ascii=False),
            "intake_context": json.dumps(analysis_input.intake_context, ensure_ascii=False),
            "sql_results": sql_text,
            "system_results": system_text,
            "manual_results": manual_text,
            "interview_transcripts": interview_text,
            "interview_summaries": interview_summary_text,
            "site_visit_reports": site_visit_text,
            "evidence_context": evidence_context or "（无额外证据检索结果）",
        }

        prompt_text = prompt_manager.render(
            module="integrity",
            stage="analysis",
            variables=variables,
        )

        messages = _parse_system_user(prompt_text)

        for attempt in range(3):
            try:
                response = await llm_adapter.invoke(
                    messages,
                    temperature=0.2,
                    max_tokens=8192,
                    timeout=45,
                )
                return self._parse_response(response, analysis_input, start_time, retry_count)
            except AIServiceUnavailableError as e:
                retry_count = attempt
                logger.warning("analysis_llm_retry", attempt=attempt + 1, error=str(e))
                if attempt < 2:
                    await _sleep_backoff(attempt)
            except Exception as e:
                logger.error("analysis_unexpected_error", error=str(e))
                break

        return self._fallback_output(analysis_input.task_id, start_time, "LLM 服务不可用")

    def _parse_response(
        self,
        response: str,
        analysis_input: AnalysisAgentInput,
        start_time: float,
        retry_count: int,
    ) -> AnalysisAgentOutput:
        processing_time_ms = int((time.monotonic() - start_time) * 1000)

        try:
            data = _extract_json(response)
            conclusion_data = data.get("case_conclusion", data)

            # 证据链
            evidence_chain = []
            for e in conclusion_data.get("evidence_chain", []):
                evidence_chain.append(EvidenceChainItem(
                    claim=e.get("claim", ""),
                    evidence_ids=e.get("evidence_ids", []),
                    strength=e.get("strength", "indirect"),
                ))

            # 涉及方
            involved_parties = []
            for p in conclusion_data.get("involved_parties", []):
                involved_parties.append(InvolvedParty(
                    name=p.get("name", ""),
                    role=p.get("role", ""),
                    involvement_level=p.get("involvement_level", "medium"),
                ))

            case_conclusion = CaseConclusion(
                conclusion_summary=conclusion_data.get("conclusion_summary", ""),
                fraud_type=conclusion_data.get("fraud_type", ""),
                confirmed_facts=conclusion_data.get("confirmed_facts", []),
                unconfirmed_claims=conclusion_data.get("unconfirmed_claims", []),
                evidence_chain=evidence_chain,
                involved_parties=involved_parties,
                estimated_total_amount=conclusion_data.get("estimated_total_amount"),
                root_cause_analysis=conclusion_data.get("root_cause_analysis"),
            )

            evidence_suff = _safe_evidence_sufficiency(data.get("evidence_sufficiency", "partial"))

            return AnalysisAgentOutput(
                case_conclusion=case_conclusion,
                data_analysis_summary=data.get("data_analysis_summary"),
                interview_analysis_summary=data.get("interview_analysis_summary"),
                site_visit_analysis_summary=data.get("site_visit_analysis_summary"),
                confidence=_safe_confidence(data.get("confidence", "medium")),
                confidence_reason=data.get("confidence_reason", ""),
                evidence_sufficiency=evidence_suff,
                processing_time_ms=processing_time_ms,
                tools_used=["llm_invoke"],
                kb_sources=data.get("kb_sources", []),
                retry_count=retry_count,
                downstream_context=_build_downstream(data, analysis_input.task_id, case_conclusion),
            )
        except Exception as e:
            logger.warning("analysis_json_parse_failed", error=str(e))
            return self._fallback_output(analysis_input.task_id, start_time, f"JSON 解析失败: {e}")

    def _fallback_output(self, task_id: str, start_time: float, reason: str) -> AnalysisAgentOutput:
        return AnalysisAgentOutput(
            case_conclusion=CaseConclusion(
                conclusion_summary=f"AI 服务异常，无法自动生成结论。{reason}",
                fraud_type="未知",
                confirmed_facts=[],
                unconfirmed_claims=["所有主张待人工确认"],
                evidence_chain=[],
                involved_parties=[],
            ),
            confidence=Confidence.UNABLE,
            confidence_reason=reason,
            evidence_sufficiency=EvidenceSufficiency.INSUFFICIENT,
            processing_time_ms=int((time.monotonic() - start_time) * 1000),
        )


# ── 辅助函数 ────────────────────────────────────────────────────────

def _format_analysis_input(analysis_input: AnalysisAgentInput) -> str:
    lines = [
        f"案件编号: {analysis_input.task_id}",
        f"事业部: {analysis_input.client.value}",
        f"证据文件数: {len(analysis_input.evidence_files)}",
    ]
    sql_count = len(analysis_input.sql_analysis_results or [])
    interview_count = len(analysis_input.interview_transcripts or [])
    site_visit_count = len(analysis_input.site_visit_reports or [])
    lines.append(f"数据汇总: SQL结果 {sql_count}份, 访谈 {interview_count}份, 现场走访 {site_visit_count}份")
    return "\n".join(lines)


def _format_list_section(title: str, items: Any) -> str:
    if not items:
        return f"（无{title}数据）"
    lines = [f"【{title}】"]
    if isinstance(items, list):
        for i, item in enumerate(items[:10], 1):
            if isinstance(item, dict):
                lines.append(f"  {i}. {json.dumps(item, ensure_ascii=False)[:500]}")
            else:
                lines.append(f"  {i}. {str(item)[:500]}")
    else:
        lines.append(str(items)[:2000])
    return "\n".join(lines)


def _build_downstream(data: dict, task_id: str, conclusion: CaseConclusion) -> dict:
    return {
        "protocol_version": "1.0",
        "source_agent": "analysis-agent",
        "target_agent": "disposition-agent",
        "case_ref": task_id,
        "conclusion_summary": conclusion.conclusion_summary,
        "fraud_type": conclusion.fraud_type,
        "confirmed_facts": conclusion.confirmed_facts,
        "estimated_total_amount": conclusion.estimated_total_amount,
        "evidence_sufficiency": len(conclusion.evidence_chain),
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
        {"role": "system", "content": "你是赫尔墨斯风控系统的舞弊调查分析师。"},
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


def _safe_evidence_sufficiency(value: Any) -> EvidenceSufficiency:
    if isinstance(value, EvidenceSufficiency):
        return value
    mapping = {"sufficient": EvidenceSufficiency.SUFFICIENT, "partial": EvidenceSufficiency.PARTIAL, "insufficient": EvidenceSufficiency.INSUFFICIENT}
    return mapping.get(str(value).lower(), EvidenceSufficiency.PARTIAL)


async def _sleep_backoff(attempt: int) -> None:
    import asyncio
    delays = [2, 4]
    delay = delays[attempt] if attempt < len(delays) else 4
    await asyncio.sleep(delay)
