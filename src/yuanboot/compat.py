"""Runtime and model APIs shared by Python 3.6+ applications."""

import asyncio
import contextvars
import functools
import inspect
import sys
import typing
from enum import Enum

from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field as Field
from pydantic import SecretStr as SecretStr
from pydantic import ValidationError as ValidationError

try:
    from contextlib import asynccontextmanager as asynccontextmanager
except ImportError:
    from async_generator import asynccontextmanager as asynccontextmanager

try:
    from importlib.resources import files as files
except ImportError:
    from importlib_resources import files as files

try:
    from typing import Annotated as Annotated
    from typing import Literal as Literal
    from typing import get_args as get_args
    from typing import get_origin as get_origin
except ImportError:
    from typing_extensions import Annotated as Annotated
    from typing_extensions import Literal as Literal

    def get_origin(value):
        if hasattr(value, "__metadata__"):
            return Annotated
        return getattr(value, "__origin__", None)

    def get_args(value):
        if hasattr(value, "__metadata__"):
            return (value.__origin__,) + value.__metadata__
        return getattr(value, "__args__", ())


try:
    from enum import StrEnum
except ImportError:

    class StrEnum(str, Enum):
        def __str__(self):
            return self.value


try:
    from builtins import ExceptionGroup
except ImportError:

    class ExceptionGroup(Exception):
        """Collected cleanup errors on runtimes without PEP 654."""

        def __init__(self, message, exceptions):
            super().__init__(message)
            self.exceptions = tuple(exceptions)


if sys.version_info < (3, 7):
    import aiocontextvars  # noqa: F401 - installs task-local context propagation

PYDANTIC_V2 = hasattr(PydanticBaseModel, "model_validate")

if PYDANTIC_V2:
    from pydantic import ConfigDict as ConfigDict
    from pydantic import model_validator as model_validator

    BaseModel = PydanticBaseModel
    GenericModel = PydanticBaseModel
else:
    from pydantic import root_validator
    from pydantic.generics import GenericModel as GenericModel

    class BaseModel(PydanticBaseModel):
        @classmethod
        def model_validate(cls, value):
            return cls.parse_obj(value)

        def model_dump(self, **kwargs):
            return self.dict(**kwargs)

        def model_copy(self, **kwargs):
            return self.copy(**kwargs)

    ConfigDict = dict

    def model_validator(*, mode):
        if mode != "after":
            raise ValueError("Only after-model validation is supported")

        def decorate(callback):
            @root_validator(allow_reuse=True, skip_on_failure=True)
            def validate(cls, values):
                instance = cls.construct(**values)
                result = callback(instance)
                return dict(result.__dict__)

            return validate

        return decorate


def validate_model(model, value):
    """Bind user-defined Pydantic models as well as framework models."""
    if hasattr(model, "model_validate"):
        return model.model_validate(value)
    return model.parse_obj(value)


def required_fields(model):
    if PYDANTIC_V2:
        return any(field.is_required() for field in model.model_fields.values())
    return any(field.required for field in model.__fields__.values())


def get_type_hints(target, *, include_extras=False):
    if sys.version_info >= (3, 9):
        return typing.get_type_hints(target, include_extras=include_extras)
    # Older typing strips Annotated metadata; resolve each annotation without stripping it.
    namespace = getattr(target, "__globals__", {})
    hints = {}
    for name, value in getattr(target, "__annotations__", {}).items():
        if isinstance(value, str):
            value = eval(value, namespace)
        hints[name] = value
    return hints


def create_task(coroutine, *, name=None):
    task = asyncio.ensure_future(coroutine)
    if name is not None and hasattr(task, "set_name"):
        task.set_name(name)
    return task


async def to_thread(callback, *args, **kwargs):
    context = contextvars.copy_context()
    call = functools.partial(context.run, callback, *args, **kwargs)
    return await asyncio.get_event_loop().run_in_executor(None, call)


def run(coroutine):
    if hasattr(asyncio, "run"):
        return asyncio.run(coroutine)
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coroutine)
    finally:
        pending = asyncio.Task.all_tasks(loop)
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.run_until_complete(loop.shutdown_asyncgens())
        asyncio.set_event_loop(None)
        loop.close()


def load_toml(stream):
    if sys.version_info >= (3, 11):
        import tomllib

        return tomllib.load(stream)
    import toml

    return toml.loads(stream.read().decode("utf-8"))


def template_response(templates, request, name, context=None):
    context = dict(context or {})
    context["request"] = request
    if "request" in inspect.signature(templates.TemplateResponse).parameters:
        return templates.TemplateResponse(request=request, name=name, context=context)
    return templates.TemplateResponse(name, context)
