"""Run: python examples/quickstart.py; or uvicorn examples.quickstart:app."""

from typing import Annotated

from pydantic import BaseModel, Field

from yuanboot import Configuration
from yuanboot.web import RouterBuilder, create_default_builder, inject
from yuanboot.web.endpoints import use_actuator


class GreetingService:
    def __init__(self, configuration: Configuration):
        self.configuration = configuration

    def greet(self, name: str):
        return f"Hello, {name}!"


class GreetingRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


def endpoints(router: RouterBuilder):
    use_actuator(router)

    @router.get("/info")
    def info():
        return {"info": "ok"}

    @router.post("/api/greet")
    def greet(body: GreetingRequest, service: Annotated[GreetingService, inject(GreetingService)]):
        return {"message": service.greet(body.name)}


host = (
    create_default_builder(endpoints)
    .configure_services(lambda services: services.add_scoped(GreetingService))
    .build()
)
app = host.app


if __name__ == "__main__":
    host.run()
