"""Phase 7 US5 entities (AgentAction, AuditLog - 2 entities)

Revision ID: b9ae4b1e91a9
Revises: 90f33f4c6e83
Create Date: 2026-01-08 10:02:10.654162

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b9ae4b1e91a9'
down_revision: Union[str, None] = '90f33f4c6e83'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create action_type enum
    action_type_enum = postgresql.ENUM(
        'create_jira_ticket',
        'create_confluence_page',
        'create_github_issue',
        name='action_type',
        create_type=False
    )
    action_type_enum.create(op.get_bind(), checkfirst=True)
    
    # Create action_status enum
    action_status_enum = postgresql.ENUM(
        'pending_approval',
        'approved',
        'executed',
        'cancelled',
        'expired',
        'failed',
        name='action_status',
        create_type=False
    )
    action_status_enum.create(op.get_bind(), checkfirst=True)
    
    # Create agent_actions table
    op.create_table(
        'agent_actions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('action_type', action_type_enum, nullable=False),
        sa.Column('status', action_status_enum, nullable=False, server_default='pending_approval'),
        sa.Column('preview_json', postgresql.JSONB, nullable=False, server_default='{}'),
        sa.Column('expires_at', sa.DateTime(timezone=False), nullable=False),
        sa.Column('result_url', sa.Text, nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='SET NULL'),
    )
    
    # Create indexes for agent_actions
    op.create_index('ix_agent_actions_workspace_id', 'agent_actions', ['workspace_id'])
    op.create_index('ix_agent_actions_user_id', 'agent_actions', ['user_id'])
    op.create_index('ix_agent_actions_conversation_id', 'agent_actions', ['conversation_id'])
    op.create_index('ix_agent_actions_status', 'agent_actions', ['status'])
    op.create_index('ix_agent_actions_expires_at', 'agent_actions', ['expires_at'])
    
    # Create audit_logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('actor_user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('target_type', sa.String(50), nullable=False),
        sa.Column('target_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('details_json', postgresql.JSONB, nullable=False, server_default='{}'),
        sa.Column('ip_address', postgresql.INET, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], ondelete='RESTRICT'),
        sa.CheckConstraint("action ~ '^[a-z_]+\\.[a-z_]+$'", name='action_format_check'),
    )
    
    # Create indexes for audit_logs
    op.create_index('ix_audit_logs_workspace_id', 'audit_logs', ['workspace_id'])
    op.create_index('ix_audit_logs_actor_user_id', 'audit_logs', ['actor_user_id'])
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'])
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'], postgresql_ops={'created_at': 'DESC'})
    op.create_index('ix_audit_logs_target', 'audit_logs', ['target_type', 'target_id'])


def downgrade() -> None:
    # Drop audit_logs table and indexes
    op.drop_index('ix_audit_logs_target', 'audit_logs')
    op.drop_index('ix_audit_logs_created_at', 'audit_logs')
    op.drop_index('ix_audit_logs_action', 'audit_logs')
    op.drop_index('ix_audit_logs_actor_user_id', 'audit_logs')
    op.drop_index('ix_audit_logs_workspace_id', 'audit_logs')
    op.drop_table('audit_logs')
    
    # Drop agent_actions table and indexes
    op.drop_index('ix_agent_actions_expires_at', 'agent_actions')
    op.drop_index('ix_agent_actions_status', 'agent_actions')
    op.drop_index('ix_agent_actions_conversation_id', 'agent_actions')
    op.drop_index('ix_agent_actions_user_id', 'agent_actions')
    op.drop_index('ix_agent_actions_workspace_id', 'agent_actions')
    op.drop_table('agent_actions')
    
    # Drop enums
    sa.Enum(name='action_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='action_type').drop(op.get_bind(), checkfirst=True)
