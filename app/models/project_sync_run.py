"""One history row per collection API invocation (all timestamps UTC)."""
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.mysql import BIGINT
from app.database.database import Base


class ProjectSyncRun(Base):
    __tablename__ = "project_sync_runs"
    __table_args__ = (Index("ix_sync_runs_project_source_started", "project_id", "source", "started_at"),)
    id = Column(BIGINT(unsigned=True).with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    project_id = Column(BIGINT(unsigned=True).with_variant(Integer, "sqlite"), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    source = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False)
    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    fetched = Column(Integer, nullable=False, default=0)
    created = Column(Integer, nullable=False, default=0)
    existing = Column(Integer, nullable=False, default=0)
    error_code = Column(Integer, nullable=True)
    error_message = Column(String(500), nullable=True)
