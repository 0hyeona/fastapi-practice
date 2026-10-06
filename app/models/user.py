"""MySQL의 users 테이블을 Python 클래스로 표현합니다."""

from sqlalchemy import Column, DateTime, Integer, String, text
from sqlalchemy.dialects.mysql import BIGINT

from app.database.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(BIGINT(unsigned=True).with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    user_id = Column(String(50), nullable=False, unique=True)
    name = Column(String(50), nullable=False)
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    account_status = Column(String(20), nullable=False, server_default=text("'active'"))
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
