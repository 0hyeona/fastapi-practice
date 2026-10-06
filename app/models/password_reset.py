"""회원별 최신 이메일 인증 및 일회성 비밀번호 재설정 권한."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.mysql import BIGINT
from app.database.database import Base


class PasswordReset(Base):
    __tablename__ = "password_resets"

    user_id = Column(BIGINT(unsigned=True).with_variant(Integer, "sqlite"), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    code_hash = Column(String(255), nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    sent_at = Column(DateTime, nullable=False)
    code_expires_at = Column(DateTime, nullable=False)
    reset_token_hash = Column(String(64), nullable=True, unique=True)
    reset_expires_at = Column(DateTime, nullable=True)
    used_at = Column(DateTime, nullable=True)
