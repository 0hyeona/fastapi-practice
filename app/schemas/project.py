"""프로젝트 생성 요청과 조회 응답의 형식을 정의합니다."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, UrlConstraints, field_validator, model_validator

ProjectLink = Annotated[HttpUrl, UrlConstraints(max_length=2048)]


class ProjectCreate(BaseModel):
    project_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    description: str | None = Field(default=None, max_length=10000)
    owner_id: int | None = Field(default=None, gt=0, description="생략하면 로그인한 회원 번호를 사용합니다.")
    github_url: ProjectLink | None = None
    figma_url: ProjectLink | None = None
    notion_url: ProjectLink | None = None

    @field_validator("github_url", "figma_url", "notion_url", mode="before")
    @classmethod
    def normalize_optional_link(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value

    model_config = ConfigDict(json_schema_extra={"example": {
        "project_name": "MOEUM",
        "description": "프로젝트 변경사항을 기록하고 관리하는 서비스",
        "github_url": "https://github.com/0hyeona/fastapi-practice",
        "figma_url": None,
        "notion_url": None,
    }})


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"example": {"project_name": "MOEUM 수정"}})

    project_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)] | None = None
    description: str | None = Field(default=None, max_length=10000)
    github_url: ProjectLink | None = None
    figma_url: ProjectLink | None = None
    notion_url: ProjectLink | None = None

    @field_validator("github_url", "figma_url", "notion_url", mode="before")
    @classmethod
    def normalize_optional_link(cls, value):
        return (value.strip() or None) if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_changes(self):
        if not self.model_fields_set:
            raise ValueError("수정할 항목을 하나 이상 입력해주세요.")
        if "project_name" in self.model_fields_set and self.project_name is None:
            raise ValueError("프로젝트 이름은 null일 수 없습니다.")
        return self


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    project_name: str
    description: str | None
    github_url: str | None
    figma_url: str | None
    notion_url: str | None
    project_status: str
    created_at: datetime
    updated_at: datetime
