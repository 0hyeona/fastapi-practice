"""회원가입부터 로그인, 만료, 로그아웃까지 검증합니다."""

from datetime import timedelta
import unittest
from unittest.mock import patch

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.auth_session import AuthSession
from app.models.user import User
from app.services.auth_service import SESSION_SECONDS, hash_token, utc_now
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
        self.assertEqual(body["expires_in"], 30 * 24 * 60 * 60)
        self.assertNotIn("password_hash", body["user"])
        headers = {"Authorization": f"Bearer {body['access_token']}"}
        with Session(self.engine) as db:
            session = db.scalar(select(AuthSession))
            self.assertEqual(session.token_hash, hash_token(body["access_token"]))
            self.assertNotEqual(session.token_hash, body["access_token"])
        self.assertEqual(self.client.get("/api/auth/me", headers=headers).json()["user_id"], "testuser")
        self.assertEqual(self.client.get('/api/auth/me', headers=headers).headers['cache-control'], 'no-store')
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

    def test_auth_diagnostics_distinguish_failures_without_logging_credentials(self):
        missing = self.client.get('/api/auth/me')
        self.assertEqual(missing.headers['X-Auth-Error'], 'AUTH_REQUIRED')
        invalid = self.client.get('/api/auth/me', headers={'Authorization': 'Bearer unknown-session'})
        self.assertEqual(invalid.headers['X-Auth-Error'], 'SESSION_NOT_FOUND')
        wrong_password = self.client.post('/api/auth/login', json={**self.login_payload, 'password': 'wrong'})
        self.assertEqual(wrong_password.headers['X-Auth-Error'], 'INVALID_CREDENTIALS')

        token = self.client.post('/api/auth/login', json=self.login_payload).json()['access_token']
        with Session(self.engine) as db:
            session = db.scalar(select(AuthSession))
            deadline, user_id = session.expires_at, session.user_id
        with patch('app.services.auth_service.utc_now', return_value=deadline), \
                self.assertLogs('uvicorn.error', level='WARNING') as logs:
            response = self.client.get('/api/auth/me?code=private-query', headers={
                'Authorization': 'Bearer ' + token, 'Origin': 'http://localhost:5173'})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers['X-Auth-Error'], 'SESSION_EXPIRED')
        request_id = response.headers['X-Request-ID']
        self.assertRegex(request_id, r'^[0-9a-f]{32}$')
        self.assertIn('X-Auth-Error', response.headers['access-control-expose-headers'])
        logged = '\n'.join(logs.output)
        self.assertIn('reason=SESSION_EXPIRED', logged)
        self.assertIn(f'user_id={user_id}', logged)
        self.assertIn('request_id=' + request_id, logged)
        for secret in (token, hash_token(token), 'private-query', 'Authorization'):
            self.assertNotIn(secret, logged)

        with Session(self.engine) as db:
            db.scalar(select(User)).account_status = 'inactive'
            db.commit()
        response = self.client.get('/api/auth/me', headers={'Authorization': 'Bearer ' + token})
        self.assertEqual(response.headers['X-Auth-Error'], 'ACCOUNT_INACTIVE')
        refresh = self.client.post('/api/auth/refresh', headers={'Origin': 'http://localhost:5173'})
        self.assertEqual(refresh.headers['X-Auth-Error'], 'ACCOUNT_INACTIVE')

    def test_https_login_uses_a_secure_host_only_cookie(self):
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app, base_url='https://testserver') as secure_client:
            response = secure_client.post('/api/auth/login', json=self.login_payload)
        cookie = response.headers['set-cookie']
        self.assertIn('Secure', cookie)
        self.assertIn('HttpOnly', cookie)
        self.assertNotIn('Domain=', cookie)

    def test_new_login_and_logout_do_not_invalidate_other_device_sessions(self):
        first = self.client.post('/api/auth/login', json=self.login_payload).json()['access_token']
        second = self.client.post('/api/auth/login', json=self.login_payload).json()['access_token']
        self.assertEqual(self.client.get('/api/auth/me', headers={'Authorization': 'Bearer ' + first}).status_code, 200)
        self.assertEqual(self.client.post('/api/auth/logout', headers={'Authorization': 'Bearer ' + second}).status_code, 204)
        self.assertEqual(self.client.get('/api/auth/me', headers={'Authorization': 'Bearer ' + first}).status_code, 200)

    def test_cookie_restores_and_renews_the_existing_session_after_browser_reopen(self):
        response = self.client.post('/api/auth/login', json=self.login_payload)
        token = response.json()['access_token']
        cookie = response.headers['set-cookie']
        for attribute in ('HttpOnly', 'SameSite=lax', 'Path=/', f'Max-Age={SESSION_SECONDS}'):
            self.assertIn(attribute, cookie)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        with Session(self.engine) as db:
            created = db.scalar(select(AuthSession)).created_at
        with patch('app.services.auth_service.utc_now', return_value=created + timedelta(days=20)):
            # No Authorization header: only the persisted browser cookie is available.
            renewed = self.client.post('/api/auth/refresh', headers={'Origin': 'http://localhost:5173'})
        self.assertEqual(renewed.status_code, 200)
        self.assertTrue(renewed.json()['access_token'] == token)
        self.assertEqual(renewed.json()['expires_in'], SESSION_SECONDS)
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(AuthSession)), 1)
            self.assertEqual(db.scalar(select(AuthSession)).expires_at, created + timedelta(days=50))
        with patch('app.services.auth_service.utc_now', return_value=created + timedelta(days=31)):
            self.assertEqual(self.client.get('/api/auth/me', headers={'Authorization': 'Bearer ' + token}).status_code, 200)
        self.assertEqual(self.client.post('/api/auth/logout', headers={'Authorization': 'Bearer ' + token}).status_code, 204)
        self.assertNotIn('moeum_session', self.client.cookies)
        self.assertEqual(self.client.post('/api/auth/refresh', headers={'Authorization': 'Bearer ' + token}).status_code, 401)

    def test_refresh_rejects_expired_and_revoked_sessions_and_untrusted_origins(self):
        token = self.client.post('/api/auth/login', json=self.login_payload).json()['access_token']
        for origin in ('https://untrusted.example', 'null'):
            self.assertEqual(self.client.post('/api/auth/refresh', headers={'Origin': origin}).status_code, 403)
        self.assertEqual(self.client.post('/api/auth/refresh').status_code, 403)
        with Session(self.engine) as db:
            db.scalar(select(AuthSession)).expires_at = utc_now() - timedelta(seconds=1)
            db.commit()
        expired = self.client.post('/api/auth/refresh', headers={'Origin': 'http://localhost:5173'})
        self.assertEqual(expired.status_code, 401)
        self.assertEqual(expired.headers['X-Auth-Error'], 'SESSION_EXPIRED')

    def test_renewal_does_not_recreate_a_concurrently_deleted_session(self):
        from app.services.auth_service import authenticated_session, renew_login_session, InvalidCredentialsError
        token = self.client.post('/api/auth/login', json=self.login_payload).json()['access_token']
        with Session(self.engine) as db:
            session, user = authenticated_session(db, token)
            db.delete(session)
            db.commit()
            with patch('app.services.auth_service.authenticated_session', return_value=(session, user)):
                with self.assertRaises(InvalidCredentialsError):
                    renew_login_session(db, token)
            self.assertEqual(db.scalar(select(func.count()).select_from(AuthSession)), 0)
