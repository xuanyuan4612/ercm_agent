"""
案件管理业务逻辑层
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hermes.db.models.integrity import Case, CaseStage


class CaseService:
    """案件管理服务 — 封装 Case / CaseStage 的常用查询与更新操作。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_case(self, case_id: uuid.UUID) -> Case | None:
        result = await self.db.execute(
            select(Case).where(Case.id == case_id, Case.is_deleted == False)
        )
        return result.scalar_one_or_none()

    async def get_case_stage(
        self, case_id: uuid.UUID, stage_name: str, status: str | None = None
    ) -> CaseStage | None:
        """获取指定阶段的最新 CaseStage 记录，可按 status 过滤。"""
        stmt = select(CaseStage).where(
            CaseStage.case_id == case_id,
            CaseStage.stage_name == stage_name,
        )
        if status:
            stmt = stmt.where(CaseStage.status == status)
        stmt = stmt.order_by(CaseStage.started_at.desc()).limit(1)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_stage_status(
        self,
        case_id: uuid.UUID,
        stage_name: str,
        status: str,
        ai_output: dict[str, Any] | None = None,
        completed_at: datetime | None = None,
        started_at: datetime | None = None,
    ) -> CaseStage | None:
        """更新指定阶段最新记录的状态与产出物。"""
        stage = await self.get_case_stage(case_id, stage_name)
        if stage:
            stage.status = status
            if ai_output is not None:
                stage.ai_output = ai_output
            if completed_at is not None:
                stage.completed_at = completed_at
            if started_at is not None and stage.started_at is None:
                stage.started_at = started_at
            await self.db.flush()
        return stage

    async def count_by_status(self, client: str | None = None) -> dict[str, int]:
        query = select(Case.status, func.count(Case.id)).where(Case.is_deleted == False)
        if client:
            query = query.where(Case.client == client)
        query = query.group_by(Case.status)
        result = await self.db.execute(query)
        return {row[0]: row[1] for row in result.all()}
