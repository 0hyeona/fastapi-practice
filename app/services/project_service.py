"""로그인한 회원의 프로젝트를 저장하고 조회합니다."""

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectUpdate


def create_project(db: Session, request: ProjectCreate, owner_id: int) -> Project:
    project = Project(
        owner_id=owner_id, project_name=request.project_name, description=request.description,
        github_url=str(request.github_url) if request.github_url is not None else None,
        figma_url=str(request.figma_url) if request.figma_url is not None else None,
        notion_url=str(request.notion_url) if request.notion_url is not None else None,
    )
    db.add(project)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    db.refresh(project)
    return project


def list_projects(db: Session, owner_id: int, limit: int, offset: int, project_status: str = "active"):
    query = select(Project).where(Project.owner_id == owner_id)
    if project_status != "all":
        query = query.where(Project.project_status == project_status)
    return db.scalars(
        query.order_by(Project.id.desc()).limit(limit).offset(offset)
    ).all()


def get_project(db: Session, project_id: int, owner_id: int) -> Project | None:
    return db.scalar(select(Project).where(Project.id == project_id, Project.owner_id == owner_id))


def set_project_status(db: Session, project_id: int, owner_id: int, project_status: str) -> Project | None:
    project = db.scalar(select(Project).where(
        Project.id == project_id, Project.owner_id == owner_id,
    ).with_for_update())
    if project is None or project.project_status == project_status:
        return project
    project.project_status = project_status
    project.updated_at = func.current_timestamp()
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    db.refresh(project)
    return project


def update_project(db: Session, project_id: int, owner_id: int, request: ProjectUpdate) -> Project | None:
    project = db.scalar(select(Project).where(
        Project.id == project_id, Project.owner_id == owner_id,
    ).with_for_update())
    if project is None:
        return None
    changes = request.model_dump(mode="json", exclude_unset=True)
    if all(getattr(project, field) == value for field, value in changes.items()):
        return project
    for field, value in changes.items():
        setattr(project, field, value)
    project.updated_at = func.current_timestamp()
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    db.refresh(project)
    return project


def delete_project(db: Session, project_id: int, owner_id: int) -> bool:
    project = db.scalar(select(Project).where(
        Project.id == project_id, Project.owner_id == owner_id,
    ).with_for_update())
    if project is None:
        return False
    db.delete(project)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    return True
