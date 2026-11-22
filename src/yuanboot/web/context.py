import typing
from dataclasses import dataclass
from typing import TypeVar

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from starlette.responses import JSONResponse

from yuanboot.compat import BaseModel, validate_model
from yuanboot.configuration import Configuration
from yuanboot.dependency_injection import ServiceProvider

T = TypeVar("T", bound=BaseModel)


@dataclass
class HttpContext:
    request: "Request"

    @property
    def services(self) -> "ServiceProvider":
        return self.request.state.services

    @property
    def configuration(self) -> "Configuration":
        return self.request.app.state.host.configuration

    @property
    def request_id(self) -> "str":
        return self.request.state.request_id

    def query(self, name: "str", default: "typing.Union[str, None]" = None):
        return self.request.query_params.get(name, default)

    def param(self, name: "str", default=None):
        return self.request.path_params.get(name, default)

    async def bind(self, model: "typing.Type[T]") -> "T":
        return validate_model(model, await self.request.json())

    def json(self, data, status_code: "int" = 200) -> "JSONResponse":
        return JSONResponse(jsonable_encoder(data), status_code=status_code)
