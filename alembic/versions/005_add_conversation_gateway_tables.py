"""add conversation gateway tables

Revision ID: 005
Revises: a4d0bb016263
Create Date: 2026-06-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '005'
down_revision: Union[str, None] = 'a4d0bb016263'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建 conversation_sessions / conversation_messages / intent_decisions 三张表"""
    op.create_table(
        'conversation_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id'), nullable=False),
        sa.Column('client_scope', postgresql.JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column('status', sa.String(20), nullable=False,
                  server_default='active'),
        sa.Column('related_case_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('related_module', sa.String(50), nullable=True),
        sa.Column('context_snapshot', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
    )
    op.create_index('ix_conversation_sessions_user_id',
                    'conversation_sessions', ['user_id'])
    op.create_index('ix_conversation_sessions_related_case_id',
                    'conversation_sessions', ['related_case_id'])

    op.create_table(
        'conversation_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('session_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('conversation_sessions.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('role', sa.String(10), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('page_context', postgresql.JSONB, nullable=True),
        sa.Column('attachment_refs', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
    )
    op.create_index('ix_conversation_messages_session_id',
                    'conversation_messages', ['session_id'])

    op.create_table(
        'intent_decisions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('session_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('conversation_sessions.id'), nullable=False),
        sa.Column('message_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('conversation_messages.id'), nullable=False),
        sa.Column('intent_type', sa.String(30), nullable=False),
        sa.Column('operation', sa.String(50), nullable=True),
        sa.Column('module', sa.String(50), nullable=True),
        sa.Column('confidence', sa.Numeric(4, 3), nullable=True),
        sa.Column('slots', postgresql.JSONB, nullable=True),
        sa.Column('missing_fields', postgresql.JSONB, nullable=True),
        sa.Column('permission_result', sa.String(10), nullable=False,
                  server_default='allowed'),
        sa.Column('denied_reason', sa.String(50), nullable=True),
        sa.Column('requires_confirmation', sa.Boolean, nullable=False,
                  server_default=sa.text('false')),
        sa.Column('risk_level', sa.String(10), nullable=False,
                  server_default='low'),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('executed_action_ref', sa.String(200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
    )
    op.create_index('ix_intent_decisions_session_id',
                    'intent_decisions', ['session_id'])
    op.create_index('ix_intent_decisions_module',
                    'intent_decisions', ['module'])
    op.create_index('ix_intent_decisions_created_at',
                    'intent_decisions', ['created_at'])


def downgrade() -> None:
    """删除三张表"""
    op.drop_table('intent_decisions')
    op.drop_table('conversation_messages')
    op.drop_table('conversation_sessions')
