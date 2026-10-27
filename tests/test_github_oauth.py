"""외부 GitHub 호출 없이 OAuth 흐름과 실패 응답을 검증합니다."""

import os
import ssl
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database.database import Base, get_db
from app.main import app
from app.models.user import User
from app.models.github_account import GithubAccount
from app.models.auth_session import AuthSession
from app.services.auth_service import hash_token


class GithubOAuthTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "GITHUB_CLIENT_ID": "test-client", "GITHUB_CLIENT_SECRET": "test-secret",
            "GITHUB_REDIRECT_URI": "http://localhost:8000/api/auth/github/callback",
            "GITHUB_TEST_EMAIL": "",
        })
        self.environment.start()
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        def test_db():
            with Session(self.engine) as db:
                yield db
        app.dependency_overrides[get_db] = test_db
        self.client = TestClient(app)
        self.calls = []
        self.token_body = {"access_token": "private-token"}
        self.user_status = 200
        self.timeout = False
        self.profile = {"id": 123, "login": "octocat", "name": "Test", "email": None,
                        "avatar_url": "https://example.com/avatar", "html_url": "https://github.com/octocat"}
        self.emails = [{"email": "octocat@example.com", "verified": True, "primary": True}]
        original_client = httpx.AsyncClient
        self.network = patch("app.services.github_oauth.httpx.AsyncClient", side_effect=lambda **kwargs:
                             original_client(transport=httpx.MockTransport(self.github), **kwargs))
        self.mock_client = self.network.start()

    def tearDown(self):
        self.network.stop()
        self.environment.stop()
        self.client.close()
        app.dependency_overrides.pop(get_db, None)
        self.engine.dispose()

    def github(self, request):
        self.calls.append(request)
        if self.timeout:
            raise httpx.ReadTimeout("timeout", request=request)
        if request.url.host == "github.com":
            return httpx.Response(200, json=self.token_body)
        return httpx.Response(self.user_status, json=self.emails if request.url.path == "/user/emails" else self.profile)

    def start_login(self):
        response = self.client.get("/api/auth/github/login", follow_redirects=False)
        self.assertEqual(response.status_code, 307)
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertEqual(response.headers["cache-control"], "no-store")
        return parse_qs(urlsplit(response.headers["location"]).query)["state"][0]

    def callback(self, **kwargs):
        state = self.start_login()
        return self.client.get("/api/auth/github/callback", params={"state": state, "code": "test-code", **kwargs})

    def test_success_and_token_privacy(self):
        response = self.callback()
        context = self.mock_client.call_args.kwargs["verify"]
        self.assertIsInstance(context, ssl.SSLContext)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["name"], "Test")
        self.assertEqual(response.json()["user"]["email"], "octocat@example.com")
        self.assertEqual(response.json()["expires_in"], 3600)
        self.assertEqual(response.json()["token_type"], "bearer")
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        self.assertEqual(self.client.get("/api/auth/me", headers=headers).status_code, 200)
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(AuthSession)).token_hash, hash_token(token))
            self.assertEqual(db.scalar(select(func.count()).select_from(GithubAccount)), 1)
        self.assertEqual(self.client.post("/api/auth/logout", headers=headers).status_code, 204)
        self.assertEqual(self.client.get("/api/auth/me", headers=headers).status_code, 401)
        self.assertNotIn("private-token", response.text)
        self.assertNotIn("test-secret", response.text)
        body = parse_qs(self.calls[0].content.decode())
        self.assertEqual(body["code"], ["test-code"])
        self.assertEqual(body["client_secret"], ["test-secret"])
        self.assertEqual(self.calls[1].headers["authorization"], "Bearer private-token")
        self.assertNotIn("github_oauth_state", self.client.cookies)
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_untrusted_callback_never_contacts_github(self):
        self.assertEqual(self.client.get("/api/auth/github/callback?code=x").status_code, 400)
        self.assertEqual(self.callback(state="wrong").status_code, 400)
        self.assertEqual(self.callback(state="잘못된값").status_code, 400)
        self.assertEqual(self.calls, [])

    def test_denial_and_missing_code(self):
        self.assertEqual(self.callback(error="access_denied").status_code, 400)
        self.assertEqual(self.callback(code="").status_code, 400)
        self.assertEqual(self.calls, [])

    def test_expired_code(self):
        self.token_body = {"error": "bad_verification_code"}
        response = self.callback()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(self.calls), 1)

    def test_upstream_failures(self):
        for token_body in ({"error": "unknown_error"}, {}, []):
            self.token_body = token_body
            self.assertEqual(self.callback().status_code, 502)
        self.token_body = {"access_token": "private-token"}
        self.user_status = 401
        self.assertEqual(self.callback().status_code, 502)
        self.timeout = True
        self.assertEqual(self.callback().status_code, 504)

    def test_missing_configuration(self):
        with patch.dict(os.environ, {"GITHUB_CLIENT_SECRET": ""}):
            self.assertEqual(self.callback().status_code, 503)
        with patch.dict(os.environ, {"GITHUB_CLIENT_ID": ""}):
            self.assertEqual(self.client.get("/api/auth/github/login").status_code, 503)
        self.assertEqual(self.calls, [])

    def test_invalid_client_credentials(self):
        self.token_body = {"error": "incorrect_client_credentials"}
        response = self.callback()
        self.assertEqual(response.status_code, 503)
        self.assertIn("Client Secret", response.json()["detail"])
        self.assertNotIn("test-secret", response.text)

    def test_repeat_login_uses_github_id_after_profile_changes(self):
        first = self.callback().json()
        self.profile.update(login="renamed", name="Changed")
        self.emails = [{"email": "changed@example.com", "verified": True, "primary": True}]
        second = self.callback().json()
        self.assertEqual(first["user"]["id"], second["user"]["id"])
        self.assertNotEqual(first["access_token"], second["access_token"])
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(User)), 1)

    def test_email_collision_does_not_link_existing_account(self):
        self.client.post("/api/auth/signup", json={"user_id": "existing", "name": "Existing",
                         "email": "octocat@example.com", "password": "test-password"})
        self.assertEqual(self.callback().status_code, 409)
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(GithubAccount)), 0)
            self.assertEqual(db.scalar(select(func.count()).select_from(AuthSession)), 0)

    def test_verified_email_required_for_signup(self):
        self.profile["email"] = "unverified@example.com"
        self.emails = [{"email": "unverified@example.com", "verified": False, "primary": True}]
        self.assertEqual(self.callback().status_code, 400)
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(User)), 0)

    def test_primary_verified_email_preferred(self):
        self.emails.insert(0, {"email": "secondary@example.com", "verified": True, "primary": False})
        self.assertEqual(self.callback().json()["user"]["email"], "octocat@example.com")

    def test_inactive_member_cannot_login(self):
        first = self.callback().json()
        with Session(self.engine) as db:
            db.get(User, first["user"]["id"]).account_status = "inactive"
            db.commit()
        self.assertEqual(self.callback().status_code, 403)
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(AuthSession)), 1)

    def test_new_member_rolled_back_when_session_creation_fails(self):
        with patch("app.services.github_login.create_login_session", side_effect=SQLAlchemyError("test")):
            self.assertEqual(self.callback().status_code, 503)
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(User)), 0)
            self.assertEqual(db.scalar(select(func.count()).select_from(GithubAccount)), 0)

    def test_local_test_email_creates_separate_member(self):
        self.client = TestClient(app, base_url="http://localhost")
        payload = {"user_id": "existing", "name": "Existing", "email": "octocat@example.com", "password": "test-password"}
        original = self.client.post("/api/auth/signup", json=payload).json()
        with patch.dict(os.environ, {"GITHUB_TEST_EMAIL": "github-local-test@example.com"}):
            first = self.callback()
            self.assertEqual(first.status_code, 200)
            self.assertEqual(first.json()["user"]["email"], "github-local-test@example.com")
            self.assertNotEqual(first.json()["user"]["id"], original["id"])
            self.assertEqual(self.callback().json()["user"]["id"], first.json()["user"]["id"])
        with Session(self.engine) as db:
            self.assertEqual(db.get(User, original["id"]).email, "octocat@example.com")
            self.assertEqual(db.scalar(select(func.count()).select_from(User)), 2)

    def test_test_email_ignored_on_nonlocal_host(self):
        self.client.post("/api/auth/signup", json={"user_id": "existing", "name": "Existing",
                         "email": "octocat@example.com", "password": "test-password"})
        with patch.dict(os.environ, {"GITHUB_TEST_EMAIL": "github-local-test@example.com"}):
            self.assertEqual(self.callback().status_code, 409)
