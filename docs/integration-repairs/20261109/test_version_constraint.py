"""Database enforcement of exactly at most one active dataset version."""
from uuid import uuid4
import pytest
from sqlalchemy.exc import IntegrityError
from backend.app.models.dataset import Dataset
from backend.app.models.dataset_version import DatasetVersion
from backend.tests.test_analysis_history_and_reports import settings, db_engine, db_session


def test_f005_database_rejects_two_active_versions(db_session):
    try:
        dataset = Dataset(dataset_id=str(uuid4()), dataset_name='Constraint fixture',
                          file_name='fixture.csv', file_type='csv', file_path='synthetic-only')
        db_session.add(dataset)
        db_session.flush()
        versions = [DatasetVersion(dataset_id=dataset.dataset_id, version_number=n,
                    change_type='upload', storage_path='synthetic-only', metadata_snapshot={},
                    quality_snapshot={}, created_by='constraint-test', is_active=(n == 1))
                    for n in (1, 2, 3)]
        db_session.add_all(versions)
        db_session.flush()  # Multiple inactive versions are valid.
        with pytest.raises(IntegrityError, match='uq_dataset_active_version'):
            with db_session.begin_nested():
                versions[1].is_active = True
                db_session.flush()
    finally:
        db_session.rollback()
