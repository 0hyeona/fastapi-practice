"""python -m scripts.setup_password_db: 기존 회원을 유지하며 재설정 테이블 추가."""
from app.database.database import engine
from app.models.user import User
from app.models.password_reset import PasswordReset


if __name__ == "__main__":
    PasswordReset.__table__.create(engine, checkfirst=True)
    print("Password reset database setup complete.")
