"""Authentication schemas."""

from typing import Any

from pydantic import BaseModel, EmailStr, Field


class CurrentUser(BaseModel):
    """Authenticated Supabase user exposed to backend routes."""

    id: str
    email: str | None = None
    aud: str | None = None
    role: str | None = None
    app_metadata: dict[str, Any] = Field(default_factory=dict)
    user_metadata: dict[str, Any] = Field(default_factory=dict)


class SignUpRequest(BaseModel):
    """Email/password sign-up request."""

    email: EmailStr
    password: str = Field(..., min_length=6)
    email_redirect_to: str | None = None


class SignUpUser(BaseModel):
    """Minimal user data returned after sign-up."""

    id: str
    email: str | None = None


class SignUpResponse(BaseModel):
    """Email/password sign-up response."""

    user: SignUpUser | None = None
    session: dict[str, Any] | None = None
    confirmation_required: bool
