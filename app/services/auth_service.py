"""중복 확인, 비밀번호 해싱, 회원 정보 저장을 담당합니다."""

from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.auth import SignupRequest

password_hasher = PasswordHash.recommended()


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
