"""案件管理接口（廉洁监察模块）"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from hermes.api.dependencies import CurrentUser, check_client_access, require_role
from hermes.core.exceptions import (
    CaseNotFoundError,
    CaseStatusConflictError,
    WorkflowAlreadyStartedError,
)
from hermes.core.response import paginated, success
from hermes.db.models.integrity import Case, CaseStage, GeneratedDocument
from hermes.db.session import get_db
from hermes.schemas.case import CaseBrief, CaseCreateRequest, CaseDetail, CaseUpdateRequest

router = APIRouter(prefix="/cases")


def _apply_client_filter(user, query):
    """应用 RBAC 行级过滤"""
    if user.role == "group":
        return query
    return query.where(Case.client == user.role)


def _case_to_brief(case: Case) -> dict:
    return {
        "id": str(case.id),
        "task_id": case.task_id,
        "case_code": case.case_code,
        "client": case.client,
        "fraud_source": case.fraud_source,
        "current_stage": case.current_stage,
        "status": case.status,
        "created_by": case.created_by,
        "created_at": case.created_at.isoformat() if case.created_at else None,
        "updated_at": case.updated_at.isoformat() if case.updated_at else None,
    }


def _case_to_detail(case: Case) -> dict:
    return {
        "id": str(case.id),
        "task_id": case.task_id,
        "case_code": case.case_code,
        "client": case.client,
        "fraud_source": case.fraud_source,
        "current_stage": case.current_stage,
        "status": case.status,
        "fraud_event_detail": case.fraud_detail,
        "proof": case.proof,
        "attachments": case.attachments or [],
        "fraud_tel": None,  # 脱敏
        "risk_control_case_id": case.risk_control_case_id,
        "workflow_state": case.workflow_state,
        "langgraph_thread_id": case.langgraph_thread_id,
        "generated_documents": [
            {"id": str(d.id), "type": d.doc_type, "name": d.file_path or "", "format": d.file_format, "created_at": d.created_at}
            for d in (case.documents or [])
        ],
        "created_by": case.created_by,
        "created_at": case.created_at.isoformat() if case.created_at else None,
        "updated_at": case.updated_at.isoformat() if case.updated_at else None,
    }


def _generate_task_id(source: str) -> str:
    """生成 task_id：来源缩写 + 年月日 + 序号"""
    prefix_map = {
        "manual": "SD", "phone": "DH", "email": "YX",
        "wechat": "GZ", "agent": "ZN",
    }
    prefix = prefix_map.get(source, "XX")
    today = datetime.now(UTC).strftime("%Y%m%d")
    # 简化实现：使用 uuid4 的后6位作为序号
    seq = uuid.uuid4().hex[:4].upper()
    return f"{prefix}{today}{seq}"


@router.post("", status_code=201)
async def create_case(
    request: CaseCreateRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """创建案件（双轨来源：系统抓取 + 人工录入）"""
    check_client_access(current_user, request.client)

    task_id = _generate_task_id(request.fraud_source)

    case = Case(
        task_id=task_id,
        fraud_source=request.fraud_source,
        client=request.client,
        fraud_detail=request.fraud_event_detail,
        proof=request.proof,
        attachments=request.attachments,
        risk_control_case_id=request.risk_control_case_id,
        status="pending",
        created_by=current_user.username,
        updated_by=current_user.username,
    )
    # 加密敏感字段（当前为明文存储，生产环境需 AES-256-GCM 加密）
    # from hermes.core.security import encrypt_sensitive
    # 敏感字段: reported_staff_names, reported_supplier_names, fraud_tel, fraud_email
    # case.reported_staff_encrypted = encrypt_sensitive(json.dumps(request.reported_staff_names))
    db.add(case)
    await db.flush()

    return success({
        "id": str(case.id),
        "task_id": case.task_id,
        "client": case.client,
        "fraud_source": case.fraud_source,
        "current_stage": case.current_stage,
        "status": case.status,
        "created_at": case.created_at.isoformat() if case.created_at else None,
    })


@router.get("")
async def list_cases(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    client: str | None = Query(None),
    source: str | None = Query(None, alias="source"),
    status: str | None = Query(None),
    stage: str | None = Query(None, alias="stage"),
    keyword: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """查询案件列表"""
    query = select(Case).where(Case.is_deleted == False)
    query = _apply_client_filter(current_user, query)

    if client:
        query = query.where(Case.client == client)
    if source:
        query = query.where(Case.fraud_source == source)
    if status:
        query = query.where(Case.status == status)
    if stage:
        query = query.where(Case.current_stage == stage)
    if keyword:
        query = query.where(
            or_(
                Case.task_id.ilike(f"%{keyword}%"),
                Case.fraud_detail.ilike(f"%{keyword}%"),
            )
        )
    if start_date:
        query = query.where(Case.created_at >= start_date)
    if end_date:
        query = query.where(Case.created_at <= end_date)

    # 计数
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # 分页
    query = query.order_by(Case.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    cases = result.scalars().all()

    return paginated(
        items=[_case_to_brief(c) for c in cases],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{case_id}")
async def get_case(
    case_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """查询案件详情"""
    result = await db.execute(
        select(Case).where(Case.id == case_id, Case.is_deleted == False)
    )
    case = result.scalar_one_or_none()
    if not case:
        raise CaseNotFoundError(str(case_id))
    check_client_access(current_user, case.client)

    return success(_case_to_detail(case))


@router.put("/{case_id}")
async def update_case(
    case_id: uuid.UUID,
    request: CaseUpdateRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """更新案件（仅 status=pending 时允许）"""
    result = await db.execute(
        select(Case).where(Case.id == case_id, Case.is_deleted == False)
    )
    case = result.scalar_one_or_none()
    if not case:
        raise CaseNotFoundError(str(case_id))
    check_client_access(current_user, case.client)

    if case.status != "pending":
        raise CaseStatusConflictError(detail="仅 status=pending 的案件可编辑")

    if request.fraud_event_detail is not None:
        case.fraud_detail = request.fraud_event_detail
    if request.proof is not None:
        case.proof = request.proof
    if request.attachments is not None:
        case.attachments = request.attachments
    case.updated_by = current_user.username

    await db.flush()
    return success(_case_to_detail(case))


@router.delete("/{case_id}")
async def delete_case(
    case_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """软删除案件"""
    result = await db.execute(
        select(Case).where(Case.id == case_id, Case.is_deleted == False)
    )
    case = result.scalar_one_or_none()
    if not case:
        raise CaseNotFoundError(str(case_id))
    check_client_access(current_user, case.client)

    if case.status not in ("pending", "closed"):
        raise CaseStatusConflictError(detail="仅 status=pending 或 closed 的案件可删除")

    case.is_deleted = True
    case.status = "closed"
    await db.flush()
    return success(message=f"案件 {case.task_id} 已删除")
