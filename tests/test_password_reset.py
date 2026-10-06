import unittest
from datetime import timedelta
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.orm import Session
import test_signup
from app.models.password_reset import PasswordReset
from app.services.auth_service import utc_now
from app.services.email_service import EmailDeliveryError


class PasswordResetTests(unittest.TestCase):
    def setUp(self):
        test_signup.SignupTests.setUp(self)
        self.client.post("/api/auth/signup", json=self.payload)
        self.email = {"email": self.payload["email"]}
        self.mail_patch = patch("app.services.password_reset_service.send_reset_code")
        self.mail = self.mail_patch.start()

    def tearDown(self):
        self.mail_patch.stop()
        test_signup.SignupTests.tearDown(self)

    def send(self):
        response = self.client.post("/api/auth/password/request-code", json=self.email)
        self.assertEqual(response.status_code, 200)
        code = self.mail.call_args.args[1]
        self.assertEqual(len(code), 6)
        self.assertNotIn(code, response.text)
        return code

    def verify(self, code):
        return self.client.post("/api/auth/password/verify-code", json={**self.email, "code": code})

    def reset_payload(self, token):
        return {"reset_token": token, "new_password": "New-pass123!", "confirm_password": "New-pass123!"}

    def test_end_to_end_reset_revokes_sessions_and_token_is_single_use(self):
        credentials = {"email": self.payload["email"], "password": self.payload["password"]}
        access = self.client.post("/api/auth/login", json=credentials).json()["access_token"]
        self.assertEqual(self.client.post("/api/auth/password/check-email", json=self.email).status_code, 200)
        code = self.send()
        with Session(self.engine) as db:
            self.assertNotEqual(db.scalar(select(PasswordReset)).code_hash, code)
        response = self.verify(code)
        self.assertEqual(response.status_code, 200)
        token = response.json()["reset_token"]
        self.assertEqual(self.verify(code).status_code, 400)
        self.assertEqual(self.client.post("/api/auth/password/reset", json=self.reset_payload(token)).status_code, 200)
        self.assertEqual(self.client.post("/api/auth/password/reset", json=self.reset_payload(token)).status_code, 400)
        self.assertEqual(self.client.post("/api/auth/login", json=credentials).status_code, 401)
        self.assertEqual(self.client.post("/api/auth/login", json={**credentials, "password": "New-pass123!"}).status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {access}"}).status_code, 401)

    def test_missing_email_and_failed_delivery(self):
        for endpoint in ("check-email", "request-code"):
            self.assertEqual(self.client.post(f"/api/auth/password/{endpoint}", json={"email": "missing@example.com"}).status_code, 404)
        self.mail.side_effect = EmailDeliveryError("메일 발송 실패")
        self.assertEqual(self.client.post("/api/auth/password/request-code", json=self.email).status_code, 503)
        with Session(self.engine) as db:
            self.assertIsNone(db.scalar(select(PasswordReset)))

    def test_attempt_limit_expiry_and_resend(self):
        code = self.send()
        self.assertEqual(self.client.post("/api/auth/password/request-code", json=self.email).status_code, 429)
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(5):
            self.assertEqual(self.verify(wrong).status_code, 400)
        self.assertEqual(self.verify(code).status_code, 400)
        with Session(self.engine) as db:
            row = db.scalar(select(PasswordReset))
            self.assertEqual(row.attempts, 5)
            row.sent_at = utc_now() - timedelta(seconds=61)
            db.commit()
        code = self.send()
        with Session(self.engine) as db:
            db.scalar(select(PasswordReset)).code_expires_at = utc_now() - timedelta(seconds=1)
            db.commit()
        self.assertEqual(self.verify(code).status_code, 400)

    def test_invalid_password_does_not_consume_permission_and_expired_token(self):
        token = self.verify(self.send()).json()["reset_token"]
        payload = self.reset_payload(token)
        for changes in ({"confirm_password": "Different123!"}, {"new_password": "abcdefgh", "confirm_password": "abcdefgh"},
                        {"new_password": "Long-password123456!", "confirm_password": "Long-password123456!"}):
            self.assertEqual(self.client.post("/api/auth/password/reset", json={**payload, **changes}).status_code, 422)
        self.assertEqual(self.client.post("/api/auth/password/reset", json=self.reset_payload("fake-token")).status_code, 400)
        with Session(self.engine) as db:
            row = db.scalar(select(PasswordReset))
            self.assertIsNone(row.used_at)
            row.reset_expires_at = utc_now() - timedelta(seconds=1)
            db.commit()
        self.assertEqual(self.client.post("/api/auth/password/reset", json=payload).status_code, 400)

    def test_resend_invalidates_previous_reset_token(self):
        token = self.verify(self.send()).json()["reset_token"]
        with Session(self.engine) as db:
            db.scalar(select(PasswordReset)).sent_at = utc_now() - timedelta(seconds=61)
            db.commit()
        self.send()
        self.assertEqual(self.client.post("/api/auth/password/reset", json=self.reset_payload(token)).status_code, 400)
