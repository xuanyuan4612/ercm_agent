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
from hermes.core.observability import create_score, get_trace_id, tag_current_span
from hermes.core.response import success
from hermes.core.security import sign_approval
from hermes.db.models.integrity import Case, CaseStage, HumanApproval
from hermes.services.case_service import CaseService

logger = get_logger(__name__)
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

    # 为当前 trace 补充多租户和案件上下文
    tag_current_span(
        tags=[f"client:{case.client}", "feature:approval"],
        metadata={"case_id": str(case.id), "task_id": case.task_id, "stage": case.current_stage},
    )

    svc = CaseService(db)

    # 查询当前阶段的待守门记录
    stage = await svc.get_case_stage(
        case.id, case.current_stage, status="pending_approval"
    )

    # 如果当前阶段已审批通过/修改通过，自动推进到下一阶段
    if not stage:
        current = await svc.get_case_stage(case.id, case.current_stage)
        if current and current.status in ("approved", "modified"):
            next_stage = _get_next_stage(case.current_stage)
            if next_stage:
                case.current_stage = next_stage
                stage = await svc.get_case_stage(case.id, next_stage)
                if stage:
                    stage.status = "pending_approval"
                    if not stage.started_at:
                        stage.started_at = datetime.now(UTC)
                else:
                    # 创建下一阶段记录
                    stage_order = {
                        "intake": 1, "investigation": 2, "analysis": 3,
                        "disposition": 4, "enforcement": 5, "post_report": 6,
                    }
                    stage = CaseStage(
                        case_id=case.id,
                        stage_name=next_stage,
                        stage_order=stage_order.get(next_stage, 0),
                        status="pending_approval",
                        started_at=datetime.now(UTC),
                    )
                    db.add(stage)
                await db.flush()
        elif current and current.status == "rejected":
            # 驳回后重新激活当前阶段，等待 AI 重新生成
            current.status = "pending_approval"
            current.completed_at = None
            stage = current
            await db.flush()

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

    # 为当前 trace 补充多租户和案件上下文
    tag_current_span(
        tags=[f"client:{case.client}", "feature:approval"],
        metadata={"case_id": str(case.id), "task_id": case.task_id, "stage": stage},
    )

    # 获取当前阶段记录（含 AI 产出）
    svc = CaseService(db)
    stage_record = await svc.get_case_stage(case.id, stage)
    original_output = stage_record.ai_output if stage_record else None

    # 创建守门记录（不可篡改，审计追溯）
    approval = HumanApproval(
        case_id=case.id,
        stage_name=stage,
        reviewer_id=current_user.username,
        action=request.action,
        original_output=original_output,
        modified_output=request.modifications if request.modifications else None,
        modifications_summary=request.comment,
        comment=request.comment,
        signature=sign_approval(
            str(case.id), stage, current_user.username, request.action
        ),
    )
    db.add(approval)

    # 更新阶段状态
    now = datetime.now(UTC)
    if request.action == "approved":
        await svc.update_stage_status(case.id, stage, "approved", completed_at=now)
    elif request.action == "modified":
        # 将修改合并到 ai_output（无修改时保留原始输出）
        merged_output = stage_record.ai_output
        if request.modifications:
            merged_output = {**(stage_record.ai_output or {}), **request.modifications}
        await svc.update_stage_status(case.id, stage, "modified", ai_output=merged_output, completed_at=now)
    else:
        await svc.update_stage_status(case.id, stage, "rejected", completed_at=now)

    # approved 和 modified 都推进到下一阶段
    next_stage = None
    if request.action in ("approved", "modified"):
        next_stage = _get_next_stage(stage)

    # 推进案件当前阶段并激活下一阶段的 CaseStage 记录
    if next_stage:
        case.current_stage = next_stage
        # 查找预创建的下一阶段 CaseStage（含 LangGraph 后台已持久化的 AI 产出），激活为待守门
        next_stage_record = await svc.get_case_stage(case.id, next_stage)
        if next_stage_record:
            next_stage_record.status = "pending_approval"
            if not next_stage_record.started_at:
                next_stage_record.started_at = now
        else:
            # 兜底：创建新记录
            stage_order = {
                "intake": 1, "investigation": 2, "analysis": 3,
                "disposition": 4, "enforcement": 5, "post_report": 6,
            }
            db.add(CaseStage(
                case_id=case.id,
                stage_name=next_stage,
                stage_order=stage_order.get(next_stage, 0),
                status="pending_approval",
                started_at=now,
            ))
    elif request.action == "rejected":
        # 驳回：保持在当前阶段，触发 AI 重新生成
        # 先同步写入"生成中"状态，让前端立即感知
        await svc.update_stage_status(
            case.id, stage, "rejected",
            ai_output={"status": "generating", "message": "AI 正在重新生成分析结果..."},
            completed_at=now,
        )
        _trigger_stage_regeneration(case, stage)
    else:
        # 最后一个阶段完成
        case.status = "closed"

    await db.flush()

    # 将人工守门决策记录为 Langfuse score（人工反馈信号）
    trace_id = get_trace_id()
    if trace_id:
        create_score(
            trace_id=trace_id,
            name="human-gate-decision",
            value=request.action,
            data_type="CATEGORICAL",
            comment=f"stage={stage} reviewer={current_user.username} comment={request.comment or ''}",
        )

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
    await _get_case(case_id, current_user, db)

    # 划词调整：调用 LLM 定向重新生成选中段落
    # 当前返回固定值：LLM 定向重新生成待接入
    try:
        from hermes.agents.llm_adapter import llm_adapter
        response = await llm_adapter.invoke(
            messages=[
                {"role": "system", "content": "你是赫尔墨斯风控系统的AI助手。根据指令对指定文本进行修改。"},
                {"role": "user", "content": (
                    f"原文:\n{request.selected_text}\n\n"
                    f"修改指令:\n{request.instruction}\n\n"
                    f"请输出修改后的文本（仅输出修改后的文本，不要额外说明）："
                )},
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


def _trigger_stage_regeneration(case: Case, stage: str) -> None:
    """驳回后触发 AI Agent 重新生成当前阶段内容（后台异步执行）"""
    import asyncio
    asyncio.create_task(_regenerate_stage_async(str(case.id), stage, case.task_id, case.client, case.fraud_source))


async def _regenerate_stage_async(case_id: str, stage: str, task_id: str, client: str, fraud_source: str) -> None:
    """后台异步：调用对应阶段 Agent 并持久化输出"""
    logger.info("stage_regeneration_start", case_id=case_id, stage=stage)
    try:
        from datetime import UTC
        from datetime import datetime as dt

        from hermes.db.models.integrity import CaseStage
        from hermes.db.session import async_session_factory

        # 1. 先写入 "正在生成" 状态，让前端轮询感知进度
        now = dt.now(UTC)
        async with async_session_factory() as db:
            result = await db.execute(
                select(CaseStage).where(
                    CaseStage.case_id == uuid.UUID(case_id),
                    CaseStage.stage_name == stage,
                ).order_by(CaseStage.started_at.desc().nullslast()).limit(1)
            )
            stage_record = result.scalar_one_or_none()
            if stage_record:
                stage_record.ai_output = {"status": "generating", "message": "AI 正在重新生成分析结果..."}
                stage_record.completed_at = None
                await db.commit()

        # 2. 调用对应阶段的 AI Agent
        ai_output = await _run_stage_agent(stage, task_id, client, fraud_source)

        # 3. 持久化生成结果
        async with async_session_factory() as db:
            result = await db.execute(
                select(CaseStage).where(
                    CaseStage.case_id == uuid.UUID(case_id),
                    CaseStage.stage_name == stage,
                ).order_by(CaseStage.started_at.desc().nullslast()).limit(1)
            )
            stage_record = result.scalar_one_or_none()
            if stage_record:
                stage_record.ai_output = ai_output
                if not stage_record.started_at:
                    stage_record.started_at = now
                await db.commit()
                logger.info("stage_regeneration_complete", case_id=case_id, stage=stage, keys=list(ai_output.keys()))

    except Exception as e:
        logger.error("stage_regeneration_failed", case_id=case_id, stage=stage, error=str(e))
        # 写入失败状态，让前端感知
        try:
            async with async_session_factory() as db:
                result = await db.execute(
                    select(CaseStage).where(
                        CaseStage.case_id == uuid.UUID(case_id),
                        CaseStage.stage_name == stage,
                    ).order_by(CaseStage.started_at.desc().nullslast()).limit(1)
                )
                stage_record = result.scalar_one_or_none()
                if stage_record:
                    stage_record.ai_output = {
                        "status": "error",
                        "message": f"AI 生成失败: {str(e)[:200]}",
                        "error": str(e),
                    }
                    await db.commit()
        except Exception:
            pass


async def _run_stage_agent(stage: str, task_id: str, client: str, fraud_source: str) -> dict:
    """根据阶段名称调用对应的 AI Agent"""
    if stage == "intake":
        from hermes.agents.integrity.intake_agent import IntakeAgent
        from hermes.agents.integrity.schemas import IntakeAgentInput
        agent = IntakeAgent()
        result = await agent.run(IntakeAgentInput(
            task_id=task_id, fraud_source=fraud_source, client=client,
            fraud_event_detail=f"案件 {task_id}，事业部 {client}，来源 {fraud_source}",
        ))
        output = result.model_dump()
        # 移除过大的下游上下文字段
        output.pop("downstream_context", None)
        return output

    elif stage == "investigation":
        from hermes.agents.integrity.investigation_agent import InvestigationAgent
        from hermes.agents.integrity.schemas import Client, InvestigationAgentInput
        agent = InvestigationAgent()
        result = await agent.run(InvestigationAgentInput(
            task_id=task_id, client=Client(client),
            intake_context={}, intake_report_summary="", involved_entity_type="混合",
            key_facts=[], suggested_focus=[], suggested_interview_targets=[],
            case_files=[], evidence_summary={},
        ))
        return result.model_dump()

    elif stage == "analysis":
        from hermes.agents.integrity.analysis_agent import AnalysisAgent
        from hermes.agents.integrity.schemas import AnalysisAgentInput, Client
        agent = AnalysisAgent()
        result = await agent.run(AnalysisAgentInput(
            task_id=task_id, client=Client(client),
            intake_context={}, investigation_context={},
        ))
        return result.model_dump()

    elif stage == "disposition":
        from hermes.agents.integrity.disposition_agent import DispositionAgent
        from hermes.agents.integrity.schemas import Client, DispositionAgentInput
        agent = DispositionAgent()
        result = await agent.run(DispositionAgentInput(
            task_id=task_id, client=Client(client), case_conclusion={},
        ))
        return result.model_dump()

    elif stage == "enforcement":
        from hermes.agents.integrity.enforcement_agent import EnforcementAgent
        from hermes.agents.integrity.schemas import Client, EnforcementAgentInput
        agent = EnforcementAgent()
        result = await agent.run(EnforcementAgentInput(
            task_id=task_id, client=Client(client), penalty_opinion={},
        ))
        return result.model_dump()

    # post_report
    from hermes.agents.integrity.post_report_agent import PostReportAgent
    from hermes.agents.integrity.schemas import DispositionPath, PostReportInput
    agent = PostReportAgent()
    result = await agent.run(PostReportInput(
        task_id=task_id, client=client,
        case_conclusion={}, penalty_opinion={}, disposition_path=DispositionPath.INTERNAL,
    ))
    return result.model_dump()
