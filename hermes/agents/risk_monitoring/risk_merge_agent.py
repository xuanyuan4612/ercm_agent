"""
风险合并 Agent (risk-merge-agent)

角色：主体识别与合并分析师
阶段：[6.3] 主体识别与合并去重

核心任务：
  1. 从散乱的异常记录中识别同一分析主体（人/公司/联系方式）
  2. 按联系方式/姓名/地址进行模糊匹配合并
  3. 生成单主体风险透视表和风险分析报告

合并规则：
  - 同一联系方式（电话/邮箱）→ 同一主体
  - 同一姓名/公司名（模糊匹配）→ 同一主体
  - 同一地址 → 同一主体

参照: doc/agents/02-risk-monitoring-agents.md §三 子阶段2
"""

from __future__ import annotations

import json
import time

from hermes.agents.base import BaseStageAgent
from hermes.core.logging import get_logger
from hermes.schemas.agents.common import Confidence
from hermes.schemas.agents.risk_monitoring import (
    AnomalyRecord,
    MergedEntityRisk,
    RiskMergeAgentInput,
    RiskMergeAgentOutput,
)

logger = get_logger(__name__)


class RiskMergeAgent(BaseStageAgent):
    """风险合并 Agent — 主体识别与合并去重"""

    agent_id = "risk-merge-agent"
    agent_name = "风险合并 Agent"
    module = "risk_monitoring"
    stage = "entity_merge"
    kb_types = ["risk_cases", "risk_rules", "common"]
    role_description = "擅长从散乱的异常记录中识别出同一分析主体，进行去重合并"

    def __init__(self) -> None:
        super().__init__()
        self._prompt_version = "v1.0"

    async def run(
        self,
        db_session,
        merge_input: RiskMergeAgentInput,
        kb_context: str = "",
    ) -> RiskMergeAgentOutput:
        """执行主体识别与合并

        Args:
            db_session: 数据库会话（用于KB检索）
            merge_input: 合并输入（异常记录列表 + 合并配置）
            kb_context: 知识库检索上下文（历史合并案例参考）

        Returns:
            RiskMergeAgentOutput: 包含合并后的主体风险列表和合并逻辑说明
        """
        start_time = time.monotonic()
        anomaly_records = merge_input.anomaly_records

        if not anomaly_records:
            logger.info(
                "risk_merge_no_data",
                task_id=merge_input.task_id,
                message="无异常数据，跳过主体合并",
            )
            return RiskMergeAgentOutput(
                merged_entities=[],
                entity_merge_rationale="无异常数据，跳过主体合并",
                merged_pivot_table_doc_id=None,
                single_entity_reports=[],
                sentinel_flags={"merge_issues_detected": False},
                confidence=Confidence.MEDIUM,
                processing_time_ms=self._elapsed_ms(start_time),
            )

        # 构建合并请求
        # 将 AnomalyRecord 序列化为 dict 供 LLM 处理
        records_for_merge = []
        for r in anomaly_records:
            if isinstance(r, AnomalyRecord):
                records_for_merge.append(r.model_dump())
            elif isinstance(r, dict):
                records_for_merge.append(r)
            else:
                records_for_merge.append({"raw": str(r)})

        merge_payload = {
            "task_id": merge_input.task_id,
            "anomaly_records": records_for_merge,
            "merge_rules": {
                "contact_match": "同一联系方式（电话/邮箱）→ 同一主体",
                "name_fuzzy_match": "同一姓名/公司名（模糊匹配）→ 同一主体",
                "address_match": "同一地址 → 同一主体",
            },
            "kb_context": kb_context,
        }

        messages = [
            {
                "role": "system",
                "content": (
                    "你擅长从散乱的异常记录中识别出同一分析主体（人/公司/联系方式）。\n"
                    "合并规则：\n"
                    "1. 同一联系方式（电话/邮箱）→ 同一主体\n"
                    "2. 同一姓名/公司名（模糊匹配，考虑同音字、简繁体、常见拼写变体）→ 同一主体\n"
                    "3. 同一地址 → 同一主体\n"
                    "请对每条异常记录进行主体识别，将属于同一主体的记录合并，"
                    "并标记每个主体涉及的指标数量和最严重的风险信号。"
                ),
            },
            {"role": "user", "content": json.dumps(merge_payload, ensure_ascii=False)},
        ]

        try:
            response = await self._invoke_llm(messages, temperature=0.2, max_tokens=4096)
            data = self._extract_json(response)

            merged_raw = data.get("merged_entities", [])
            rationale = data.get("rationale", "")

            # 构建结构化的合并实体
            merged_entities = []
            for m in merged_raw:
                entity_records = []
                for ar in m.get("anomaly_records", []):
                    entity_records.append(AnomalyRecord(
                        rule_id=ar.get("rule_id", ""),
                        rule_level3_scenario=ar.get("rule_level3_scenario", ""),
                        anomaly_detail=ar.get("anomaly_detail", {}),
                        ai_initial_judgment=ar.get("ai_initial_judgment", "abnormal"),
                        ai_judgment_reason=ar.get("ai_judgment_reason", ""),
                        anomaly_score=float(ar.get("anomaly_score", 0.0)),
                    ))

                merged_entities.append(MergedEntityRisk(
                    entity_id=m.get("entity_id", ""),
                    entity_type=m.get("entity_type", "contact"),
                    anomaly_count=m.get("anomaly_count", len(entity_records)),
                    anomaly_records=entity_records,
                    involved_indicators=m.get("involved_indicators", []),
                ))

            # 哨兵：检测合并问题
            merge_issues = []
            total_records_input = len(anomaly_records)
            total_records_merged = sum(len(me.anomaly_records) for me in merged_entities)
            if total_records_merged < total_records_input:
                merge_issues.append(f"输入{total_records_input}条，合并后仅{total_records_merged}条，可能存在遗漏")

            sentinel_flags = {
                "merge_issues_detected": len(merge_issues) > 0,
                "merge_issues": merge_issues,
                "input_count": total_records_input,
                "merged_entity_count": len(merged_entities),
                "merged_record_count": total_records_merged,
            }

            logger.info(
                "risk_merge_complete",
                task_id=merge_input.task_id,
                input_records=total_records_input,
                merged_entities=len(merged_entities),
                issues=len(merge_issues),
            )

            return RiskMergeAgentOutput(
                merged_entities=merged_entities,
                entity_merge_rationale=rationale,
                merged_pivot_table_doc_id=None,
                single_entity_reports=data.get("single_entity_reports", []),
                sentinel_flags=sentinel_flags,
                confidence=self._safe_confidence(data.get("confidence")),
                processing_time_ms=self._elapsed_ms(start_time),
            )
        except Exception as e:
            logger.error("risk_merge_failed", task_id=merge_input.task_id, error=str(e))
            return RiskMergeAgentOutput(
                merged_entities=[],
                entity_merge_rationale=f"主体合并失败: {str(e)[:200]}",
                merged_pivot_table_doc_id=None,
                single_entity_reports=[],
                sentinel_flags={"merge_issues_detected": True, "error": str(e)[:200]},
                confidence=Confidence.UNABLE,
                processing_time_ms=self._elapsed_ms(start_time),
            )

    # ── 辅助方法 ──

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
    def _safe_confidence(value) -> Confidence:
        if isinstance(value, Confidence):
            return value
        mapping = {"high": Confidence.HIGH, "medium": Confidence.MEDIUM, "low": Confidence.LOW, "unable": Confidence.UNABLE}
        return mapping.get(str(value).lower() if isinstance(value, str) else "", Confidence.MEDIUM)
