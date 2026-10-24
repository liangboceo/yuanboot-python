from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TaskStatus(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200, description="任务标题")
    description: str = Field(default="", max_length=5000, description="任务描述")
    status: TaskStatus = TaskStatus.TODO

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value):
        return value.strip() if isinstance(value, str) else value


class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    status: TaskStatus | None = None

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError("至少提供一个需要修改的字段")
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("字段不能为 null；清空描述请传入空字符串")
        return self


class Task(BaseModel):
    id: UUID
    title: str
    description: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime


class TaskPage(BaseModel):
    items: list[Task]
    total: int
    page: int
    page_size: int


class TaskStats(BaseModel):
    total: int
    todo: int
    in_progress: int
    done: int
