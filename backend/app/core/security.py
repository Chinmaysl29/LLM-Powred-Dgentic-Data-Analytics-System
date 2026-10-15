"""JWT authentication, Supabase verification, password hashing, and user validation.

Supports:
1. Supabase Auth JWT tokens verified dynamically via Supabase project JWKS (ES256).
2. Local HS256 tokens signed with JWT_SECRET_KEY for backward compatibility and test suites.
3. Automatic database provisioning for authenticated Supabase users.
"""

import json
import logging
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.app.core.config import Settings, get_settings
from backend.app.database.postgres import get_db_session

logger = logging.getLogger(__name__)

# Bearer token scheme
bearer_scheme = HTTPBearer(auto_error=False)

# In-memory cache for Supabase JWKS public keys
_JWKS_CACHE: dict[str, dict[str, Any]] = {}
_JWKS_CACHE_TTL_SECONDS = 3600  # 1 hour


def _get_supabase_jwks(supabase_url: str) -> dict[str, Any]:
    """Fetch and cache public signing keys from Supabase JWKS endpoint."""
    now = time.time()
    project_url = supabase_url.rstrip("/")
    cached = _JWKS_CACHE.get(project_url, {})
    if cached.get("keys") and now < cached.get("expires_at", 0):
        return cached["keys"]

    jwks_url = f"{project_url}/auth/v1/.well-known/jwks.json"
    try:
        from jose import jwk

        req = urllib.request.Request(
            jwks_url,
            headers={"User-Agent": "AI-Data-Analyst-OS-Backend"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        constructed = {}
        for key_dict in data.get("keys", []):
            kid = key_dict.get("kid")
            if kid:
                constructed[kid] = jwk.construct(key_dict)

        _JWKS_CACHE[project_url] = {"keys": constructed, "expires_at": now + _JWKS_CACHE_TTL_SECONDS}
        logger.info("Successfully refreshed Supabase JWKS keys count=%d", len(constructed))
        return constructed
    except Exception as exc:
        logger.warning("Failed to fetch Supabase JWKS from %s: %s", jwks_url, exc)
        # An unavailable key service must not authorize with expired keys or
        # keys cached for a different project.
        return {}


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    import bcrypt

    pwd_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    import bcrypt

    try:
        pwd_bytes = plain_password.encode("utf-8")[:72]
        return bcrypt.checkpw(pwd_bytes, hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_access_token(
    data: dict[str, Any],
    settings: Settings | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT access token.

    Uses JWT_SECRET_KEY, JWT_ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES from settings.
    """
    if settings is None:
        settings = get_settings()

    if not settings.jwt_secret_key:
        raise RuntimeError("JWT_SECRET_KEY is not configured in .env")

    from jose import jwt

    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc), "token_type": "access"})
    return jwt.encode(
        to_encode,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def verify_token(token: str, settings: Settings | None = None) -> dict[str, Any]:
    """Decode and validate a JWT token against Supabase JWKS or local HMAC secret."""
    if settings is None:
        settings = get_settings()

    from jose import jwt

    # 1. Try Supabase JWKS verification if token has a matching kid
    try:
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        alg = unverified_header.get("alg")

        if kid and settings.supabase_url and alg in {"ES256", "RS256"}:
            jwks_keys = _get_supabase_jwks(settings.supabase_url)
            if kid in jwks_keys:
                key = jwks_keys[kid]
                payload = jwt.decode(
                    token,
                    key,
                    algorithms=["ES256", "RS256"],
                    audience=settings.supabase_jwt_aud,
                    issuer=f"{settings.supabase_url.rstrip('/')}/auth/v1",
                    options={"require_exp": True, "require_aud": True, "require_iss": True, "require_sub": True},
                )
                return payload
    except Exception:
        pass

    # 2. Fall back to local HS256 verification using JWT_SECRET_KEY
    if settings.jwt_secret_key:
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret_key.get_secret_value(),
                algorithms=[settings.jwt_algorithm],
                options={"require_exp": True, "require_sub": True},
            )
            if payload.get("token_type") != "access":
                raise ValueError("An access token is required")
            return payload
        except Exception:
            pass

    # 3. If both failed, raise 401 Unauthorized
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db_session),
) -> Any:
    """FastAPI dependency that extracts and validates the current user from a JWT.

    Returns the User ORM object. Supports automatic provisioning for Supabase accounts.
    """
    from backend.app.models.user import User

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_token(credentials.credentials)
    user_id: str | None = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    import uuid as _uuid

    target_id: Any = user_id
    if isinstance(user_id, str):
        try:
            target_id = _uuid.UUID(user_id)
        except (ValueError, AttributeError):
            target_id = user_id

    user = None
    if db is not None:
        user = db.query(User).filter(User.id == target_id).first()

    # If user doesn't exist in the local database yet (e.g. Supabase Auth user),
    # auto-provision their record to enable relationships and foreign keys.
    if user is None:
        email = payload.get("email") or f"{user_id}@supabase.user"
        meta = payload.get("user_metadata", {}) or {}
        full_name = meta.get("full_name") or meta.get("name") or (email.split("@")[0] if email else "Analyst")
        role = "analyst"  # Roles are assigned in the server database, never provisioned from claims.

        if db is not None:
            user = User(
                id=target_id,
                email=email,
                hashed_password="",  # Auth handled by Supabase
                full_name=full_name,
                role=role,
                is_active=True,
            )
            try:
                db.add(user)
                db.commit()
                db.refresh(user)
                logger.info("Persisted external identity")
            except Exception as exc:
                db.rollback()
                # If race condition inserted the user, re-query
                user = db.query(User).filter(User.id == target_id).first()
                if not user:
                    # Email is not identity. A legacy/local account may already
                    # use this address; never link its datasets or roles to the
                    # newly verified JWT subject. Keep a separate passwordless
                    # principal with an internal, non-deliverable unique address.
                    from sqlalchemy.exc import IntegrityError
                    conflict = isinstance(exc, IntegrityError) and db.query(User).filter(User.email == email).first() is not None
                    if conflict:
                        user = User(id=target_id, email=f"external-{_uuid.uuid4().hex}@identity.invalid",
                                    hashed_password="", full_name=full_name, role="analyst", is_active=True)
                        try:
                            db.add(user)
                            db.commit()
                            db.refresh(user)
                            logger.info("Persisted separate external identity after contact-address conflict")
                        except Exception:
                            db.rollback()
                            user = db.query(User).filter(User.id == target_id).first()
                    if not user:
                        logger.warning("Identity persistence failed category=%s", type(exc).__name__)

    if user is None:
        raise HTTPException(status_code=503, detail="Identity persistence is unavailable")

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )

    request.state.actor_id = str(user.id)
    return user


async def get_current_admin(
    current_user: Any = Depends(get_current_user),
) -> Any:
    """FastAPI dependency that requires admin role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user


async def require_dataset_access(
    request: Request,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> None:
    """Authorize dataset references before any feature service can load artifacts."""
    from backend.security.rbac import enforce_permission
    permission = "read_dataset"
    if request.url.path.rstrip("/").endswith("/chat"):
        permission = "use_chat"
    elif "/datasets" in request.url.path and request.method not in {"GET", "HEAD", "OPTIONS"}:
        permission = "delete_own_dataset" if request.method == "DELETE" else "write_dataset"
    enforce_permission(getattr(current_user, "role", "viewer"), permission)
    dataset_id = request.path_params.get("dataset_id")
    if not dataset_id and request.method in {"POST", "PUT", "PATCH"} and "application/json" in request.headers.get("content-type", ""):
        try:
            payload = await request.json()
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid JSON request")
        dataset_id = payload.get("dataset_id") if isinstance(payload, dict) else None
    if not dataset_id:
        return
    from backend.app.core.authorization import owned_dataset
    from backend.app.core.exceptions import DatasetNotFoundError, DatabaseConnectionError
    try:
        owned_dataset(db, str(dataset_id), str(current_user.id))
    except DatasetNotFoundError:
        raise HTTPException(status_code=404, detail="Dataset not found")
    except DatabaseConnectionError:
        raise HTTPException(status_code=503, detail="Authorization storage is unavailable")
