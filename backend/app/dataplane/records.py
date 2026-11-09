"""Immutable, scoped metadata documents; bulk data never enters Postgres."""
from uuid import UUID, uuid4
from sqlalchemy import Column, DateTime, MetaData, String, Table, Uuid, select, text
from sqlalchemy.dialects.postgresql import JSONB
from fastapi import HTTPException
from backend.app.core.workspace_authorization import authorize_workspace, authorize_bound_dataset

metadata = MetaData()
artifacts = Table("dataplane_artifacts", metadata,
    Column("id", Uuid, primary_key=True), Column("tenant_id", Uuid),
    Column("workspace_id", Uuid), Column("actor_id", Uuid), Column("dataset_id", String(36)),
    Column("job_id", Uuid), Column("parent_id", Uuid), Column("kind", String(20)),
    Column("payload", JSONB), Column("created_at", DateTime(timezone=True)))


def scoped(db, actor, workspace, permission="read"):
    access = authorize_workspace(db, actor, workspace, permission)
    if db.bind.dialect.name == "postgresql":
        for key, value in (("tenant_id", access.tenant_id), ("workspace_id", access.workspace_id),
                           ("actor_id", access.actor_id)):
            db.execute(text("SELECT set_config(:key,:value,true)"),
                       {"key": "app." + key, "value": str(value)})
    return access


def conditions(access):
    return (artifacts.c.tenant_id == access.tenant_id,
            artifacts.c.workspace_id == access.workspace_id,
            artifacts.c.actor_id == access.actor_id)


def get_record(db, access, record_id, kind=None):
    try:
        record_id = UUID(str(record_id))
    except ValueError:
        raise HTTPException(404, "Artifact not found") from None
    row = db.execute(select(artifacts).where(artifacts.c.id == record_id, *conditions(access))).mappings().first()
    if row is None or (kind and row["kind"] != kind):
        raise HTTPException(404, "Artifact not found")
    if row["dataset_id"]:
        authorize_bound_dataset(db, access, row["dataset_id"])
    return dict(row)


def add_record(db, access, kind, payload, *, dataset_id=None, job_id=None, parent_id=None, record_id=None):
    if dataset_id:
        authorize_bound_dataset(db, access, dataset_id)
    if parent_id:
        parent = get_record(db, access, parent_id)
        if parent["dataset_id"] is not None and parent["dataset_id"] != dataset_id:
            raise HTTPException(422, "Artifact lineage dataset mismatch")
    identity = UUID(str(record_id)) if record_id else uuid4()
    db.execute(artifacts.insert().values(id=identity, tenant_id=access.tenant_id,
        workspace_id=access.workspace_id, actor_id=access.actor_id, dataset_id=dataset_id,
        job_id=job_id, parent_id=parent_id, kind=kind, payload=payload))
    return str(identity)
