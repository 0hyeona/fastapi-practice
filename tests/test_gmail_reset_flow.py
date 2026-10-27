"""HTTP 테스트 클라이언트 없이 실제 DB 처리와 Gmail 발송 연동을 검증합니다."""

import base64
import os
import unittest
from email import policy
from email.parser import BytesParser
from unittest.mock import patch

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.database import Base
from app.models.user import User
from app.models.password_reset import PasswordReset
from app.schemas.password_reset import ResetRequest
from app.services.auth_service import password_hasher
from app.services.password_reset_service import request_code, verify_code, reset_password, ResetError


class GmailResetFlowTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.user = User(user_id="gmail-test", name="Test", email="recipient@example.com",
                         password_hash=password_hasher.hash("Old-pass123!"))
        self.db.add(self.user)
        self.db.commit()
        self.env = patch.dict(os.environ, {
            "GMAIL_CLIENT_ID": "test", "GMAIL_CLIENT_SECRET": "secret",
            "GMAIL_REFRESH_TOKEN": "refresh", "GMAIL_FROM_EMAIL": "sender@gmail.com",
        })
        self.env.start()
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        self.addCleanup(self.env.stop)

    def response(self, status, body):
        return httpx.Response(status, json=body,
                              request=httpx.Request("POST", "https://gmail.googleapis.com/"))

    def test_gmail_message_code_verifies_and_resets_password_once(self):
        with patch("app.services.email_service.httpx.Client") as factory:
            client = factory.return_value.__enter__.return_value
            client.post.side_effect = [self.response(200, {"access_token": "access"}),
                                       self.response(200, {"id": "sent-id"})]
            request_code(self.db, self.user.email)
            raw = client.post.call_args.kwargs["json"]["raw"]
        message = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(raw))
        code = message.get_content().splitlines()[0].split(": ", 1)[1]
        self.assertEqual(message["To"], self.user.email)
        self.assertRegex(code, r"^[0-9]{6}$")
        row = self.db.scalar(select(PasswordReset))
        self.assertNotEqual(row.code_hash, code)
        token = verify_code(self.db, self.user.email, code)
        payload = ResetRequest(reset_token=token, new_password="New-pass123!",
                               confirm_password="New-pass123!")
        reset_password(self.db, payload)
        self.db.refresh(self.user)
        self.assertTrue(password_hasher.verify("New-pass123!", self.user.password_hash))
        with self.assertRaises(ResetError):
            reset_password(self.db, payload)

    def test_google_rejection_rolls_back_and_allows_retry(self):
        with patch("app.services.email_service.httpx.Client") as factory:
            client = factory.return_value.__enter__.return_value
            client.post.return_value = self.response(400, {"error": "invalid_grant"})
            with self.assertRaises(ResetError) as error:
                request_code(self.db, self.user.email)
            self.assertEqual(error.exception.status_code, 503)
            self.assertIsNone(self.db.scalar(select(PasswordReset)))
            client.post.side_effect = [self.response(200, {"access_token": "access"}),
                                       self.response(200, {"id": "sent-id"})]
            request_code(self.db, self.user.email)
            self.assertIsNotNone(self.db.scalar(select(PasswordReset)))
