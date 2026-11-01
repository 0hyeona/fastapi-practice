"""Owner-scoped collection history; contains no credentials or upstream errors."""
from datetime import datetime
from typing import Literal
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.models.project_sync_run import ProjectSyncRun
from app.routers.project_github import owned_project

Source = Literal["github", "figma", "notion"]
Status = Literal["running", "success", "failed"]
router = APIRouter(prefix="/api/projects", tags=["project-sync-runs"])


class SyncRun(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    source: Source
    status: Status
    started_at: datetime
    finished_at: datetime | None
    fetched: int
    created: int
    existing: int
    error_code: int | None
    error_message: str | None


@router.get("/{project_id}/sync-runs", response_model=list[SyncRun])
def list_runs(source: Source | None = None, status: Status | None = None,
              limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
              project=Depends(owned_project), db: Session = Depends(get_db)):
    query = select(ProjectSyncRun).where(ProjectSyncRun.project_id == project.id)
    if source:
        query = query.where(ProjectSyncRun.source == source)
    if status:
        query = query.where(ProjectSyncRun.status == status)
    return db.scalars(query.order_by(ProjectSyncRun.started_at.desc(), ProjectSyncRun.id.desc()).limit(limit).offset(offset)).all()
