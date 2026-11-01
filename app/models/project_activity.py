"""Project-owned project_activities."""
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.mysql import BIGINT
from app.database.database import Base


class ProjectActivity(Base):
    __tablename__ = "project_activities"
    __table_args__ = (Index("ix_project_activities_project_created", "project_id", "created_at"),)

    id = Column(BIGINT(unsigned=True).with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    project_id = Column(BIGINT(unsigned=True).with_variant(Integer, "sqlite"), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    story_id = Column(BIGINT(unsigned=True).with_variant(Integer, "sqlite"), ForeignKey("stories.id", ondelete="SET NULL"), nullable=True)
    external_id = Column(String(255), nullable=True)
    branch_name = Column(String(255), nullable=True)
    source = Column(String(20), nullable=False)
    activity_type = Column(String(50), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    source_url = Column(String(2048), nullable=True)
    occurred_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
