from datetime import UTC, datetime
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


class TaskResponse(BaseModel):
    id: int
    title: str
    description: str
    status: TaskStatus
    priority: TaskPriority
    estimated_minutes: int
    created_at: datetime


tasks: list[TaskResponse] = []


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "agent-learning-api",
    }


@app.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(task: TaskCreate) -> TaskResponse:
    created_task = TaskResponse(
        id=len(tasks) + 1,
        created_at=datetime.now(UTC),
        **task.model_dump(),
    )
    tasks.append(created_task)
    return created_task


@app.get("/tasks", response_model=list[TaskResponse])
async def list_tasks() -> list[TaskResponse]:
    return tasks


@app.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int) -> TaskResponse:
    for task in tasks:
        if task.id == task_id:
            return task
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")


@app.get("/test")
async def test_endpoint() -> dict[str, str]:
    return {
        "message": "hhy is pig",
    }
