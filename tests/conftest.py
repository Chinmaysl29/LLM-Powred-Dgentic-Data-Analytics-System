"""Root-level pytest configuration for tests/ directory.

Tests in this directory (test_schema_contract.py,
test_recommendation_schema_reconciliation.py,
test_authenticated_dataset_isolation.py) target the CI-isolated PostgreSQL
database via DATABASE_URL.

No customer storage is accessed.
"""

import os
import sys
from pathlib import Path

# Ensure the repository root is on sys.path so that
# `from backend.app...` imports resolve correctly regardless of how
# pytest is invoked (e.g., `pytest tests/` from repo root).
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def pytest_configure(config):
    """Register custom markers used by the test suite."""
    config.addinivalue_line(
        "markers",
        "migration: tests that require a live migrated PostgreSQL database",
    )
    config.addinivalue_line(
        "markers",
        "isolation: tests that verify multi-tenant dataset isolation contracts",
    )
    config.addinivalue_line(
        "markers",
        "schema: tests that verify schema compatibility via inspect_schema()",
    )
