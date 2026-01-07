"""Phase 2 foundational entities: Workspace, User, ConnectorDefinition

Revision ID: d984e2ccbfe5
Revises: 
Create Date: 2026-01-07 17:40:06.860000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = 'd984e2ccbfe5'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create workspaces table
    op.create_table(
        'workspaces',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_workspaces_id'), 'workspaces', ['id'], unique=False)

    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workspace_id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=False, server_default='user'),
        sa.Column('connector_identities', JSONB, nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_workspace_id'), 'users', ['workspace_id'], unique=False)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=False)

    # Create connector_definitions table
    op.create_table(
        'connector_definitions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('connector_type', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=1000), nullable=True),
        sa.Column('config_schema', JSONB, nullable=False, server_default='{}'),
        sa.Column('oauth_scopes', JSONB, nullable=False, server_default='[]'),
        sa.Column('supports_read', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('supports_write', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('version', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('connector_type')
    )
    op.create_index(op.f('ix_connector_definitions_id'), 'connector_definitions', ['id'], unique=False)
    op.create_index(op.f('ix_connector_definitions_connector_type'), 'connector_definitions', ['connector_type'], unique=True)


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_index(op.f('ix_connector_definitions_connector_type'), table_name='connector_definitions')
    op.drop_index(op.f('ix_connector_definitions_id'), table_name='connector_definitions')
    op.drop_table('connector_definitions')
    
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_index(op.f('ix_users_workspace_id'), table_name='users')
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_table('users')
    
    op.drop_index(op.f('ix_workspaces_id'), table_name='workspaces')
    op.drop_table('workspaces')
