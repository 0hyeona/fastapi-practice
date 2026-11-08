"""Last fully collected Notion page, committed together with its changes."""
from sqlalchemy import Column, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.dialects.mysql import BIGINT
from app.database.database import Base


class ProjectNotionSnapshot(Base):
    __tablename__ = "project_notion_snapshots"
    __table_args__ = (UniqueConstraint("project_id", "resource_id", name="uq_notion_snapshot_page"),)

    id = Column(BIGINT(unsigned=True).with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    project_id = Column(BIGINT(unsigned=True).with_variant(Integer, "sqlite"),
                        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    resource_id = Column(String(32), nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    content = Column(JSON, nullable=False)
