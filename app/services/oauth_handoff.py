"""Single-use OAuth handoff using the existing auth_sessions table."""
import secrets
from datetime import timedelta
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from app.models.auth_session import AuthSession
from app.models.user import User
from app.schemas.auth import LoginResponse, SignupResponse
from app.services.auth_service import SESSION_SECONDS, InvalidCredentialsError, hash_token, utc_now

HANDOFF_SECONDS = 60


def handoff_hash(code: str) -> str:
    # Non-hex namespace: a pending code can never match a normal Bearer SHA256.
    # Fits the existing VARCHAR(64); retains 232 bits of the digest.
    return "oauth:" + hash_token(code)[:58]


def create_handoff(db: Session, session: LoginResponse) -> str:
    code = secrets.token_urlsafe(32)
    try:
        result = db.execute(update(AuthSession).where(
            AuthSession.token_hash == hash_token(session.access_token)
        ).values(token_hash=handoff_hash(code), expires_at=utc_now() + timedelta(seconds=HANDOFF_SECONDS)))
        if result.rowcount != 1:
            raise InvalidCredentialsError("로그인 세션을 찾을 수 없습니다.")
        db.commit()
    except Exception:
        db.rollback()
        raise
    return code


def exchange_handoff(db: Session, code: str) -> LoginResponse:
    now = utc_now()
    pending_hash = handoff_hash(code)
    try:
        row = db.execute(select(AuthSession, User).join(User, AuthSession.user_id == User.id).where(
            AuthSession.token_hash == pending_hash, AuthSession.expires_at > now,
            User.account_status == "active",
        )).first()
        if row is None:
            raise InvalidCredentialsError("로그인 코드가 만료되었거나 이미 사용되었습니다. 다시 로그인해 주세요.")
        session, user = row
        token = secrets.token_urlsafe(32)
        response = LoginResponse(access_token=token, expires_in=SESSION_SECONDS,
                                 user=SignupResponse.model_validate(user))
        # Compare-and-swap makes two concurrent exchanges yield at most one token.
        result = db.execute(update(AuthSession).where(
            AuthSession.id == session.id, AuthSession.token_hash == pending_hash,
            AuthSession.expires_at > now,
        ).values(token_hash=hash_token(token), created_at=now,
                 expires_at=now + timedelta(seconds=SESSION_SECONDS)))
        if result.rowcount != 1:
            raise InvalidCredentialsError("이미 사용된 로그인 코드입니다. 다시 로그인해 주세요.")
        db.commit()
        return response
    except Exception:
        db.rollback()
        raise
