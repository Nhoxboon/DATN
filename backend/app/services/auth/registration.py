"""Registration helpers."""

from typing import Any


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _to_dict(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "dict"):
        return value.dict()
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)

    return None


def _user_email(user: Any) -> str | None:
    if isinstance(user, dict):
        email = user.get("email")
    else:
        email = getattr(user, "email", None)

    return str(email) if email else None


def user_exists_by_email(admin_client: Any, email: str) -> bool:
    """Return true if a Supabase Auth user already exists for the email."""
    target_email = _normalize_email(email)
    page = 1
    per_page = 1000

    while True:
        users = admin_client.auth.admin.list_users(page=page, per_page=per_page)
        if not users:
            return False

        for user in users:
            if _normalize_email(_user_email(user) or "") == target_email:
                return True

        if len(users) < per_page:
            return False

        page += 1


def sign_up_with_email(anon_client: Any, email: str, password: str, email_redirect_to: str | None) -> dict[str, Any]:
    """Create a user through Supabase's public sign-up flow."""
    credentials = {
        "email": email,
        "password": password,
    }

    if email_redirect_to:
        credentials["options"] = {"email_redirect_to": email_redirect_to}

    response = anon_client.auth.sign_up(credentials)

    user = getattr(response, "user", None)
    session = getattr(response, "session", None)

    user_data = _to_dict(user)
    session_data = _to_dict(session)

    return {
        "user": {
            "id": str(user_data.get("id")),
            "email": user_data.get("email"),
        }
        if user_data and user_data.get("id")
        else None,
        "session": session_data,
        "confirmation_required": session_data is None,
    }
