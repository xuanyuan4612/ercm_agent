"""外部系统 Webhook 回调接口"""

from __future__ import annotations

from fastapi import APIRouter, Request

from hermes.core.logging import get_logger
from hermes.core.response import success

logger = get_logger(__name__)

router = APIRouter(prefix="/webhooks")


@router.post("/risk-control")
async def risk_control_webhook(request: Request):
    """风控系统 Webhook 回调

    场景：
    - case_created: 风控系统创建案件 → Hermes 同步创建
    - status_sync: 状态同步确认
    - closure_confirmed: 闭环推送确认
    """
    body = await request.json()
    event = body.get("event", "")
    logger.info("webhook_risk_control", event=event)

    if event == "case_created":
        # TODO: 同步创建 Hermes 案件
        return success({
            "acknowledged": True,
            "hermes_case_id": "c-new",
            "hermes_task_id": "DH20260606001",
        })
    elif event == "status_sync":
        # TODO: 更新同步状态
        return success({"acknowledged": True})
    elif event == "closure_confirmed":
        # TODO: 记录闭环确认
        return success({"acknowledged": True})
    return success({"acknowledged": True, "event": event})


@router.post("/oa")
async def oa_webhook(request: Request):
    """OA 系统审批结果回调

    添可事业部处罚公告 OA 审批完成后回调。
    """
    body = await request.json()
    logger.info("webhook_oa", event=body.get("event"))
    return success({"acknowledged": True})


@router.post("/mdm")
async def mdm_webhook(request: Request):
    """MDM 黑名单库操作结果回调"""
    body = await request.json()
    logger.info("webhook_mdm", event=body.get("event"))
    return success({"acknowledged": True})


@router.post("/a2a/{agent}")
async def a2a_webhook(agent: str, request: Request):
    """A2A 外部智能体回调

    龟宝/西塞罗/波特处理完成后回调。
    """
    body = await request.json()
    logger.info("webhook_a2a", agent=agent, status=body.get("status"))

    from hermes.integrations.a2a import a2a_adapter
    result = await a2a_adapter.handle_callback(agent, body)
    return success(result)
