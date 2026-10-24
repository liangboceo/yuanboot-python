from typing import Annotated

from pydantic import BaseModel, Field

from yuanboot.web import RouterBuilder, inject
from yuanboot.web.endpoints import use_actuator

from .services import GreetingService


class GreetingRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


def register_endpoints(router: RouterBuilder):
    use_actuator(router)

    @router.get("/info")
    def info():
        return {"info": "ok"}

    with router.group("/api", tags=["Greeting"]) as api:
        @api.post("/greet")
        def greet(body: GreetingRequest, service: Annotated[GreetingService, inject(GreetingService)]):
            return {"message": service.greet(body.name)}
