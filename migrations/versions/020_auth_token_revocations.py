"""Persist token hashes so logout and rotation survive process restarts."""
from alembic import op
import sqlalchemy as sa

revision = '020_auth_token_revocations'
down_revision = '019_dataplane'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('auth_token_revocations',
        sa.Column('token_hash', sa.String(64), primary_key=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index('ix_auth_token_revocations_expires_at', 'auth_token_revocations', ['expires_at'])
    op.execute('REVOKE ALL ON auth_token_revocations FROM PUBLIC')
    op.execute('ALTER TABLE auth_token_revocations ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE auth_token_revocations FORCE ROW LEVEL SECURITY')
    predicate = "token_hash = current_setting('app.token_hash', true)"
    op.execute(f'CREATE POLICY token_revocation_read ON auth_token_revocations FOR SELECT USING ({predicate})')
    op.execute(f'CREATE POLICY token_revocation_insert ON auth_token_revocations FOR INSERT WITH CHECK ({predicate})')


def downgrade():
    op.drop_table('auth_token_revocations')
