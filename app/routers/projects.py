"""Swagger에서 프로젝트 생성 및 조회를 제공합니다."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.user import User
from app.routers.auth import current_user as get_current_user
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate
from app.services import project_service

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED, summary="프로젝트 생성")
def create_project(request: ProjectCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if request.owner_id is not None and request.owner_id != user.id:
        raise HTTPException(status_code=403, detail="다른 회원의 프로젝트를 생성할 수 없습니다.")
    return project_service.create_project(db, request, user.id)


@router.get("", response_model=list[ProjectResponse], summary="내 프로젝트 목록 조회")
def list_projects(
    limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0),
    project_status: Literal["active", "archived", "all"] = Query(default="active", description="active: 활성, archived: 보관, all: 전체"),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    return project_service.list_projects(db, user.id, limit, offset, project_status)


@router.get("/{project_id}", response_model=ProjectResponse, summary="내 프로젝트 상세 조회")
def get_project(
    project_id: int = Path(gt=0), db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    project = project_service.get_project(db, project_id, user.id)
    if project is None:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")
    return project


@router.patch("/{project_id}", response_model=ProjectResponse, summary="프로젝트 수정")
def update_project(
    request: ProjectUpdate, project_id: int = Path(gt=0),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    project = project_service.update_project(db, project_id, user.id, request)
    if project is None:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response,
               summary="프로젝트 영구 삭제", description="본인 소유 프로젝트를 DB에서 영구 삭제합니다. 보관과 달리 복원할 수 없습니다.")
def delete_project(
    project_id: int = Path(gt=0), db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    if not project_service.delete_project(db, project_id, user.id):
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{project_id}/archive", response_model=ProjectResponse, summary="프로젝트 보관")
def archive_project(
    project_id: int = Path(gt=0), db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    project = project_service.set_project_status(db, project_id, user.id, "archived")
    if project is None:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")
    return project


@router.patch("/{project_id}/restore", response_model=ProjectResponse, summary="프로젝트 보관 해제")
def restore_project(
    project_id: int = Path(gt=0), db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    project = project_service.set_project_status(db, project_id, user.id, "active")
    if project is None:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")
    return project
