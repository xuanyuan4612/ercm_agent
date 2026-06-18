"""工作流接口（LangGraph 驱动）"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hermes.api.dependencies import CurrentUser, check_client_access
from hermes.core.exceptions import (
    CaseNotFoundError,
    WorkflowAlreadyCompletedError,
    WorkflowAlreadyStartedError,
    WorkflowNotStartedError,
)
from hermes.core.logging import get_logger
from hermes.core.response import success
from hermes.db.models.integrity import Case, CaseStage
from hermes.db.session import get_db
from hermes.schemas.workflow import (
    StageHistoryEntry,
    WorkflowResumeRequest,
    WorkflowStatusResponse,
)
from hermes.services.case_service import CaseService

logger = get_logger(__name__)

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

    # 预先创建所有阶段的 CaseStage 记录，供后台 LangGraph 节点持久化 AI 产出
    stages_config = [
        ("intake", 1),
        ("investigation", 2),
        ("analysis", 3),
        ("disposition", 4),
        ("enforcement", 5),
        ("post_report", 6),
    ]
    now = datetime.now(UTC)
    for stage_name, stage_order in stages_config:
        db.add(CaseStage(
            case_id=case.id,
            stage_name=stage_name,
            stage_order=stage_order,
            status="pending_approval" if stage_name == "intake" else "pending",
            started_at=now if stage_name == "intake" else None,
        ))
    await db.flush()

    # LangGraph 工作流启动（当前为骨架实现，Celery/RabbitMQ 调度待接入）
    # 生产环境：通过 Celery task 异步执行 LangGraph graph.ainvoke()
    # 当前直接进入守门等待状态
    try:
        # 异步启动工作流（后台执行，不阻塞响应）
        import asyncio

        from hermes.workflows.integrity.graph import integrity_graph
        asyncio.create_task(
            integrity_graph.start_workflow(str(case.id), case.task_id, case.client, case.fraud_source)
        )
        logger.info("workflow_started_async", task_id=case.task_id, thread_id=thread_id)
    except Exception as e:
        logger.warning("workflow_graph_unavailable", error=str(e),
                        message="LangGraph 工作流图不可用，使用骨架推进模式")
        # 降级为骨架推进：直接从 pending_approval 开始

    return success({
        "thread_id": thread_id,
        "current_stage": "intake",
        "status": "pending_approval",
        "mode": "skeleton",
        "message": "工作流已启动，等待第一阶段 AI 分析（LangGraph 工作流待完整接入）",
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

    # LangGraph 工作流恢复（当前骨架推进到下一阶段，LangGraph update_state 待接入）
    # 生产环境：通过 LangGraph 的 update_state + invoke 恢复执行

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
        # 查找预创建的 CaseStage 记录（含 LangGraph 后台已持久化的 AI 产出），激活为待守门
        svc = CaseService(db)
        existing = await svc.get_case_stage(case.id, next_stage)
        if existing:
            existing.status = "pending_approval"
            if not existing.started_at:
                existing.started_at = datetime.now(UTC)
        else:
            # 兜底：创建新记录（旧数据兼容）
            order = stage_order.get(next_stage, 0)
            db.add(CaseStage(
                case_id=case.id,
                stage_name=next_stage,
                stage_order=order,
                status="pending_approval",
                started_at=datetime.now(UTC),
            ))
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

    # LangGraph interrupt 机制调用（当前骨架实现）
    # 生产环境：调用 LangGraph graph.interrupt() 方法
    try:
        from hermes.workflows.integrity.graph import integrity_graph
        integrity_graph.interrupt_workflow(case.task_id, case.current_stage)
    except Exception as e:
        logger.warning("workflow_interrupt_graph_unavailable", error=str(e))

    return success(message=f"工作流 {case.task_id} 阶段 {case.current_stage} 已中断")
