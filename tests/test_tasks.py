import os
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

os.environ["DATABASE_URL"] = "sqlite+pysqlite://"

import app.database as database  # noqa: E402
from app.database import Base  # noqa: E402
from app.main import app  # noqa: E402


client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'tasks.db'}")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(database, "SessionLocal", session_factory)
    yield engine
    engine.dispose()


def test_session_is_rolled_back_and_closed_on_failure(monkeypatch) -> None:
    class TrackingSession:
        rolled_back = False
        closed = False

        def rollback(self) -> None:
            self.rolled_back = True

        def close(self) -> None:
            self.closed = True

    session = TrackingSession()
    monkeypatch.setattr(database, "SessionLocal", lambda: session)
    dependency = database.get_db()
    assert next(dependency) is session

    with pytest.raises(RuntimeError, match="database write failed"):
        dependency.throw(RuntimeError("database write failed"))

    assert session.rolled_back
    assert session.closed


def valid_task_data() -> dict[str, object]:
    return {
        "title": "Learn FastAPI",
        "description": "Build task endpoints",
        "status": "todo",
        "priority": 1,
        "estimated_minutes": 45,
    }


def create_task(
    title: str,
    description: str,
    task_status: str,
    priority: int,
) -> dict[str, object]:
    task_data = valid_task_data()
    task_data.update(
        title=title,
        description=description,
        status=task_status,
        priority=priority,
    )
    response = client.post("/tasks", json=task_data)
    assert response.status_code == 201
    return response.json()


def create_filter_test_tasks() -> list[dict[str, object]]:
    return [
        create_task("Learn FastAPI", "Build API endpoints", "todo", 1),
        create_task("Write docs", "FastAPI query guide", "doing", 2),
        create_task("Tune database", "Review slow queries", "done", 3),
        create_task("Clean desk", "Organize the workspace", "todo", 2),
        create_task("Release API", "Publish backend changes", "doing", 3),
    ]


def test_health_endpoint_is_unchanged() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "agent-learning-api",
    }


def test_create_task_returns_201() -> None:
    response = client.post("/tasks", json=valid_task_data())

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == 1
    assert body["title"] == "Learn FastAPI"
    assert body["description"] == "Build task endpoints"
    assert body["status"] == "todo"
    assert body["priority"] == 1
    assert body["estimated_minutes"] == 45
    assert datetime.fromisoformat(body["created_at"]).tzinfo is not None
    assert datetime.fromisoformat(body["updated_at"]).tzinfo is not None
    assert body["updated_at"] == body["created_at"]


def test_list_tasks_returns_created_tasks() -> None:
    client.post("/tasks", json=valid_task_data())

    response = client.get("/tasks")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["page"] == 1
    assert response.json()["page_size"] == 20
    assert len(response.json()["items"]) == 1
    assert response.json()["items"][0]["title"] == "Learn FastAPI"


@pytest.mark.parametrize(
    ("query", "expected_titles"),
    [
        ("status=todo", ["Learn FastAPI", "Clean desk"]),
        ("priority=2", ["Write docs", "Clean desk"]),
        (
            "min_priority=2",
            ["Write docs", "Tune database", "Clean desk", "Release API"],
        ),
        ("search=fastapi", ["Learn FastAPI", "Write docs"]),
    ],
)
def test_list_tasks_supports_individual_filters(
    query: str, expected_titles: list[str]
) -> None:
    create_filter_test_tasks()

    response = client.get(f"/tasks?{query}")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == len(expected_titles)
    assert [item["title"] for item in body["items"]] == expected_titles


def test_list_tasks_combines_filters() -> None:
    create_filter_test_tasks()

    response = client.get(
        "/tasks?status=doing&min_priority=2&search=api&sort_by=priority&sort_order=desc"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert [item["title"] for item in body["items"]] == [
        "Release API",
        "Write docs",
    ]


def test_search_treats_sql_wildcards_as_literal_characters() -> None:
    create_task("Reach 100% coverage", "Testing target", "todo", 1)
    create_task("Reach 1000 coverage", "Different target", "todo", 1)

    response = client.get("/tasks", params={"search": "100%"})

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["title"] == "Reach 100% coverage"


def test_search_input_is_not_interpreted_as_sql() -> None:
    create_filter_test_tasks()

    response = client.get("/tasks", params={"search": "' OR 1=1 --"})

    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert response.json()["items"] == []


def test_list_tasks_paginates_and_sorts() -> None:
    tasks = create_filter_test_tasks()

    response = client.get(
        "/tasks?page=2&page_size=2&sort_by=priority&sort_order=desc"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 5
    assert body["page"] == 2
    assert body["page_size"] == 2
    assert [item["id"] for item in body["items"]] == [tasks[3]["id"], tasks[1]["id"]]


def test_list_tasks_uses_count_limit_and_offset_in_database(
    isolated_database,
) -> None:
    create_filter_test_tasks()
    select_statements: list[str] = []

    def record_selects(
        _connection, _cursor, statement, _parameters, _context, _executemany
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            select_statements.append(statement.lower())

    event.listen(isolated_database, "before_cursor_execute", record_selects)
    try:
        response = client.get("/tasks?status=doing&page=2&page_size=1")
    finally:
        event.remove(isolated_database, "before_cursor_execute", record_selects)

    assert response.status_code == 200
    assert len(select_statements) == 2
    assert "count(" in select_statements[0]
    assert "where tasks.status = ?" in select_statements[0]
    assert "limit ? offset ?" in select_statements[1]


@pytest.mark.parametrize(
    "query",
    [
        "page=0",
        "page_size=0",
        "page_size=101",
        "status=blocked",
        "priority=0",
        "priority=4",
        "min_priority=0",
        "min_priority=4",
        "sort_by=description",
        "sort_order=sideways",
    ],
)
def test_list_tasks_rejects_invalid_query_parameters(query: str) -> None:
    response = client.get(f"/tasks?{query}")

    assert response.status_code == 422


def test_get_task_returns_matching_task() -> None:
    created = client.post("/tasks", json=valid_task_data()).json()

    response = client.get(f"/tasks/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created


def test_get_missing_task_returns_404() -> None:
    response = client.get("/tasks/999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found"}


def test_patch_task_partially_updates_task() -> None:
    created = client.post("/tasks", json=valid_task_data()).json()

    response = client.patch(f"/tasks/{created['id']}", json={"title": "Learn PATCH"})

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Learn PATCH"
    assert body["description"] == created["description"]
    assert body["status"] == created["status"]
    assert body["priority"] == created["priority"]
    assert body["estimated_minutes"] == created["estimated_minutes"]
    assert body["created_at"] == created["created_at"]
    assert datetime.fromisoformat(body["updated_at"]) > datetime.fromisoformat(
        created["updated_at"]
    )


def test_patch_missing_task_returns_404() -> None:
    response = client.patch("/tasks/999", json={"title": "Missing"})

    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found"}


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("title", ""),
        ("title", "   "),
        ("title", None),
        ("status", "blocked"),
        ("priority", 4),
        ("estimated_minutes", 0),
    ],
)
def test_invalid_patch_data_returns_422(field: str, invalid_value: object) -> None:
    created = client.post("/tasks", json=valid_task_data()).json()

    response = client.patch(f"/tasks/{created['id']}", json={field: invalid_value})

    assert response.status_code == 422


def test_done_task_cannot_be_changed_directly_back_to_todo() -> None:
    task_data = valid_task_data()
    task_data["status"] = "done"
    created = client.post("/tasks", json=task_data).json()

    response = client.patch(f"/tasks/{created['id']}", json={"status": "todo"})

    assert response.status_code == 409
    assert response.json() == {
        "detail": "A done task cannot be changed directly back to todo"
    }
    assert client.get(f"/tasks/{created['id']}").json()["status"] == "done"


def test_done_task_can_be_changed_to_doing() -> None:
    task_data = valid_task_data()
    task_data["status"] = "done"
    created = client.post("/tasks", json=task_data).json()

    response = client.patch(
        f"/tasks/{created['id']}",
        json={"status": "doing"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "doing"

def test_delete_task_returns_204_and_removes_task() -> None:
    created = client.post("/tasks", json=valid_task_data()).json()

    response = client.delete(f"/tasks/{created['id']}")

    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"/tasks/{created['id']}").status_code == 404


def test_delete_missing_task_returns_404() -> None:
    response = client.delete("/tasks/999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found"}


def test_complete_task_crud_flow() -> None:
    created = client.post("/tasks", json=valid_task_data())
    task_id = created.json()["id"]

    assert client.get(f"/tasks/{task_id}").json() == created.json()
    updated = client.patch(
        f"/tasks/{task_id}",
        json={"description": "CRUD verified", "status": "doing"},
    )
    assert updated.status_code == 200
    assert updated.json()["description"] == "CRUD verified"
    assert updated.json()["status"] == "doing"
    assert client.delete(f"/tasks/{task_id}").status_code == 204
    assert client.get("/tasks").json()["items"] == []


def test_creating_after_delete_does_not_duplicate_an_existing_id() -> None:
    first = client.post("/tasks", json=valid_task_data()).json()
    second = client.post("/tasks", json=valid_task_data()).json()
    client.delete(f"/tasks/{first['id']}")

    third = client.post("/tasks", json=valid_task_data()).json()

    assert third["id"] > second["id"]


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("title", ""),
        ("title", "   "),
        ("status", "blocked"),
        ("priority", 0),
        ("priority", 4),
        ("estimated_minutes", 0),
        ("estimated_minutes", -1),
    ],
)
def test_invalid_task_data_returns_422(field: str, invalid_value: object) -> None:
    task_data = valid_task_data()
    task_data[field] = invalid_value

    response = client.post("/tasks", json=task_data)

    assert response.status_code == 422
