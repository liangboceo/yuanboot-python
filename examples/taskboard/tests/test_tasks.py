from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from taskboard.main import create_app


def test_full_task_lifecycle(client):
    created = client.post(
        "/api/tasks",
        json={"title": "  完成 yuanboot Python 版  ", "description": "验证模板创建与项目运行"},
    )
    assert created.status_code == 201, created.text
    task = created.json()["data"]
    assert task["title"] == "完成 yuanboot Python 版"
    assert task["status"] == "todo"
    task_id = task["id"]
    assert client.get(f"/api/tasks/{task_id}").json()["data"] == task
    updated = client.patch(f"/api/tasks/{task_id}", json={"status": "done", "description": ""})
    assert updated.status_code == 200
    assert updated.json()["data"]["status"] == "done"
    assert updated.json()["data"]["updated_at"] >= task["created_at"]
    assert client.get("/api/tasks/stats").json()["data"] == {
        "total": 1,
        "todo": 0,
        "in_progress": 0,
        "done": 1,
    }
    assert client.delete(f"/api/tasks/{task_id}").status_code == 204
    assert client.get(f"/api/tasks/{task_id}").status_code == 404
    assert client.get("/api/tasks").json()["data"]["total"] == 0


def test_filter_search_and_pagination(client):
    for title, status in (("接口开发", "todo"), ("接口测试", "done"), ("文档完善", "todo")):
        assert client.post("/api/tasks", json={"title": title, "status": status}).status_code == 201
    response = client.get("/api/tasks", params={"q": "接口", "page_size": 1})
    data = response.json()["data"]
    assert data["total"] == 2 and len(data["items"]) == 1
    second = client.get("/api/tasks", params={"q": "接口", "page_size": 1, "page": 2}).json()[
        "data"
    ]
    assert second["items"][0]["id"] != data["items"][0]["id"]
    done = client.get("/api/tasks", params={"status": "done"}).json()["data"]
    assert done["total"] == 1 and done["items"][0]["title"] == "接口测试"


@pytest.mark.parametrize(
    "payload",
    [{"title": " "}, {"title": "x", "status": "invalid"}, {"title": "x", "unknown": 1}, {}],
)
def test_create_validation(client, payload):
    assert client.post("/api/tasks", json=payload).status_code == 422
    assert client.get("/api/tasks/stats").json()["data"]["total"] == 0


@pytest.mark.parametrize("payload", [{}, {"title": " "}, {"status": None}, {"unknown": "x"}])
def test_patch_validation_keeps_original(client, payload):
    task_id = client.post("/api/tasks", json={"title": "keep"}).json()["data"]["id"]
    assert client.patch(f"/api/tasks/{task_id}", json=payload).status_code == 422
    assert client.get(f"/api/tasks/{task_id}").json()["data"]["title"] == "keep"


def test_not_found_invalid_path_and_query(client):
    missing = str(uuid4())
    assert client.get(f"/api/tasks/{missing}").status_code == 404
    assert client.patch(f"/api/tasks/{missing}", json={"title": "x"}).status_code == 404
    assert client.delete(f"/api/tasks/{missing}").status_code == 404
    assert client.get("/api/tasks/not-a-uuid").status_code == 422
    for query in ({"page": 0}, {"page_size": 101}, {"status": "invalid"}):
        assert client.get("/api/tasks", params=query).status_code == 422


def test_sql_input_is_data_and_search_wildcards_are_literal(client):
    dangerous = "Robert'); DROP TABLE tasks;--"
    for title in (dangerous, "完成 100%", "100 things"):
        assert client.post("/api/tasks", json={"title": title}).status_code == 201
    assert client.get("/api/tasks", params={"q": dangerous}).json()["data"]["total"] == 1
    assert client.get("/api/tasks", params={"q": "%"}).json()["data"]["total"] == 1
    assert client.get("/api/tasks/stats").json()["data"]["total"] == 3


def test_data_survives_application_restart(configuration):
    with TestClient(create_app(configuration)) as first:
        task_id = first.post("/api/tasks", json={"title": "persistent"}).json()["data"]["id"]
    with TestClient(create_app(configuration)) as second:
        assert second.get(f"/api/tasks/{task_id}").json()["data"]["title"] == "persistent"


def test_concurrent_requests_have_independent_sessions(client):
    with ThreadPoolExecutor(max_workers=6) as executor:
        responses = list(
            executor.map(
                lambda i: client.post("/api/tasks", json={"title": f"task {i}"}), range(12)
            )
        )
    assert all(response.status_code == 201 for response in responses)
    assert client.get("/api/tasks/stats").json()["data"]["total"] == 12
