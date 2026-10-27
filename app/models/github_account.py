"""변경되지 않는 GitHub 숫자 ID와 서비스 회원을 연결합니다."""

from sqlalchemy import Column, ForeignKey, Integer
from sqlalchemy.dialects.mysql import BIGINT

from app.database.database import Base


class GithubAccount(Base):
    __tablename__ = "github_accounts"

    github_id = Column(BIGINT(unsigned=True).with_variant(Integer, "sqlite"), primary_key=True)
    user_id = Column(BIGINT(unsigned=True).with_variant(Integer, "sqlite"),
                     ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
