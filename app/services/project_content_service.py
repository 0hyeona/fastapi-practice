"""Ownership checks and persistence shared by project content APIs."""
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from app.models.project import Project
from app.models.story import Story


def validate_story(db, project_id, story_id):
    if story_id is not None:
        story = db.scalar(select(Story).where(Story.id == story_id, Story.project_id == project_id).with_for_update())
        if story is None:
            raise HTTPException(404, "Story not found in this project.")


def require_project(db, project_id, owner_id):
    project = db.scalar(select(Project).where(Project.id == project_id, Project.owner_id == owner_id))
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


def save(db, record):
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    if record is not None:
        db.refresh(record)
    return record


def values(request, exclude_unset=True):
    data = request.model_dump(exclude_unset=exclude_unset)
    if data.get("source_url") is not None:
        data["source_url"] = str(data["source_url"])
    return data


def create(db, model, request, owner_id):
    require_project(db, request.project_id, owner_id)
    validate_story(db, request.project_id, getattr(request, "story_id", None))
    record = model(**values(request, exclude_unset=False))
    db.add(record)
    return save(db, record)


def get(db, model, record_id, owner_id):
    record = db.scalar(select(model).join(Project, model.project_id == Project.id).where(
        model.id == record_id, Project.owner_id == owner_id))
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found.")
    return record


def list_records(db, model, owner_id, project_id, limit, offset, order_column, **filters):
    query = select(model).join(Project, model.project_id == Project.id).where(Project.owner_id == owner_id)
    if project_id is not None:
        require_project(db, project_id, owner_id)
        query = query.where(model.project_id == project_id)
    for field, value in filters.items():
        if value is not None:
            if field == "unorganized":
                query = query.where(model.story_id.is_(None) if value else model.story_id.is_not(None))
            else:
                query = query.where(getattr(model, field) == value)
    return db.scalars(query.order_by(order_column.desc(), model.id.desc()).limit(limit).offset(offset)).all()


def update(db, model, record_id, owner_id, request):
    record = get(db, model, record_id, owner_id)
    if "story_id" in request.model_fields_set:
        validate_story(db, record.project_id, request.story_id)
    if getattr(record, "external_id", None) and "source" in request.model_fields_set and request.source != record.source:
        raise HTTPException(422, "An imported activity's source cannot be changed.")
    for field, value in values(request).items():
        setattr(record, field, value)
    if hasattr(model, "updated_at"):
        record.updated_at = func.current_timestamp()
    return save(db, record)


def delete(db, model, record_id, owner_id):
    db.delete(get(db, model, record_id, owner_id))
    save(db, None)
