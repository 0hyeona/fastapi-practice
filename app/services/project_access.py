"""Owners manage projects; explicitly added members read and refresh Notion."""
from fastapi import HTTPException
from sqlalchemy import exists, or_, select
from app.models.project import Project
from app.models.project_member import ProjectMember


def readable_by(user_id):
    return or_(Project.owner_id == user_id, exists().where(
        ProjectMember.project_id == Project.id, ProjectMember.user_id == user_id))


def get_accessible_project(db, project_id, user_id):
    return db.scalar(select(Project).where(Project.id == project_id, readable_by(user_id)))


def require_accessible_project(db, project_id, user_id):
    project = get_accessible_project(db, project_id, user_id)
    if project is None:
        raise HTTPException(404, "Project not found.")
    return project
