from datetime import datetime
from pydantic import BaseModel
from app.schemas.story import StoryResponse
from app.schemas.project_activity import ProjectActivityResponse
from app.schemas.project import ProjectResponse


class CommitSummary(BaseModel):
    sha: str
    message: str
    author_name: str | None
    author_login: str | None
    avatar_url: str | None
    committed_at: datetime | None
    html_url: str


class CommitPage(BaseModel):
    items: list[CommitSummary]
    page: int
    per_page: int
    has_next: bool


class CommitStats(BaseModel):
    additions: int
    deletions: int
    total: int


class CommitFile(BaseModel):
    filename: str
    previous_filename: str | None = None
    status: str
    additions: int
    deletions: int
    changes: int
    patch: str | None = None


class CommitDetail(CommitSummary):
    stats: CommitStats
    files: list[CommitFile]
    page: int
    per_page: int
    has_next: bool


class Branch(BaseModel):
    name: str
    sha: str
    protected: bool


class BranchPage(BaseModel):
    items: list[Branch]
    page: int
    per_page: int
    has_next: bool


class RepositorySummary(BaseModel):
    full_name: str
    html_url: str
    default_branch: str
    language: str | None
    stars: int
    forks: int
    open_issues_count: int


class UnorganizedCounts(BaseModel):
    github: int = 0
    figma: int = 0
    notion: int = 0
    total: int = 0


class SyncResult(BaseModel):
    fetched: int
    created: int
    existing: int
    page: int
    per_page: int
    has_next: bool


class Dashboard(BaseModel):
    unorganized_counts: UnorganizedCounts
    recent_stories: list[StoryResponse]
    recent_activities: list[ProjectActivityResponse]
    github_error: str | None = None
    project: ProjectResponse
    github: RepositorySummary | None
    recent_commits: list[CommitSummary]
