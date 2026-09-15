from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field, field_validator


app = FastAPI(title="Agent Learning API hhy")


TaskStatus = Literal["todo", "doing", "done"]
TaskPriority = Literal[1, 2, 3]


class TaskCreate(BaseModel):
    title: str = Field(min_length=1)
    description: str = ""
    status: TaskStatus = "todo"
    priority: TaskPriority = 2
    estimated_minutes: int = Field(gt=0)

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        title = value.strip()
        if not title:
            raise ValueError("title must not be blank")
        return title


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    description: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    estimated_minutes: int | None = Field(default=None, gt=0)

    @field_validator(
        "title",
        "description",
        "status",
        "priority",
        "estimated_minutes",
        mode="before",
    )
    @classmethod
    def fields_must_not_be_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("updated fields must not be null")
        return value

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        title = value.strip()
        if not title:
            raise ValueError("title must not be blank")
        return title


class TaskResponse(BaseModel):
    id: int
    title: str
    description: str
    status: TaskStatus
    priority: TaskPriority
    estimated_minutes: int
    created_at: datetime
    updated_at: datetime


tasks: list[TaskResponse] = []


def find_task_index(task_id: int) -> int:
    for index, task in enumerate(tasks):
        if task.id == task_id:
            return index
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "agent-learning-api",
    }


@app.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(task: TaskCreate) -> TaskResponse:
    now = datetime.now(UTC)
    created_task = TaskResponse(
        id=max((existing_task.id for existing_task in tasks), default=0) + 1,
        created_at=now,
        updated_at=now,
        **task.model_dump(),
    )
    tasks.append(created_task)
    return created_task


@app.get("/tasks", response_model=list[TaskResponse])
async def list_tasks() -> list[TaskResponse]:
    return tasks


@app.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int) -> TaskResponse:
    return tasks[find_task_index(task_id)]


@app.patch("/tasks/{task_id}", response_model=TaskResponse)
async def update_task(task_id: int, task_update: TaskUpdate) -> TaskResponse:
    task_index = find_task_index(task_id)
    current_task = tasks[task_index]
    update_data = task_update.model_dump(exclude_unset=True)

    if current_task.status == "done" and update_data.get("status") == "todo":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A done task cannot be changed directly back to todo",
        )

    task_data = current_task.model_dump()
    task_data.update(update_data)
    now = datetime.now(UTC)
    task_data["updated_at"] = max(
        now,
        current_task.updated_at + timedelta(microseconds=1),
    )
    updated_task = TaskResponse.model_validate(task_data)
    tasks[task_index] = updated_task
    return updated_task


@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: int) -> None:
    tasks.pop(find_task_index(task_id))


@app.get("/test")
async def test_endpoint() -> dict[str, str]:
    return {
        "message": "hhy is pig",
    }
