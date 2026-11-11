"""Real HTTP read-timeout regression; keep production deadlines and isolation intact."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
import time
from uuid import uuid4

import httpx

from backend.tests.test_verified_learning_integration import environment, identity
from backend.tests.test_perceptron_memory import case, approve, QUESTION, PLAN
from backend.app.core.config import get_settings
from backend.app.learning.memory_chroma import MemoryIndex, METADATA


def test_planner_read_timeout_returns_baseline_then_recovers(case, monkeypatch):
    env, account, dataset_id, _ = case
    # Approval is persisted in real isolated PostgreSQL; the delayed HTTP server
    # supplies only the candidate ID, never a correction or authority decision.
    approved = approve(case)
    assert approved['approved']
    collection_id = str(uuid4())
    queries = []
    timeouts = []

    class DelayedIndex(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send_json(self, value):
            body = json.dumps(value).encode()
            try:
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass  # Expected when the real client abandons the first query.

        def do_GET(self):
            self.send_json('0.6.3' if self.path == '/api/v2/version'
                           else {'id': collection_id, 'metadata': METADATA})

        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length', '0')))
            queries.append(self.path)
            if len(queries) == 1:
                time.sleep(1.3)  # Exceeds the unchanged one-second HTTP deadline.
            self.send_json({'ids': [[approved['mistake_id']]]})

    original = MemoryIndex.request

    def observe_timeout(self, method, path, body=None):
        try:
            return original(self, method, path, body)
        except httpx.ReadTimeout:
            timeouts.append((path.endswith('/query'), self.client.timeout.read))
            raise

    server = ThreadingHTTPServer(('127.0.0.1', 0), DelayedIndex)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(get_settings(), 'chroma_host', '127.0.0.1')
    monkeypatch.setattr(get_settings(), 'chroma_port', server.server_port)
    monkeypatch.setattr(MemoryIndex, 'request', observe_timeout)
    body = dict(query=QUESTION, dataset_id=dataset_id, intent=PLAN['intent'])

    def plan(who=account):
        response = env['client'].post('/api/v1/planner/plan', headers=who['headers'], json=body)
        assert response.status_code == 200, response.text
        value = response.json()
        value.pop('workflow_id')  # New IDs are expected even for identical plans.
        return value

    try:
        monkeypatch.setattr(get_settings(), 'learning_enabled', False)
        baseline = plan()
        assert queries == []
        monkeypatch.setattr(get_settings(), 'learning_enabled', True)
        assert plan() == baseline
        assert timeouts == [(True, 1.0)]
        assert len(queries) == 1
        recovered = plan()
        assert 'Added analytical checks from a reviewed past failure.' in recovered['rules_triggered']
        assert len(queries) == 2  # No request-time retries and no leaked read slot.
        outsider = identity(env)
        assert plan(outsider) == baseline
        assert len(queries) == 2  # An unauthorized caller never reaches the index.
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
