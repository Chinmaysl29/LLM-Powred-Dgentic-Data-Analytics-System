"""Train only in the existing killable child protocol, without application secrets."""
import json
from pathlib import Path
import tempfile

from backend.app.dataplane.config import Limits
from backend.app.dataplane.supervisor import execute


def fit_bounded(store, job, *, train_x, train_y, development_x, development_y,
                manifest, implementation_hashes, seed, max_epochs, deadline_seconds):
    """Return candidate weights; this function never changes the active selector.

    The existing durable job's admission/lease remains authoritative. Only
    decision-time features and frozen provenance enter this temporary child.
    """
    if len(train_x) > 10000 or len(development_x) > 5000:
        raise ValueError('TRAINING_CAPACITY_EXCEEDED: reduce the eligible batch')
    inputs = dict(train_x=train_x, train_y=train_y, development_x=development_x,
        development_y=development_y, manifest=manifest,
        implementation_hashes=implementation_hashes, seed=seed,
        max_epochs=max_epochs, deadline_seconds=deadline_seconds)
    if len(json.dumps(inputs, allow_nan=False).encode()) > 16 * 1024**2:
        raise ValueError('TRAINING_INPUT_BUDGET_EXCEEDED')
    policy = Limits()
    timeout = min(900, deadline_seconds + 30)  # bounded interpreter/import overhead
    limits = policy.model_copy(update={'timeout_s': timeout, 'result_bytes': 8 * 1024**2})
    with tempfile.TemporaryDirectory(prefix='analyst-selector-training-') as temporary:
        root = Path(temporary)
        request = {'kind': 'selector_train', 'root': str(root), 'output': str(root/'model'),
            'limits': limits.model_dump(mode='json'), 'training': inputs}
        result = execute(request, root/'execution',
            lambda: store.heartbeat(job['id'], job['lease_token']), timeout_s=timeout)
        usage_file = root/'execution'/'supervision.json'
        if usage_file.is_file():
            result['measurements']['supervision'] = json.loads(usage_file.read_text())
        return result['bundles'], result['measurements']
