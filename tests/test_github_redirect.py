"""Redirect contract tests without an event loop or external OAuth requests."""
import os
import unittest
from unittest.mock import patch, MagicMock
from urllib.parse import parse_qs, urlsplit
from fastapi import HTTPException
from starlette.requests import Request
from app.routers.auth import frontend_callback_url, github_callback, github_completion_response
from app.schemas.auth import LoginResponse


class GithubRedirectTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "FRONTEND_AUTH_CALLBACK_URL": "http://127.0.0.1:5173/auth/github/callback",
            "GITHUB_TEST_EMAIL": "",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def invoke(self, **kwargs):
        request = Request({"type": "http", "method": "GET", "scheme": "http",
            "path": "/api/auth/github/callback", "query_string": b"",
            "headers": [(b"host", b"localhost"), (b"cookie", b"github_oauth_state=good")]})
        coroutine = github_callback(request, db=MagicMock(), **kwargs)
        try:
            coroutine.send(None)
        except StopIteration as result:
            return result.value
        finally:
            coroutine.close()
        self.fail("Unexpected network IO in isolated test")

    def test_success_matches_frontend_fragment_contract(self):
        async def profile(code):
            return {"id": 123, "login": "test"}
        session = LoginResponse(access_token="app-session", expires_in=3600, user={
            "id": 1, "user_id": "test", "name": "Test", "email": "test@example.com",
            "account_status": "active", "created_at": "2026-10-27T00:00:00"})
        with patch("app.routers.auth.fetch_github_user", profile), patch(
                "app.routers.auth.github_login_session", return_value=session):
            response = self.invoke(code="code", state="good")
        self.assertEqual(response.status_code, 303)
        url = urlsplit(response.headers["location"])
        self.assertEqual(url.netloc, "127.0.0.1:5173")
        self.assertEqual(url.path, "/auth/github/callback")
        self.assertEqual(url.query, "")
        self.assertEqual(parse_qs(url.fragment), {
            "access_token": ["app-session"], "token_type": ["bearer"], "expires_in": ["3600"]})
        self.assertNotIn("test@example.com", response.headers["location"])
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["referrer-policy"], "no-referrer")
        self.assertIn("Max-Age=0", response.headers["set-cookie"])

    def test_invalid_state_denial_and_missing_code_redirect_without_token(self):
        for params in ({"state": "wrong", "code": "code"},
                       {"state": "good", "error": "access_denied"}, {"state": "good"}):
            with self.subTest(params=params), patch("app.routers.auth.fetch_github_user") as fetch:
                response = self.invoke(**params)
                self.assertEqual(response.status_code, 303)
                result = parse_qs(urlsplit(response.headers["location"]).fragment)
                self.assertEqual(result["error"], ["github_login_failed"])
                self.assertNotIn("access_token", result)
                fetch.assert_not_called()

    def test_json_compatibility_when_redirect_disabled(self):
        with patch.dict(os.environ, {"FRONTEND_AUTH_CALLBACK_URL": ""}):
            response = github_completion_response({"detail": "denied"}, 403)
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("location", response.headers)

    def test_invalid_destinations_rejected(self):
        for value in ("https://", "javascript:alert(1)", "http://example.com/callback",
                      "https://example.com/#token", "https://user:pass@example.com",
                      "https://example.com:bad", "https://[invalid"):
            with self.subTest(value=value), patch.dict(os.environ, {"FRONTEND_AUTH_CALLBACK_URL": value}):
                with self.assertRaises(HTTPException) as error:
                    frontend_callback_url()
                self.assertEqual(error.exception.status_code, 503)

    def test_https_frontend_allowed(self):
        url = "https://moeum.example/auth/github/callback"
        with patch.dict(os.environ, {"FRONTEND_AUTH_CALLBACK_URL": url}):
            self.assertEqual(frontend_callback_url(), url)
