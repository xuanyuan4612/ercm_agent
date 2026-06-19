"""extend knowledge_documents with security and approval fields

Revision ID: 003
Revises: 002
Create Date: 2026-06-19
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("knowledge_documents", sa.Column("approval_status", sa.String(20), nullable=False, server_default="approved", comment="审核状态"))
    op.add_column("knowledge_documents", sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True, comment="生效日期"))
    op.add_column("knowledge_documents", sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True, comment="失效日期"))
    op.add_column("knowledge_documents", sa.Column("security_level", sa.String(20), nullable=False, server_default="internal", comment="密级"))
    op.add_column("knowledge_documents", sa.Column("client", sa.String(20), nullable=False, server_default="group", comment="租户"))
    op.add_column("knowledge_documents", sa.Column("org_id", sa.String(50), nullable=False, server_default="*", comment="组织ID"))
    op.create_index("idx_kd_approval_status", "knowledge_documents", ["approval_status"])
    op.create_index("idx_kd_security_level", "knowledge_documents", ["security_level"])
    op.create_index("idx_kd_client", "knowledge_documents", ["client"])
    op.create_index("idx_kd_org_id", "knowledge_documents", ["org_id"])
    op.create_index("idx_kd_content_hash", "knowledge_documents", ["content_hash"])


def downgrade() -> None:
    op.drop_index("idx_kd_content_hash")
    op.drop_index("idx_kd_org_id")
    op.drop_index("idx_kd_client")
    op.drop_index("idx_kd_security_level")
    op.drop_index("idx_kd_approval_status")
    op.drop_column("knowledge_documents", "org_id")
    op.drop_column("knowledge_documents", "client")
    op.drop_column("knowledge_documents", "security_level")
    op.drop_column("knowledge_documents", "expired_at")
    op.drop_column("knowledge_documents", "effective_at")
    op.drop_column("knowledge_documents", "approval_status")
