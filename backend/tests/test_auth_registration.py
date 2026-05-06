"""Tests for registration helpers."""

from types import SimpleNamespace
import unittest

from app.services.auth.registration import sign_up_with_email, user_exists_by_email


class FakeAdminAuth:
    def __init__(self, pages: list[list[object]]):
        self.pages = pages
        self.calls: list[tuple[int | None, int | None]] = []

    def list_users(self, page: int | None = None, per_page: int | None = None) -> list[object]:
        self.calls.append((page, per_page))
        index = (page or 1) - 1
        return self.pages[index] if index < len(self.pages) else []


class FakeSignUpAuth:
    def __init__(self):
        self.credentials: dict[str, object] | None = None

    def sign_up(self, credentials: dict[str, object]) -> SimpleNamespace:
        self.credentials = credentials
        return SimpleNamespace(
            user=SimpleNamespace(id="new-user", email=credentials["email"]),
            session=None,
        )


class AuthRegistrationTests(unittest.TestCase):
    def test_user_exists_by_email_matches_case_insensitively(self) -> None:
        admin_client = SimpleNamespace(
            auth=SimpleNamespace(
                admin=FakeAdminAuth(
                    pages=[
                        [
                            SimpleNamespace(id="user-1", email="Existing@Example.com"),
                        ]
                    ]
                )
            )
        )

        exists = user_exists_by_email(admin_client, "existing@example.com")

        self.assertTrue(exists)

    def test_user_exists_by_email_returns_false_after_last_page(self) -> None:
        admin_client = SimpleNamespace(
            auth=SimpleNamespace(
                admin=FakeAdminAuth(
                    pages=[
                        [
                            SimpleNamespace(id="user-1", email="other@example.com"),
                        ]
                    ]
                )
            )
        )

        exists = user_exists_by_email(admin_client, "missing@example.com")

        self.assertFalse(exists)

    def test_sign_up_with_email_uses_public_signup_flow(self) -> None:
        auth = FakeSignUpAuth()
        anon_client = SimpleNamespace(auth=auth)

        result = sign_up_with_email(
            anon_client=anon_client,
            email="new@example.com",
            password="password123",
            email_redirect_to="http://localhost:5173/auth/callback",
        )

        self.assertEqual(result["user"]["id"], "new-user")
        self.assertEqual(result["user"]["email"], "new@example.com")
        self.assertIsNone(result["session"])
        self.assertTrue(result["confirmation_required"])
        self.assertEqual(
            auth.credentials,
            {
                "email": "new@example.com",
                "password": "password123",
                "options": {"email_redirect_to": "http://localhost:5173/auth/callback"},
            },
        )


if __name__ == "__main__":
    unittest.main()
