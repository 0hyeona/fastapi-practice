"""Explicit, idempotent GitHub import. GET routes never write activities."""
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select
from app.models.project import Project
from app.models.project_activity import ProjectActivity
from app.services.project_github import GitHubClient, repository_name


def sync_commits(db, project, branch, page, per_page):
    repository = repository_name(project.github_url)
    github = GitHubClient(repository, project.owner_id)
    params = {"page": page, "per_page": per_page}
    if branch:
        params["sha"] = branch
    items, has_next = github.get("/commits", params, empty_list=True)
    created = 0
    try:
        # Serialize imports per project, including concurrent requests and branches.
        locked = db.scalar(select(Project).where(Project.id == project.id).with_for_update().execution_options(populate_existing=True))
        if locked is None or repository_name(locked.github_url) != repository:
            raise HTTPException(409, "Repository changed. Retry synchronization.")
        existing = set(db.scalars(select(ProjectActivity.external_id).where(
            ProjectActivity.project_id == project.id, ProjectActivity.source == "github"
        ).with_for_update()).all())
        for item in items:
            external_id = repository.lower() + ":" + item["sha"]
            if external_id in existing or item["sha"] in existing:
                continue
            commit = item["commit"]
            date = (commit.get("committer") or {}).get("date") or (commit.get("author") or {}).get("date")
            if not date:
                raise HTTPException(502, "GitHub commit date is missing.")
            message = commit["message"]
            db.add(ProjectActivity(project_id=project.id, source="github", activity_type="commit",
                external_id=external_id, branch_name=branch, title=(message.splitlines() or ["Commit"])[0][:200] or "Commit",
                description=message, source_url=item["html_url"],
                occurred_at=datetime.fromisoformat(date.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)))
            existing.add(external_id)
            created += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"fetched": len(items), "created": created, "existing": len(items)-created,
            "page": page, "per_page": per_page, "has_next": has_next}
