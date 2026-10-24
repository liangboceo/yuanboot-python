"""XXL-Job BEAN executor HTTP protocol integrated with the web host."""

from __future__ import annotations

import asyncio
import hmac
import logging
from dataclasses import dataclass
from pathlib import Path

import httpx
from fastapi import Request
from pydantic import AliasChoices, BaseModel, Field, SecretStr

from yuanboot.configuration import Configuration
from yuanboot.hosting import HostedService

logger = logging.getLogger("yuanboot.xxljob")


class XxlJobOptions(BaseModel):
    admin_url: str = Field(default="", validation_alias=AliasChoices("admin_url", "serveraddr"))
    access_token: SecretStr = Field(
        default=SecretStr(""), validation_alias=AliasChoices("access_token", "accesstoken")
    )
    registry_key: str = Field(
        default="yuanboot", validation_alias=AliasChoices("registry_key", "registrykey")
    )
    executor_url: str = "http://127.0.0.1:8080/xxl-job/"
    log_dir: Path = Path("logs/xxljob")
    timeout: float = Field(default=5, gt=0)
    registry_interval: float = Field(default=20, gt=0, lt=30)


@dataclass
class JobContext:
    job_id: int
    log_id: int
    parameter: str
    shard_index: int
    shard_total: int
    _path: Path

    def report(self, message: str):
        with self._path.open("a", encoding="utf-8") as stream:
            stream.write(message + "\n")


class XxlJobExecutor(HostedService):
    """BEAN handlers are async callables receiving JobContext; kill cancels cooperatively."""

    def __init__(self, options: XxlJobOptions, handlers: dict, *, transport=None):
        self.options, self.handlers = options, dict(handlers)
        self._running: dict[int, asyncio.Task] = {}
        self._finished = set()
        self._registry_task = None
        self._pending_callbacks = []
        self._client = httpx.AsyncClient(
            timeout=options.timeout, transport=transport, trust_env=False
        )

    async def _admin(self, method, payload):
        if not self.options.admin_url:
            return
        headers = {"XXL-JOB-ACCESS-TOKEN": self.options.access_token.get_secret_value()}
        response = await self._client.post(
            self.options.admin_url.rstrip("/") + "/api/" + method, headers=headers, json=payload
        )
        if not response.is_success or response.json().get("code") != 200:
            raise RuntimeError("XXL-Job admin request failed")

    def _registry(self):
        return {
            "registryGroup": "EXECUTOR",
            "registryKey": self.options.registry_key,
            "registryValue": self.options.executor_url,
        }

    async def _register(self):
        while True:
            try:
                await self._admin("registry", self._registry())
                if self._pending_callbacks:
                    batch = list(self._pending_callbacks)
                    await self._admin("callback", batch)
                    del self._pending_callbacks[: len(batch)]
            except Exception:
                logger.warning("XXL-Job admin unavailable; will retry")
            await asyncio.sleep(self.options.registry_interval)

    async def start(self):
        self.options.log_dir.mkdir(parents=True, exist_ok=True)
        if self.options.admin_url:
            self._registry_task = asyncio.create_task(self._register())

    async def stop(self):
        if self._registry_task:
            self._registry_task.cancel()
            await asyncio.gather(self._registry_task, return_exceptions=True)
        for task in self._running.values():
            task.cancel()
        await asyncio.gather(*self._running.values(), return_exceptions=True)
        try:
            if self.options.admin_url:
                if self._pending_callbacks:
                    await self._admin("callback", self._pending_callbacks)
                await self._admin("registryRemove", self._registry())
        finally:
            await self._client.aclose()

    async def _execute(self, payload):
        job_id, log_id = int(payload["jobId"]), int(payload["logId"])
        context = JobContext(
            job_id,
            log_id,
            payload.get("executorParams", ""),
            int(payload.get("broadcastIndex", 0)),
            int(payload.get("broadcastTotal", 1)),
            self.options.log_dir / f"{log_id}.log",
        )
        code, message = 200, "success"
        try:
            handler = self.handlers[payload["executorHandler"]]
            # Cancellation of a thread cannot stop its work; require async BEAN handlers.
            message = str(await handler(context) or "success")
            context.report(message)
        except asyncio.CancelledError:
            code, message = 500, "cancelled"
            context.report(message)
        except Exception:
            code, message = 500, "handler failed"
            context.report(message)
            logger.exception("XXL-Job handler failed: %s", payload["executorHandler"])
        finally:
            self._finished.add(log_id)
            self._pending_callbacks.append(
                {
                    "logId": log_id,
                    "logDateTim": payload.get("logDateTime", 0),
                    "handleCode": code,
                    "handleMsg": message,
                }
            )

    async def dispatch(self, action, payload):
        ok = {"code": 200, "msg": ""}
        if action == "beat":
            return ok
        if action in {"idleBeat", "kill", "run"}:
            job_id = int(payload["jobId"])
            task = self._running.get(job_id)
            busy = task is not None and not task.done()
            if action == "idleBeat":
                return {"code": 500, "msg": "job is running"} if busy else ok
            if action == "kill":
                if busy:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                return ok
            if payload.get("glueType", "BEAN") != "BEAN":
                return {"code": 500, "msg": "Only BEAN handlers are supported"}
            if payload.get("executorHandler") not in self.handlers:
                return {"code": 500, "msg": "Unknown executorHandler"}
            if busy:
                return {"code": 500, "msg": "job is running; retry later"}
            int(payload["logId"])
            self._running[job_id] = asyncio.create_task(self._execute(payload))
            return ok
        if action == "log":
            log_id, start = int(payload["logId"]), max(1, int(payload.get("fromLineNum", 1)))
            path = self.options.log_dir / f"{log_id}.log"
            lines = (
                await asyncio.to_thread(path.read_text, encoding="utf-8") if path.exists() else ""
            )
            lines = lines.splitlines()
            return {
                **ok,
                "content": {
                    "fromLineNum": start,
                    "toLineNum": len(lines),
                    "logContent": "\n".join(lines[start - 1 :]),
                    "isEnd": log_id in self._finished,
                },
            }
        return {"code": 500, "msg": "Unknown action"}


def use_xxl_job(builder, handlers: dict, *, prefix="/xxl-job"):
    import inspect

    if any(not inspect.iscoroutinefunction(handler) for handler in handlers.values()):
        raise ValueError("XXL-Job handlers must be async callables")

    def services(collection):
        def factory(configuration: Configuration):
            values = configuration.get("yuanboot.application.xxl", {})
            values.setdefault("registry_key", configuration.get_string("yuanboot.application.name"))
            return XxlJobExecutor(XxlJobOptions.model_validate(values), handlers)

        collection.add_hosted_service(XxlJobExecutor)
        collection.add_singleton(XxlJobExecutor, factory)

    def configure(app):
        async def endpoint(action: str, request: Request):
            executor = request.app.state.services.get_service(XxlJobExecutor)
            expected = executor.options.access_token.get_secret_value()
            actual = request.headers.get("XXL-JOB-ACCESS-TOKEN", "")
            if not hmac.compare_digest(expected.encode(), actual.encode()):
                return {"code": 500, "msg": "Invalid access token"}
            try:
                return await executor.dispatch(action, await request.json())
            except (ValueError, KeyError, TypeError):
                return {"code": 500, "msg": "Invalid request"}

        app.router.add_api_route(
            prefix.rstrip("/") + "/{action}", endpoint, methods=["POST"], include_in_schema=False
        )

    return builder.configure_services(services).configure(configure)
