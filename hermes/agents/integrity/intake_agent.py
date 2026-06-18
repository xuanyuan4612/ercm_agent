"""
初筛 Agent (intake-agent)

角色：案件初审官 (15年反舞弊调查经验)
阶段：[4.1] 材料初判 + 分流决策

核心任务：
  1. 分析案件材料（文本、附件、语音转录）
  2. 检索相关制度法规和过往案例
  3. 评估线索可信度，判断案件性质和严重程度
  4. 做出分流决策：不处理 / 转交 / 继续调查
  5. 标记是否为 HR 管辖

状态机：IDLE → KB_RETRIEVE → EVIDENCE_ANALYZE → TRIAGE_DECIDE → PENDING_APPROVAL
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from hermes.agents.integrity.schemas import (
    Confidence,
    IntakeAgentInput,
    IntakeAgentOutput,
    LegalReference,
    RiskLevel,
    TransferTarget,
    TriagedEntityType,
    Urgency,
)
from hermes.agents.llm_adapter import llm_adapter
from hermes.agents.prompt_manager import prompt_manager
from hermes.core.exceptions import AIServiceUnavailableError
from hermes.core.logging import get_logger

logger = get_logger(__name__)

# 一级标题模式，用于应急解析自由文本输出
SECTION_PATTERNS = {
    "case_summary": re.compile(r"(?:案件摘要|案情概要)[：:]\s*(.+?)(?=\n[#＃]|\n[A-Za-z一-鿿]{2,10}[：:]|\Z)", re.DOTALL),
    "should_investigate": re.compile(r"(?:是否立案|立案建议)[：:]\s*(.+?)(?=\n)", re.DOTALL),
    "risk_level": re.compile(r"(?:风险等级)[：:]\s*(高|中|低)"),
    "confidence": re.compile(r"(?:置信度)[：:]\s*(high|medium|low|unable)", re.IGNORECASE),
}

# 涉及金额 >100万 强制升级阈值
HIGH_AMOUNT_THRESHOLD = 1_000_000


class IntakeAgent:
    """初筛 Agent — 案件初审官

    职责：
    1. 知识库检索：组织架构、制度法规、人员名单、供应商清单、历史案例
    2. 证据分析：附件文本、语音转录、举报信息，提取关键事实
    3. 分流决策：是否立案、是否转交、是否 HR 管辖
    4. 生成初判报告

    降级：
    - LLM 不可用 → 切换备用 LLM → 仍失败则进入 human_intervention
    - KB 检索为空 → 标记置信度 low，依赖 LLM 内部知识
    - 语音转录未完成 → 跳过语音证据分析
    - 上游字段严重缺失 → 置信度 unable，直接进入 human_intervention
    """

    def __init__(self) -> None:
        self.agent_id = "intake-agent"
        self.agent_name = "初筛 Agent"
        self.role = "案件初审官"
        self.kb_types = ["intake", "common"]
        self._prompt_version = "v1.0"

    async def run(
        self,
        case_input: IntakeAgentInput,
        kb_context: str = "",
        similar_cases_context: str = "",
    ) -> IntakeAgentOutput:
        """执行初筛分析

        Args:
            case_input: 案件输入 (Pydantic 模型)
            kb_context: 知识库检索上下文
            similar_cases_context: 历史相似案例上下文

        Returns:
            IntakeAgentOutput: 结构化输出
        """
        start_time = time.monotonic()

        # 1. 上游字段校验
        if len(case_input.fraud_event_detail.strip()) < 10:
            logger.warning("intake_insufficient_input", task_id=case_input.task_id)
            return self._build_unable_output(case_input.task_id, start_time, "案件描述不足10字符，无法判断")

        # 2. 构建 Prompt
        prompt_text = prompt_manager.render(
            module="integrity",
            stage="intake",
            variables={
                "case_info": _format_case_from_input(case_input),
                "kb_context": kb_context or "（无相关知识库检索结果）",
                "similar_cases": similar_cases_context or "（无相似历史案例）",
                "upstream_context": json.dumps(_build_upstream_dict(case_input), ensure_ascii=False),
            },
        )

        # 3. 解析 System/User 段落（附加 JSON 输出格式定义）
        output_schema = _build_output_format(IntakeAgentOutput)
        messages = _parse_prompt_to_messages(prompt_text)
        messages[-1]["content"] += (
            "\n\n【严格输出格式 — 直接输出下面的JSON，不要修改字段名】\n"
            "重要：整个响应应该是一段纯JSON，以 { 开头、以 } 结束。\n"
            "不要将JSON包裹在markdown代码块中，不要添加额外说明文字。\n"
            "每个字段的值必须是你在JSON中直接填写的，而不是将整个输出放入某个字段。\n\n"
            f"需要的JSON格式（用实际分析内容替换示例值）：\n{output_schema}"
        )

        # 4. 调用 LLM
        retry_count = 0
        last_error: Exception | None = None

        for attempt in range(3):  # 最多3次尝试
            try:
                response = await llm_adapter.invoke(
                    messages,
                    temperature=0.3,
                    max_tokens=4096,
                )
                return self._parse_response(response, case_input.task_id, start_time, retry_count)
            except AIServiceUnavailableError as e:
                last_error = e
                retry_count = attempt
                logger.warning("intake_llm_retry", attempt=attempt + 1, error=str(e))
                if attempt < 2:
                    await _sleep_backoff(attempt)
            except Exception as e:
                last_error = e
                logger.error("intake_unexpected_error", error=str(e))
                break

        # 5. 降级：LLM 全部失败
        logger.error("intake_all_llm_failed", task_id=case_input.task_id, error=str(last_error))
        return self._fallback_output(case_input.task_id, start_time, str(last_error))

    def _parse_response(
        self,
        response: str,
        task_id: str,
        start_time: float,
        retry_count: int,
    ) -> IntakeAgentOutput:
        """解析 LLM 响应为结构化输出"""
        processing_time_ms = int((time.monotonic() - start_time) * 1000)

        # 尝试 JSON 解析
        try:
            data = _extract_json(response)
            return _build_output_from_data(data, task_id, processing_time_ms, retry_count)
        except (json.JSONDecodeError, KeyError) as e:
            logger.info("intake_direct_parse_failed", error=str(e), task_id=task_id)
        except Exception as parse_err:
            logger.warning("intake_json_parse_failed", error=str(parse_err), task_id=task_id)
            # 如果 Pydantic 验证失败，尝试从嵌套的 case_summary 中提取
            try:
                data = _extract_json(response)
                # 检测 LLM 是否将整个输出嵌套在 case_summary 字段内
                if isinstance(data.get("case_summary"), dict):
                    logger.info("intake_detected_nested_output, extracting from case_summary")
                    nested = data["case_summary"]
                    return _build_output_from_data(nested, task_id, processing_time_ms, retry_count)
                # 检测是否嵌套在顶层对象的第一个字段中
                for key in ("case_summary", "case_review_report", "analysis"):
                    if isinstance(data.get(key), dict):
                        nested = data[key]
                        if any(f in nested for f in ("should_investigate", "risk_level")):
                            logger.info(f"intake_detected_nested_{key}, extracting")
                            return _build_output_from_data(nested, task_id, processing_time_ms, retry_count)
            except Exception:
                pass
            # 降级为自由文本解析
            return self._parse_free_text(response, task_id, processing_time_ms, retry_count)

    def _parse_free_text(
        self, response: str, task_id: str, processing_time_ms: int, retry_count: int
    ) -> IntakeAgentOutput:
        """应急解析非 JSON 自由文本输出"""
        summary = _extract_section(response, "case_summary", response[:500])
        should_inv = "立案" in response and "不立案" not in response
        risk = RiskLevel.MEDIUM
        risk_match = SECTION_PATTERNS["risk_level"].search(response)
        if risk_match:
            risk = _safe_risk_level(risk_match.group(1))

        return IntakeAgentOutput(
            case_summary=summary,
            key_facts=["LLM 输出格式异常，以下为原始输出摘要"],
            involved_entity_type=TriagedEntityType.MIXED,
            should_investigate=should_inv,
            investigation_reason="（JSON 解析失败，以下为原始输出摘要）",
            should_transfer=False,
            transfer_target=TransferTarget.NONE,
            is_hr_related=False,
            risk_level=risk,
            urgency=Urgency.NORMAL,
            confidence=Confidence.LOW,
            confidence_reason="LLM 输出格式异常，已降级解析",
            uncertainty_factors=["输出格式非标准JSON"],
            missing_information=["需人工复核"],
            processing_time_ms=processing_time_ms,
            retry_count=retry_count,
            downstream_context={"raw_response": response[:2000]},
        )

    def _fallback_output(
        self, task_id: str, start_time: float, error_msg: str
    ) -> IntakeAgentOutput:
        """LLM 完全不可用时的降级输出"""
        return IntakeAgentOutput(
            case_summary="（AI 服务暂时不可用，建议人工初判）",
            key_facts=["AI 服务不可用，所有分析结论需人工判定"],
            involved_entity_type=TriagedEntityType.MIXED,
            should_investigate=True,
            investigation_reason="AI 服务不可用，默认立案建议（需人工确认）",
            should_transfer=False,
            transfer_target=TransferTarget.NONE,
            is_hr_related=False,
            risk_level=RiskLevel.HIGH,
            urgency=Urgency.NORMAL,
            confidence=Confidence.UNABLE,
            confidence_reason=f"LLM 调用全部失败: {error_msg[:200]}",
            uncertainty_factors=["AI 服务不可用", "所有分析结论需人工判定"],
            missing_information=["需人工完成全部分析"],
            processing_time_ms=int((time.monotonic() - start_time) * 1000),
        )

    @staticmethod
    def _build_unable_output(task_id: str, start_time: float, reason: str) -> IntakeAgentOutput:
        """信息严重不足时的 unable 输出"""
        return IntakeAgentOutput(
            case_summary=f"无法完成初判：{reason}",
            key_facts=[f"输入信息严重不足: {reason}"],
            involved_entity_type=TriagedEntityType.MIXED,
            should_investigate=False,
            investigation_reason=reason,
            should_transfer=False,
            transfer_target=TransferTarget.NONE,
            is_hr_related=False,
            risk_level=RiskLevel.LOW,
            urgency=Urgency.LOW,
            confidence=Confidence.UNABLE,
            confidence_reason=reason,
            uncertainty_factors=["输入信息严重不足"],
            missing_information=["需补充足够的案件描述信息"],
            processing_time_ms=int((time.monotonic() - start_time) * 1000),
        )


# ── 辅助函数 ────────────────────────────────────────────────────────

def _format_case_from_input(case_input: IntakeAgentInput) -> str:
    """将 IntakeAgentInput 格式化为 Prompt 文本"""
    lines = [
        f"案件编号: {case_input.task_id}",
        f"来源: {case_input.fraud_source.value}",
        f"事业部: {case_input.client.value}",
        f"举报内容: {case_input.fraud_event_detail}",
    ]

    if case_input.reported_staff_names:
        lines.append(f"涉及员工: {', '.join(case_input.reported_staff_names)}")
    if case_input.reported_supplier_names:
        lines.append(f"涉及供应商: {', '.join(case_input.reported_supplier_names)}")
    if case_input.reported_dealer_names:
        lines.append(f"涉及经销商: {', '.join(case_input.reported_dealer_names)}")

    # 音频转录摘要
    if case_input.audio_transcriptions:
        audio_summaries = []
        for at in case_input.audio_transcriptions[:3]:
            snippet = at.text[:300] + "..." if len(at.text) > 300 else at.text
            audio_summaries.append(f"  [{at.file_id}] ({at.language}): {snippet}")
        lines.append("语音转录:\n" + "\n".join(audio_summaries))

    # OCR 关键文本
    if case_input.ocr_texts:
        ocr_summaries = []
        for ocr in case_input.ocr_texts[:3]:
            snippet = ocr.text[:300] + "..." if len(ocr.text) > 300 else ocr.text
            ocr_summaries.append(f"  [{ocr.file_id}]: {snippet}")
        lines.append("图片OCR:\n" + "\n".join(ocr_summaries))

    if case_input.reported_files:
        lines.append(f"附件数量: {len(case_input.reported_files)}")
    if case_input.recording_files:
        lines.append(f"录音文件数: {len(case_input.recording_files)}")
    if case_input.image_files:
        lines.append(f"图片文件数: {len(case_input.image_files)}")

    return "\n".join(lines)


def _build_upstream_dict(case_input: IntakeAgentInput) -> dict:
    """构建上游案件上下文字典"""
    return {
        "protocol_version": case_input.context_version,
        "source": "risk_control_system",
        "case_data": {
            "task_id": case_input.task_id,
            "fraud_source": case_input.fraud_source.value,
            "client": case_input.client.value,
            "has_audio": len(case_input.recording_files) > 0,
            "has_images": len(case_input.image_files) > 0,
            "has_documents": len(case_input.reported_files) > 0,
        },
    }


def _build_downstream_context(data: dict, task_id: str) -> dict:
    """构建传递给 investigation-agent 的下游上下文"""
    return {
        "protocol_version": "1.0",
        "source_agent": "intake-agent",
        "target_agent": "investigation-agent",
        "case_ref": task_id,
        "confidence": data.get("confidence", "medium"),
        "key_findings": data.get("key_facts", []),
        "outstanding_questions": data.get("uncertainty_factors", []),
        "suggested_focus": data.get("suggested_next_steps", []),
        "risk_flags": _extract_risk_flags(data),
        "evidence_summary": {
            "key_evidence_ids": data.get("kb_sources", []),
        },
    }


def _extract_risk_flags(data: dict) -> list[str]:
    """提取风险标记"""
    flags = []
    risk = data.get("risk_level", "")
    if risk == "高":
        flags.append("高风险案件")
    amount = data.get("estimated_amount_range", "")
    if amount and any(w in str(amount) for w in ["百万", "千万", "亿", "100万"]):
        flags.append("涉及金额较大")
    if data.get("is_hr_related"):
        flags.append("涉及HR管辖")
    return flags


def _parse_prompt_to_messages(prompt_text: str) -> list[dict]:
    """将 prompt_manager 的输出解析为 messages 列表"""
    if "[System]" in prompt_text and "[User]" in prompt_text:
        system_part = prompt_text.split("[User]")[0].replace("[System]\n", "").strip()
        user_part = prompt_text.split("[User]")[1].strip()
        return [
            {"role": "system", "content": system_part},
            {"role": "user", "content": user_part},
        ]
    return [
        {"role": "system", "content": "你是赫尔墨斯风控系统的案件初审专家。"},
        {"role": "user", "content": prompt_text},
    ]


def _extract_json(text: str) -> dict:
    """从 LLM 响应中提取 JSON"""
    text = text.strip()
    # 去除 markdown 代码块包裹
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:]) if len(lines) > 1 else text
        if text.endswith("```"):
            text = text[:-3]
    # 查找 JSON 边界
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        return json.loads(text[start:end])
    raise ValueError("No JSON found in response")


def _extract_section(text: str, section_key: str, default: str) -> str:
    """从自由文本中按标题提取段落"""
    pattern = SECTION_PATTERNS.get(section_key)
    if pattern:
        match = pattern.search(text)
        if match:
            return match.group(1).strip()[:500]
    return default


def _safe_risk_level(value: Any) -> RiskLevel:
    if isinstance(value, RiskLevel):
        return value
    mapping = {"高": RiskLevel.HIGH, "中": RiskLevel.MEDIUM, "低": RiskLevel.LOW}
    return mapping.get(str(value), RiskLevel.MEDIUM)


def _safe_urgency(value: Any) -> Urgency:
    if isinstance(value, Urgency):
        return value
    mapping = {"紧急": Urgency.URGENT, "一般": Urgency.NORMAL, "低": Urgency.LOW}
    return mapping.get(str(value), Urgency.NORMAL)


def _safe_confidence(value: Any) -> Confidence:
    if isinstance(value, Confidence):
        return value
    mapping = {
        "high": Confidence.HIGH,
        "medium": Confidence.MEDIUM,
        "low": Confidence.LOW,
        "unable": Confidence.UNABLE,
    }
    return mapping.get(str(value).lower(), Confidence.MEDIUM)


def _parse_legal_refs(refs: list) -> list[LegalReference]:
    result = []
    for r in refs if isinstance(refs, list) else []:
        if isinstance(r, dict):
            result.append(LegalReference(
                article=r.get("article", ""),
                content=r.get("content", ""),
                relevance=r.get("relevance", ""),
            ))
    return result


# 元数据字段，跳过输出格式说明（由 Agent 代码自动填充）
skip_fields = {
    "processing_time_ms", "kb_sources", "retry_count", "downstream_context",
    "intake_report_doc_id", "investigation_report_doc_id",
    "analysis_report_doc_id", "disposition_report_doc_id",
    "enforcement_report_doc_id", "post_report_doc_id",
}


def _build_output_format(model_class: type) -> str:
    """根据 Pydantic 模型生成 LLM 输出的 JSON 格式说明"""
    schema = model_class.model_json_schema()
    props = schema.get("properties", {})
    required = set(schema.get("required", []))

    # 手动定义枚举映射，确保 LLM 输出精确的枚举值
    enum_values = {
        "involved_entity_type": '必须是以下之一: "员工", "供应商", "经销商", "混合"',
        "risk_level": '必须是以下之一: "高", "中", "低"',
        "urgency": '必须是以下之一: "紧急", "一般", "低"',
        "confidence": '必须是以下之一: "high", "medium", "low", "unable"',
        "transfer_target": '必须是以下之一: "龟宝(HR-A2A)", "辛顿平台任务中心", "不转交"',
    }

    lines = []
    for name in props:
        if name in skip_fields:
            continue
        prop = props[name]
        desc = prop.get("description", "")
        is_req = "必填" if name in required else "可选"

        if name in enum_values:
            desc = enum_values[name]
        elif "type" in prop:
            field_type = prop.get("type", "string")
            if field_type == "array":
                items = prop.get("items", {})
                desc = f"[{items.get('type', 'string')}数组] {desc}"
            elif field_type == "boolean":
                desc = f"[true/false] {desc}"
            elif field_type == "object":
                desc = f"[对象] {desc}"
            elif field_type == "string":
                desc = f"[字符串] {desc}"

        example = _get_example_value(name, prop)
        lines.append(f'  "{name}": {example},  // {is_req}, {desc}')

    return "{\n" + "\n".join(lines) + "\n}"


def _get_example_value(name: str, prop: dict) -> str:
    """根据字段类型生成示例值"""
    field_type = prop.get("type", "string")
    any_of = prop.get("anyOf", [])
    enum_vals = None
    for t in any_of:
        if t.get("type") == "string" and "enum" in t:
            enum_vals = t["enum"]
    if not enum_vals and "enum" in prop:
        enum_vals = prop["enum"]

    if enum_vals:
        return json.dumps(enum_vals[0])
    if field_type == "boolean":
        return "true"
    if field_type == "integer" or field_type == "number":
        return "0"
    if field_type == "array":
        items = prop.get("items", {})
        item_type = items.get("type", "string")
        if item_type == "object":
            return "[{}]"
        return '["示例1", "示例2"]'
    if field_type == "object":
        return "{}"
    return '"此处填写"'


def _build_output_from_data(data: dict, task_id: str, processing_time_ms: int, retry_count: int) -> IntakeAgentOutput:
    """从解析后的 JSON 数据构建 IntakeAgentOutput, 对非法枚举值进行容错处理"""
    return IntakeAgentOutput(
        case_summary=data.get("case_summary", "（摘要生成失败）"),
        key_facts=_safe_list(data.get("key_facts"), min_len=1, fallback=["LLM 未提供关键事实"]),
        involved_entity_type=_safe_enum(data.get("involved_entity_type"), TriagedEntityType, TriagedEntityType.MIXED),
        should_investigate=bool(data.get("should_investigate", True)),
        investigation_reason=str(data.get("investigation_reason", "")),
        should_transfer=bool(data.get("should_transfer", False)),
        transfer_target=_safe_enum(data.get("transfer_target"), TransferTarget, TransferTarget.NONE),
        transfer_reason=data.get("transfer_reason"),
        is_hr_related=bool(data.get("is_hr_related", False)),
        risk_level=_safe_risk_level(data.get("risk_level")),
        estimated_amount_range=data.get("estimated_amount_range"),
        urgency=_safe_urgency(data.get("urgency")),
        confidence=_safe_confidence(data.get("confidence")),
        confidence_reason=str(data.get("confidence_reason", "")),
        uncertainty_factors=_safe_list(data.get("uncertainty_factors")),
        missing_information=_safe_list(data.get("missing_information")),
        legal_references=_parse_legal_refs(data.get("legal_references", [])),
        suggested_next_steps=_safe_list(data.get("suggested_next_steps")),
        suggested_interview_targets=_safe_list(data.get("suggested_interview_targets")),
        processing_time_ms=processing_time_ms,
        kb_sources=_safe_list(data.get("kb_sources")),
        retry_count=retry_count,
        downstream_context=_build_downstream_context(data, task_id),
    )


def _safe_list(value: Any, min_len: int = 0, fallback: list | None = None) -> list:
    """安全转换为列表，处理 LLM 返回字符串而非数组的情况"""
    if isinstance(value, list):
        result = list(value)
    elif isinstance(value, str) and value:
        result = [value]
    else:
        result = []
    if min_len > 0 and len(result) < min_len:
        return fallback or [f"LLM 未提供足够数据 (需要至少{min_len}项)"]
    return result


def _safe_enum(value: Any, enum_cls: type, default: Any) -> Any:
    """安全转换枚举值，忽略非法值"""
    if value is None:
        return default
    try:
        return enum_cls(str(value))
    except ValueError:
        return default


async def _sleep_backoff(attempt: int) -> None:
    """指数退避等待"""
    import asyncio
    delays = [2, 4]  # seconds
    delay = delays[attempt] if attempt < len(delays) else 4
    await asyncio.sleep(delay)
