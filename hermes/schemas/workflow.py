"""工作流与守门审批 Pydantic schemas"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# ── 工作流 ─────────────────────────────────────────────────────

class WorkflowStartResponse(BaseModel):
    thread_id: str
    current_stage: str
    status: str


class WorkflowResumeRequest(BaseModel):
    human_modifications: dict[str, Any] | None = Field(
        None, description="碳基修改后的状态（按阶段 key）"
    )


class WorkflowResumeResponse(BaseModel):
    thread_id: str
    current_stage: str
    status: str


class WorkflowStatusResponse(BaseModel):
    current_stage: str | None = None
    stage_history: list[str] = Field(default_factory=list)
    pending_approval_stage: str | None = None
    error_info: dict | None = None
    needs_human_intervention: bool = False


class StageHistoryEntry(BaseModel):
    stage_name: str
    status: str
    ai_output_type: str | None = None
    approval_result: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


# ── 守门审批 ──────────────────────────────────────────────────

class ApprovalAction(str):
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"


class PendingApprovalResponse(BaseModel):
    stage: str
    ai_output: dict[str, Any]
    original_prompt: str | None = None
    knowledge_refs: list[dict] = Field(default_factory=list)


class ApprovalSubmitRequest(BaseModel):
    action: str = Field(..., description="approved / rejected / modified")
    modifications: dict[str, Any] = Field(default_factory=dict)
    comment: str | None = None


class ApprovalSubmitResponse(BaseModel):
    status: str
    next_stage: str | None = None


class RegenerateRequest(BaseModel):
    selected_text: str = Field(..., description="选中的文本")
    instruction: str = Field(..., description="修改指令")


class RegenerateResponse(BaseModel):
    regenerated_text: str


class ApprovalHistoryEntry(BaseModel):
    id: str
    stage_name: str
    reviewer_id: str
    action: str
    comment: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
