"""案件管理 Pydantic schemas"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class FraudSource(str, Enum):
    manual = "manual"
    phone = "phone"
    email = "email"
    wechat = "wechat"
    agent = "agent"


class Client(str, Enum):
    ecovacs = "ecovacs"
    tineco = "tineco"
    group = "group"


class CaseStatus(str, Enum):
    pending = "pending"
    investigating = "investigating"
    disposing = "disposing"
    enforcing = "enforcing"
    closed = "closed"
    transferred = "transferred"


class StageName(str, Enum):
    intake = "intake"
    investigation = "investigation"
    analysis = "analysis"
    disposition = "disposition"
    enforcement = "enforcement"
    post_report = "post_report"


# ── 请求体 ─────────────────────────────────────────────────────

class CaseCreateRequest(BaseModel):
    """创建案件请求"""
    fraud_source: str = Field(..., description="舞弊来源")
    client: str = Field(..., description="事业部")
    reported_staff_names: list[str] = Field(default_factory=list, description="被举报人员姓名")
    reported_supplier_names: list[str] = Field(default_factory=list)
    reported_dealer_names: list[str] = Field(default_factory=list)
    fraud_event_detail: str | None = Field(None, description="舞弊事件详情")
    proof: str | None = Field(None, description="证据简述")
    attachments: list[str] = Field(default_factory=list, description="附件路径")
    fraud_tel: str | None = Field(None, description="举报人电话")
    fraud_email: str | None = Field(None, description="举报人邮箱")
    fraud_other_info: str | None = Field(None, description="其他信息")
    risk_control_case_id: str | None = Field(None, description="风控系统案件ID")


class CaseUpdateRequest(BaseModel):
    """更新案件请求（仅允许更新未启动工作流的案件）"""
    fraud_event_detail: str | None = None
    proof: str | None = None
    attachments: list[str] | None = None
    reported_staff_names: list[str] | None = None
    reported_supplier_names: list[str] | None = None


class CaseQueryParams(BaseModel):
    """案件列表查询参数"""
    client: str | None = None
    source: str | None = None
    status: str | None = None
    stage: str | None = None
    keyword: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


# ── 响应体 ─────────────────────────────────────────────────────

class CaseBrief(BaseModel):
    """案件简要信息"""
    id: str
    task_id: str
    case_code: str | None = None
    client: str
    fraud_source: str
    current_stage: str | None = None
    status: str
    created_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class DocumentBrief(BaseModel):
    """生成文档简要"""
    id: str
    type: str = Field(..., alias="doc_type")
    name: str = ""
    format: str = Field(..., alias="file_format")
    created_at: datetime | None = None

    model_config = {"from_attributes": True, "populate_by_name": True}


class CaseDetail(BaseModel):
    """案件详细信息"""
    id: str
    task_id: str
    case_code: str | None = None
    client: str
    fraud_source: str
    current_stage: str | None = None
    status: str
    fraud_event_detail: str | None = None
    proof: str | None = None
    attachments: list | None = None
    fraud_tel: str | None = None
    risk_control_case_id: str | None = None
    workflow_state: dict | None = None
    langgraph_thread_id: str | None = None
    generated_documents: list[DocumentBrief] = Field(default_factory=list)
    created_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
