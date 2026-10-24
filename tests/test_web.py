import asyncio
import time
import uuid
from typing import Annotated

import jwt
from fastapi import Depends, Request, Security, WebSocket
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse

from yuanboot import Configuration, ServiceProvider
from yuanboot.web import (
    ApiController,
    ApiResult,
    WebHostBuilder,
    controller,
    inject,
    inject_websocket,
    route,
)
from yuanboot.web.endpoints import use_actuator, use_health
from yuanboot.web.security import JwtBearer


class RequestResource:
    closed_ids = []

    def __init__(self):
        self.id = uuid.uuid4().hex
        self.closed = False

    async def aclose(self):
        self.closed = True
        self.closed_ids.append(self.id)


class Payload(BaseModel):
    name: str = Field(min_length=1)


@controller("/api", tags=["Test"])
class TestApiController(ApiController):
    __test__ = False

    def __init__(self, resource: RequestResource):
        self.resource = resource

    @route("/users/stats")
    def stats(self) -> dict:
        return {"total": 0}

    @route("/users/{user_id}")
    def find(self, user_id: int) -> dict:
        return {"id": user_id}

    @route("/users/{user_id}", methods=["POST"])
    async def create(self, user_id: int, body: Payload, q: str = "default") -> ApiResult[dict]:
        return self.ok({"id": user_id, "name": body.name, "q": q, "scope": self.resource.id})

    @route("/sync")
    def sync(self, request: Request) -> dict:
        return {"same": request.state.services.get_service(RequestResource) is self.resource}


def make_host():
    background_observations = []

    def endpoints(router):
        use_actuator(router)

        @router.get("/scopes")
        def scopes(request: Request, resource: Annotated[RequestResource, inject(RequestResource)]):
            provider: ServiceProvider = request.state.services
            assert provider.get_service(RequestResource) is resource
            return {"id": resource.id}

        @router.get("/error")
        def error(resource: Annotated[RequestResource, inject(RequestResource)]):
            raise ValueError("private error detail")

        @router.get("/stream")
        async def stream(resource: Annotated[RequestResource, inject(RequestResource)]):
            async def generate():
                yield b"first"
                await asyncio.sleep(0)
                assert not resource.closed
                yield b"second"

            def after_response():
                background_observations.append(not resource.closed)

            return StreamingResponse(generate(), background=BackgroundTask(after_response))

        @router.websocket("/ws")
        async def websocket(
            websocket: WebSocket,
            resource: Annotated[RequestResource, inject_websocket(RequestResource)],
        ):
            await websocket.accept()
            await websocket.send_json({"id": resource.id})
            await websocket.close()

    host = (
        WebHostBuilder(Configuration())
        .configure_services(lambda s: s.add_scoped(RequestResource))
        .configure(
            lambda app: (
                app.use_cors(allow_origins=["https://example.com"])
                .use_endpoints(endpoints)
                .use_mvc(lambda mvc: mvc.add_controller(TestApiController))
            )
        )
        .build()
    )
    return host, background_observations


def test_request_scopes_recovery_and_metrics():
    host, _ = make_host()
    with TestClient(host) as client:
        assert client.get("/actuator/health/readiness").json() == {"status": "up"}
        first = client.get("/scopes", headers={"X-Request-ID": "request-123"})
        assert first.headers["x-request-id"] == "request-123"
        assert first.json()["id"] in RequestResource.closed_ids
        assert client.get("/scopes").json()["id"] != first.json()["id"]
        error = client.get("/error")
        assert error.status_code == 500
        assert "private error detail" not in error.text
        assert error.json()["request_id"] == error.headers["x-request-id"]
        preflight = client.options(
            "/scopes",
            headers={"Origin": "https://example.com", "Access-Control-Request-Method": "GET"},
        )
        assert preflight.headers["access-control-allow-origin"] == "https://example.com"
        client.post("/api/users/1", json={"name": "A"})
        client.post("/api/users/2", json={"name": "B"})
        client.get("/missing/random-value")
        metrics = client.get("/actuator/prometheus")
        assert metrics.status_code == 200
        assert 'path="/api/users/{user_id}"' in metrics.text
        assert 'path="__unmatched__"' in metrics.text
    assert host.life.state == "down"


def test_controller_validation_binding_and_openapi():
    host, _ = make_host()
    with TestClient(host.app) as client:
        response = client.post("/api/users/42?q=hello", json={"name": "yuanboot"})
        assert response.status_code == 200, response.text
        assert response.json()["data"]["id"] == 42
        assert response.json()["data"]["q"] == "hello"
        assert response.json()["data"]["scope"] in RequestResource.closed_ids
        assert client.get("/api/sync").json() == {"same": True}
        assert client.get("/api/users/stats").json() == {"total": 0}
        assert client.get("/api/users/42").json() == {"id": 42}
        assert client.post("/api/users/not-int", json={"name": "x"}).status_code == 422
        assert client.post("/api/users/1", json={"name": ""}).status_code == 422
        schema = client.get("/openapi.json").json()
        operation = schema["paths"]["/api/users/{user_id}"]["post"]
        assert operation["requestBody"]["required"] is True
        assert "_yuanboot_controller" not in str(operation)
        assert operation["tags"] == ["Test"]


def test_streaming_background_and_websocket_disposal():
    host, observations = make_host()
    with TestClient(host) as client:
        assert client.get("/stream").content == b"firstsecond"
        assert observations == [True]
        with client.websocket_connect("/ws") as websocket:
            resource_id = websocket.receive_json()["id"]
        # The WebSocket task has completed when its client context exits.
        assert resource_id in RequestResource.closed_ids


def test_custom_health_and_failure():
    async def failing():
        raise RuntimeError("connection details must stay private")

    async def slow():
        await asyncio.sleep(0.2)
        return True

    host = (
        WebHostBuilder()
        .configure(
            lambda app: app.use_endpoints(
                lambda router: use_health(router, {"db": failing, "slow": slow}, timeout=0.01)
            )
        )
        .build()
    )
    with TestClient(host) as client:
        response = client.get("/actuator/health/detail")
        assert response.status_code == 503
        assert response.json()["components"]["slow"]["status"] == "down"
        assert "connection details" not in response.text


def test_jwt_authentication_and_schema():
    secret = "test-signing-secret-at-least-32-characters"
    bearer = JwtBearer(secret, issuer="test", audience="api")

    def endpoints(router):
        @router.get("/private")
        def private(claims: Annotated[dict, Security(bearer)]):
            return {"subject": claims["sub"]}

    host = WebHostBuilder().configure(lambda app: app.use_endpoints(endpoints)).build()
    claims = {"sub": "user", "iss": "test", "aud": "api", "exp": time.time() + 60}
    with TestClient(host) as client:
        assert client.get("/private").status_code == 401
        good = jwt.encode(claims, secret, algorithm="HS256")
        assert client.get("/private", headers={"Authorization": f"Bearer {good}"}).json() == {
            "subject": "user"
        }
        for token in (
            jwt.encode({**claims, "exp": time.time() - 60}, secret, algorithm="HS256"),
            jwt.encode(claims, "different-key-with-at-least-32-characters", algorithm="HS256"),
            jwt.encode({k: v for k, v in claims.items() if k != "exp"}, secret, algorithm="HS256"),
        ):
            assert (
                client.get("/private", headers={"Authorization": f"Bearer {token}"}).status_code
                == 401
            )
        assert "BearerAuth" in client.get("/openapi.json").json()["components"]["securitySchemes"]


def test_fastapi_dependencies_work_in_controller():
    def authenticated():
        return "user"

    @controller("/secured")
    class SecuredController:
        @route("")
        def index(self, user: str = Depends(authenticated)) -> dict:
            return {"user": user}

    host = (
        WebHostBuilder()
        .configure(lambda app: app.use_mvc(lambda mvc: mvc.add_controller(SecuredController)))
        .build()
    )
    with TestClient(host) as client:
        assert client.get("/secured").json() == {"user": "user"}
