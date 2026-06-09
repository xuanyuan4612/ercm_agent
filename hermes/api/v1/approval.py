"""守门审批接口（HITL - Human-in-the-Loop）"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hermes.api.dependencies import CurrentUser, check_client_access
from hermes.core.exceptions import (
    CaseNotFoundError,
    NoPendingApprovalError,
)
from hermes.core.logging import get_logger
from hermes.core.response import success
from hermes.core.security import sign_approval

logger = get_logger(__name__)
from hermes.db.models.integrity import Case, CaseStage, HumanApproval
from hermes.db.session import get_db
from hermes.schemas.workflow import (
    ApprovalHistoryEntry,
    ApprovalSubmitRequest,
    PendingApprovalResponse,
    RegenerateRequest,
)

router = APIRouter(prefix="/cases/{case_id}/approval")


async def _get_case(case_id: uuid.UUID, current_user, db: AsyncSession) -> Case:
    result = await db.execute(
        select(Case).where(Case.id == case_id, Case.is_deleted == False)
    )
    case = result.scalar_one_or_none()
    if not case:
        raise CaseNotFoundError(str(case_id))
    check_client_access(current_user, case.client)
    return case


@router.get("/pending")
async def get_pending_approval(
    case_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """查询当前待守门阶段的内容"""
    case = await _get_case(case_id, current_user, db)

    if not case.current_stage:
        raise NoPendingApprovalError()

    # 查询当前阶段的最新 AI 输出
    result = await db.execute(
        select(CaseStage)
        .where(
            CaseStage.case_id == case.id,
            CaseStage.stage_name == case.current_stage,
            CaseStage.status == "pending_approval",
        )
        .order_by(CaseStage.started_at.desc())
        .limit(1)
    )
    stage = result.scalar_one_or_none()

    ai_output = stage.ai_output if stage and stage.ai_output else {
        "status": "pending",
        "message": "AI 分析结果生成中...",
    }

    return success(PendingApprovalResponse(
        stage=case.current_stage,
        ai_output=ai_output,
        original_prompt=None,
        knowledge_refs=[],
    ).model_dump())


@router.post("/{stage}")
async def submit_approval(
    case_id: uuid.UUID,
    stage: str,
    request: ApprovalSubmitRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """碳基提交守门决定"""
    case = await _get_case(case_id, current_user, db)

    if case.current_stage != stage:
        raise NoPendingApprovalError()

    # 创建守门记录
    signature = sign_approval(
        str(case.id), stage, current_user.username, request.action
    )
    approval = HumanApproval(
        case_id=case.id,
        stage_name=stage,
        reviewer_id=current_user.username,
        action=request.action,
        modifications_summary=request.comment,
        comment=request.comment,
        signature=signature,
    )
    db.add(approval)

    # 更新阶段状态
    result = await db.execute(
        select(CaseStage)
        .where(CaseStage.case_id == case.id, CaseStage.stage_name == stage)
        .order_by(CaseStage.started_at.desc())
        .limit(1)
    )
    stage_record = result.scalar_one_or_none()
    if stage_record:
        stage_record.status = "approved" if request.action == "approved" else "rejected"
        stage_record.completed_at = datetime.now(UTC)

    next_stage = None
    if request.action == "approved":
        next_stage = _get_next_stage(stage)

    await db.flush()

    return success({
        "status": request.action,
        "next_stage": next_stage,
    })


@router.post("/{stage}/regenerate")
async def regenerate_content(
    case_id: uuid.UUID,
    stage: str,
    request: RegenerateRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """划词调整：碳基选中 AI 输出段落，提供修改指令，AI 重新生成指定部分。"""
    case = await _get_case(case_id, current_user, db)

    # 划词调整：调用 LLM 定向重新生成选中段落
    # 当前返回固定值：LLM 定向重新生成待接入
    try:
        from hermes.agents.llm_adapter import llm_adapter
        response = await llm_adapter.invoke(
            messages=[
                {"role": "system", "content": "你是赫尔墨斯风控系统的AI助手。根据指令对指定文本进行修改。"},
                {"role": "user", "content": f"原文:\n{request.selected_text}\n\n修改指令:\n{request.instruction}\n\n请输出修改后的文本（仅输出修改后的文本，不要额外说明）："},
            ],
            temperature=0.3,
            max_tokens=1024,
        )
        regenerated_text = response.strip()
    except Exception as e:
        logger.warning("regenerate_llm_failed", error=str(e))
        regenerated_text = f"[AI服务暂不可用] 根据指令 '{request.instruction}' 的重新生成结果（当前人工审核模式）"

    return success({"regenerated_text": regenerated_text})


@router.get("/history")
async def get_approval_history(
    case_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """查询该案件所有阶段的守门记录"""
    case = await _get_case(case_id, current_user, db)

    result = await db.execute(
        select(HumanApproval)
        .where(HumanApproval.case_id == case.id)
        .order_by(HumanApproval.created_at.desc())
    )
    approvals = result.scalars().all()

    return success([
        ApprovalHistoryEntry(
            id=str(a.id),
            stage_name=a.stage_name,
            reviewer_id=a.reviewer_id,
            action=a.action,
            comment=a.comment,
            created_at=a.created_at,
        ).model_dump()
        for a in approvals
    ])


def _get_next_stage(current: str) -> str | None:
    stages = {
        "intake": "investigation",
        "investigation": "analysis",
        "analysis": "disposition",
        "disposition": "enforcement",
        "enforcement": "post_report",
        "post_report": None,
    }
    return stages.get(current)
