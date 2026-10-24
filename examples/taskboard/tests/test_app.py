from fastapi.testclient import TestClient
from taskboard.main import create_app


def test_lifecycle_and_openapi(configuration):
    app = create_app(configuration)
    with TestClient(app) as client:
        assert client.get("/actuator/health/readiness").status_code == 200
        response = client.get("/openapi.json")
        assert response.status_code == 200
        assert response.json()["info"]["title"] == "taskboard-test"
    assert app.state.host.life.state == "down"
