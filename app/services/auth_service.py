"""중복 확인, 비밀번호 해싱, 회원 정보 저장을 담당합니다."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.auth_session import AuthSession
from app.schemas.auth import LoginRequest, LoginResponse, SignupRequest, SignupResponse

password_hasher = PasswordHash.recommended()
SESSION_SECONDS = 3600
DUMMY_PASSWORD_HASH = password_hasher.hash(secrets.token_urlsafe(32))


class InvalidCredentialsError(Exception):
    """이메일, 비밀번호 또는 계정 상태가 유효하지 않습니다."""


def utc_now() -> datetime:
    # MySQL DATETIME에는 시간대 없이 UTC로 저장합니다.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def login(db: Session, request: LoginRequest) -> LoginResponse:
    user = db.scalar(select(User).where(User.email == str(request.email)))
    try:
        valid = password_hasher.verify(
            request.password.get_secret_value(),
            user.password_hash if user and user.password_hash else DUMMY_PASSWORD_HASH,
        )
    except UnknownHashError:
        valid = False
    if not user or not user.password_hash or not valid or user.account_status != "active":
        raise InvalidCredentialsError("이메일 또는 비밀번호가 올바르지 않습니다.")

    token = secrets.token_urlsafe(32)
    now = utc_now()
    db.add(AuthSession(user_id=user.id, token_hash=hash_token(token), created_at=now,
                       expires_at=now + timedelta(seconds=SESSION_SECONDS)))
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    return LoginResponse(access_token=token, expires_in=SESSION_SECONDS,
                         user=SignupResponse.model_validate(user))


def authenticated_session(db: Session, token: str) -> tuple[AuthSession, User]:
    row = db.execute(select(AuthSession, User).join(User, AuthSession.user_id == User.id).where(
        AuthSession.token_hash == hash_token(token), AuthSession.expires_at > utc_now(),
        User.account_status == "active",
    )).first()
    if row is None:
        raise InvalidCredentialsError("유효하지 않거나 만료된 로그인입니다.")
    return row[0], row[1]


def logout(db: Session, session: AuthSession) -> None:
    db.delete(session)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


class DuplicateUserError(Exception):
    """아이디 또는 이메일이 이미 사용 중일 때 발생합니다."""


def check_duplicates(db: Session, user_id: str, email: str) -> None:
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise DuplicateUserError("이미 사용 중인 이메일입니다.")
    if db.scalar(select(User.id).where(User.user_id == user_id)) is not None:
        raise DuplicateUserError("이미 사용 중인 아이디입니다.")


def signup(db: Session, request: SignupRequest) -> User:
    email = str(request.email)
    check_duplicates(db, request.user_id, email)

    user = User(
        user_id=request.user_id,
        name=request.name,
        email=email,
        password_hash=password_hasher.hash(request.password.get_secret_value()),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # 첫 중복 검사 이후 다른 요청이 먼저 가입한 경우도 처리합니다.
        if getattr(exc.orig, "args", (None,))[0] == 1062 or getattr(exc.orig, "sqlite_errorname", "") == "SQLITE_CONSTRAINT_UNIQUE":
            raise DuplicateUserError("이미 사용 중인 아이디 또는 이메일입니다.") from exc
        raise
    except SQLAlchemyError:
        db.rollback()
        raise

    db.refresh(user)
    return user
