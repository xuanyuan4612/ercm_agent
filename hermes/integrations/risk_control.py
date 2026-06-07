"""
风控系统集成适配器 (Risk Control Adapter)

职责：
- 字段映射（Hermes ↔ 风控系统双向）
- 状态同步（WebSocket 推送案件状态变更）
- Webhook 接收（案件创建同步、闭环推送确认）
"""

from __future__ import annotations

from typing import Any

from hermes.core.logging import get_logger

logger = get_logger(__name__)


class RiskControlAdapter:
    """风控系统适配器

    处理 Hermes 与外部风控系统之间的数据交互：
    - 案件创建 → 风控推送
    - 工作流状态 → 风控按钮联动
    - 闭环结果 → 风控确认
    """

    # 字段映射：Hermes 案件字段 ↔ 风控系统字段
    FIELD_MAP = {
        "fraud_source": "fraudSource",
        "reported_staff_names": "reportedStaffName",
        "reported_supplier_names": "reportedSupplierName",
        "reported_dealer_names": "reportedDealerName",
        "fraud_event_detail": "fraudEventDetail",
        "proof": "proof",
        "fraud_tel": "fraudTel",
        "fraud_email": "fraudEmail",
        "attachments": "attachments",
        "client": "client",
        "current_stage": "currentStage",
        "status": "status",
    }

    def to_risk_control(self, hermes_case: dict[str, Any]) -> dict[str, Any]:
        """将 Hermes 案件数据映射为风控系统格式"""
        mapped = {}
        for hermes_key, rc_key in self.FIELD_MAP.items():
            if hermes_key in hermes_case:
                mapped[rc_key] = hermes_case[hermes_key]
        return mapped

    def from_risk_control(self, rc_data: dict[str, Any]) -> dict[str, Any]:
        """将风控系统数据映射为 Hermes 格式"""
        reverse_map = {v: k for k, v in self.FIELD_MAP.items()}
        mapped = {}
        for rc_key, value in rc_data.items():
            hermes_key = reverse_map.get(rc_key)
            if hermes_key:
                mapped[hermes_key] = value
        return mapped

    async def push_case_update(
        self, hermes_case_id: str, updates: dict[str, Any]
    ) -> dict[str, Any]:
        """向风控系统推送案件更新"""
        # TODO: 通过 RabbitMQ 或 HTTP 回调推送至风控系统
        logger.info(
            "risk_control_push",
            hermes_case_id=hermes_case_id,
            updates=list(updates.keys()),
        )
        return {"status": "queued"}

    async def sync_status(
        self, hermes_case_id: str, stage: str, status: str
    ) -> dict[str, Any]:
        """同步工作流状态到风控系统（用于按钮联动）"""
        button_status_map = {
            "intake": "线索初判-待确认",
            "investigation": "调查进行中",
            "analysis": "报告撰写中",
            "disposition": "处置分流中",
            "enforcement": "处罚执行中",
            "post_report": "报案协助中",
        }

        # TODO: 通过 WebSocket 推送至风控系统
        return {
            "hermes_case_id": hermes_case_id,
            "current_stage": stage,
            "button_status": button_status_map.get(stage, "处理中"),
        }


# 全局单例
risk_control_adapter = RiskControlAdapter()
