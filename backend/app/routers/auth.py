"""Authentication routes."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from app.db.dependencies import get_supabase_admin_client, get_supabase_anon_client
from app.schemas.auth import CurrentUser, SignUpRequest, SignUpResponse
from app.services.auth.dependencies import get_current_user
from app.services.auth.registration import sign_up_with_email, user_exists_by_email


router = APIRouter(prefix="/auth", tags=["auth"])


class CheckEmailRequest(BaseModel):
    """Request body for the email-existence check."""

    email: EmailStr


@router.post("/check-email")
async def check_email(
    payload: CheckEmailRequest,
    admin_client: Any = Depends(get_supabase_admin_client),
) -> dict[str, bool]:
    """Return 404 when the email is not registered."""
    email = payload.email.strip().lower()

    if not user_exists_by_email(admin_client, email):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tài khoản không tồn tại",
        )

    return {"exists": True}


@router.get("/me", response_model=CurrentUser)
async def read_current_user(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Return the authenticated Supabase user."""
    return current_user


@router.post("/sign-up", response_model=SignUpResponse, status_code=status.HTTP_201_CREATED)
async def sign_up(
    payload: SignUpRequest,
    admin_client: Any = Depends(get_supabase_admin_client),
    anon_client: Any = Depends(get_supabase_anon_client),
) -> SignUpResponse:
    """Register a user, returning a clear conflict when the email already exists."""
    email = payload.email.strip().lower()

    if user_exists_by_email(admin_client, email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already registered",
        )

    result = sign_up_with_email(
        anon_client=anon_client,
        email=email,
        password=payload.password,
        email_redirect_to=payload.email_redirect_to,
    )

    return SignUpResponse(**result)
