from fastapi import Depends, Request, WebSocket

from yuanboot.web.context import HttpContext


def get_services(request: Request):
    return request.state.services


def get_context(request: Request) -> HttpContext:
    return HttpContext(request)


def inject(service_type):
    """Use as Annotated[MyService, inject(MyService)] or Depends-compatible default."""

    def resolve(request: Request):
        return request.state.services.get_service(service_type)

    return Depends(resolve)


def inject_websocket(service_type):
    def resolve(websocket: WebSocket):
        return websocket.state.services.get_service(service_type)

    return Depends(resolve)
