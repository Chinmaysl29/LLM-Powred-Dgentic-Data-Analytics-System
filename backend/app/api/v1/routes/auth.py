"""Authentication API endpoints: register, login, refresh, logout, profile."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from backend.app.core.config import get_settings
from backend.app.core.security import (
    get_current_user,
    hash_password,
    verify_token,
    verify_password,
)
from backend.app.database.postgres import get_db_session
from backend.app.models.user import User
from backend.app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    LogoutRequest,
    RefreshTokenRequest,
    RegisterRequest,
    UserResponse,
)
from backend.security.auth_service import auth_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    db: Session = Depends(get_db_session),
) -> UserResponse:
    """Register a new user account."""
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("User registered email=%s", payload.email)

    return UserResponse(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    db: Session = Depends(get_db_session),
) -> AuthResponse:
    """Authenticate a user and return access & refresh tokens."""
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    tokens = auth_service.create_token_pair(
        user_id=str(user.id),
        email=user.email,
        role=user.role,
    )
    logger.info("User logged in email=%s", payload.email)

    return AuthResponse(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        token_type=tokens["token_type"],
        expires_in=tokens["expires_in"],
    )


@router.post("/refresh", response_model=AuthResponse)
async def refresh_token(
    payload: RefreshTokenRequest,
    db: Session = Depends(get_db_session),
) -> AuthResponse:
    """Rotate an expired access token using a valid refresh token."""
    if db is None:
        raise HTTPException(503, 'Authentication storage is unavailable')
    try:
        new_tokens = auth_service.refresh_token(payload.refresh_token, db=db)
        return AuthResponse(
            access_token=new_tokens["access_token"],
            refresh_token=new_tokens["refresh_token"],
            token_type=new_tokens["token_type"],
            expires_in=new_tokens["expires_in"],
        )
    except HTTPException:
        raise
    except SQLAlchemyError:
        raise HTTPException(503, 'Authentication storage is unavailable') from None
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid or expired refresh token',
        ) from exc


@router.post("/logout")
async def logout(
    payload: LogoutRequest | None = None,
    authorization: str | None = Header(None),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """Revoke tokens and terminate the user session."""
    from jose import jwt, JWTError
    from sqlalchemy.exc import SQLAlchemyError
    from backend.security.token_revocations import consume
    tokens = []
    if payload and payload.refresh_token:
        tokens.append(payload.refresh_token)
    if authorization and authorization.startswith("Bearer "):
        tokens.append(authorization.split(" ", 1)[1])
    try:
        for token in tokens:
            try:
                secret, algorithm = auth_service._get_secret_and_algo()
                claims = jwt.decode(token, secret, algorithms=[algorithm], options={
                    'verify_exp': False, 'require_exp': True, 'require_sub': True})
            except (JWTError, RuntimeError):
                # Preserve externally signed Supabase access-token verification.
                claims = verify_token(token)
            consume(db, token, claims)
        if tokens:
            db.commit()
    except SQLAlchemyError:
        raise HTTPException(503, 'Authentication storage is unavailable') from None
    for token in tokens:
        auth_service.revoke_token(token)

    return {
        "status": "success",
        "message": "Logged out successfully",
        "revoked": bool(tokens),
    }


@router.get("/profile", response_model=UserResponse)
async def get_profile(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Return the authenticated user's profile."""
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        is_active=current_user.is_active,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Alias for /profile endpoint."""
    return await get_profile(current_user=current_user)
