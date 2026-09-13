from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app, tasks


client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_tasks() -> None:
    tasks.clear()


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
