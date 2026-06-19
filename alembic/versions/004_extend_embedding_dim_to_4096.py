"""extend embedding vector dimension from 1536 to 4096 (Qwen3-Embedding-8B)

Revision ID: 004
Revises: 003
Create Date: 2026-06-19
"""
from collections.abc import Sequence

from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE knowledge_documents ALTER COLUMN embedding TYPE vector(4096);")


def downgrade() -> None:
    op.execute("ALTER TABLE knowledge_documents ALTER COLUMN embedding TYPE vector(1536);")
