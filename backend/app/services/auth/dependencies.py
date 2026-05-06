"""Reusable authentication dependencies for protected backend routes."""

from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.db.dependencies import get_supabase_admin_client
from app.schemas.auth import CurrentUser


bearer_scheme = HTTPBearer(auto_error=False)


def _metadata(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _to_current_user(user: Any) -> CurrentUser:
    return CurrentUser(
        id=str(user.id),
        email=getattr(user, "email", None),
        aud=getattr(user, "aud", None),
        role=getattr(user, "role", None),
        app_metadata=_metadata(getattr(user, "app_metadata", None)),
        user_metadata=_metadata(getattr(user, "user_metadata", None)),
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    supabase_client: Any = Depends(get_supabase_admin_client),
) -> CurrentUser:
    """Validate a Supabase access token and return the current user."""
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        response = supabase_client.auth.get_user(credentials.credentials)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = getattr(response, "user", None)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return _to_current_user(user)
