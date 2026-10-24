import asyncio

import httpx
from fastapi.testclient import TestClient

from yuanboot import Configuration
from yuanboot.components.xxljob import XxlJobExecutor, XxlJobOptions, use_xxl_job
from yuanboot.web import WebHostBuilder


def test_xxl_job_auth_execution_logs_callback_and_cleanup(tmp_path):
    async def scenario():
        requests = []
        done = asyncio.Event()

        async def job(context):
            context.report("parameter=" + context.parameter)
            done.set()
            return "completed"

        async def handler(request):
            requests.append(request)
            assert request.headers["XXL-JOB-ACCESS-TOKEN"] == "test-token"
            return httpx.Response(200, json={"code": 200})

        executor = XxlJobExecutor(
            XxlJobOptions(
                admin_url="http://admin/xxl-job-admin",
                access_token="test-token",
                log_dir=tmp_path,
                registry_interval=0.01,
            ),
            {"probe": job},
            transport=httpx.MockTransport(handler),
        )
        await executor.start()
        try:
            assert (
                await executor.dispatch(
                    "run",
                    {"jobId": 1, "logId": 2, "executorHandler": "probe", "executorParams": "hello"},
                )
            )["code"] == 200
            await asyncio.wait_for(done.wait(), timeout=1)
            await executor._running[1]
            logs = await executor.dispatch("log", {"logId": 2, "fromLineNum": 1})
            assert logs["content"]["isEnd"]
            assert "parameter=hello" in logs["content"]["logContent"]
        finally:
            await executor.stop()
        assert any(request.url.path.endswith("/callback") for request in requests)
        assert requests[-1].url.path.endswith("/registryRemove")

    asyncio.run(scenario())

    config = Configuration(
        {
            "yuanboot": {
                "application": {"xxl": {"access_token": "test-token", "log_dir": str(tmp_path)}}
            }
        }
    )

    async def job(context):
        return "done"

    host = use_xxl_job(WebHostBuilder(config), {"test": job}).build()
    with TestClient(host.app) as client:
        assert client.post("/xxl-job/beat", json={}).json()["code"] == 500
        assert (
            client.post(
                "/xxl-job/beat", json={}, headers={"XXL-JOB-ACCESS-TOKEN": "test-token"}
            ).json()["code"]
            == 200
        )
