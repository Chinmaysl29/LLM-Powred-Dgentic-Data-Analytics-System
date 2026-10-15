"""Fresh database authorization for each enqueue, execution and explicit retry."""
from backend.app.core.workspace_authorization import authorize_workspace, authorize_bound_dataset


class DatabaseJobAuthorizer:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def __call__(self, job):
        with self.session_factory() as db:
            access = authorize_workspace(db, job.actor_id, job.workspace_id, 'write')
            if str(access.tenant_id) != job.tenant_id:
                raise PermissionError('Job tenant mismatch')
            for field, expected in (('workspace_id', str(access.workspace_id)),
                                    ('owner_id', str(access.actor_id)), ('user_id', str(access.actor_id)),
                                    ('tenant_id', str(access.tenant_id))):
                if field in job.payload and str(job.payload[field]) != expected:
                    raise PermissionError('Job resource scope mismatch')
            if job.payload.get('dataset_id'):
                authorize_bound_dataset(db, access, str(job.payload['dataset_id']))
