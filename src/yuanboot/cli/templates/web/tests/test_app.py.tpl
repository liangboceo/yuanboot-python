from fastapi.testclient import TestClient

from __PACKAGE__.main import create_app


def test_lifecycle_and_openapi():
    app = create_app()
    with TestClient(app) as client:
        assert client.get("/actuator/health/readiness").status_code == 200
        response = client.get("/openapi.json")
        assert response.status_code == 200
        assert response.json()["info"]["title"] == "__PROJECT__"
    assert app.state.host.life.state == "down"
