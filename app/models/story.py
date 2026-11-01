"""Project-owned stories."""
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, text
from sqlalchemy.dialects.mysql import BIGINT
from app.database.database import Base


class Story(Base):
    __tablename__ = "stories"
    __table_args__ = (Index("ix_stories_project_created", "project_id", "created_at"),)

    id = Column(BIGINT(unsigned=True).with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    project_id = Column(BIGINT(unsigned=True).with_variant(Integer, "sqlite"), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    why = Column(Text, nullable=True)
    problem = Column(Text, nullable=True)
    solution = Column(Text, nullable=True)
    result = Column(Text, nullable=True)
    learned = Column(Text, nullable=True)
    next_steps = Column(Text, nullable=True)
    ai_analysis = Column(JSON(none_as_null=True), nullable=True)
    # API 필드 story_status를 실제 DB 컬럼 status에 연결합니다.
    story_status = Column("status", String(20), nullable=False, server_default=text("'draft'"))
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), server_onupdate=text("CURRENT_TIMESTAMP"))
