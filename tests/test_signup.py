"""실제 MySQL 데이터 대신 임시 DB로 회원가입을 검증합니다."""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database.database import Base, get_db
from app.main import app
from app.models.user import User
from app.services.auth_service import password_hasher


class SignupTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(self.engine)

        def test_db():
            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[get_db] = test_db
        self.client = TestClient(app)
        self.payload = {
            "user_id": "testuser", "name": "테스트 회원",
            "email": "testuser@example.com", "password": "test-password-123",
        }

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.pop(get_db, None)
        self.engine.dispose()

    def test_signup_stores_hash_and_returns_safe_response(self):
        response = self.client.post("/api/auth/signup", json=self.payload)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["account_status"], "active")
        self.assertNotIn("password", response.json())
        self.assertNotIn("password_hash", response.json())
        with Session(self.engine) as db:
            user = db.scalar(select(User))
            self.assertNotEqual(user.password_hash, self.payload["password"])
            self.assertTrue(password_hasher.verify(self.payload["password"], user.password_hash))

    def test_duplicate_email(self):
        self.client.post("/api/auth/signup", json=self.payload)
        response = self.client.post("/api/auth/signup", json={**self.payload, "user_id": "another"})
        self.assertEqual(response.status_code, 409)
        self.assertIn("이메일", response.json()["detail"])

    def test_duplicate_user_id(self):
        self.client.post("/api/auth/signup", json=self.payload)
        response = self.client.post("/api/auth/signup", json={**self.payload, "email": "another@example.com"})
        self.assertEqual(response.status_code, 409)
        self.assertIn("아이디", response.json()["detail"])

    def test_invalid_requests_do_not_create_users(self):
        for changes in (
            {"email": "invalid"}, {"password": "short"}, {"password": "x" * 129},
            {"user_id": "   "}, {"name": "   "}, {"user_id": "x" * 51},
        ):
            with self.subTest(changes=changes):
                response = self.client.post("/api/auth/signup", json={**self.payload, **changes})
                self.assertEqual(response.status_code, 422)
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(User)), 0)

    def test_database_duplicate_is_rolled_back(self):
        self.client.post("/api/auth/signup", json=self.payload)
        # 중복 검사 직후 다른 가입 요청이 저장한 상황을 재현합니다.
        with patch("app.services.auth_service.check_duplicates"):
            response = self.client.post("/api/auth/signup", json=self.payload)
        self.assertEqual(response.status_code, 409)
        response = self.client.post("/api/auth/signup", json={
            **self.payload, "user_id": "newuser", "email": "newuser@example.com",
        })
        self.assertEqual(response.status_code, 201)
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(User)), 2)


if __name__ == "__main__":
    unittest.main()
