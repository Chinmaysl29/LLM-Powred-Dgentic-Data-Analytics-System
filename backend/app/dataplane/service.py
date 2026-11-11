"""Authorized job preparation and atomic, lease-fenced metadata publication."""
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4
from sqlalchemy import select, update
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

from backend.app.dataplane.config import Limits
from backend.app.dataplane.records import artifacts, scoped, conditions, get_record, add_record
from backend.app.dataplane.storage import scope_root, confined, fingerprint
from backend.app.dataplane.contracts import Metric, QueryPlan, CleaningPlan
from backend.app.core.workspace_authorization import authorize_bound_dataset
from backend.app.models.background_job import DurableJob
from backend.app.models.dataset_version import DatasetVersion
from backend.app.models.dataset import Dataset
from backend.jobs.persistence import PersistentJobStore, LostLeaseError, ACTIVE

KINDS = ("dp_ingest", "dp_query", "dp_quality", "dp_proposal", "dp_clean", "dp_postgres", "dp_workflow")


def enqueue(db, access, kind, key, payload):
    if kind not in KINDS:
        raise ValueError("Unknown job kind")
    if payload.get("dataset_id"):
        authorize_bound_dataset(db, access, payload["dataset_id"])
    db.commit()
    factory = sessionmaker(db.get_bind(), expire_on_commit=False)
    return PersistentJobStore(factory).create(workspace_id=access.workspace_id, owner_id=access.actor_id,
        kind=kind, key=key, payload=payload, retry_eligible=True)


def resolve_source(db, access, dataset_id, version_id, limits):
    authorize_bound_dataset(db, access, dataset_id)
    version = db.get(DatasetVersion, version_id)
    if version is None or version.dataset_id != dataset_id:
        raise HTTPException(404, "Dataset version not found")
    # Legacy paths are accepted only if they resolve inside the configured upload root.
    from backend.app.core.config import get_settings
    base = get_settings().upload_path.resolve()
    path = Path(version.storage_path).resolve()
    if path.is_relative_to(limits.root.resolve()):
        path = confined(limits.root, str(path.relative_to(limits.root.resolve())))
    elif path.is_relative_to(base):
        path = confined(base, str(path.relative_to(base)))
    else:
        raise ValueError("Dataset source is outside the authorized storage root")
    return path


def prepare(db, job, limits):
    access = scoped(db, job["owner_id"], job["workspace_id"], "write")
    payload, kind = job["payload"], job["kind"].removeprefix("dp_")
    dataset_id = payload.get("dataset_id")
    if dataset_id:
        authorize_bound_dataset(db, access, dataset_id)
    root = scope_root(limits.root, access.tenant_id, access.workspace_id, access.actor_id)
    root.mkdir(parents=True, exist_ok=True)
    attempt = root/"jobs"/str(job["id"])/str(job["lease_token"])
    layer = "raw" if kind == "ingest" else "curated" if kind in ("query", "postgres", "workflow") else "work"
    request = {"kind": kind, "root": str(root), "output": str(attempt/layer),
               "limits": limits.model_dump(mode="json")}
    parent_id = None
    if kind == 'workflow':
        from backend.app.dataplane.company_api import workflow_payload
        pinned = workflow_payload(db, access, payload['workflow_id'], pinned=payload)
        if any(pinned.get(key) != payload.get(key) for key in ('workflow_hash', 'definition_hash', 'snapshot_id', 'plan')):
            raise ValueError('Workflow manifest changed')
        kind = request['kind'] = 'query'
        for key, value in pinned['resource_limits'].items():
            request['limits'][key] = min(request['limits'][key], value)
    if payload.get('definition_id'):
        from backend.app.dataplane.company import eligible
        definition, spec = eligible(db, access, payload['definition_id'], payload['business_date'])
        if definition.content_hash != payload['definition_hash'] or definition.governance['spec_hash'] != payload['spec_hash']:
            raise ValueError('Company definition changed')
        request['health_rules'] = [r.model_dump() for r in spec.health_rules]
        if spec.definition.metric.missing == 'reject' and not any(r.column == spec.definition.metric.column and r.check == 'not_null' and r.severity == 'critical' for r in spec.health_rules):
            request['health_rules'].append({'column': spec.definition.metric.column, 'check': 'not_null', 'severity': 'critical'})
    if kind == "ingest":
        source = resolve_source(db, access, dataset_id, payload["version_id"], limits)
        request.update(source=str(source), version_id=payload["version_id"],
            ingestion_options=payload.get('ingestion_options', {}))
        # Resume only this job's immutable, checksummed parts; never another job's output.
        import json
        previous = sorted((root/"jobs"/str(job["id"])).glob("*/*/checkpoint-*.json"),
                          key=lambda p: p.stat().st_mtime, reverse=True)
        if previous:
            checkpoint_path = confined(root, str(previous[0].relative_to(root)))
            if checkpoint_path.stat().st_size <= 4*1024**2:
                request["checkpoint"] = json.loads(checkpoint_path.read_text())
    elif kind == "postgres":
        connector = get_record(db, access, payload["connector_id"], "connector")
        metric = get_record(db, access, payload["metric_id"], "metric")
        if metric["dataset_id"] != dataset_id or metric["payload"].get("connector_id") != str(connector["id"]):
            raise ValueError("Metric and company source mismatch")
        from backend.app.dataplane.postgres import decrypt
        request.update(connection=decrypt(connector["payload"]["encrypted"], limits),
            metric=metric["payload"]["definition"], semantic_id=str(metric["id"]),
            plan=QueryPlan(**payload["plan"]).model_dump(), source_id=str(connector["id"]))
        parent_id = connector["id"]
    else:
        snapshot = get_record(db, access, payload["snapshot_id"], "snapshot")
        if snapshot["dataset_id"] != dataset_id:
            raise ValueError("Snapshot dataset mismatch")
        request.update(manifest=snapshot["payload"], snapshot_id=str(snapshot["id"]))
        parent_id = snapshot["id"]
        if kind == "query":
            if payload.get('definition_id'):
                request.update(metric=payload['company_metric'], semantic_id=payload['definition_id'], plan=payload['plan'])
            else:
                metric = get_record(db, access, payload["metric_id"], "metric")
                if metric["parent_id"] != snapshot["id"]:
                    raise ValueError("Metric belongs to another snapshot")
                request.update(metric=metric["payload"]["definition"], semantic_id=str(metric["id"]),
                               plan=QueryPlan(**payload["plan"]).model_dump())
        elif kind == "quality":
            rows = db.execute(select(artifacts.c.payload).where(*conditions(access),
                artifacts.c.kind == "quality", artifacts.c.dataset_id == dataset_id)
                .order_by(artifacts.c.created_at.desc()).limit(100)).scalars().all()
            history = list(reversed(rows))
            request.update(history=history, source_created=snapshot["created_at"].isoformat(),
                           previous_schema=history[-1].get("schema") if history else None)
        elif kind == "proposal":
            request["plan"] = CleaningPlan(**payload["plan"]).model_dump()
        elif kind == "clean":
            proposal = get_record(db, access, payload["proposal_id"], "proposal")
            approval = get_record(db, access, payload["approval_id"], "approval")
            if proposal["parent_id"] != snapshot["id"] or approval["parent_id"] != proposal["id"]:
                raise ValueError("Approval is not bound to this proposal and snapshot")
            if approval["payload"]["proposal_hash"] != fingerprint(proposal["payload"]):
                raise ValueError("Approval content mismatch")
            if proposal["payload"]["snapshot_hash"] != snapshot["payload"]["snapshot_hash"]:
                raise ValueError("Stale cleaning proposal")
            request["plan"] = proposal["payload"]["plan"]
            request["version_id"] = str(uuid4())
    return request, attempt/"execution", parent_id


def publish(db, job, result, parent_id):
    # Lock the authoritative lease and reauthorize in the same publication transaction.
    now = datetime.now(timezone.utc)
    row = db.scalar(select(DurableJob).where(DurableJob.id == job["id"]).with_for_update())
    if row is None or row.status not in ACTIVE or row.lease_token != job["lease_token"] or row.lease_expires_at <= now:
        raise LostLeaseError("Publication lease lost")
    access = scoped(db, job["owner_id"], job["workspace_id"], "write")
    kind = {"ingest": "snapshot", "clean": "snapshot", "query": "evidence", "postgres": "evidence", "workflow": "evidence",
            "quality": "quality", "proposal": "proposal"}[job["kind"].removeprefix("dp_")]
    record_id = str(uuid4())
    if job['payload'].get('definition_id'):
        from backend.app.dataplane.company import eligible
        definition, spec = eligible(db, access, job['payload']['definition_id'], job['payload']['business_date'], lock=True)
        if job['kind'] == 'dp_workflow':
            from backend.app.dataplane.company import lock_artifact
            lock_artifact(db, access, job['payload']['workflow_id'], 'workflow')
            from backend.app.dataplane.company_api import workflow_payload
            workflow_payload(db, access, job['payload']['workflow_id'], pinned=job['payload'])
        snapshot = get_record(db, access, parent_id, 'snapshot')
        result.update(contract_version=1, workspace_id=str(access.workspace_id), run_id=str(job['id']), result_id=record_id,
            started_at=row.started_at.isoformat() if row.started_at else None,
            attempt_id=f"{job['id']}:{job['attempt']}",
            definition_id=definition.id, definition_hash=definition.content_hash, spec_hash=definition.governance['spec_hash'],
            definition_version=definition.version, business_date=job['payload']['business_date'],
            definition_context={'formula': f'{spec.definition.metric.aggregation}({spec.definition.metric.column})',
                'key': definition.key, 'grain': spec.grain, 'units': spec.definition.units, 'currency': spec.definition.currency,
                'timezone': spec.timezone, 'date_basis': spec.date_basis, 'exclusions': spec.exclusions,
                'missing': spec.definition.metric.missing, 'rounding': 'Engine precision preserved; no display rounding in artifact'},
            transformation=snapshot['payload'].get('transformation'), coverage='full',
            collected_at=now.isoformat(), completed_at=now.isoformat(), execution_status='succeeded',
            source_version=snapshot['payload']['version_id'], snapshot_guarantee='immutable checksummed file snapshot',
            model={'provider': 'none', 'model': None, 'prompt_version': None},
            implementation_version='company-evidence-v1',
            computation_precision='Native engine aggregation over ' + snapshot['payload']['schema'][spec.definition.metric.column] + '; exact decimal results serialized as text',
            time_window=job['payload'].get('time_window'),
            validation_outcomes=['Source checksum verified', 'Typed aggregate plan validated', 'Result limits enforced', 'Configured full-snapshot quality rules evaluated'],
            lineage={'snapshot_id': str(parent_id), 'definition_id': definition.id,
                'fields': sorted(set([spec.definition.metric.column, *result['plan']['dimensions'],
                    *(f['column'] for f in result['plan']['filters'])]))})
        if any(c['blocks'] for c in result.get('quality_checks', [])):
            result.update(validation_status='failed', execution_status='blocked')
            finding_key = fingerprint({'snapshot': str(parent_id), 'definition': definition.id,
                'checks': [{k: v for k, v in c.items() if k != 'collected_at'} for c in result['quality_checks']]})
            prior = db.execute(select(artifacts.c.id).where(*conditions(access), artifacts.c.kind == 'incident',
                artifacts.c.parent_id == parent_id, artifacts.c.payload['finding_key'].as_string() == finding_key).limit(1)).scalar()
            incident = str(prior) if prior else add_record(db, access, 'incident', {'definition_id': definition.id,
                'finding_key': finding_key,
                'snapshot_id': str(parent_id), 'checks': result['quality_checks'], 'coverage': 'full',
                'run_id': str(job['id']), 'impact': 'directly_affected',
                'impact_path': [str(parent_id), definition.id, str(job['id'])]},
                dataset_id=job['payload']['dataset_id'], parent_id=parent_id)
            row.status, row.error_code, row.result, row.completed_at = 'FAILED', 'QUALITY_BLOCKED', {'incident_id': incident}, now
            row.lease_token, row.lease_expires_at = None, None
            return incident
        result['validation_status'] = 'passed'
        from backend.app.dataplane.company_contracts import EvidenceContract
        EvidenceContract.model_validate({k: result[k] for k in EvidenceContract.model_fields})
        if job['kind'] == 'dp_workflow':
            result.update(workflow_id=job['payload']['workflow_id'], workflow_version=job['payload']['workflow_version'],
                          require_artifact_review=job['payload']['require_artifact_review'])
            # A ready workflow must already have a valid report, not defer a
            # possible renderer failure until its first download.
            from backend.app.dataplane.reporting import render_pdf
            from backend.app.dataplane.storage import digest
            report_bytes = render_pdf(record_id, result)
            if len(report_bytes) > 8 * 1024**2 or not report_bytes.startswith(b'%PDF'):
                raise ValueError('Workflow report validation or byte budget failed')
            root = scope_root(Limits().root, access.tenant_id, access.workspace_id, access.actor_id)
            relative = f"jobs/{job['id']}/{job['lease_token']}/workflow-report.pdf"
            report_path = confined(root, relative, exists=False)
            with report_path.open('xb') as target:
                target.write(report_bytes)
            result['report_artifact'] = {'path': relative, 'sha256': digest(report_path),
                'bytes': len(report_bytes), 'content_type': 'application/pdf'}
    if job["kind"] == "dp_clean":
        from sqlalchemy import func
        dataset_id = job["payload"]["dataset_id"]
        db.scalar(select(Dataset).where(Dataset.dataset_id == dataset_id).with_for_update())
        number = db.scalar(select(func.max(DatasetVersion.version_number)).where(DatasetVersion.dataset_id == dataset_id)) + 1
        root = scope_root(Limits().root, access.tenant_id, access.workspace_id, access.actor_id)
        manifest_path = (root/result["files"][0]["path"]).parent/"manifest.json"
        db.add(DatasetVersion(version_id=result["version_id"], dataset_id=dataset_id,
            version_number=number, parent_version_id=result["parent_version_id"], change_type="dataplane_cleaning",
            transformation_metadata=result["transformation"], storage_path=str(manifest_path),
            metadata_snapshot={"snapshot_hash": result["snapshot_hash"], "row_count": result["row_count"]},
            quality_snapshot=result["reconciliation"], is_active=False, created_by=str(access.actor_id)))
    if job["kind"] == "dp_ingest":
        dataset = db.get(Dataset, job["payload"]["dataset_id"])
        if dataset.canonical_format == "dataplane":
            dataset.status, dataset.row_count = "ready", result["row_count"]
            dataset.column_count = len(result["schema"])
    record_id = add_record(db, access, kind, result, dataset_id=job["payload"].get("dataset_id"),
                          job_id=job["id"], parent_id=parent_id, record_id=record_id)
    if row.lease_expires_at <= datetime.now(timezone.utc):
        raise LostLeaseError("Publication lease expired")
    row.status, row.result, row.completed_at = "READY", {"artifact_id": record_id, "kind": kind}, now
    row.lease_token, row.lease_expires_at, row.updated_at = None, None, now
    return record_id
