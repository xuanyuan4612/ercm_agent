"""
共享枚举和基类 — 所有模块 Agent Schema 共用
"""

from __future__ import annotations

from enum import StrEnum


class Client(StrEnum):
    """事业部"""
    ECOVACS = "ecovacs"
    TINECO = "tineco"
    GROUP = "group"


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
    CRITICAL = "严重"


class Urgency(StrEnum):
    """紧急程度"""
    URGENT = "紧急"
    NORMAL = "一般"
    LOW = "低"


class AuditType(StrEnum):
    """审计类型"""
    INTERNAL_CONTROL = "ic_evaluation"
    SPECIAL_AUDIT = "special_audit"
    EXIT_AUDIT = "exit_audit"


class IssueSource(StrEnum):
    """问题来源"""
    INTEGRITY = "integrity"
    RISK_MONITOR = "risk_monitor"
    IC_EVALUATION = "ic_evaluation"
    SPECIAL_AUDIT = "special_audit"
    EXIT_AUDIT = "exit_audit"
    BEHAVIOR_RISK = "behavior_risk"
    TRADE_SECRET = "trade_secret"
    BUSINESS_ASSIGNED = "business_assigned"


class IssueStatus(StrEnum):
    """整改问题状态"""
    PENDING_PUSH = "问题待推送"
    PLAN_PENDING = "计划待提交"
    PLAN_PENDING_APPROVAL = "计划待审批"
    RESPONSE_PENDING = "整改答复待提交"
    REVIEW_PENDING = "已整改待复核"
    COMPLETED = "整改完成"
