from datetime import datetime
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Content = Annotated[str, StringConstraints(max_length=15000)]
StoryStatus = Literal["draft", "published"]


class StoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: int = Field(gt=0)
    title: Title
    content: Content = ""
    story_status: StoryStatus = "draft"


class StoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Title | None = None
    content: Content | None = None
    story_status: StoryStatus | None = None

    @model_validator(mode="after")
    def validate_changes(self):
        if not self.model_fields_set or any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("Provide at least one non-null field.")
        return self


class StoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    title: str
    content: str
    story_status: StoryStatus
    created_at: datetime
    updated_at: datetime
