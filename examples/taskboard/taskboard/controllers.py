from typing import Annotated
from uuid import UUID

from fastapi import Query
from starlette.responses import Response

from yuanboot.web import ApiController, ApiResult, controller, route

from .models import Task, TaskCreate, TaskPage, TaskStats, TaskStatus, TaskUpdate
from .services import TaskService


@controller("/api/tasks", tags=["任务管理"])
class TaskController(ApiController):
    def __init__(self, service: TaskService):
        self.service = service

    @route("", methods=["POST"], status_code=201, summary="创建任务")
    def create(self, body: TaskCreate) -> ApiResult[Task]:
        return self.ok(self.service.create(body), "任务已创建")

    @route("", summary="分页查询任务")
    def list(
        self,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = 20,
        status: TaskStatus | None = None,
        q: Annotated[str, Query(max_length=200)] = "",
    ) -> ApiResult[TaskPage]:
        return self.ok(self.service.list(page, page_size, status, q))

    @route("/stats", summary="任务状态统计")
    def stats(self) -> ApiResult[TaskStats]:
        return self.ok(self.service.stats())

    @route("/{task_id}", summary="获取任务详情")
    def get(self, task_id: UUID) -> ApiResult[Task]:
        return self.ok(self.service.get(task_id))

    @route("/{task_id}", methods=["PATCH"], summary="更新任务")
    def update(self, task_id: UUID, body: TaskUpdate) -> ApiResult[Task]:
        return self.ok(self.service.update(task_id, body), "任务已更新")

    @route(
        "/{task_id}",
        methods=["DELETE"],
        status_code=204,
        response_class=Response,
        summary="删除任务",
    )
    def delete(self, task_id: UUID) -> Response:
        self.service.delete(task_id)
        return Response(status_code=204)
