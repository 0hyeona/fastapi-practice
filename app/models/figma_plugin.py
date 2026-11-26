"""Project-scoped editor sessions and the last complete editor snapshot."""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.dialects.mysql import BIGINT

from app.database.database import Base


class FigmaPluginConnection(Base):
    __tablename__ = 'figma_plugin_connections'

    project_id = Column(BIGINT(unsigned=True).with_variant(Integer, 'sqlite'),
                        ForeignKey('projects.id', ondelete='CASCADE'), primary_key=True)
    user_id = Column(BIGINT(unsigned=True).with_variant(Integer, 'sqlite'),
                     ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    resource_id = Column(String(128), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    pairing_hash = Column(String(64), nullable=True, unique=True)
    pairing_expires_at = Column(DateTime, nullable=True)
    token_hash = Column(String(64), nullable=True, unique=True)
    expires_at = Column(DateTime, nullable=True)
    last_sequence = Column(Integer, nullable=False, default=0)
    last_received_at = Column(DateTime, nullable=True)
    last_seen_at = Column(DateTime, nullable=True)
    collection_state = Column(String(24), nullable=True)


class ProjectFigmaSnapshot(Base):
    __tablename__ = 'project_figma_snapshots'

    project_id = Column(BIGINT(unsigned=True).with_variant(Integer, 'sqlite'),
                        ForeignKey('projects.id', ondelete='CASCADE'), primary_key=True)
    resource_id = Column(String(128), nullable=False)
    revision = Column(Integer, nullable=False)
    fingerprint = Column(String(64), nullable=False)
    content = Column(JSON, nullable=False)
    received_at = Column(DateTime, nullable=False)
