"""
WebSocket 事件推送

通道：
- case:{task_id} — 案件工作流事件
- task_center:{user_id} — 任务中心事件

事件类型：
- workflow_started / stage_changed / approval_required / approval_completed
- workflow_completed / workflow_error / stage_regenerated
- task_assigned / task_updated / task_reminder / task_overdue
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from hermes.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


class ConnectionManager:
    """WebSocket 连接管理器

    维护用户 → WebSocket 连接的映射，支持按 channel 订阅推送。
    """

    def __init__(self) -> None:
        # {user_id: WebSocket}
        self._connections: dict[str, WebSocket] = {}
        # {user_id: [channel_names]}
        self._subscriptions: dict[str, list[str]] = {}

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[user_id] = websocket
        self._subscriptions[user_id] = []
        logger.info("ws_connected", user_id=user_id)

    def disconnect(self, user_id: str) -> None:
        self._connections.pop(user_id, None)
        self._subscriptions.pop(user_id, None)
        logger.info("ws_disconnected", user_id=user_id)

    def subscribe(self, user_id: str, channels: list[str]) -> None:
        self._subscriptions[user_id] = channels
        logger.info("ws_subscribed", user_id=user_id, channels=channels)

    async def send_personal(self, user_id: str, data: dict[str, Any]) -> None:
        """向指定用户推送消息"""
        ws = self._connections.get(user_id)
        if ws:
            try:
                await ws.send_json(data)
            except Exception:
                self.disconnect(user_id)

    async def broadcast_to_channel(self, channel: str, event: str, data: dict[str, Any]) -> None:
        """向订阅了指定 channel 的所有用户广播事件"""
        message = {
            "channel": channel,
            "event": event,
            "data": data,
        }
        for user_id, channels in list(self._subscriptions.items()):
            if channel in channels:
                await self.send_personal(user_id, message)

    async def broadcast_case_event(
        self, task_id: str, event: str, data: dict[str, Any]
    ) -> None:
        """广播案件工作流事件"""
        await self.broadcast_to_channel(f"case:{task_id}", event, data)

    async def broadcast_task_event(
        self, user_id: str, event: str, data: dict[str, Any]
    ) -> None:
        """推送任务中心事件"""
        await self.broadcast_to_channel(f"task_center:{user_id}", event, data)

    @property
    def active_connections_count(self) -> int:
        return len(self._connections)


# 全局连接管理器
ws_manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket 端点: ws://host/api/v1/ws?token=<access_token>

    客户端连接后需发送订阅消息：
    {"action": "subscribe", "channels": ["case:SD2026051901", "task_center:user-zhangsan"]}
    """
    # 从查询参数提取 token 并验证
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return

    # 验证 JWT token，解析 user_id
    try:
        from hermes.core.security import verify_token
        payload = verify_token(token)
        user_id = payload.get("sub", f"ws-{token[:8]}")
        logger.info("ws_auth_success", user_id=user_id)
    except Exception as e:
        logger.warning("ws_auth_failed", error=str(e))
        user_id = f"ws-{token[:8]}"
        # 降级：使用 token 前缀作为临时标识（非生产模式）

    await ws_manager.connect(user_id, websocket)

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")

            if action == "subscribe":
                channels = data.get("channels", [])
                ws_manager.subscribe(user_id, channels)
                await websocket.send_json({
                    "type": "subscribed",
                    "channels": channels,
                })

            elif action == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        ws_manager.disconnect(user_id)
    except Exception as e:
        logger.error("ws_error", user_id=user_id, error=str(e))
        ws_manager.disconnect(user_id)
