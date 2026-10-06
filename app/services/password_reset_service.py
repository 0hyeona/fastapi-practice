import secrets
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.auth_session import AuthSession
from app.models.password_reset import PasswordReset
from app.models.user import User
from app.schemas.password_reset import ResetRequest
from app.services.auth_service import hash_token, password_hasher, utc_now
from app.services.email_service import EmailDeliveryError, send_reset_code

CODE_SECONDS = 600
RESET_SECONDS = 600
MAX_ATTEMPTS = 5


class ResetError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


def find_user(db: Session, email: str, lock=False) -> User:
    query = select(User).where(User.email == email, User.account_status == "active")
    user = db.scalar(query.with_for_update() if lock else query)
    if user is None:
        raise ResetError(404, "등록되지 않은 이메일 주소입니다. 다시 확인해주세요.")
    return user


def request_code(db: Session, email: str) -> None:
    try:
        user = find_user(db, email, lock=True)
        row = db.get(PasswordReset, user.id)
        now = utc_now()
        if row and (now - row.sent_at).total_seconds() < 60:
            raise ResetError(429, "인증번호 재발송은 60초 후에 가능합니다.")
        code = f"{secrets.randbelow(1000000):06d}"
        if row is None:
            row = PasswordReset(user_id=user.id)
            db.add(row)
        row.code_hash = password_hasher.hash(code)
        row.attempts = 0
        row.sent_at = now
        row.code_expires_at = now + timedelta(seconds=CODE_SECONDS)
        row.reset_token_hash = None
        row.reset_expires_at = None
        row.used_at = None
        db.flush()
        send_reset_code(email, code)
        db.commit()
    except EmailDeliveryError as exc:
        db.rollback()
        raise ResetError(503, str(exc)) from exc
    except Exception:
        db.rollback()
        raise


def verify_code(db: Session, email: str, code: str) -> str:
    try:
        user = find_user(db, email, lock=True)
        row = db.get(PasswordReset, user.id)
        now = utc_now()
        if (not row or row.used_at or row.reset_token_hash or row.code_expires_at <= now
                or row.attempts >= MAX_ATTEMPTS):
            raise ResetError(400, "인증번호가 일치하지 않거나 유효시간이 만료되었습니다.")
        if not password_hasher.verify(code, row.code_hash):
            row.attempts += 1
            db.commit()  # 실패 횟수는 이후 오류 응답에도 유지합니다.
            raise ResetError(400, "인증번호가 일치하지 않거나 유효시간이 만료되었습니다.")
        token = secrets.token_urlsafe(32)
        row.reset_token_hash = hash_token(token)
        row.reset_expires_at = now + timedelta(seconds=RESET_SECONDS)
        db.commit()
        return token
    except Exception:
        db.rollback()
        raise


def reset_password(db: Session, request: ResetRequest) -> None:
    try:
        token_hash = hash_token(request.reset_token.get_secret_value())
        # 발송/검증과 동일하게 회원부터 잠가 동시 요청을 직렬화합니다.
        user_id = db.scalar(select(PasswordReset.user_id).where(PasswordReset.reset_token_hash == token_hash))
        user = db.scalar(select(User).where(User.id == user_id).with_for_update()) if user_id else None
        row = db.scalar(select(PasswordReset).where(PasswordReset.user_id == user_id).with_for_update()) if user else None
        now = utc_now()
        if (not user or user.account_status != "active" or not row or row.used_at
                or row.reset_token_hash != token_hash or not row.reset_expires_at or row.reset_expires_at <= now):
            raise ResetError(400, "비밀번호 재설정 권한이 없거나 만료되었습니다. 이메일 인증을 다시 진행해주세요.")
        user.password_hash = password_hasher.hash(request.new_password.get_secret_value())
        row.used_at = now
        db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
        db.commit()
    except Exception:
        db.rollback()
        raise
