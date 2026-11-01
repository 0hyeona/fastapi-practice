from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from app.models.project_activity import ProjectActivity
from app.models.story import Story
from app.schemas.project_activity import ProjectActivityResponse, Source
from app.schemas.story import StoryResponse, StoryStatus
from app.services import project_content_service as content
from app.services.github_sync import sync_commits
from app.schemas.project_github import SyncResult

from app.database.database import get_db
from app.models.user import User
from app.routers.auth import current_user
from app.schemas.project_github import BranchPage, CommitDetail, CommitPage, Dashboard
from app.services.project_service import get_project
from app.services.project_github import GitHubClient, commit_summary, repository_name

router = APIRouter(prefix="/api/projects", tags=["project-github"])


def owned_project(project_id: int = Path(gt=0), db: Session = Depends(get_db), user: User = Depends(current_user)):
    project = get_project(db, project_id, user.id)
    if project is None:
        raise HTTPException(404, "프로젝트를 찾을 수 없습니다.")
    return project


def github_client(project=Depends(owned_project)):
    return GitHubClient(repository_name(project.github_url), project.owner_id)


@router.get("/{project_id}/dashboard", response_model=Dashboard, summary="대시보드 요약")
def dashboard(project=Depends(owned_project), db: Session = Depends(get_db)):
    counts = {"github": 0, "figma": 0, "notion": 0}
    rows = db.execute(select(ProjectActivity.source, func.count()).where(
        ProjectActivity.project_id == project.id, ProjectActivity.story_id.is_(None)
    ).group_by(ProjectActivity.source)).all()
    counts.update({source: count for source, count in rows if source in counts})
    counts["total"] = sum(counts.values())
    result = {"project": project, "github": None, "recent_commits": [],
              "unorganized_counts": counts,
              "recent_stories": content.list_records(db, Story, project.owner_id, project.id, 3, 0, Story.created_at),
              "recent_activities": content.list_records(db, ProjectActivity, project.owner_id, project.id, 5, 0, ProjectActivity.occurred_at)}
    if not project.github_url:
        return result
    try:
        github = GitHubClient(repository_name(project.github_url), project.owner_id)
        repo, _ = github.get()
        commits, _ = github.get("/commits", {"per_page": 5, "page": 1}, empty_list=True)
        result.update(github={
            "full_name": repo["full_name"], "html_url": repo["html_url"],
            "default_branch": repo["default_branch"], "language": repo.get("language"),
            "stars": repo["stargazers_count"], "forks": repo["forks_count"],
            "open_issues_count": repo["open_issues_count"],
        }, recent_commits=[commit_summary(item) for item in commits])
    except HTTPException as error:
        result["github_error"] = str(error.detail)
    return result


@router.get("/{project_id}/activities", response_model=list[ProjectActivityResponse], summary="프로젝트 변경사항 조회")
def project_activities(project=Depends(owned_project), db: Session = Depends(get_db),
                       unorganized: bool | None = None, source: Source | None = None,
                       limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    return content.list_records(db, ProjectActivity, project.owner_id, project.id, limit, offset,
                                ProjectActivity.occurred_at, source=source, unorganized=unorganized)


@router.get("/{project_id}/stories", response_model=list[StoryResponse], summary="프로젝트 Story 목록")
def project_stories(project=Depends(owned_project), db: Session = Depends(get_db),
                    story_status: StoryStatus | None = None,
                    limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    return content.list_records(db, Story, project.owner_id, project.id, limit, offset,
                                Story.created_at, story_status=story_status)


@router.post("/{project_id}/github/sync", response_model=SyncResult, summary="GitHub 커밋을 변경사항으로 저장",
             description="선택한 브랜치의 커밋 한 페이지를 저장합니다. has_next가 true이면 다음 page로 요청하세요. 기존 커밋과 Story 연결은 유지됩니다.")
def sync_github(project=Depends(owned_project), db: Session = Depends(get_db),
                branch: str | None = Query(None, min_length=1, max_length=255),
                page: int = Query(1, ge=1), per_page: int = Query(100, ge=1, le=100)):
    return sync_commits(db, project, branch, page, per_page)


@router.get("/{project_id}/github/commits", response_model=CommitPage, summary="최근 커밋")
def commits(page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=100),
            branch: str | None = Query(None, min_length=1, max_length=255), github=Depends(github_client)):
    params = {"page": page, "per_page": per_page}
    if branch:
        params["sha"] = branch
    items, has_next = github.get("/commits", params, empty_list=True)
    return {"items": [commit_summary(item) for item in items], "page": page,
            "per_page": per_page, "has_next": has_next}


@router.get("/{project_id}/github/commits/{sha}", response_model=CommitDetail, summary="커밋 상세")
def commit_detail(sha: str = Path(pattern=r"^[0-9a-fA-F]{7,40}$"),
                  page: int = Query(1, ge=1), per_page: int = Query(100, ge=1, le=100),
                  github=Depends(github_client)):
    item, has_next = github.get(f"/commits/{sha}", {"page": page, "per_page": per_page})
    return {**commit_summary(item), "stats": item["stats"], "files": item.get("files", []),
            "page": page, "per_page": per_page, "has_next": has_next}


@router.get("/{project_id}/github/branches", response_model=BranchPage, summary="브랜치 목록")
def branches(page: int = Query(1, ge=1), per_page: int = Query(30, ge=1, le=100),
             github=Depends(github_client)):
    items, has_next = github.get("/branches", {"page": page, "per_page": per_page}, empty_list=True)
    return {"items": [{"name": item["name"], "sha": item["commit"]["sha"],
                       "protected": item["protected"]} for item in items],
            "page": page, "per_page": per_page, "has_next": has_next}
