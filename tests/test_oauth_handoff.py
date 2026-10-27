import unittest
from datetime import timedelta
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.database.database import Base
from app.models.user import User
from app.models.auth_session import AuthSession
from app.services.auth_service import create_login_session, authenticated_session, InvalidCredentialsError, utc_now
from app.services.oauth_handoff import create_handoff, exchange_handoff, handoff_hash


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.user = User(user_id="test", name="Test", email="test@example.com",
                         password_hash="unused", account_status="active")
        self.db.add(self.user)
        self.db.commit()
        self.session = create_login_session(self.db, self.user)
        self.code = create_handoff(self.db, self.session)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_exchange_rotates_token_and_rejects_replay(self):
        result = exchange_handoff(self.db, self.code)
        self.assertNotEqual(result.access_token, self.session.access_token)
        self.assertEqual(authenticated_session(self.db, result.access_token)[1].id, self.user.id)
        with self.assertRaises(InvalidCredentialsError):
            exchange_handoff(self.db, self.code)

    def test_pending_code_and_old_token_cannot_authenticate(self):
        for value in (self.code, self.session.access_token, "oauth:" + self.code):
            with self.assertRaises(InvalidCredentialsError):
                authenticated_session(self.db, value)
        stored = self.db.scalar(select(AuthSession)).token_hash
        self.assertEqual(stored, handoff_hash(self.code))
        self.assertEqual(len(stored), 64)
        self.assertNotIn(self.code, stored)

    def test_expired_code_rejected(self):
        self.db.scalar(select(AuthSession)).expires_at = utc_now() - timedelta(seconds=1)
        self.db.commit()
        with self.assertRaises(InvalidCredentialsError):
            exchange_handoff(self.db, self.code)

    def test_wrong_code_does_not_consume_valid_code(self):
        with self.assertRaises(InvalidCredentialsError):
            exchange_handoff(self.db, "x" * 43)
        self.assertEqual(exchange_handoff(self.db, self.code).user.id, self.user.id)

    def test_inactive_user_cannot_exchange(self):
        self.user.account_status = "inactive"
        self.db.commit()
        with self.assertRaises(InvalidCredentialsError):
            exchange_handoff(self.db, self.code)
