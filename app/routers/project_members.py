"""Project sharing never exposes or copies the owner's OAuth credentials."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Path, Response
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.user import User
from app.routers.auth import current_user
from app.routers.project_github import accessible_project, owned_project

router = APIRouter(prefix="/api/projects", tags=["project-members"])


class MemberAdd(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr


class MemberResponse(BaseModel):
    user_id: int
    name: str
    email: str
    joined_at: datetime


class ProjectAccess(BaseModel):
    project_id: int
    role: str
    can_manage: bool
    can_sync_notion: bool
    notion_connection_owner_id: int


@router.get("/{project_id}/access", response_model=ProjectAccess)
def access(project=Depends(accessible_project), user: User = Depends(current_user)):
    return dict(project_id=project.id, role="owner" if project.owner_id == user.id else "member",
                can_manage=project.owner_id == user.id, can_sync_notion=True,
                notion_connection_owner_id=project.owner_id)


@router.get("/{project_id}/members", response_model=list[MemberResponse])
def members(project=Depends(owned_project), db: Session = Depends(get_db)):
    rows = db.execute(select(User, ProjectMember.created_at).join(
        ProjectMember, ProjectMember.user_id == User.id).where(
        ProjectMember.project_id == project.id).order_by(ProjectMember.user_id)).all()
    return [dict(user_id=user.id, name=user.name, email=user.email, joined_at=joined)
            for user, joined in rows]


@router.post("/{project_id}/members", response_model=MemberResponse,
             description="소유자만 기존 모음 회원을 이메일로 추가합니다. 추가된 회원은 프로젝트 전체 기록을 조회하고 소유자 연결로 Notion을 새로고침할 수 있습니다.")
def add_member(request: MemberAdd, project=Depends(owned_project), db: Session = Depends(get_db)):
    # Serialize membership changes for the same project, including duplicate adds.
    db.scalar(select(Project).where(Project.id == project.id).with_for_update())
    user = db.scalar(select(User).where(func.lower(User.email) == str(request.email).lower(),
                                        User.account_status == "active"))
    if user is None:
        raise HTTPException(404, "Active MOEUM account not found. Sign up first.")
    if user.id == project.owner_id:
        raise HTTPException(409, "The owner already has project access.")
    member = db.get(ProjectMember, (project.id, user.id))
    if member is None:
        member = ProjectMember(project_id=project.id, user_id=user.id)
        db.add(member)
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
        db.refresh(member)
    return dict(user_id=user.id, name=user.name, email=user.email, joined_at=member.created_at)


@router.delete("/{project_id}/members/{user_id}", status_code=204, response_class=Response)
def remove_member(user_id: int = Path(gt=0), project=Depends(owned_project), db: Session = Depends(get_db)):
    db.scalar(select(Project).where(Project.id == project.id).with_for_update())
    member = db.get(ProjectMember, (project.id, user_id))
    if member is None:
        raise HTTPException(404, "Project member not found.")
    db.delete(member)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return Response(status_code=204)
