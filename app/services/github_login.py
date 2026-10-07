"""GitHub 회원을 생성하거나 찾아 서비스 로그인 세션을 발급합니다."""

import secrets

from fastapi import HTTPException
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.github_account import GithubAccount
from app.models.user import User
from app.schemas.auth import LoginResponse
from app.services.auth_service import create_login_session, password_hasher


def find_github_member(db: Session, github_id: int) -> User | None:
    return db.scalar(select(User).join(GithubAccount, GithubAccount.user_id == User.id)
                     .where(GithubAccount.github_id == github_id))


def github_login_session(db: Session, profile: dict, test_email: str | None = None) -> LoginResponse:
    github_id = profile["id"]
    try:
        user = find_github_member(db, github_id)
        if user is None:
            try:
                email = str(TypeAdapter(EmailStr).validate_python(profile.get("email")))
            except ValidationError as exc:
                raise HTTPException(400, "GitHub에서 인증된 이메일을 확인할 수 없습니다.") from exc
            if len(email) > 255:
                raise HTTPException(400, "GitHub 이메일이 너무 깁니다.")
            if db.scalar(select(User.id).where(User.email == email)) is not None:
                if not test_email:
                    raise HTTPException(409, "이미 가입된 이메일입니다. 기존 계정으로 로그인하세요. GitHub 계정 자동 연결은 지원하지 않습니다.")
                try:
                    email = str(TypeAdapter(EmailStr).validate_python(test_email))
                except ValidationError as exc:
                    raise HTTPException(503, "GitHub 테스트 이메일 설정이 올바르지 않습니다.") from exc
                if len(email) > 255 or db.scalar(select(User.id).where(User.email == email)) is not None:
                    raise HTTPException(409, "GitHub 테스트 이메일이 이미 사용 중이거나 너무 깁니다.")
            user = User(
                user_id=f"github_{github_id}_{secrets.token_hex(4)}",
                name=(profile.get("name") or profile["login"]).strip()[:50] or profile["login"][:50],
                email=email,
                # 기존 NOT NULL 스키마를 유지하며 알 수 없는 무작위 비밀번호의 해시만 저장합니다.
                password_hash=password_hasher.hash(secrets.token_urlsafe(48)),
                account_status="active",
            )
            db.add(user)
            db.flush()
            db.add(GithubAccount(github_id=github_id, user_id=user.id))
            db.flush()
        return create_login_session(db, user)
    except IntegrityError as exc:
        db.rollback()
        # 동시에 같은 GitHub 계정이 가입한 경우 먼저 저장된 회원으로 로그인합니다.
        user = find_github_member(db, github_id)
        if user is not None:
            return create_login_session(db, user)
        raise HTTPException(409, "회원 정보가 이미 사용 중입니다. 기존 계정으로 로그인하세요.") from exc
    except Exception:
        db.rollback()
        raise
