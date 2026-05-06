"""Authentication schemas."""

from typing import Any

from pydantic import BaseModel, Field


class CurrentUser(BaseModel):
    """Authenticated Supabase user exposed to backend routes."""

    id: str
    email: str | None = None
    aud: str | None = None
    role: str | None = None
    app_metadata: dict[str, Any] = Field(default_factory=dict)
    user_metadata: dict[str, Any] = Field(default_factory=dict)
