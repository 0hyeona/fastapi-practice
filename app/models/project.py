"""기존 MySQL projects 테이블과 연결합니다."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.mysql import BIGINT

from app.database.database import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(BIGINT(unsigned=True).with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    owner_id = Column(
        BIGINT(unsigned=True).with_variant(Integer, "sqlite"),
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    project_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    github_url = Column(String(2048), nullable=True)
    figma_url = Column(String(2048), nullable=True)
    notion_url = Column(String(2048), nullable=True)
    project_status = Column(String(20), nullable=False, server_default=text("'active'"))
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"),
        server_onupdate=text("CURRENT_TIMESTAMP"),
    )
