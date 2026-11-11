"""Bounds, audit integrity and event-loop responsiveness for remaining findings."""
import asyncio
from contextlib import contextmanager
import threading
from types import SimpleNamespace
from uuid import uuid4

from fastapi import Depends, FastAPI, Request, WebSocket
from fastapi.testclient import TestClient
import httpx
import pytest
from redis.exceptions import RedisError
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse

from backend.tests.test_verified_learning_integration import environment
from backend.app.core.config import get_settings
from backend.app.core.exceptions import RedisConnectionError
from backend.app.database.redis import RedisCache
from backend.app.middleware.audit import AuditTrailMiddleware
from backend.app.models.audit_entry import AuditEntry
from backend.app.services.audit_trail_service import audit_trail_service


class RedisFixture:
    def __init__(self, names, fail=None):
        self.names = names
        self.live = set(names)
        self.batches = []
        self.fail = fail

    async def scan_iter(self, **kwargs):
        assert kwargs == {'match': 'synthetic:*', 'count': 200}
        for key in self.names:
            yield key

    async def delete(self, *keys):
        self.batches.append(keys)
        if len(self.batches) == self.fail:
            raise RedisError('synthetic transport failure')
        deleted = len(self.live.intersection(keys))
        self.live.difference_update(keys)
        return deleted


@pytest.mark.parametrize('size', [0, 1, 200, 201, 10001])
def test_redis_invalidation_bounds_and_duplicate_counts(size):
    cache = RedisCache(get_settings())
    keys = [f'synthetic:{i}' for i in range(size)]
    # SCAN may repeat a key; return Redis's actual delete counts.
    fixture = RedisFixture(keys + keys[:1])
    cache._client = fixture
    assert asyncio.run(cache.delete_matching('synthetic:*')) == size
    assert fixture.live == set()
    assert all(1 <= len(batch) <= 200 for batch in fixture.batches)


def test_redis_invalidation_preserves_visible_partial_failure():
    cache = RedisCache(get_settings())
    fixture = RedisFixture([f'synthetic:{i}' for i in range(450)], fail=2)
    cache._client = fixture
    with pytest.raises(RedisConnectionError, match='pattern delete'):
        asyncio.run(cache.delete_matching('synthetic:*'))
    assert len(fixture.live) == 250


@pytest.mark.parametrize('full_stack', [False, True])
def test_audit_after_request_release_with_real_small_pool(environment, full_stack):
    engine = create_engine(get_settings().postgres_dsn, pool_size=2, max_overflow=0, pool_timeout=.5)
    # Exercise a saturated existing pool, independently of first-connect dialect
    # discovery and connection establishment on a shared verification machine.
    with engine.connect() as first, engine.connect() as second:
        first.execute(text('SELECT 1'))
        second.execute(text('SELECT 1'))
    factory = sessionmaker(engine)
    actor = 'optimization-test-' + uuid4().hex
    if full_stack:
        from backend.app.main import create_app
        app = create_app()
    else:
        app = FastAPI()
        app.add_middleware(AuditTrailMiddleware)
    app.state.postgres = SimpleNamespace(_session_factory=factory)
    def session():
        with factory() as db:
            db.execute(text('SELECT 1'))
            yield db
    @app.get('/synthetic/{n}')
    async def route(n: int, request: Request, db=Depends(session)):
        request.state.actor_id = actor
        await asyncio.sleep(.01)
        return {'n': n}
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            replies = await asyncio.gather(*(client.get('/synthetic/'+str(n), headers={'X-Request-ID': f'run-{n}'}) for n in range(8)))
        assert [reply.json() for reply in replies] == [{'n': n} for n in range(8)]
    try:
        asyncio.run(run())
        with factory() as db:
            records = db.scalars(select(AuditEntry).where(AuditEntry.actor == actor)).all()
            assert len(records) == 8
            assert {row.request_id for row in records} == {f'run-{n}' for n in range(8)}
            assert all(row.details['status_code'] == 200 for row in records)
        assert engine.pool.checkedout() == 0
    finally:
        engine.dispose()


def test_slow_audit_does_not_block_unrelated_async_request(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    def record(**kwargs):
        entered.set()
        release.wait(2)
    monkeypatch.setattr(audit_trail_service, 'record', record)
    app = FastAPI()
    app.add_middleware(AuditTrailMiddleware)
    @app.get('/synthetic')
    async def route():
        return {'ok': True}
    @app.get('/metrics')
    async def ping():
        return {'ready': True}
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            pending = asyncio.create_task(client.get('/synthetic'))
            try:
                assert await asyncio.to_thread(entered.wait, 1)
                assert not pending.done()
                assert (await asyncio.wait_for(client.get('/metrics'), .5)).json() == {'ready': True}
                assert not pending.done()
            finally:
                release.set()
                await pending
    asyncio.run(check())


def test_audit_stream_background_cleanup_and_thread_owned_session(monkeypatch):
    lifecycle, calls = [], []
    session_threads = []
    @contextmanager
    def factory():
        session_threads.append(threading.get_ident())
        yield 'synthetic-session'
        session_threads.append(threading.get_ident())
    def record(**kwargs):
        assert lifecycle == ['background', 'released']
        session_threads.append(threading.get_ident())
        calls.append(kwargs)
    monkeypatch.setattr(audit_trail_service, 'record', record)
    app = FastAPI()
    app.state.postgres = SimpleNamespace(_session_factory=factory)
    app.add_middleware(AuditTrailMiddleware)
    async def resource():
        yield
        lifecycle.append('released')
    @app.get('/datasets/synthetic')
    async def route(request: Request, unused=Depends(resource)):
        request.state.actor_id = 'synthetic-owner'
        async def stream():
            yield b'first,'
            await asyncio.sleep(0)
            yield b'second'
        return StreamingResponse(stream(), headers={'X-Preserved': 'yes'},
            background=BackgroundTask(lambda: lifecycle.append('background')))
    with TestClient(app) as client:
        response = client.get('/datasets/synthetic', headers={'X-Request-ID': 'synthetic-request', 'User-Agent': 'synthetic-agent'})
    assert response.content == b'first,second' and response.headers['X-Preserved'] == 'yes'
    assert len(calls) == 1
    assert calls[0]['actor'] == 'synthetic-owner' and calls[0]['action'] == 'dataset.access'
    assert calls[0]['request_id'] == 'synthetic-request' and calls[0]['user_agent'] == 'synthetic-agent'
    assert len(session_threads) == 3 and len(set(session_threads)) == 1


def test_audit_failure_exclusions_and_non_http_passthrough(monkeypatch):
    calls = []
    def unavailable(**kwargs):
        calls.append(kwargs)
        raise RuntimeError('synthetic unavailable sink')
    monkeypatch.setattr(audit_trail_service, 'record', unavailable)
    app = FastAPI()
    app.add_middleware(AuditTrailMiddleware)
    @app.get('/synthetic')
    async def route():
        return {'ok': True}
    @app.get('/metrics')
    @app.get('/api/v1/audit/events')
    async def excluded():
        return {'ok': True}
    @app.websocket('/socket')
    async def socket(ws: WebSocket):
        await ws.accept()
        await ws.send_text('ok')
        await ws.close()
    with TestClient(app) as client:
        assert client.get('/synthetic').json() == {'ok': True}
        assert client.get('/missing').status_code == 404
        assert client.get('/metrics').status_code == 200
        assert client.get('/api/v1/audit/events').status_code == 200
        with client.websocket_connect('/socket') as ws:
            assert ws.receive_text() == 'ok'
    assert len(calls) == 1
