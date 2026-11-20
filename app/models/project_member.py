"""Explicit MOEUM project access, independent of Notion workspace membership."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, text
from sqlalchemy.dialects.mysql import BIGINT
from app.database.database import Base


class ProjectMember(Base):
    __tablename__ = "project_members"

    project_id = Column(BIGINT(unsigned=True).with_variant(Integer, "sqlite"),
                        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(BIGINT(unsigned=True).with_variant(Integer, "sqlite"),
                     ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
