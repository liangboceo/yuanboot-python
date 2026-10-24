from fastapi import Request
from pydantic import BaseModel, Field
from starlette.responses import HTMLResponse
from starlette.templating import Jinja2Templates

from yuanboot import Configuration
from yuanboot.web import ApiController, ApiResult, controller, route


class GreetingRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class GreetingService:
    def __init__(self, configuration: Configuration):
        self.configuration = configuration

    def greet(self, name: str) -> str:
        return f"{self.configuration.get_string('greeting.message')}, {name}!"


@controller("/api", tags=["Greeting"])
class GreetingController(ApiController):
    def __init__(self, service: GreetingService):
        self.service = service

    @route("/greet", methods=["POST"])
    def greet(self, body: GreetingRequest) -> ApiResult[str]:
        return self.ok(self.service.greet(body.name))


@controller(tags=["Pages"])
class HomeController:
    def __init__(self, templates: Jinja2Templates):
        self.templates = templates

    @route("/", response_class=HTMLResponse)
    def index(self, request: Request):
        return self.templates.TemplateResponse(
            request=request, name="index.html", context={"title": "__PROJECT__"}
        )
