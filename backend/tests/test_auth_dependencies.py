"""Tests for auth dependencies."""

from types import SimpleNamespace
import unittest

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.services.auth.dependencies import get_current_user


class FakeSupabaseAuth:
    def __init__(self, user: object | None = None, should_fail: bool = False):
        self.user = user
        self.should_fail = should_fail
        self.seen_token: str | None = None

    def get_user(self, token: str) -> SimpleNamespace:
        self.seen_token = token
        if self.should_fail:
            raise RuntimeError("bad token")

        return SimpleNamespace(user=self.user)


class AuthDependencyTests(unittest.TestCase):
    def test_get_current_user_maps_supabase_user(self) -> None:
        auth = FakeSupabaseAuth(
            user=SimpleNamespace(
                id="user-123",
                email="user@example.com",
                aud="authenticated",
                role="authenticated",
                app_metadata={"provider": "email"},
                user_metadata={"full_name": "Demo User"},
            )
        )
        client = SimpleNamespace(auth=auth)
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="access-token")

        current_user = get_current_user(credentials=credentials, supabase_client=client)

        self.assertEqual(current_user.id, "user-123")
        self.assertEqual(current_user.email, "user@example.com")
        self.assertEqual(current_user.user_metadata["full_name"], "Demo User")
        self.assertEqual(auth.seen_token, "access-token")

    def test_get_current_user_rejects_missing_token(self) -> None:
        with self.assertRaises(HTTPException) as exc:
            get_current_user(credentials=None, supabase_client=SimpleNamespace())

        self.assertEqual(exc.exception.status_code, 401)

    def test_get_current_user_rejects_invalid_token(self) -> None:
        client = SimpleNamespace(auth=FakeSupabaseAuth(should_fail=True))
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad-token")

        with self.assertRaises(HTTPException) as exc:
            get_current_user(credentials=credentials, supabase_client=client)

        self.assertEqual(exc.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
