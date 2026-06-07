"""工作流接口（LangGraph 驱动）"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hermes.api.dependencies import CurrentUser, check_client_access
from hermes.core.exceptions import (
    CaseNotFoundError,
    NoPendingApprovalError,
    WorkflowAlreadyCompletedError,
    WorkflowAlreadyStartedError,
    WorkflowExecutionError,
    WorkflowNotStartedError,
)
from hermes.core.response import success
from hermes.db.models.integrity import Case, CaseStage
from hermes.db.session import get_db
from hermes.schemas.workflow import (
    StageHistoryEntry,
    WorkflowResumeRequest,
    WorkflowStatusResponse,
)

router = APIRouter(prefix="/cases/{case_id}/workflow")


async def _get_case(case_id: uuid.UUID, current_user, db: AsyncSession) -> Case:
    result = await db.execute(
        select(Case).where(Case.id == case_id, Case.is_deleted == False)
    )
    case = result.scalar_one_or_none()
    if not case:
        raise CaseNotFoundError(str(case_id))
    check_client_access(current_user, case.client)
    return case


@router.post("/start", status_code=202)
async def start_workflow(
    case_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """启动 LangGraph 工作流，自动运行至第一个 interrupt 点（intake 节点）。"""
    case = await _get_case(case_id, current_user, db)

    if case.langgraph_thread_id:
        raise WorkflowAlreadyStartedError(detail=f"工作流已启动, thread_id={case.langgraph_thread_id}")

    # 创建工作流线程
    thread_id = f"thread-{case.task_id}"
    case.langgraph_thread_id = thread_id
    case.status = "investigating"
    case.current_stage = "intake"

    # 创建阶段记录
    stage = CaseStage(
        case_id=case.id,
        stage_name="intake",
        stage_order=1,
        status="pending_approval",
        started_at=datetime.now(UTC),
    )
    db.add(stage)
    await db.flush()

    # TODO: 实际启动 LangGraph 工作流（异步执行，通过 Celery / RabbitMQ 调度）
    # 当前为骨架实现：直接进入守门等待状态

    return success({
        "thread_id": thread_id,
        "current_stage": "intake",
        "status": "pending_approval",
    })


@router.post("/resume", status_code=202)
async def resume_workflow(
    case_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    request: WorkflowResumeRequest | None = None,
):
    """碳基守门完成后恢复工作流继续执行。"""
    case = await _get_case(case_id, current_user, db)

    if not case.langgraph_thread_id:
        raise WorkflowNotStartedError()

    if case.status == "closed":
        raise WorkflowAlreadyCompletedError()

    # TODO: 通过 LangGraph 的 update_state + invoke 恢复执行
    # 当前骨架：简单推进到下一阶段

    stage_order = {
        "intake": 1, "investigation": 2, "analysis": 3,
        "disposition": 4, "enforcement": 5, "post_report": 6,
    }
    next_stages = {
        "intake": "investigation",
        "investigation": "analysis",
        "analysis": "disposition",
        "disposition": "enforcement",
        "enforcement": "post_report",
        "post_report": None,
    }

    current = case.current_stage
    next_stage = next_stages.get(current) if current else None

    if next_stage:
        case.current_stage = next_stage
        order = stage_order.get(next_stage, 0)
        stage = CaseStage(
            case_id=case.id,
            stage_name=next_stage,
            stage_order=order,
            status="pending_approval",
            started_at=datetime.now(UTC),
        )
        db.add(stage)
    else:
        case.status = "closed"

    await db.flush()

    return success({
        "thread_id": case.langgraph_thread_id,
        "current_stage": case.current_stage,
        "status": case.status,
    })


@router.get("/status")
async def get_workflow_status(
    case_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """查询工作流当前状态"""
    case = await _get_case(case_id, current_user, db)

    return success(WorkflowStatusResponse(
        current_stage=case.current_stage,
        stage_history=[],
        pending_approval_stage=case.current_stage,
        error_info=None,
        needs_human_intervention=case.current_stage is not None and case.status != "closed",
    ).model_dump())


@router.get("/history")
async def get_workflow_history(
    case_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """查询工作流历史"""
    case = await _get_case(case_id, current_user, db)

    result = await db.execute(
        select(CaseStage)
        .where(CaseStage.case_id == case.id)
        .order_by(CaseStage.stage_order)
    )
    stages = result.scalars().all()

    history = []
    for s in stages:
        history.append(StageHistoryEntry(
            stage_name=s.stage_name,
            status=s.status,
            ai_output_type=None,
            approval_result=None,
            started_at=s.started_at,
            completed_at=s.completed_at,
        ).model_dump())

    return success(history)


@router.post("/interrupt", status_code=200)
async def interrupt_workflow(
    case_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """碳基主动中断当前阶段（需 group 角色权限）。"""
    if current_user.role != "group":
        from hermes.core.exceptions import ForbiddenError
        raise ForbiddenError(detail="仅集团角色可中断工作流")

    case = await _get_case(case_id, current_user, db)

    if not case.langgraph_thread_id:
        raise WorkflowNotStartedError()

    # TODO: 调用 LangGraph interrupt 机制
    return success(message=f"工作流 {case.task_id} 阶段 {case.current_stage} 已中断")
