from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Task

app = FastAPI(title="Agent Learning API hhy")


TaskStatus = Literal["todo", "doing", "done"]
TaskPriority = Literal[1, 2, 3]
TaskSortField = Literal[
    "id", "title", "status", "priority", "created_at", "updated_at"
]
SortOrder = Literal["asc", "desc"]


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
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    status: TaskStatus
    priority: TaskPriority
    estimated_minutes: int
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def mysql_datetime_is_utc(cls, value: datetime) -> datetime:
        # MySQL DATETIME does not retain timezone information.
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class TaskListResponse(BaseModel):
    items: list[TaskResponse]
    total: int
    page: int
    page_size: int


def find_task(db: Session, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "agent-learning-api",
    }


@app.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(task: TaskCreate, db: Session = Depends(get_db)) -> Task:
    now = datetime.now(UTC)
    created_task = Task(
        created_at=now,
        updated_at=now,
        **task.model_dump(),
    )
    db.add(created_task)
    db.commit()
    db.refresh(created_task)
    return created_task


@app.get("/tasks", response_model=TaskListResponse)
def list_tasks(
    status_filter: TaskStatus | None = Query(default=None, alias="status"),
    priority: int | None = Query(default=None, ge=1, le=3),
    min_priority: int | None = Query(default=None, ge=1, le=3),
    search: str | None = Query(default=None, min_length=1, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: TaskSortField = "id",
    sort_order: SortOrder = "asc",
    db: Session = Depends(get_db),
) -> TaskListResponse:
    filters = []
    if status_filter is not None:
        filters.append(Task.status == status_filter)
    if priority is not None:
        filters.append(Task.priority == priority)
    if min_priority is not None:
        filters.append(Task.priority >= min_priority)
    if search is not None:
        escaped_search = (
            search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        search_pattern = f"%{escaped_search}%"
        filters.append(
            or_(
                Task.title.ilike(search_pattern, escape="\\"),
                Task.description.ilike(search_pattern, escape="\\"),
            )
        )

    total = db.scalar(select(func.count()).select_from(Task).where(*filters)) or 0

    sort_columns = {
        "id": Task.id,
        "title": Task.title,
        "status": Task.status,
        "priority": Task.priority,
        "created_at": Task.created_at,
        "updated_at": Task.updated_at,
    }
    sort_column = sort_columns[sort_by]
    direction = sort_column.asc if sort_order == "asc" else sort_column.desc
    order_by = [direction()]
    if sort_by != "id":
        id_direction = Task.id.asc if sort_order == "asc" else Task.id.desc
        order_by.append(id_direction())

    statement = (
        select(Task)
        .where(*filters)
        .order_by(*order_by)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list(db.scalars(statement))
    return TaskListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@app.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: int, db: Session = Depends(get_db)) -> Task:
    return find_task(db, task_id)


@app.patch("/tasks/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: int, task_update: TaskUpdate, db: Session = Depends(get_db)
) -> Task:
    current_task = find_task(db, task_id)
    update_data = task_update.model_dump(exclude_unset=True)

    if current_task.status == "done" and update_data.get("status") == "todo":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A done task cannot be changed directly back to todo",
        )

    for field, value in update_data.items():
        setattr(current_task, field, value)
    now = datetime.now(UTC)
    previous_updated_at = current_task.updated_at
    if previous_updated_at.tzinfo is None:
        previous_updated_at = previous_updated_at.replace(tzinfo=UTC)
    current_task.updated_at = max(
        now,
        previous_updated_at + timedelta(microseconds=1),
    )
    db.commit()
    db.refresh(current_task)
    return current_task


@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, db: Session = Depends(get_db)) -> None:
    db.delete(find_task(db, task_id))
    db.commit()


@app.get("/test")
async def test_endpoint() -> dict[str, str]:
    return {
        "message": "hhy is pig",
    }
