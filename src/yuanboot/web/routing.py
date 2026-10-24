from contextlib import contextmanager

from fastapi import APIRouter


class RouterBuilder(APIRouter):
    @contextmanager
    def group(self, prefix: str, **kwargs):
        router = RouterBuilder(prefix=prefix, **kwargs)
        yield router
        self.include_router(router)
