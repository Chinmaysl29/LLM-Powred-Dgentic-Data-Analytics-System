"""Request-session revocation checks and atomic single-use token consumption."""
from datetime import datetime, timezone
from hashlib import sha256
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from backend.app.models.auth_token_revocation import AuthTokenRevocation


def _scope(db, token):
    if db is None:
        raise HTTPException(503, 'Authentication storage is unavailable')
    token_hash = sha256(token.encode('utf-8')).hexdigest()
    db.execute(text("SELECT set_config('app.token_hash', :value, true)"), {'value': token_hash})
    return token_hash


def is_revoked(db, token):
    try:
        token_hash = _scope(db, token)
        return db.scalar(select(AuthTokenRevocation.token_hash).where(
            AuthTokenRevocation.token_hash == token_hash)) is not None
    except SQLAlchemyError:
        raise HTTPException(503, 'Authentication storage is unavailable') from None


def consume(db, token, claims):
    """Return True only for the first consumer; caller commits before issuing tokens."""
    expires = datetime.fromtimestamp(float(claims['exp']), timezone.utc)
    try:
        token_hash = _scope(db, token)
        statement = insert(AuthTokenRevocation).values(token_hash=token_hash, expires_at=expires)
        return db.scalar(statement.on_conflict_do_nothing(
            index_elements=['token_hash']).returning(AuthTokenRevocation.token_hash)) is not None
    except SQLAlchemyError:
        raise HTTPException(503, 'Authentication storage is unavailable') from None
