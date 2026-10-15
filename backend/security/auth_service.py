"""Authentication Service for Enterprise Phase 8.

Handles:
- JWT Access token generation (configurable expiration, defaults to 3600 seconds)
- Refresh token issuance and rotation (single-use rotation)
- Session validation and revocation
- In-memory session and revocation store with optional Redis backing
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from backend.app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class AuthService:
    """Enterprise authentication and session management service."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._revoked_tokens: set[str] = set()
        self._active_sessions: dict[str, dict[str, Any]] = {}

    def _get_secret_and_algo(self) -> tuple[str, str]:
        if not self.settings.jwt_secret_key or not self.settings.jwt_secret_key.get_secret_value():
            raise RuntimeError("Local authentication signing key is not configured")
        secret = (
            self.settings.jwt_secret_key.get_secret_value()
        )
        algo = self.settings.jwt_algorithm or "HS256"
        return secret, algo

    def create_access_token(
        self,
        data: dict[str, Any],
        expires_delta: timedelta | None = None,
    ) -> str:
        """Issue a signed JWT access token."""
        secret, algo = self._get_secret_and_algo()
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + (
            expires_delta
            or timedelta(minutes=self.settings.access_token_expire_minutes or 60)
        )
        to_encode.update({
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "token_type": "access",
        })
        return jwt.encode(to_encode, secret, algorithm=algo)

    def create_refresh_token(
        self,
        user_id: str,
        expires_delta: timedelta | None = None,
    ) -> str:
        """Issue a single-use refresh token with unique JTI."""
        secret, algo = self._get_secret_and_algo()
        jti = str(uuid.uuid4())
        expire = datetime.now(timezone.utc) + (expires_delta or timedelta(days=7))
        payload = {
            "sub": str(user_id),
            "jti": jti,
            "token_type": "refresh",
            "exp": expire,
            "iat": datetime.now(timezone.utc),
        }
        token = jwt.encode(payload, secret, algorithm=algo)
        self._active_sessions[jti] = {
            "user_id": str(user_id),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "active",
        }
        return token

    def create_token_pair(
        self,
        user_id: str,
        email: str,
        role: str,
        expires_in_seconds: int = 3600,
    ) -> dict[str, Any]:
        """Issue both access and refresh tokens."""
        access_token = self.create_access_token(
            data={"sub": str(user_id), "email": email, "role": role},
            expires_delta=timedelta(seconds=expires_in_seconds),
        )
        refresh_token = self.create_refresh_token(user_id=user_id)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": expires_in_seconds,
        }

    def verify_token(self, token: str) -> dict[str, Any]:
        """Decode and validate a JWT token, ensuring it hasn't been revoked."""
        if token in self._revoked_tokens:
            raise ValueError("Token has been revoked")

        secret, algo = self._get_secret_and_algo()
        try:
            payload = jwt.decode(token, secret, algorithms=[algo])
        except JWTError as exc:
            raise ValueError(f"Invalid or expired token: {exc}") from exc

        jti = payload.get("jti")
        if jti and jti in self._revoked_tokens:
            raise ValueError("Token session has been revoked")

        return payload

    def refresh_token(self, refresh_token_str: str) -> dict[str, Any]:
        """Rotate a refresh token: validate, revoke old, and issue a fresh pair."""
        payload = self.verify_token(refresh_token_str)
        if payload.get("token_type") != "refresh":
            raise ValueError("Provided token is not a refresh token")

        jti = payload.get("jti")
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("Refresh token missing subject claim")

        # Invalidate the old refresh token (single-use rotation)
        if jti:
            self._revoked_tokens.add(jti)
            if jti in self._active_sessions:
                self._active_sessions[jti]["status"] = "rotated"

        self._revoked_tokens.add(refresh_token_str)

        # Issue new token pair
        return self.create_token_pair(
            user_id=user_id,
            email=payload.get("email", ""),
            role=payload.get("role", "analyst"),
        )

    def revoke_token(self, token: str) -> bool:
        """Revoke a token (access or refresh) and its session."""
        self._revoked_tokens.add(token)
        try:
            payload = self.verify_token_claims_unverified(token)
            jti = payload.get("jti")
            if jti:
                self._revoked_tokens.add(jti)
                if jti in self._active_sessions:
                    self._active_sessions[jti]["status"] = "revoked"
        except Exception:
            pass
        return True

    def verify_token_claims_unverified(self, token: str) -> dict[str, Any]:
        """Inspect claims without verification for revocation handling."""
        secret, algo = self._get_secret_and_algo()
        return jwt.decode(
            token,
            secret,
            algorithms=[algo],
            options={"verify_signature": False, "verify_exp": False},
        )

    def validate_session(self, token: str) -> dict[str, Any]:
        """Validate if a session associated with a token is active."""
        payload = self.verify_token(token)
        return {
            "valid": True,
            "user_id": payload.get("sub"),
            "role": payload.get("role"),
            "token_type": payload.get("token_type"),
        }


# Global singleton instance
auth_service = AuthService()
