"""风险监控模块 API 接口

规则管理 + 扫描任务 + 预警处置
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hermes.api.dependencies import CurrentUser
from hermes.core.exceptions import NotFoundError
from hermes.core.response import paginated, success
from hermes.db.models.risk_monitor import (
    RiskAlert,
    RiskAnalysisSubject,
    RiskPushRecord,
    RiskRule,
    RuleIterationLog,
)
from hermes.db.session import get_db


class RuleCreateRequest(BaseModel):
    """创建规则请求体"""
    business_unit: str | None = None
    channel: str | None = None
    format: str | None = None
    department: str | None = None
    position: str | None = None
    personnel_info: str | None = None
    business_cycle: str | None = None
    level1_scene: str | None = None
    level2_scene: str | None = None
    level3_scene: str
    sql_statement: str
    risk_level: str = "中"
    threshold: float | None = None
    monitor_frequency: str = "daily"
    monitor_business_unit: str | None = None
    use_external_data: bool = False


class RuleUpdateRequest(BaseModel):
    """更新规则请求体"""
    level1_scene: str | None = None
    level2_scene: str | None = None
    level3_scene: str | None = None
    sql_statement: str | None = None
    risk_level: str | None = None
    threshold: float | None = None
    monitor_frequency: str | None = None
    monitor_business_unit: str | None = None
    use_external_data: bool | None = None


class RuleApproveRequest(BaseModel):
    """规则审批请求体"""
    action: str = Field(..., description="approved / rejected")
    comment: str | None = None


class AlertApproveRequest(BaseModel):
    """预警审批请求体"""
    action: str = Field(..., description="approved / rejected / revised")
    comment: str | None = None
    modifications: str | None = Field(None, description="修正内容 (JSON)")

router = APIRouter(prefix="/risk-monitor")

# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════


def _generate_rule_code() -> str:
    seq = uuid.uuid4().hex[:6].upper()
    return f"RULE-{seq}"


def _generate_alert_code() -> str:
    seq = uuid.uuid4().hex[:6].upper()
    return f"ALT-{seq}"


def _rule_to_dict(rule: RiskRule) -> dict:
    return {
        "id": str(rule.id),
        "rule_code": rule.rule_code,
        "business_unit": rule.business_unit,
        "channel": rule.channel,
        "format": rule.format,
        "department": rule.department,
        "position": rule.position,
        "personnel_info": rule.personnel_info,
        "business_cycle": rule.business_cycle,
        "level1_scene": rule.level1_scene,
        "level2_scene": rule.level2_scene,
        "level3_scene": rule.level3_scene,
        "sql_statement": rule.sql_statement,
        "risk_level": rule.risk_level,
        "threshold": float(rule.threshold) if rule.threshold else None,
        "monitor_frequency": rule.monitor_frequency,
        "monitor_business_unit": rule.monitor_business_unit,
        "use_external_data": rule.use_external_data,
        "status": rule.status,
        "version": rule.version,
        "reviewed_by": rule.reviewed_by,
        "reviewed_at": rule.reviewed_at.isoformat() if rule.reviewed_at else None,
        "created_by": rule.created_by,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
    }


def _alert_to_brief(alert: RiskAlert) -> dict:
    return {
        "id": str(alert.id),
        "alert_code": alert.alert_code,
        "rule_id": str(alert.rule_id) if alert.rule_id else None,
        "analysis_subject_id": str(alert.analysis_subject_id) if alert.analysis_subject_id else None,
        "business_unit": alert.business_unit,
        "alert_time": alert.alert_time.isoformat() if alert.alert_time else None,
        "risk_type": alert.risk_type,
        "risk_level": alert.risk_level,
        "severity": alert.severity,
        "status": alert.status,
        "impact_amount": float(alert.impact_amount) if alert.impact_amount else None,
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
    }


def _alert_to_detail(alert: RiskAlert) -> dict:
    data = _alert_to_brief(alert)
    data.update({
        "alert_data": alert.alert_data,
        "widespread": alert.widespread,
        "impact_degree": alert.impact_degree,
        "handling_suggestion": alert.handling_suggestion,
        "reviewed_by": alert.reviewed_by,
        "reviewed_at": alert.reviewed_at.isoformat() if alert.reviewed_at else None,
    })
    return data


# ═══════════════════════════════════════════════════════════════
# 规则管理
# ═══════════════════════════════════════════════════════════════


@router.get("/rules")
async def list_rules(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    status: str | None = Query(None, description="规则状态: draft/pending_review/active/deprecated"),
    risk_level: str | None = Query(None, description="风险等级: 高/中/低"),
    business_unit: str | None = Query(None, description="事业部"),
    keyword: str | None = Query(None, description="搜索关键词"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """查询风险规则列表"""
    query = select(RiskRule)

    if status:
        query = query.where(RiskRule.status == status)
    if risk_level:
        query = query.where(RiskRule.risk_level == risk_level)
    if business_unit:
        query = query.where(RiskRule.business_unit == business_unit)
    if keyword:
        from sqlalchemy import or_
        query = query.where(
            or_(
                RiskRule.rule_code.ilike(f"%{keyword}%"),
                RiskRule.level1_scene.ilike(f"%{keyword}%"),
                RiskRule.level2_scene.ilike(f"%{keyword}%"),
                RiskRule.level3_scene.ilike(f"%{keyword}%"),
                RiskRule.sql_statement.ilike(f"%{keyword}%"),
            )
        )

    # 计数
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # 分页
    query = query.order_by(RiskRule.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    rules = result.scalars().all()

    return paginated(
        items=[_rule_to_dict(r) for r in rules],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/rules", status_code=201)
async def create_rule(
    request: RuleCreateRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """人工录入创建风险规则"""
    rule = RiskRule(
        rule_code=_generate_rule_code(),
        business_unit=request.business_unit,
        channel=request.channel,
        format=request.format,
        department=request.department,
        position=request.position,
        personnel_info=request.personnel_info,
        business_cycle=request.business_cycle,
        level1_scene=request.level1_scene,
        level2_scene=request.level2_scene,
        level3_scene=request.level3_scene,
        sql_statement=request.sql_statement,
        risk_level=request.risk_level,
        threshold=request.threshold,
        monitor_frequency=request.monitor_frequency,
        monitor_business_unit=request.monitor_business_unit,
        use_external_data=request.use_external_data,
        status="draft",
        created_by=current_user.username,
    )
    db.add(rule)
    await db.flush()

    return success(_rule_to_dict(rule))


@router.get("/rules/{rule_id}")
async def get_rule(
    rule_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """查询规则详情"""
    result = await db.execute(select(RiskRule).where(RiskRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise NotFoundError(detail=f"规则 {rule_id} 不存在")

    # 同时返回迭代历史
    iter_result = await db.execute(
        select(RuleIterationLog)
        .where(RuleIterationLog.rule_id == rule_id)
        .order_by(RuleIterationLog.created_at.desc())
    )
    iterations = iter_result.scalars().all()

    return success({
        "rule": _rule_to_dict(rule),
        "iterations": [
            {
                "id": str(it.id),
                "iteration_type": it.iteration_type,
                "old_sql": it.old_sql,
                "new_sql": it.new_sql,
                "old_threshold": float(it.old_threshold) if it.old_threshold else None,
                "new_threshold": float(it.new_threshold) if it.new_threshold else None,
                "reason": it.reason,
                "operator_id": it.operator_id,
                "created_at": it.created_at.isoformat() if it.created_at else None,
            }
            for it in iterations
        ],
    })


@router.put("/rules/{rule_id}")
async def update_rule(
    rule_id: uuid.UUID,
    request: RuleUpdateRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """更新规则（仅草稿和已驳回状态可编辑）"""
    result = await db.execute(select(RiskRule).where(RiskRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise NotFoundError(detail=f"规则 {rule_id} 不存在")

    if rule.status not in ("draft", "rejected"):
        from hermes.core.exceptions import CaseStatusConflictError
        raise CaseStatusConflictError(detail="仅草稿和已驳回状态的规则可编辑")

    # 记录变更
    for field, new_val in [
        ("level1_scene", request.level1_scene), ("level2_scene", request.level2_scene),
        ("level3_scene", request.level3_scene), ("sql_statement", request.sql_statement),
        ("risk_level", request.risk_level), ("threshold", request.threshold),
        ("monitor_frequency", request.monitor_frequency),
        ("monitor_business_unit", request.monitor_business_unit),
    ]:
        if new_val is not None:
            setattr(rule, field, new_val)

    if request.use_external_data is not None:
        rule.use_external_data = request.use_external_data

    rule.updated_by = current_user.username
    await db.flush()

    return success(_rule_to_dict(rule))


@router.post("/rules/{rule_id}/approve")
async def approve_rule(
    rule_id: uuid.UUID,
    request: RuleApproveRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """审批规则（通过/驳回）"""
    result = await db.execute(select(RiskRule).where(RiskRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise NotFoundError(detail=f"规则 {rule_id} 不存在")

    if request.action == "approved":
        rule.status = "active"
    elif request.action == "rejected":
        rule.status = "rejected"
    else:
        from hermes.core.exceptions import BadRequestError
        raise BadRequestError(detail=f"无效的审批动作: {request.action}")

    rule.reviewed_by = current_user.username
    rule.reviewed_at = datetime.now(UTC)
    await db.flush()

    # 记录审批日志
    log = RuleIterationLog(
        rule_id=rule.id,
        iteration_type="approval",
        reason=request.comment or f"审批结果: {request.action}",
        operator_id=current_user.username,
    )
    db.add(log)
    await db.flush()

    return success(_rule_to_dict(rule))


@router.delete("/rules/{rule_id}")
async def deactivate_rule(
    rule_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """禁用规则（软删除为 deprecated）"""
    result = await db.execute(select(RiskRule).where(RiskRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise NotFoundError(detail=f"规则 {rule_id} 不存在")

    rule.status = "deprecated"
    rule.updated_by = current_user.username
    await db.flush()

    return success(message=f"规则 {rule.rule_code} 已禁用")


# ═══════════════════════════════════════════════════════════════
# 扫描任务
# ═══════════════════════════════════════════════════════════════


@router.get("/scans")
async def list_scans(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """查询扫描任务列表（基于预警记录聚合）"""
    # 扫描任务目前没有独立表，基于 RiskAlert 的 alert_time 聚合为扫描批次
    scan_time_expr = func.date_trunc("hour", RiskAlert.alert_time)

    query = (
        select(
            scan_time_expr.label("scan_time"),
            func.count(RiskAlert.id).label("alert_count"),
            func.array_agg(func.distinct(RiskAlert.status)).label("statuses"),
        )
        .group_by(scan_time_expr)
        .order_by(scan_time_expr.desc())
    )

    # 计数（按小时去重后的扫描批次总数）
    total = (await db.execute(
        select(func.count(func.distinct(scan_time_expr)))
    )).scalar() or 0

    # 分页
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    rows = result.all()

    scan_tasks = []
    for row in rows:
        scan_tasks.append({
            "scan_id": f"SCAN-{row.scan_time.strftime('%Y%m%d%H')}",
            "scan_time": row.scan_time.isoformat() if row.scan_time else None,
            "alert_count": row.alert_count,
            "statuses": list({s for s in row.statuses if s}),
            "status": "completed" if all(s in ("approved", "rejected", "pushed") for s in row.statuses) else "in_progress",
        })

    return paginated(
        items=scan_tasks,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/scans", status_code=201)
async def trigger_scan(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    target_rules: str | None = Query(None, description="目标规则ID列表，逗号分隔，空=全部生效规则"),
    target_business_units: str | None = Query(None, description="目标事业部，逗号分隔，空=全部"),
):
    """手动触发风险扫描"""
    # 查询生效的规则
    rules_query = select(RiskRule).where(RiskRule.status == "active")
    if target_rules:
        rule_ids = [uuid.UUID(rid.strip()) for rid in target_rules.split(",")]
        rules_query = rules_query.where(RiskRule.id.in_(rule_ids))
    if target_business_units:
        units = [u.strip() for u in target_business_units.split(",")]
        rules_query = rules_query.where(RiskRule.monitor_business_unit.in_(units))

    result = await db.execute(rules_query)
    rules = result.scalars().all()

    # TODO: 实际触发 Celery 任务执行扫描
    # from hermes.tasks.risk_scan import execute_risk_scan
    # task_ids = []
    # for rule in rules:
    #     task = execute_risk_scan.delay(str(rule.id), rule.sql_statement)
    #     task_ids.append(task.id)

    return success({
        "message": f"已创建扫描任务，涉及 {len(rules)} 条规则",
        "rule_count": len(rules),
        "rules": [{"id": str(r.id), "rule_code": r.rule_code, "level3_scene": r.level3_scene} for r in rules],
        # "celery_task_ids": task_ids,
    })


# ═══════════════════════════════════════════════════════════════
# 预警管理
# ═══════════════════════════════════════════════════════════════


@router.get("/alerts")
async def list_alerts(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    status: str | None = Query(None, description="预警状态: pending/reviewing/approved/rejected/pushed"),
    risk_type: str | None = Query(None, description="风险类型"),
    risk_level: str | None = Query(None, description="风险等级: 高/中/低"),
    business_unit: str | None = Query(None, description="事业部"),
    keyword: str | None = Query(None, description="搜索关键词"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """查询预警列表"""
    query = select(RiskAlert)

    if status:
        query = query.where(RiskAlert.status == status)
    if risk_type:
        query = query.where(RiskAlert.risk_type == risk_type)
    if risk_level:
        query = query.where(RiskAlert.risk_level == risk_level)
    if business_unit:
        query = query.where(RiskAlert.business_unit == business_unit)
    if keyword:
        from sqlalchemy import or_
        query = query.where(
            or_(
                RiskAlert.alert_code.ilike(f"%{keyword}%"),
                RiskAlert.risk_type.ilike(f"%{keyword}%"),
            )
        )

    # 计数
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # 分页
    query = query.order_by(RiskAlert.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    alerts = result.scalars().all()

    return paginated(
        items=[_alert_to_brief(a) for a in alerts],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/alerts/{alert_id}")
async def get_alert(
    alert_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """查询预警详情（含关联规则、主体、推送记录）"""
    result = await db.execute(select(RiskAlert).where(RiskAlert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise NotFoundError(detail=f"预警 {alert_id} 不存在")

    data = _alert_to_detail(alert)

    # 关联规则
    if alert.rule_id:
        rule_result = await db.execute(select(RiskRule).where(RiskRule.id == alert.rule_id))
        rule = rule_result.scalar_one_or_none()
        if rule:
            data["rule"] = _rule_to_dict(rule)

    # 关联分析主体
    if alert.analysis_subject_id:
        subj_result = await db.execute(
            select(RiskAnalysisSubject).where(RiskAnalysisSubject.id == alert.analysis_subject_id)
        )
        subject = subj_result.scalar_one_or_none()
        if subject:
            data["analysis_subject"] = {
                "id": str(subject.id),
                "subject_code": subject.subject_code,
                "subject_name": subject.subject_name,
                "subject_type": subject.subject_type,
                "contact_info": subject.contact_info,
                "merge_source_ids": subject.merge_source_ids,
                "risk_behavior": subject.risk_behavior,
                "risk_business": subject.risk_business,
                "impact_scope": subject.impact_scope,
                "involved_amount": float(subject.involved_amount) if subject.involved_amount else None,
                "analysis_report_path": subject.analysis_report_path,
            }

    # 推送记录
    push_result = await db.execute(
        select(RiskPushRecord)
        .where(RiskPushRecord.alert_id == alert_id)
        .order_by(RiskPushRecord.created_at.desc())
    )
    pushes = push_result.scalars().all()
    data["push_records"] = [
        {
            "id": str(p.id),
            "target_module": p.target_module,
            "target_record_id": str(p.target_record_id) if p.target_record_id else None,
            "push_status": p.push_status,
            "callback_status": p.callback_status,
            "callback_detail": p.callback_detail,
            "push_at": p.push_at.isoformat() if p.push_at else None,
            "callback_at": p.callback_at.isoformat() if p.callback_at else None,
        }
        for p in pushes
    ]

    return success(data)


@router.post("/alerts/{alert_id}/approve")
async def approve_alert(
    alert_id: uuid.UUID,
    request: AlertApproveRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """审批预警（确认/驳回/修正）"""
    result = await db.execute(select(RiskAlert).where(RiskAlert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise NotFoundError(detail=f"预警 {alert_id} 不存在")

    import json
    if request.action == "approved":
        alert.status = "approved"
    elif request.action == "rejected":
        alert.status = "rejected"
    elif request.action == "revised":
        alert.status = "reviewing"
        if request.modifications:
            try:
                mods = json.loads(request.modifications)
                if "risk_type" in mods:
                    alert.risk_type = mods["risk_type"]
                if "risk_level" in mods:
                    alert.risk_level = mods["risk_level"]
                if "severity" in mods:
                    alert.severity = mods["severity"]
                if "handling_suggestion" in mods:
                    alert.handling_suggestion = mods["handling_suggestion"]
            except json.JSONDecodeError:
                pass
    else:
        from hermes.core.exceptions import BadRequestError
        raise BadRequestError(detail=f"无效的审批动作: {request.action}")

    alert.reviewed_by = current_user.username
    alert.reviewed_at = datetime.now(UTC)
    await db.flush()

    return success(_alert_to_detail(alert))


@router.get("/alerts/{alert_id}/pushes")
async def get_alert_pushes(
    alert_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """查询预警推送记录"""
    result = await db.execute(
        select(RiskPushRecord)
        .where(RiskPushRecord.alert_id == alert_id)
        .order_by(RiskPushRecord.created_at.desc())
    )
    pushes = result.scalars().all()

    return success([
        {
            "id": str(p.id),
            "alert_id": str(p.alert_id),
            "target_module": p.target_module,
            "target_record_id": str(p.target_record_id) if p.target_record_id else None,
            "push_payload": p.push_payload,
            "push_status": p.push_status,
            "callback_status": p.callback_status,
            "callback_detail": p.callback_detail,
            "push_at": p.push_at.isoformat() if p.push_at else None,
            "callback_at": p.callback_at.isoformat() if p.callback_at else None,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in pushes
    ])
