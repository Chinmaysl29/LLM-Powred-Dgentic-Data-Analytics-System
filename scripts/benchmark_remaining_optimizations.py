"""Guarded Redis and audit benchmarks; synthetic namespaces and isolated PG only."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
import tracemalloc
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.benchmark_company_reads import configure


async def redis_measure():
    from urllib.parse import urlsplit
    from backend.app.core.config import get_settings
    from backend.app.database.redis import RedisCache
    settings = get_settings()
    target = urlsplit(settings.redis_url)
    assert target.hostname == 'redis' and target.port == 6379, 'Isolated Redis only'
    cache = RedisCache(settings)
    await cache.connect()
    prefix = 'optimization-measure:' + uuid4().hex
    keep = prefix + ':keep'
    measurements = []
    try:
        await cache.set(keep, 'untouched', 300)
        for run in range(12):
            # Seed outside the timed/traced section. TTL bounds cleanup on failure.
            for start in range(0, 10000, 200):
                async with cache.client.pipeline(transaction=False) as pipeline:
                    for n in range(start, start+200):
                        pipeline.set(f'{prefix}:target:{n:05}', 'synthetic', ex=300)
                    await pipeline.execute()
            tracemalloc.start()
            started = time.perf_counter()
            deleted = await cache.delete_matching(prefix+':target:*')
            duration = (time.perf_counter()-started)*1000
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            assert deleted == 10000
            assert not [key async for key in cache.client.scan_iter(match=prefix+':target:*')]
            assert await cache.get(keep) == 'untouched'
            if run >= 2:
                measurements.append({'ms': duration, 'python_peak_allocated_bytes': peak})
        return {'keys': 10000, 'warmups': 2, 'samples': measurements,
                'median_ms': statistics.median(row['ms'] for row in measurements),
                'median_peak_bytes': statistics.median(row['python_peak_allocated_bytes'] for row in measurements)}
    finally:
        await cache.delete_matching(prefix+':*')
        await cache.close()


async def audit_measure():
    from fastapi import Depends, FastAPI, Request
    import httpx
    from sqlalchemy import create_engine, func, select, text
    from sqlalchemy.orm import sessionmaker
    from backend.app.core.config import get_settings
    from backend.app.middleware.audit import AuditTrailMiddleware
    from backend.app.models.audit_entry import AuditEntry
    from backend.app.services.audit_trail_service import audit_trail_service

    # Deliberately constrained pool reproduces nested checkout while a request
    # still owns its connection. This is not a production sizing recommendation.
    engine = create_engine(get_settings().postgres_dsn, pool_size=1, max_overflow=0, pool_timeout=.15)
    factory = sessionmaker(engine)
    actor = 'optimization-audit-' + uuid4().hex
    app = FastAPI()
    app.state.postgres = SimpleNamespace(_session_factory=factory)
    app.add_middleware(AuditTrailMiddleware)
    def session():
        with factory() as db:
            db.execute(text('SELECT 1'))
            yield db
    @app.get('/synthetic')
    def endpoint(request: Request, db=Depends(session)):
        request.state.actor_id = actor
        return {'ok': True}
    samples = []
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://synthetic') as client:
        for run in range(12):
            started = time.perf_counter()
            response = await client.get('/synthetic', headers={'X-Request-ID': f'synthetic-{run}'})
            assert response.status_code == 200 and response.json() == {'ok': True}
            if run >= 2:
                samples.append((time.perf_counter()-started)*1000)
    with factory() as db:
        persisted = db.scalar(select(func.count()).select_from(AuditEntry).where(AuditEntry.actor == actor))
    engine.dispose()

    # Independently quantify event-loop blocking with a controlled 50 ms sink.
    delayed = FastAPI()
    delayed.add_middleware(AuditTrailMiddleware)
    @delayed.get('/synthetic')
    async def delayed_endpoint():
        return {'ok': True}
    gaps = []
    async def ticker():
        previous = time.perf_counter()
        while True:
            await asyncio.sleep(.001)
            current = time.perf_counter()
            gaps.append((current-previous)*1000)
            previous = current
    with patch.object(audit_trail_service, 'record', side_effect=lambda **kw: time.sleep(.05)):
        task = asyncio.create_task(ticker())
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=delayed), base_url='http://synthetic') as client:
                for _ in range(10):
                    await client.get('/synthetic')
                    await asyncio.sleep(.002)
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    return {'pool_size': 1, 'overflow': 0, 'checkout_timeout_s': .15, 'warmups': 2,
            'samples_ms': samples, 'median_ms': statistics.median(samples),
            'requests_including_warmups': 12, 'persisted_audit_events': persisted,
            'controlled_sink_delay_ms': 50, 'maximum_event_loop_tick_gap_ms': max(gaps)}


async def main(output):
    result = {'redis': await redis_measure(), 'audit': await audit_measure(),
              'source_hashes': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                  [ROOT/'backend/app/database/redis.py', ROOT/'backend/app/middleware/audit.py']}}
    Path(output).write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    configure()
    asyncio.run(main(args.output))
