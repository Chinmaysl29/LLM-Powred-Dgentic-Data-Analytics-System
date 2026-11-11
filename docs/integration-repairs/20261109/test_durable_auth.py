"""Revocations must survive replacement of all process-local auth state."""
import importlib
from hashlib import sha256
from sqlalchemy import text
from backend.security.auth_service import AuthService
from backend.tests.test_analysis_history_and_reports import (
    settings, db_engine, db_session, client, make_test_user_and_workspace,
)


def test_f004_logout_survives_fresh_auth_services(client, db_session, settings, monkeypatch):
    service_module = importlib.import_module('backend.security.auth_service')
    routes = importlib.import_module('backend.app.api.v1.routes.auth')
    owner, _, _ = make_test_user_and_workspace(db_session, 'durable_logout')
    pair = routes.auth_service.create_token_pair(str(owner.id), owner.email, 'analyst')
    access, refresh = pair['access_token'], pair['refresh_token']
    result = client.post('/api/v1/auth/logout',
        headers={'Authorization': 'Bearer '+access}, json={'refresh_token': refresh})
    assert result.status_code == 200
    fresh = AuthService(settings)
    monkeypatch.setattr(routes, 'auth_service', fresh)
    monkeypatch.setattr(service_module, 'auth_service', fresh)
    denied = client.post('/api/v1/auth/refresh', json={'refresh_token': refresh})
    assert denied.status_code == 401
    denied_access = client.get('/api/v1/auth/me', headers={'Authorization': 'Bearer '+access})
    assert denied_access.status_code == 401
    hashes = set(db_session.execute(text('SELECT token_hash FROM auth_token_revocations')).scalars())
    assert {sha256(t.encode()).hexdigest() for t in (access, refresh)} <= hashes
    assert access not in hashes and refresh not in hashes


def test_f004_rotated_refresh_cannot_be_replayed_after_state_reset(client, db_session, settings, monkeypatch):
    routes = importlib.import_module('backend.app.api.v1.routes.auth')
    owner, _, _ = make_test_user_and_workspace(db_session, 'durable_rotation')
    refresh = routes.auth_service.create_refresh_token(str(owner.id))
    result = client.post('/api/v1/auth/refresh', json={'refresh_token': refresh})
    assert result.status_code == 200
    monkeypatch.setattr(routes, 'auth_service', AuthService(settings))
    replay = client.post('/api/v1/auth/refresh', json={'refresh_token': refresh})
    assert replay.status_code == 401
