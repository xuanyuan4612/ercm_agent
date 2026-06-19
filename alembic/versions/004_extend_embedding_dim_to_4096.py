"""extend embedding vector dimension from 1536 to 4096 (Qwen3-Embedding-8B)

Revision ID: 004
Revises: 003
Create Date: 2026-06-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE knowledge_documents ALTER COLUMN embedding TYPE vector(4096);")


def downgrade() -> None:
    op.execute("ALTER TABLE knowledge_documents ALTER COLUMN embedding TYPE vector(1536);")
