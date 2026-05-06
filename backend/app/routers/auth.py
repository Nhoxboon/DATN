"""Authentication routes."""

from fastapi import APIRouter, Depends

from app.schemas.auth import CurrentUser
from app.services.auth.dependencies import get_current_user


router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=CurrentUser)
async def read_current_user(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Return the authenticated Supabase user."""
    return current_user
