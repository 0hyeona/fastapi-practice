from datetime import datetime, timezone
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, UrlConstraints, field_validator, model_validator
from app.schemas.story import Title

Source = Literal["github", "figma", "notion"]
ActivityType = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
SourceUrl = Annotated[HttpUrl, UrlConstraints(max_length=2048)]


class ActivityFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("occurred_at", check_fields=False)
    @classmethod
    def utc_datetime(cls, value):
        if value is None:
            return value
        if value.tzinfo is None:
            raise ValueError("occurred_at must include a timezone.")
        return value.astimezone(timezone.utc).replace(tzinfo=None)


class ProjectActivityCreate(ActivityFields):
    project_id: int = Field(gt=0)
    story_id: int | None = Field(default=None, gt=0)
    source: Source
    activity_type: ActivityType
    title: Title
    description: str | None = Field(default=None, max_length=10000)
    source_url: SourceUrl | None = None
    occurred_at: datetime


class ProjectActivityUpdate(ActivityFields):
    story_id: int | None = Field(default=None, gt=0)
    source: Source | None = None
    activity_type: ActivityType | None = None
    title: Title | None = None
    description: str | None = Field(default=None, max_length=10000)
    source_url: SourceUrl | None = None
    occurred_at: datetime | None = None

    @model_validator(mode="after")
    def validate_changes(self):
        if not self.model_fields_set:
            raise ValueError("Provide at least one field.")
        for key in self.model_fields_set - {"description", "source_url", "story_id"}:
            if getattr(self, key) is None:
                raise ValueError(f"{key} cannot be null.")
        return self


class ProjectActivityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    activity_id: int = Field(validation_alias="id")
    project_id: int
    story_id: int | None
    external_id: str | None
    branch_name: str | None
    source: Source
    activity_type: str | None
    title: str
    description: str | None
    source_url: str | None
    occurred_at: datetime
    created_at: datetime
