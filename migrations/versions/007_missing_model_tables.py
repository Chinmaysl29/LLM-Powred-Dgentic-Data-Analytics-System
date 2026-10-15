"""Add model tables absent from the original migration history.

Existing tables and rows are preserved. Definitions are frozen in this revision.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "007_missing_model_tables"
down_revision = "006_reconcile_recommendations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if 'forecast_runs' not in existing:
        op.create_table('forecast_runs',
        sa.Column('run_id', sa.String(length=36), nullable=False),
        sa.Column('model_type', sa.String(length=50), nullable=False),
        sa.Column('target', sa.String(length=100), nullable=False),
        sa.Column('params', sa.JSON(), nullable=False),
        sa.Column('output', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('run_id')
        )
    if 'tenants' not in existing:
        op.create_table('tenants',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_name', sa.String(length=255), nullable=False),
        sa.Column('tenant_slug', sa.String(length=100), nullable=False),
        sa.Column('tenant_status', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_slug', name='uq_tenants_tenant_slug')
        )
        op.create_index(op.f('ix_tenants_id'), 'tenants', ['id'], unique=False)
        op.create_index('ix_tenants_status_created', 'tenants', ['tenant_status', 'created_at'], unique=False)
        op.create_index(op.f('ix_tenants_tenant_slug'), 'tenants', ['tenant_slug'], unique=True)
        op.create_index(op.f('ix_tenants_tenant_status'), 'tenants', ['tenant_status'], unique=False)
    if 'users' not in existing:
        op.create_table('users',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.Text(), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    if 'analyses' not in existing:
        op.create_table('analyses',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('dataset_id', sa.String(length=36), nullable=False),
        sa.Column('analysis_type', sa.String(length=100), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('result_json', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['dataset_id'], ['datasets.dataset_id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_analyses_dataset_id'), 'analyses', ['dataset_id'], unique=False)
    if 'connectors' not in existing:
        op.create_table('connectors',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('connector_name', sa.String(length=255), nullable=False),
        sa.Column('connector_type', sa.Enum('DATABASE', 'STORAGE', 'CRM', 'ERP', 'WAREHOUSE', name='connectortype'), nullable=False),
        sa.Column('connector_subtype', sa.String(length=100), nullable=False),
        sa.Column('status', sa.Enum('ACTIVE', 'INACTIVE', 'ERROR', 'SYNCING', name='connectorstatus'), nullable=False),
        sa.Column('version', sa.String(length=50), nullable=False),
        sa.Column('config', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_connectors_connector_subtype'), 'connectors', ['connector_subtype'], unique=False)
        op.create_index(op.f('ix_connectors_connector_type'), 'connectors', ['connector_type'], unique=False)
        op.create_index(op.f('ix_connectors_status'), 'connectors', ['status'], unique=False)
        op.create_index(op.f('ix_connectors_tenant_id'), 'connectors', ['tenant_id'], unique=False)
        op.create_index('ix_connectors_tenant_type', 'connectors', ['tenant_id', 'connector_type'], unique=False)
    if 'conversations' not in existing:
        op.create_table('conversations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_conversations_user_id'), 'conversations', ['user_id'], unique=False)
    if 'workspaces' not in existing:
        op.create_table('workspaces',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('workspace_name', sa.String(length=255), nullable=False),
        sa.Column('workspace_slug', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'workspace_slug', name='uq_workspaces_tenant_slug')
        )
        op.create_index(op.f('ix_workspaces_id'), 'workspaces', ['id'], unique=False)
        op.create_index(op.f('ix_workspaces_status'), 'workspaces', ['status'], unique=False)
        op.create_index(op.f('ix_workspaces_tenant_id'), 'workspaces', ['tenant_id'], unique=False)
        op.create_index('ix_workspaces_tenant_status', 'workspaces', ['tenant_id', 'status'], unique=False)
        op.create_index(op.f('ix_workspaces_workspace_slug'), 'workspaces', ['workspace_slug'], unique=False)
    if 'activities' not in existing:
        op.create_table('activities',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('actor_id', sa.UUID(), nullable=False),
        sa.Column('actor_name', sa.String(length=255), nullable=False),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('resource_type', sa.String(length=50), nullable=False),
        sa.Column('resource_id', sa.String(length=255), nullable=False),
        sa.Column('summary', sa.String(length=500), nullable=False),
        sa.Column('details', sa.JSON(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_activities_action'), 'activities', ['action'], unique=False)
        op.create_index(op.f('ix_activities_actor_id'), 'activities', ['actor_id'], unique=False)
        op.create_index(op.f('ix_activities_resource_id'), 'activities', ['resource_id'], unique=False)
        op.create_index(op.f('ix_activities_resource_type'), 'activities', ['resource_type'], unique=False)
        op.create_index(op.f('ix_activities_tenant_id'), 'activities', ['tenant_id'], unique=False)
        op.create_index('ix_activities_tenant_ws_time', 'activities', ['tenant_id', 'workspace_id', 'timestamp'], unique=False)
        op.create_index(op.f('ix_activities_timestamp'), 'activities', ['timestamp'], unique=False)
        op.create_index(op.f('ix_activities_workspace_id'), 'activities', ['workspace_id'], unique=False)
    if 'departments' not in existing:
        op.create_table('departments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('department_name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workspace_id', 'department_name', name='uq_departments_workspace_name')
        )
        op.create_index(op.f('ix_departments_id'), 'departments', ['id'], unique=False)
        op.create_index('ix_departments_workspace', 'departments', ['workspace_id'], unique=False)
        op.create_index(op.f('ix_departments_workspace_id'), 'departments', ['workspace_id'], unique=False)
    if 'messages' not in existing:
        op.create_table('messages',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('conversation_id', sa.UUID(), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('metadata_json', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_messages_conversation_id'), 'messages', ['conversation_id'], unique=False)
    if 'notifications' not in existing:
        op.create_table('notifications',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('type', sa.Enum('MENTION', 'COMMENT', 'TASK_ASSIGNED', 'FORECAST_COMPLETED', 'REPORT_GENERATED', name='notificationtype'), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('channel', sa.Enum('IN_APP', 'EMAIL', name='notificationchannel'), nullable=False),
        sa.Column('is_read', sa.Boolean(), nullable=False),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_notifications_is_read'), 'notifications', ['is_read'], unique=False)
        op.create_index(op.f('ix_notifications_tenant_id'), 'notifications', ['tenant_id'], unique=False)
        op.create_index(op.f('ix_notifications_type'), 'notifications', ['type'], unique=False)
        op.create_index(op.f('ix_notifications_user_id'), 'notifications', ['user_id'], unique=False)
        op.create_index('ix_notifications_user_read', 'notifications', ['user_id', 'is_read'], unique=False)
        op.create_index(op.f('ix_notifications_workspace_id'), 'notifications', ['workspace_id'], unique=False)
    if 'projects' not in existing:
        op.create_table('projects',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('project_name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workspace_id', 'project_name', name='uq_projects_workspace_name')
        )
        op.create_index(op.f('ix_projects_id'), 'projects', ['id'], unique=False)
        op.create_index(op.f('ix_projects_status'), 'projects', ['status'], unique=False)
        op.create_index(op.f('ix_projects_workspace_id'), 'projects', ['workspace_id'], unique=False)
        op.create_index('ix_projects_workspace_status', 'projects', ['workspace_id', 'status'], unique=False)
    if 'comments' not in existing:
        op.create_table('comments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=True),
        sa.Column('author_id', sa.UUID(), nullable=False),
        sa.Column('author_name', sa.String(length=255), nullable=False),
        sa.Column('resource_type', sa.String(length=50), nullable=False),
        sa.Column('resource_id', sa.String(length=255), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('parent_id', sa.UUID(), nullable=True),
        sa.Column('is_edited', sa.Boolean(), nullable=False),
        sa.Column('is_resolved', sa.Boolean(), nullable=False),
        sa.Column('resolved_by', sa.UUID(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['parent_id'], ['comments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_comments_author_id'), 'comments', ['author_id'], unique=False)
        op.create_index(op.f('ix_comments_parent_id'), 'comments', ['parent_id'], unique=False)
        op.create_index(op.f('ix_comments_project_id'), 'comments', ['project_id'], unique=False)
        op.create_index('ix_comments_resource', 'comments', ['tenant_id', 'workspace_id', 'resource_type', 'resource_id'], unique=False)
        op.create_index(op.f('ix_comments_resource_id'), 'comments', ['resource_id'], unique=False)
        op.create_index(op.f('ix_comments_resource_type'), 'comments', ['resource_type'], unique=False)
        op.create_index(op.f('ix_comments_tenant_id'), 'comments', ['tenant_id'], unique=False)
        op.create_index(op.f('ix_comments_workspace_id'), 'comments', ['workspace_id'], unique=False)
    if 'tasks' not in existing:
        op.create_table('tasks',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('status', sa.Enum('TODO', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED', name='taskstatus'), nullable=False),
        sa.Column('priority', sa.Enum('LOW', 'MEDIUM', 'HIGH', 'URGENT', name='taskpriority'), nullable=False),
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('assigned_to', sa.UUID(), nullable=True),
        sa.Column('created_by', sa.UUID(), nullable=False),
        sa.Column('comments_count', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_tasks_assigned_to'), 'tasks', ['assigned_to'], unique=False)
        op.create_index(op.f('ix_tasks_created_by'), 'tasks', ['created_by'], unique=False)
        op.create_index(op.f('ix_tasks_priority'), 'tasks', ['priority'], unique=False)
        op.create_index(op.f('ix_tasks_project_id'), 'tasks', ['project_id'], unique=False)
        op.create_index(op.f('ix_tasks_status'), 'tasks', ['status'], unique=False)
        op.create_index(op.f('ix_tasks_tenant_id'), 'tasks', ['tenant_id'], unique=False)
        op.create_index('ix_tasks_tenant_ws_status', 'tasks', ['tenant_id', 'workspace_id', 'status'], unique=False)
        op.create_index(op.f('ix_tasks_workspace_id'), 'tasks', ['workspace_id'], unique=False)
    if 'teams' not in existing:
        op.create_table('teams',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('department_id', sa.UUID(), nullable=False),
        sa.Column('team_name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('department_id', 'team_name', name='uq_teams_department_name')
        )
        op.create_index('ix_teams_department', 'teams', ['department_id'], unique=False)
        op.create_index(op.f('ix_teams_department_id'), 'teams', ['department_id'], unique=False)
        op.create_index(op.f('ix_teams_id'), 'teams', ['id'], unique=False)
    if 'mentions' not in existing:
        op.create_table('mentions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('comment_id', sa.UUID(), nullable=False),
        sa.Column('mentioned_user_id', sa.UUID(), nullable=False),
        sa.Column('mentioner_user_id', sa.UUID(), nullable=False),
        sa.Column('username', sa.String(length=100), nullable=False),
        sa.Column('is_read', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['comment_id'], ['comments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_mentions_comment_id'), 'mentions', ['comment_id'], unique=False)
        op.create_index(op.f('ix_mentions_mentioned_user_id'), 'mentions', ['mentioned_user_id'], unique=False)
        op.create_index(op.f('ix_mentions_tenant_id'), 'mentions', ['tenant_id'], unique=False)
        op.create_index('ix_mentions_user_unread', 'mentions', ['mentioned_user_id', 'is_read'], unique=False)
        op.create_index(op.f('ix_mentions_username'), 'mentions', ['username'], unique=False)
        op.create_index(op.f('ix_mentions_workspace_id'), 'mentions', ['workspace_id'], unique=False)


def downgrade() -> None:
    raise RuntimeError("Additive schema recovery is forward-only; use a verified backup and recovery plan")
