"""로그인 토큰의 해시와 만료 시간을 저장합니다."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.mysql import BIGINT

from app.database.database import Base


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id = Column(BIGINT(unsigned=True).with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    user_id = Column(BIGINT(unsigned=True).with_variant(Integer, "sqlite"), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True)
    created_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
