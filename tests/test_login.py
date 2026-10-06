"""회원가입부터 로그인, 만료, 로그아웃까지 검증합니다."""

from datetime import timedelta
import unittest

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.auth_session import AuthSession
from app.models.user import User
from app.services.auth_service import hash_token, utc_now
import test_signup


class LoginTests(unittest.TestCase):
    def setUp(self):
        test_signup.SignupTests.setUp(self)
        self.client.post("/api/auth/signup", json=self.payload)
        self.login_payload = {key: self.payload[key] for key in ("email", "password")}

    def tearDown(self):
        test_signup.SignupTests.tearDown(self)

    def test_login_me_and_logout(self):
        response = self.client.post("/api/auth/login", json=self.login_payload)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["expires_in"], 3600)
        self.assertNotIn("password_hash", body["user"])
        headers = {"Authorization": f"Bearer {body['access_token']}"}
        with Session(self.engine) as db:
            session = db.scalar(select(AuthSession))
            self.assertEqual(session.token_hash, hash_token(body["access_token"]))
            self.assertNotEqual(session.token_hash, body["access_token"])
        self.assertEqual(self.client.get("/api/auth/me", headers=headers).json()["user_id"], "testuser")
        self.assertEqual(self.client.post("/api/auth/logout", headers=headers).status_code, 204)
        self.assertEqual(self.client.get("/api/auth/me", headers=headers).status_code, 401)

    def test_invalid_credentials_create_no_session(self):
        for changes in ({"email": "missing@example.com"}, {"password": "wrong-password"}):
            response = self.client.post("/api/auth/login", json={**self.login_payload, **changes})
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json()["detail"], "이메일 또는 비밀번호가 올바르지 않습니다.")
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(AuthSession)), 0)

    def test_expired_and_inactive_sessions(self):
        token = self.client.post("/api/auth/login", json=self.login_payload).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        with Session(self.engine) as db:
            db.scalar(select(AuthSession)).expires_at = utc_now() - timedelta(seconds=1)
            db.commit()
        self.assertEqual(self.client.get("/api/auth/me", headers=headers).status_code, 401)
        token = self.client.post("/api/auth/login", json=self.login_payload).json()["access_token"]
        with Session(self.engine) as db:
            db.scalar(select(User)).account_status = "inactive"
            db.commit()
        self.assertEqual(self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code, 401)
        self.assertEqual(self.client.post("/api/auth/login", json=self.login_payload).status_code, 401)

    def test_missing_invalid_token_and_invalid_input(self):
        for headers in ({}, {"Authorization": "Bearer invalid"}, {"Authorization": "Basic invalid"}):
            self.assertEqual(self.client.get("/api/auth/me", headers=headers).status_code, 401)
        for changes in ({"email": " "}, {"email": "invalid"}, {"password": ""}, {"password": "x" * 129}):
            self.assertEqual(self.client.post("/api/auth/login", json={**self.login_payload, **changes}).status_code, 422)
        self.assertEqual(self.client.post("/api/auth/login", json={
            "user_id": self.payload["user_id"], "password": self.payload["password"],
        }).status_code, 422)
