"""Real local-token authentication regressions, promoted when F-003 starts."""
from uuid import uuid4

import pytest
from jose import jwt

from backend.app.core.security import create_access_token
from backend.security.auth_service import auth_service
from backend.tests.test_analysis_history_and_reports import (
    settings, db_engine, db_session, client, make_test_user_and_workspace,
)


@pytest.mark.parametrize('issuer', [create_access_token, auth_service.create_access_token])
def test_f003_new_access_tokens_have_distinct_session_identifiers(issuer):
    subject = str(uuid4())
    first = jwt.get_unverified_claims(issuer({'sub': subject}))
    second = jwt.get_unverified_claims(issuer({'sub': subject}))
    assert first.get('jti') and second.get('jti')
    assert first['jti'] != second['jti']


def test_f003_logout_denies_old_access_but_allows_new_session(client, db_session):
    owner, token, _ = make_test_user_and_workspace(db_session, 'logout_regression')
    headers = {'Authorization': 'Bearer '+token}
    before = client.get('/api/v1/auth/me', headers=headers)
    assert before.status_code == 200
    logout = client.post('/api/v1/auth/logout', headers=headers, json={})
    assert logout.status_code == 200
    after = client.get('/api/v1/auth/me', headers=headers)
    assert after.status_code == 401
    new_token = create_access_token({'sub': str(owner.id), 'email': owner.email})
    fresh = client.get('/api/v1/auth/me', headers={'Authorization': 'Bearer '+new_token})
    assert fresh.status_code == 200
