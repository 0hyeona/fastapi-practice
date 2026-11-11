from datetime import datetime
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints, model_validator

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Content = Annotated[str, StringConstraints(max_length=15000)]
StoryStatus = Literal["draft", "published"]
ActivityId = Annotated[int, Field(gt=0)]
SelectedActivityIds = Annotated[list[ActivityId], Field(max_length=20)]
AnalysisSection = Literal["tags", "title", "before", "after", "summary"]
AnalysisText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=3000)]
Tag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]


class StoryDetails(BaseModel):
    why: Content | None = None
    problem: Content | None = None
    solution: Content | None = None
    result: Content | None = None
    learned: Content | None = None
    next_steps: Content | None = None
    ai_analysis: JsonValue = None


class StoryCreate(StoryDetails):
    model_config = ConfigDict(extra="forbid")
    project_id: int = Field(gt=0)
    title: Title
    content: Content = ""
    story_status: StoryStatus = "draft"
    activity_ids: SelectedActivityIds = Field(
        default_factory=list, description="Story 작성과 동시에 연결할 미정리 변경사항 ID"
    )


class StoryUpdate(StoryDetails):
    model_config = ConfigDict(extra="forbid")
    title: Title | None = None
    content: Content | None = None
    story_status: StoryStatus | None = None

    @model_validator(mode="after")
    def validate_changes(self):
        if not self.model_fields_set:
            raise ValueError("Provide at least one field.")
        for key in ("title", "content", "story_status"):
            if key in self.model_fields_set and getattr(self, key) is None:
                raise ValueError(f"{key} cannot be null.")
        return self


class StoryResponse(StoryDetails):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    title: str
    content: str
    story_status: StoryStatus
    created_at: datetime
    updated_at: datetime


class StoryAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: int = Field(gt=0)
    activity_ids: SelectedActivityIds = Field(min_length=1)
    section: AnalysisSection | None = Field(default=None, description="재생성할 필드 (생략 시 전체 분석)")


class StoryAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tags: list[Tag] = Field(default_factory=list, max_length=10)
    title: Title | None = None
    before: AnalysisText | None = None
    after: AnalysisText | None = None
    summary: AnalysisText | None = None
