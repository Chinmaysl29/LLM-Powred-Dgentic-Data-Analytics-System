"""A slow synchronous identity lookup must not stall unrelated async requests."""
import asyncio
import threading

from fastapi import Depends, FastAPI
import httpx

from backend.tests.test_verified_learning_integration import environment, identity
from backend.app.core.security import get_current_user
from backend.app.database.postgres import get_db_session
from backend.security import token_revocations


def test_identity_lookup_leaves_event_loop_responsive(environment, monkeypatch):
    account = identity(environment)
    entered, release = threading.Event(), threading.Event()
    original = token_revocations.is_revoked

    def slow_lookup(db, token):
        entered.set()
        release.wait(2)  # bounded failure mode if the event loop regresses
        return original(db, token)

    monkeypatch.setattr(token_revocations, 'is_revoked', slow_lookup)
    app = FastAPI()
    app.dependency_overrides[get_db_session] = environment['client'].app.dependency_overrides[get_db_session]

    @app.get('/identity')
    def identity_route(user=Depends(get_current_user)):
        return {'id': str(user.id)}

    @app.get('/ping')
    async def ping():
        return {'ready': True}

    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            pending = asyncio.create_task(client.get('/identity', headers=account['headers']))
            try:
                assert await asyncio.to_thread(entered.wait, 1)
                assert not pending.done(), 'Blocking authentication stalled the event loop until the lookup finished'
                response = await asyncio.wait_for(client.get('/ping'), .5)
                assert response.json() == {'ready': True}
                assert not pending.done(), 'Public request must finish before the held identity lookup'
            finally:
                release.set()
                response = await pending
            assert response.status_code == 200
            assert response.json()['id'] == str(account['user'])

    asyncio.run(check())
