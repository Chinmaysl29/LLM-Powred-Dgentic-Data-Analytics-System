"""Revocations must survive replacement of all process-local auth state."""
import importlib
from hashlib import sha256
from sqlalchemy import text
from sqlalchemy.orm import Session
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
from fastapi import HTTPException
import pytest
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


def test_f004_concurrent_consumption_has_exactly_one_winner(db_engine, settings):
    from backend.security.token_revocations import consume, is_revoked
    service = AuthService(settings)
    token = service.create_refresh_token(str(uuid4()))
    claims = service.verify_token(token)
    barrier = Barrier(2)
    def attempt():
        with Session(db_engine) as db:
            barrier.wait(timeout=10)
            won = consume(db, token, claims)
            db.commit()
            return won
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: attempt(), range(2)))
    assert sorted(results) == [False, True]
    with Session(db_engine) as db:
        assert is_revoked(db, token)


def test_f004_absent_auth_storage_fails_closed():
    from backend.security.token_revocations import is_revoked
    with pytest.raises(HTTPException) as error:
        is_revoked(None, 'synthetic-token')
    assert error.value.status_code == 503


def test_f004_supabase_logout_without_local_signing_key(client, settings, monkeypatch):
    from datetime import datetime, timezone
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, PublicFormat, NoEncryption
    from jose import jwk, jwt
    from backend.app.core import security
    routes = importlib.import_module('backend.app.api.v1.routes.auth')
    project = 'https://synthetic.supabase.co'
    hosted = settings.model_copy(update={'jwt_secret_key': None, 'supabase_url': project})
    private = ec.generate_private_key(ec.SECP256R1())
    signing = private.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()
    public = private.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()
    key = jwk.construct(public, 'ES256')
    monkeypatch.setattr(security, 'get_settings', lambda: hosted)
    monkeypatch.setattr(security, '_get_supabase_jwks', lambda _: {'fixture': key})
    monkeypatch.setattr(routes, 'auth_service', AuthService(hosted))
    token = jwt.encode({'sub': str(uuid4()), 'aud': 'authenticated', 'iss': project+'/auth/v1',
                        'exp': int(datetime.now(timezone.utc).timestamp())+300},
                       signing, algorithm='ES256', headers={'kid': 'fixture'})
    logged_out = client.post('/api/v1/auth/logout', headers={'Authorization': 'Bearer '+token})
    assert logged_out.status_code == 200
    denied = client.get('/api/v1/auth/me', headers={'Authorization': 'Bearer '+token})
    assert denied.status_code == 401
