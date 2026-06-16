"""
Module Agent Profile — 模块级 AI 能力配置

每个模块维护一个 Profile 作为 Agent Runtime 的配置入口，统一定义：
- 知识库范围 (knowledge_scopes)
- 工具权限 (allowed_tools)
- Prompt 包引用
- 模型路由策略
- 质量门禁

Profile 不是主 Agent，不拥有状态跳转权。

参照: doc/agents/00-agent-architecture.md §三
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ModelRoutingPolicy(str, Enum):
    """模型路由策略"""
    PRIMARY_ONLY = "primary_only"
    PRIMARY_WITH_FALLBACK = "primary_with_fallback"
    SENSITIVE_DATA = "sensitive_data"  # 敏感数据走私有模型


@dataclass
class QualityGate:
    """质量门禁配置"""
    require_citations: bool = False
    require_evidence_chain: bool = False
    require_confidence: bool = True
    require_uncertainties: bool = True
    require_human_review: bool = True
    require_sql_review: bool = False
    require_false_positive_feedback: bool = False
    require_human_review_for_push: bool = False
    require_control_activity_mapping: bool = False
    require_deficiency_basis: bool = False
    require_tenure_rule_check: bool = False
    require_issue_category: bool = False
    require_policy_basis: bool = False
    require_legal_case_reference: bool = False
    require_data_scope_confirmation: bool = False
    require_privacy_minimization: bool = False
    require_issue_source: bool = False
    require_rectification_mapping: bool = False
    require_evidence_sufficiency: bool = False
    require_issue_evidence_mapping: bool = False


@dataclass
class ModuleAgentProfile:
    """模块 Agent Profile

    定义模块的 AI 能力边界，Agent Runtime 据此装配上下文、校验权限、路由模型。

    每个模块必须维护一个 Profile 实例。
    """

    profile_id: str
    module: str
    module_graph: str
    schema_version: str = "1.0"

    # 知识库范围
    knowledge_scopes: list[str] = field(default_factory=list)

    # 工具权限 (最小权限原则)
    allowed_tools: list[str] = field(default_factory=list)

    # 模型路由策略
    model_routing_policy: ModelRoutingPolicy = ModelRoutingPolicy.PRIMARY_WITH_FALLBACK
    primary_provider: str = "deepseek-provider"
    fallback_provider: str = "qwen-provider"
    sensitive_fallback: str = "private-model-provider"

    # 质量门禁
    quality_gates: QualityGate = field(default_factory=QualityGate)

    # 描述
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "profile_id": self.profile_id,
            "module": self.module,
            "module_graph": self.module_graph,
            "schema_version": self.schema_version,
            "knowledge_scopes": self.knowledge_scopes,
            "allowed_tools": self.allowed_tools,
            "model_routing_policy": self.model_routing_policy.value,
            "primary_provider": self.primary_provider,
            "fallback_provider": self.fallback_provider,
            "sensitive_fallback": self.sensitive_fallback,
            "quality_gates": {
                k: v for k, v in self.quality_gates.__dict__.items() if v
            },
        }


# ═══════════════════════════════════════════════════════════════
# 8 个模块的 Agent Profile 实例
# ═══════════════════════════════════════════════════════════════

INTEGRITY_SUPERVISION_PROFILE = ModuleAgentProfile(
    profile_id="integrity-supervision-agent-profile",
    module="integrity_supervision",
    module_graph="integrity-supervision-graph",
    knowledge_scopes=[
        "kb_integrity_policy",
        "kb_integrity_cases",
        "kb_law_and_regulation",
        "kb_disposition_template",
    ],
    allowed_tools=[
        "rag_search",
        "evidence_search",
        "sql_analyze_readonly",
        "doc_generate",
        "a2a_send",
        "external_sync_outbox",
    ],
    quality_gates=QualityGate(
        require_citations=True,
        require_evidence_chain=True,
        require_human_review=True,
    ),
    description="廉洁监察（反舞弊调查）模块 Agent Profile — 6 阶段反舞弊调查",
)

RISK_MONITORING_PROFILE = ModuleAgentProfile(
    profile_id="risk-monitoring-agent-profile",
    module="risk_monitoring",
    module_graph="risk-monitoring-graph",
    knowledge_scopes=[
        "risk_rules",
        "risk_cases",
        "database_schema",
        "disposition_feedback",
    ],
    allowed_tools=[
        "rag_search",
        "sql_syntax_validate",
        "sql_test_execute_readonly",
        "risk_scan_submit",
        "external_data_query",
        "outbox_publish",
    ],
    quality_gates=QualityGate(
        require_sql_review=True,
        require_false_positive_feedback=True,
        require_human_review_for_push=True,
        require_human_review=True,
    ),
    description="风险监控（主动风险扫描）模块 Agent Profile — 7×24 无人值守自动扫描",
)

INTERNAL_CONTROL_EVALUATION_PROFILE = ModuleAgentProfile(
    profile_id="internal-control-evaluation-agent-profile",
    module="internal_control_evaluation",
    module_graph="internal-control-evaluation-graph",
    knowledge_scopes=[
        "ic_policy",
        "control_matrix",
        "audit_plan",
        "interview_template",
        "deficiency_rating",
    ],
    allowed_tools=[
        "rag_search",
        "control_matrix_read",
        "interview_plan_generate",
        "audit_workpaper_analyze",
        "score_calculate",
        "doc_generate",
    ],
    quality_gates=QualityGate(
        require_control_activity_mapping=True,
        require_deficiency_basis=True,
        require_human_review=True,
    ),
    description="内控评价（合规评价）模块 Agent Profile — 19 个业务循环 + 13 步骤工作流",
)

SPECIAL_AUDIT_PROFILE = ModuleAgentProfile(
    profile_id="special-audit-agent-profile",
    module="special_audit",
    module_graph="special-audit-graph",
    knowledge_scopes=[
        "sa_plan",
        "sa_history",
        "audit_workpaper_template",
        "interview_template",
        "improvement_suggestion",
    ],
    allowed_tools=[
        "rag_search",
        "evidence_search",
        "interview_plan_generate",
        "sql_analyze_readonly",
        "doc_generate",
        "issue_deduplicate",
    ],
    quality_gates=QualityGate(
        require_citations=True,
        require_issue_evidence_mapping=True,
        require_human_review=True,
    ),
    description="专项审计（专项检查）模块 Agent Profile — 5 阶段专项审计",
)

EXIT_AUDIT_PROFILE = ModuleAgentProfile(
    profile_id="exit-audit-agent-profile",
    module="exit_audit",
    module_graph="exit-audit-graph",
    knowledge_scopes=[
        "ea_plan",
        "position_duty",
        "personal_risk_case",
        "business_audit_case",
        "behavioral_risk_history",
    ],
    allowed_tools=[
        "rag_search",
        "hr_profile_read",
        "behavior_risk_summary_read",
        "finance_voucher_readonly",
        "evidence_search",
        "doc_generate",
    ],
    quality_gates=QualityGate(
        require_tenure_rule_check=True,
        require_issue_category=True,
        require_citations=True,
        require_human_review=True,
    ),
    description="离任审计（离职审查）模块 Agent Profile — 6 阶段离任审计",
)

TRADE_SECRETS_PROFILE = ModuleAgentProfile(
    profile_id="trade-secrets-agent-profile",
    module="trade_secrets",
    module_graph="trade-secrets-graph",
    knowledge_scopes=[
        "trade_secret_policy",
        "ip_policy",
        "trade_secret_law",
        "trade_secret_cases",
        "historical_secret_review",
        "ic_policy",
    ],
    allowed_tools=[
        "rag_search",
        "policy_compare",
        "historical_review_search",
        "behavior_risk_summary_read",
        "doc_generate",
        "sensitivity_classifier",
    ],
    quality_gates=QualityGate(
        require_policy_basis=True,
        require_legal_case_reference=True,
        require_uncertainties=True,
        require_human_review=True,
    ),
    description="商业秘密保护（保密管理）模块 Agent Profile — 定密预审+评审+管理报告",
)

BEHAVIORAL_RISK_PROFILE = ModuleAgentProfile(
    profile_id="behavioral-risk-agent-profile",
    module="behavioral_risk",
    module_graph="behavioral-risk-graph",
    knowledge_scopes=[
        "behavior_policy",
        "employee_lifecycle",
        "trade_secret_policy",
        "law_and_regulation",
        "historical_behavior_analysis",
    ],
    allowed_tools=[
        "behavior_log_query_readonly",
        "hr_profile_read",
        "mDM_org_read",
        "rag_search",
        "evidence_search",
        "doc_generate",
    ],
    quality_gates=QualityGate(
        require_data_scope_confirmation=True,
        require_privacy_minimization=True,
        require_uncertainties=True,
        require_human_review=True,
    ),
    description="行为风险（员工行为分析）模块 Agent Profile — 跨系统行为数据整合+异常识别",
)

CONTINUOUS_IMPROVEMENT_PROFILE = ModuleAgentProfile(
    profile_id="continuous-improvement-agent-profile",
    module="continuous_improvement",
    module_graph="continuous-improvement-graph",
    knowledge_scopes=[
        "improvement_case",
        "rectification_template",
        "audit_issue_history",
        "policy_and_process",
    ],
    allowed_tools=[
        "issue_deduplicate",
        "evidence_search",
        "rag_search",
        "doc_parse",
        "image_compare",
        "notification_draft",
        "doc_generate",
    ],
    quality_gates=QualityGate(
        require_issue_source=True,
        require_rectification_mapping=True,
        require_evidence_sufficiency=True,
        require_human_review=True,
    ),
    description="持续改善（整改跟踪）模块 Agent Profile — 全模块问题统一承接+闭环跟踪",
)

# 所有 Profile 注册表
MODULE_PROFILES: dict[str, ModuleAgentProfile] = {
    "integrity_supervision": INTEGRITY_SUPERVISION_PROFILE,
    "risk_monitoring": RISK_MONITORING_PROFILE,
    "internal_control_evaluation": INTERNAL_CONTROL_EVALUATION_PROFILE,
    "special_audit": SPECIAL_AUDIT_PROFILE,
    "exit_audit": EXIT_AUDIT_PROFILE,
    "trade_secrets": TRADE_SECRETS_PROFILE,
    "behavioral_risk": BEHAVIORAL_RISK_PROFILE,
    "continuous_improvement": CONTINUOUS_IMPROVEMENT_PROFILE,
}


def get_profile(module: str) -> Optional[ModuleAgentProfile]:
    """获取模块 Agent Profile"""
    return MODULE_PROFILES.get(module)
