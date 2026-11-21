"""One encrypted Figma OAuth connection per MOEUM user."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.mysql import BIGINT
from app.database.database import Base

class FigmaAccount(Base):
    __tablename__ = 'figma_accounts'

    user_id = Column(BIGINT(unsigned=True).with_variant(Integer, 'sqlite'),
                     ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    figma_user_id = Column(String(128), nullable=False)
    credentials = Column(Text, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
