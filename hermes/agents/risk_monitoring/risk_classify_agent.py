"""
风险定性 Agent (risk-classify-agent)

角色：风险定性分析师
阶段：[6.4] 风险类型/等级/处置建议判定

核心任务：
  1. 综合判断风险的性质、等级和影响范围
  2. 自动判定风险类型（合规风险/舞弊风险/商业秘密风险/其他）
  3. 给出处置建议和推送目标模块

评估维度：岗位敏感度 × 金额大小 × 业务影响范围 × 发生频次

参照: doc/agents/02-risk-monitoring-agents.md §三 子阶段3
"""

from __future__ import annotations

import json
import time

from hermes.agents.base import BaseStageAgent
from hermes.core.logging import get_logger
from hermes.schemas.agents.common import Confidence
from hermes.schemas.agents.risk_monitoring import (
    MergedEntityRisk,
    RiskClassification,
    RiskClassifyAgentInput,
    RiskClassifyAgentOutput,
)

logger = get_logger(__name__)


class RiskClassifyAgent(BaseStageAgent):
    """风险定性 Agent — 风险类型/等级/处置建议判定"""

    agent_id = "risk-classify-agent"
    agent_name = "风险定性 Agent"
    module = "risk_monitoring"
    stage = "risk_classify"
    kb_types = ["risk_cases", "disposition_feedback", "risk_rules", "common"]
    role_description = "擅长综合判断风险的性质、等级和影响范围，给出处置建议"

    def __init__(self) -> None:
        super().__init__()
        self._prompt_version = "v1.0"

    async def run(
        self,
        db_session,
        classify_input: RiskClassifyAgentInput,
        kb_context: str = "",
    ) -> RiskClassifyAgentOutput:
        """执行风险定性分析

        Args:
            db_session: 数据库会话（用于KB检索历史案例）
            classify_input: 定性输入（合并后的主体风险列表 + 分析上下文）
            kb_context: 知识库检索上下文（历史风险案例、定级标准、处置指南）

        Returns:
            RiskClassifyAgentOutput: 包含风险分类列表和推送建议
        """
        start_time = time.monotonic()
        merged_entities = classify_input.merged_entities

        if not merged_entities:
            logger.info(
                "risk_classify_no_data",
                task_id=classify_input.task_id,
                message="无合并实体，跳过风险定性",
            )
            return RiskClassifyAgentOutput(
                risk_classifications=[],
                classification_summary={"total_entities": 0},
                sentinel_flags={"rule_optimization_needed": False, "novel_risk_detected": False},
                confidence=Confidence.MEDIUM,
                processing_time_ms=self._elapsed_ms(start_time),
            )

        # 序列化实体数据
        entities_for_classify = []
        for e in merged_entities:
            if isinstance(e, MergedEntityRisk):
                entities_for_classify.append(e.model_dump())
            elif isinstance(e, dict):
                entities_for_classify.append(e)
            else:
                entities_for_classify.append({"raw": str(e)})

        classify_payload = {
            "task_id": classify_input.task_id,
            "entities": entities_for_classify,
            "classification_criteria": {
                "risk_types": ["合规风险", "舞弊风险", "商业秘密风险", "其他"],
                "risk_levels": ["高", "中", "低"],
                "assessment_dimensions": [
                    "岗位敏感度",
                    "金额大小",
                    "业务影响范围",
                    "发生频次",
                ],
                "push_targets": [
                    "integrity_supervision",
                    "internal_control_evaluation",
                    "trade_secrets",
                    "behavioral_risk",
                    "business_department",
                ],
            },
            "kb_context": kb_context,
            "anomaly_summary": classify_input.anomaly_summary,
        }

        messages = [
            {
                "role": "system",
                "content": (
                    "你擅长综合判断风险的性质、等级和影响范围。\n"
                    "综合评估维度：岗位敏感度 × 金额大小 × 业务影响范围 × 发生频次\n"
                    "风险类型：合规风险 / 舞弊风险 / 商业秘密风险 / 其他\n"
                    "风险等级：高 / 中 / 低\n"
                    "对每个风险主体，给出：\n"
                    "1. 风险类型和等级\n"
                    "2. 严重程度和广泛性\n"
                    "3. 影响评估（岗位/金额/业务范围/频次）\n"
                    "4. 处置建议\n"
                    "5. 推送目标模块列表"
                ),
            },
            {"role": "user", "content": json.dumps(classify_payload, ensure_ascii=False)},
        ]

        try:
            response = await self._invoke_llm(messages, temperature=0.3, max_tokens=4096)
            data = self._extract_json(response)

            classifications_raw = data.get("classifications", [])
            classifications = []
            high_risk_count = 0

            for c in classifications_raw:
                risk_level = c.get("risk_level", "中")
                if risk_level == "高":
                    high_risk_count += 1

                classifications.append(RiskClassification(
                    risk_type=c.get("risk_type", "其他"),
                    risk_level=risk_level,
                    severity=c.get("severity", ""),
                    scope=c.get("scope", ""),
                    impact_assessment=c.get("impact_assessment", {}),
                    disposal_suggestion=c.get("disposal_suggestion", ""),
                    push_targets=c.get("push_targets", []),
                ))

            # 哨兵判定
            novel_risk_detected = data.get("novel_risk_detected", False)
            novel_risk_description = data.get("novel_risk_description", "")

            sentinel_flags = {
                "rule_optimization_needed": self._check_rule_optimization(classifications_raw, classify_input),
                "novel_risk_detected": novel_risk_detected,
                "novel_risk_description": novel_risk_description,
                "high_risk_count": high_risk_count,
                "total_classified": len(classifications),
            }

            logger.info(
                "risk_classify_complete",
                task_id=classify_input.task_id,
                total_classified=len(classifications),
                high_risk=high_risk_count,
                novel_risk=novel_risk_detected,
            )

            return RiskClassifyAgentOutput(
                risk_classifications=classifications,
                classification_summary={
                    "total_entities": len(merged_entities),
                    "total_classified": len(classifications),
                    "high_risk_count": high_risk_count,
                    "risk_type_distribution": self._count_risk_types(classifications),
                },
                sentinel_flags=sentinel_flags,
                confidence=self._safe_confidence(data.get("confidence")),
                processing_time_ms=self._elapsed_ms(start_time),
            )
        except Exception as e:
            logger.error("risk_classify_failed", task_id=classify_input.task_id, error=str(e))
            return RiskClassifyAgentOutput(
                risk_classifications=[],
                classification_summary={"error": str(e)[:200]},
                sentinel_flags={"rule_optimization_needed": False, "novel_risk_detected": False, "error": str(e)[:200]},
                confidence=Confidence.UNABLE,
                processing_time_ms=self._elapsed_ms(start_time),
            )

    # ── 辅助方法 ──

    @staticmethod
    def _check_rule_optimization(
        classifications: list[dict],
        classify_input: RiskClassifyAgentInput,
    ) -> bool:
        """检查是否需要规则优化（基于当前扫描的指示性信号）"""
        # 如果有大量低风险分类，可能是规则过于敏感
        low_count = sum(1 for c in classifications if c.get("risk_level") == "低")
        total = len(classifications)
        if total > 0 and low_count / total > 0.5:
            return True
        return classify_input.rule_optimization_signal

    @staticmethod
    def _count_risk_types(classifications: list[RiskClassification]) -> dict[str, int]:
        """统计风险类型分布"""
        dist: dict[str, int] = {}
        for c in classifications:
            dist[c.risk_type] = dist.get(c.risk_type, 0) + 1
        return dist

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
