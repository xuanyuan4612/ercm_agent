"""
廉洁监察模块 — Agent 输入/输出 Pydantic Schemas

覆盖 5 个 Agent:
  intake-agent → investigation-agent → analysis-agent → disposition-agent → enforcement-agent
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

# ═══════════════════════════════════════════════════════════════
# 共享枚举
# ═══════════════════════════════════════════════════════════════

class Client(StrEnum):
    """事业部"""
    ECOVACS = "ecovacs"
    TINECO = "tineco"
    GROUP = "group"


class FraudSource(StrEnum):
    """案件来源（DB 存储值，task_id 前缀通过来源缩写映射生成）"""
    WECHAT = "wechat"   # 公众号 → GZ
    MANUAL = "manual"   # 手动录入 → SD
    EMAIL = "email"     # 邮箱举报 → YX
    AGENT = "agent"     # 智能体推送 → ZN
    PHONE = "phone"     # 电话举报 → DH


class Confidence(StrEnum):
    """置信度"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNABLE = "unable"


class RiskLevel(StrEnum):
    """风险等级"""
    HIGH = "高"
    MEDIUM = "中"
    LOW = "低"


class Urgency(StrEnum):
    """紧急程度"""
    URGENT = "紧急"
    NORMAL = "一般"
    LOW = "低"


# ═══════════════════════════════════════════════════════════════
# 4.1 intake-agent (初筛 Agent)
# ═══════════════════════════════════════════════════════════════

class TriagedEntityType(StrEnum):
    EMPLOYEE = "员工"
    SUPPLIER = "供应商"
    DEALER = "经销商"
    MIXED = "混合"


class InvestigationDecision(StrEnum):
    INVESTIGATE = "继续调查"
    NOT_INVESTIGATE = "不处理"
    TRANSFER = "转交"


class TransferTarget(StrEnum):
    HR_GUIBAO = "龟宝(HR-A2A)"
    OTHER_DEPT_TASK = "辛顿平台任务中心"
    NONE = "不转交"


class AudioTranscription(BaseModel):
    file_id: str
    text: str
    segments: list[dict] | None = None
    language: str = "zh"


class OCRText(BaseModel):
    file_id: str
    text: str
    tables: list[dict] | None = None


class DocText(BaseModel):
    file_id: str
    text: str
    chunks: list[dict] | None = None


class IntakeAgentInput(BaseModel):
    """初筛 Agent 输入"""
    task_id: str = Field(..., description="案件编号")
    fraud_source: FraudSource = Field(..., description="案件来源")
    client: Client = Field(..., description="事业部")

    # 舞弊信息
    fraud_event_detail: str = Field(..., min_length=10, description="舞弊事件详情描述")
    reported_staff_names: list[str] = Field(default_factory=list, description="被举报员工姓名列表")
    reported_supplier_names: list[str] = Field(default_factory=list, description="被举报供应商名称列表")
    reported_dealer_names: list[str] = Field(default_factory=list, description="被举报经销商名称列表")

    # 举报人信息
    fraud_tel: str | None = Field(None, description="举报人电话")
    fraud_email: str | None = Field(None, description="举报人邮箱")
    fraud_other_info: str | None = Field(None, description="举报人其他信息")

    # 证据附件
    reported_files: list[str] = Field(default_factory=list, description="附件文件 ID 列表")
    recording_files: list[str] = Field(default_factory=list, description="录音文件 ID 列表")
    image_files: list[str] = Field(default_factory=list, description="图片文件 ID 列表")

    # 预处理结果
    audio_transcriptions: list[AudioTranscription] | None = Field(None, description="语音转文字结果")
    ocr_texts: list[OCRText] | None = Field(None, description="图片 OCR 结果")
    doc_texts: list[DocText] | None = Field(None, description="文档解析结果")

    context_version: str = Field(default="1.0", description="上下文传递协议版本号")


class LegalReference(BaseModel):
    article: str = Field(..., description="法条名称")
    content: str = Field(..., description="相关内容")
    relevance: str = Field(..., description="关联性说明")


class IntakeAgentOutput(BaseModel):
    """初筛 Agent 输出"""
    # 基础分析
    case_summary: str = Field(..., description="案件摘要 (≤500字)")
    key_facts: list[str] = Field(..., min_length=1, description="关键事实列表")
    involved_entity_type: TriagedEntityType = Field(..., description="调查对象类型")

    # 分流决策
    should_investigate: bool = Field(..., description="是否立案调查")
    investigation_reason: str = Field(..., description="立案/不立案理由 (≤300字)")

    should_transfer: bool = Field(..., description="是否需要转交")
    transfer_target: TransferTarget = Field(..., description="转交目标")
    transfer_reason: str | None = Field(None, description="转交理由")

    is_hr_related: bool = Field(..., description="是否归属 HR 管辖")

    # 风险评估
    risk_level: RiskLevel = Field(..., description="风险等级")
    estimated_amount_range: str | None = Field(None, description="预估涉案金额范围")
    urgency: Urgency = Field(..., description="紧急程度")

    # 置信度
    confidence: Confidence = Field(..., description="置信度")
    confidence_reason: str = Field(..., description="置信度判断理由")
    uncertainty_factors: list[str] = Field(default_factory=list, description="不确定因素列表")
    missing_information: list[str] = Field(default_factory=list, description="缺失的关键信息")

    # 法律引用
    legal_references: list[LegalReference] = Field(default_factory=list, description="引用法规")

    # 下一步建议
    suggested_next_steps: list[str] = Field(default_factory=list, description="建议后续步骤")
    suggested_interview_targets: list[str] | None = Field(None, description="建议访谈人员")

    # 输出文件
    intake_report_doc_id: str | None = Field(None, description="初判报告 Word 文档 MinIO key")

    # 元数据
    processing_time_ms: int = Field(..., description="Agent 处理耗时(毫秒)")
    kb_sources: list[str] = Field(default_factory=list, description="引用的知识库文档 ID 列表")
    retry_count: int = Field(default=0, description="重试次数")

    # 下游上下文
    downstream_context: dict | None = Field(None, description="传递给 investigation-agent 的结构化上下文")


# ═══════════════════════════════════════════════════════════════
# 4.2 investigation-agent (调查方案 Agent)
# ═══════════════════════════════════════════════════════════════

class InvestigationAgentInput(BaseModel):
    """调查方案 Agent 输入"""
    task_id: str = Field(..., description="案件编号")
    client: Client = Field(..., description="事业部")

    # 上游传递的上下文
    intake_context: dict = Field(..., description="intake-agent 传递的上下文 JSON")

    # 初判报告内容
    intake_report_summary: str = Field(..., description="初判报告摘要")
    involved_entity_type: str = Field(..., description="调查对象类型")
    key_facts: list[str] = Field(..., description="关键事实列表")
    suggested_focus: list[str] = Field(default_factory=list, description="建议调查方向")
    suggested_interview_targets: list[str] = Field(default_factory=list, description="建议访谈人员")

    # 案件材料
    case_files: list[str] = Field(default_factory=list, description="案件相关文件 ID 列表")
    evidence_summary: dict = Field(default_factory=dict, description="证据摘要")

    context_version: str = Field(default="1.0")


class DataRequirement(BaseModel):
    system: str = Field(..., description="数据系统名称")
    data_type: str = Field(..., description="数据类型")
    time_range: str = Field(..., description="时间范围")
    purpose: str = Field(..., description="用途说明")
    filters: str | None = Field(None, description="筛选条件")


class InterviewPlan(BaseModel):
    targets: list[str] = Field(..., description="访谈人员列表")
    strategy: str = Field(..., description="访谈策略")
    key_questions: list[str] = Field(default_factory=list, description="关键问题")


class TimelinePhase(BaseModel):
    name: str = Field(..., description="阶段名称")
    duration: str = Field(..., description="持续时间")
    tasks: list[str] = Field(..., description="阶段任务")


class InvestigationPlan(BaseModel):
    """调查方案结构"""
    investigation_objectives: list[str] = Field(..., description="调查目标列表")
    investigation_scope: str = Field(..., description="调查范围")
    investigation_methods: list[str] = Field(..., description="调查方法")
    data_requirements: list[DataRequirement] = Field(..., description="数据需求")
    interview_plan: InterviewPlan = Field(..., description="访谈计划")
    timeline: list[TimelinePhase] = Field(..., description="时间安排")
    sampling_strategy: str | None = Field(None, description="抽样策略")
    risk_mitigation: list[str] = Field(default_factory=list, description="风险控制措施")


class InvestigationAgentOutput(BaseModel):
    """调查方案 Agent 输出"""
    investigation_plan: InvestigationPlan = Field(..., description="调查方案")
    plan_rationale: str = Field(..., description="方案制定理由 (≤500字)")
    similar_cases_referenced: list[dict] = Field(default_factory=list, description="参考的相似案例")

    # 置信度
    confidence: Confidence = Field(..., description="置信度")
    confidence_reason: str = Field(..., description="置信度判断理由")

    # 输出文件
    plan_doc_id: str | None = Field(None, description="调查方案 Excel 文档 MinIO key")

    # 元数据
    processing_time_ms: int = Field(...)
    kb_sources: list[str] = Field(default_factory=list)
    retry_count: int = Field(default=0)

    # 下游上下文
    downstream_context: dict | None = Field(None, description="传递给 analysis-agent 的上下文")


# ═══════════════════════════════════════════════════════════════
# 4.3 analysis-agent (分析报告 Agent)
# ═══════════════════════════════════════════════════════════════

class AnalysisAgentInput(BaseModel):
    """分析报告 Agent 输入"""
    task_id: str = Field(..., description="案件编号")
    client: Client = Field(..., description="事业部")

    # 上游传递
    intake_context: dict = Field(..., description="intake-agent 上下文")
    investigation_context: dict = Field(..., description="investigation-agent 上下文")

    # 碳基上传的数据
    sql_analysis_results: list[dict] | None = Field(None, description="数据中台 SQL 分析结果")
    system_analysis_results: list[dict] | None = Field(None, description="其他智能体分析报告")
    manual_upload_results: list[dict] | None = Field(None, description="人工上传的原始数据分析结果")

    # 访谈相关
    interview_transcripts: list[dict] | None = Field(None, description="访谈转录结果")
    interview_summaries: list[dict] | None = Field(None, description="访谈纪要")

    # 现场走访
    site_visit_reports: list[dict] | None = Field(None, description="现场走访记录和发现")
    site_visit_files: list[str] | None = Field(None, description="现场走访附件")

    # 证据
    evidence_files: list[str] = Field(default_factory=list, description="所有证据文件 ID 列表")

    context_version: str = Field(default="1.0")


class EvidenceChainItem(BaseModel):
    claim: str = Field(..., description="主张")
    evidence_ids: list[str] = Field(..., description="支撑证据 ID 列表")
    strength: str = Field(..., description="证据强度: direct/indirect/testimony/inference")


class InvolvedParty(BaseModel):
    name: str = Field(..., description="涉及方名称")
    role: str = Field(..., description="角色")
    involvement_level: str = Field(..., description="涉及程度: high/medium/low")


class CaseConclusion(BaseModel):
    """案件结论结构"""
    conclusion_summary: str = Field(..., description="结论摘要 (≤500字)")
    fraud_type: str = Field(..., description="舞弊类型")
    confirmed_facts: list[str] = Field(..., description="已确认的事实")
    unconfirmed_claims: list[str] = Field(..., description="无法确认的主张")
    evidence_chain: list[EvidenceChainItem] = Field(..., description="证据链")
    involved_parties: list[InvolvedParty] = Field(..., description="涉及方")
    estimated_total_amount: str | None = Field(None, description="涉案总金额")
    root_cause_analysis: str | None = Field(None, description="根因分析")


class EvidenceSufficiency(StrEnum):
    SUFFICIENT = "sufficient"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"


class AnalysisAgentOutput(BaseModel):
    """分析报告 Agent 输出"""
    case_conclusion: CaseConclusion = Field(..., description="案件结论")

    # 多维度分析摘要
    data_analysis_summary: str | None = Field(None, description="数据分析摘要")
    interview_analysis_summary: str | None = Field(None, description="访谈分析摘要")
    site_visit_analysis_summary: str | None = Field(None, description="现场走访分析摘要")

    # 置信度
    confidence: Confidence = Field(..., description="置信度")
    confidence_reason: str = Field(..., description="置信度判断理由")
    evidence_sufficiency: EvidenceSufficiency = Field(..., description="证据充分性")

    # 输出文件
    conclusion_doc_id: str | None = Field(None, description="案件结论报告 Word 文档 object key")
    full_report_doc_id: str | None = Field(None, description="完整廉洁监察报告 Word 文档 object key")

    # 元数据
    processing_time_ms: int = Field(...)
    tools_used: list[str] = Field(default_factory=list)
    kb_sources: list[str] = Field(default_factory=list)
    retry_count: int = Field(default=0)

    # 下游上下文
    downstream_context: dict | None = Field(None, description="传递给 disposition-agent 的上下文")


# ═══════════════════════════════════════════════════════════════
# 4.4 disposition-agent (处置分流 Agent)
# ═══════════════════════════════════════════════════════════════

class DispositionType(StrEnum):
    NO_ACTION = "不追责"
    CRIMINAL = "刑事"
    CIVIL = "民事"
    INTERNAL = "内部"


class DispositionAgentInput(BaseModel):
    """处置分流 Agent 输入"""
    task_id: str = Field(..., description="案件编号")
    client: Client = Field(..., description="事业部")

    # 上游传递
    intake_context: dict = Field(..., description="intake-agent 上下文")
    investigation_context: dict = Field(..., description="investigation-agent 上下文")
    case_conclusion: CaseConclusion = Field(..., description="案件结论")

    # 证据汇总
    evidence_summary: dict = Field(default_factory=dict, description="证据汇总")

    context_version: str = Field(default="1.0")


class LegalAnalysis(BaseModel):
    applicable_laws: list[str] = Field(..., description="适用法律法规")
    criminal_liability: str | None = Field(None, description="刑事责任分析")
    civil_liability: str | None = Field(None, description="民事责任分析")
    internal_violation: str | None = Field(None, description="内部违规分析")
    recommended_path: DispositionType = Field(..., description="建议处置路径")


class PenaltyOpinion(BaseModel):
    target_person: str = Field(..., description="处罚对象")
    penalty_type: str = Field(..., description="处罚类型")
    penalty_detail: str = Field(..., description="处罚详情")
    legal_basis: str = Field(..., description="法律/制度依据")
    effective_date: str | None = Field(None, description="生效日期")


class DispositionAgentOutput(BaseModel):
    """处置分流 Agent 输出"""
    disposition_type: DispositionType = Field(..., description="处置类型")
    disposition_reason: str = Field(..., description="处置决定理由 (≤300字)")

    # 法律分析
    legal_analysis: LegalAnalysis = Field(..., description="法律路径分析")

    # 追责意见
    penalty_opinions: list[PenaltyOpinion] = Field(default_factory=list, description="追责意见列表")

    # 报案书（刑事路径）
    prosecution_letter: str | None = Field(None, description="报案书文本")

    # 民事路径
    civil_case_summary: str | None = Field(None, description="民事案件摘要（推送给西塞罗）")

    # 内部路径
    internal_remediation: str | None = Field(None, description="内部整改建议")

    # 涉及人员清单
    involved_personnel: list[dict] = Field(default_factory=list, description="处罚涉及人员清单")

    # 置信度
    confidence: Confidence = Field(..., description="置信度")
    confidence_reason: str = Field(..., description="置信度判断理由")

    # 输出文件
    disposition_report_doc_id: str | None = Field(None, description="处置报告 Word 文档")
    prosecution_letter_doc_id: str | None = Field(None, description="报案书 Word 文档")

    # 元数据
    processing_time_ms: int = Field(...)
    kb_sources: list[str] = Field(default_factory=list)
    retry_count: int = Field(default=0)

    # 下游上下文
    downstream_context: dict | None = Field(None, description="传递给 enforcement-agent 的上下文")


# ═══════════════════════════════════════════════════════════════
# 4.5 enforcement-agent (处罚执行 Agent)
# ═══════════════════════════════════════════════════════════════

class EnforcementAgentInput(BaseModel):
    """处罚执行 Agent 输入"""
    task_id: str = Field(..., description="案件编号")
    client: Client = Field(..., description="事业部")

    # 上游传递
    disposition_context: dict = Field(..., description="disposition-agent 上下文")
    penalty_opinions: list[PenaltyOpinion] = Field(..., description="追责意见")
    involved_personnel: list[dict] = Field(..., description="处罚涉及人员清单")

    context_version: str = Field(default="1.0")


class PenaltyAnnouncement(BaseModel):
    title: str = Field(..., description="公告标题")
    content: str = Field(..., description="公告内容（脱敏）")
    publish_scope: str = Field(..., description="发布范围")
    publish_date: str | None = Field(None, description="发布日期")


class A2ATaskItem(BaseModel):
    target_agent: str = Field(..., description="目标智能体 (guibao/cicero/porter)")
    command: str = Field(..., description="A2A 指令")
    payload: dict = Field(..., description="任务载荷")
    priority: str = Field(default="normal", description="优先级")


class EnforcementAgentOutput(BaseModel):
    """处罚执行 Agent 输出"""
    # 处罚公告
    penalty_announcements: list[PenaltyAnnouncement] = Field(default_factory=list, description="处罚公告")

    # 协议文件
    agreement_doc_ids: list[str] = Field(default_factory=list, description="协议/合同文件 ID 列表")

    # A2A 任务
    a2a_tasks: list[A2ATaskItem] = Field(default_factory=list, description="A2A 任务列表")
    a2a_task_ids: list[str] = Field(default_factory=list, description="A2A 任务 ID 列表")

    # 黑名单维护
    blacklist_updates: list[dict] = Field(default_factory=list, description="黑名单更新记录")

    # 外部系统同步
    sync_tasks: list[dict] = Field(default_factory=list, description="外部系统同步任务 (MDM/OA)")

    # 置信度
    confidence: Confidence = Field(..., description="置信度")

    # 元数据
    processing_time_ms: int = Field(...)
    kb_sources: list[str] = Field(default_factory=list)
    retry_count: int = Field(default=0)


# ═══════════════════════════════════════════════════════════════
# 4.6 post-report-agent (报案协助 Agent)
# ═══════════════════════════════════════════════════════════════

class DispositionPath(StrEnum):
    """处置路径"""
    CRIMINAL = "criminal"    # 刑事报案
    CIVIL = "civil"          # 民事追偿
    INTERNAL = "internal"    # 内部处罚
    NONE = "none"            # 不追责


class PostReportInput(BaseModel):
    """报案协助 Agent 输入"""
    task_id: str = Field(..., description="案件编号")
    client: Client = Field(..., description="事业部")

    # 上游传递
    case_conclusion: dict = Field(..., description="案件结论（来自 analysis-agent）")
    penalty_opinion: dict | None = Field(None, description="追责意见（来自 disposition-agent）")
    disposition_path: DispositionPath = Field(..., description="处置路径")

    # 证据材料
    evidence_files: list[str] = Field(default_factory=list, description="证据文件 ID 列表")
    prosecution_letter_draft: str | None = Field(None, description="已有报案书草稿（如有则补充）")

    context_version: str = Field(default="1.0")


class MaterialItem(BaseModel):
    """报案材料项"""
    name: str = Field(..., description="材料名称")
    description: str = Field(..., description="材料说明")
    required: bool = Field(default=True, description="是否必需")
    source: str = Field(default="", description="来源：系统导出/人工准备/法务提供")
    status: str = Field(default="待准备", description="准备状态")


class PostReportOutput(BaseModel):
    """报案协助 Agent 输出"""
    # 材料清单
    material_checklist: list[MaterialItem] = Field(default_factory=list, description="报案材料清单")

    # 报案书
    prosecution_letter: str = Field(default="", description="报案书草稿（或补充内容）")

    # 后续协助建议
    follow_up_suggestions: list[str] = Field(default_factory=list, description="后续协助建议")

    # 证据补充
    evidence_supplement_needed: bool = Field(default=False, description="是否需要补充证据")
    evidence_supplement_items: list[str] = Field(default_factory=list, description="待补充证据项")

    # 司法鉴定
    forensic_identification_needed: bool = Field(default=False, description="是否需要司法鉴定")
    estimated_timeline: str = Field(default="", description="预计报案时间线")

    # 律师对接
    legal_counsel_recommendation: str = Field(default="", description="律师/法务对接建议")

    # 置信度
    confidence: Confidence = Field(..., description="置信度")
    confidence_reason: str = Field(default="", description="置信度判断理由")

    # 元数据
    processing_time_ms: int = Field(default=0)
    kb_sources: list[str] = Field(default_factory=list)
    retry_count: int = Field(default=0)
