import os
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
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
    yield
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
    assert len(response.json()) == 1
    assert response.json()[0]["title"] == "Learn FastAPI"


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
    assert client.get("/tasks").json() == []


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
