"""One encrypted Notion OAuth connection per MOEUM user."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.mysql import BIGINT
from app.database.database import Base


class NotionAccount(Base):
    __tablename__ = 'user_notion_accounts'

    user_id = Column(BIGINT(unsigned=True).with_variant(Integer, 'sqlite'),
                     ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    workspace_id = Column(String(36), nullable=False)
    workspace_name = Column(String(255), nullable=True)
    credentials = Column(Text, nullable=False)
    updated_at = Column(DateTime, nullable=False)
