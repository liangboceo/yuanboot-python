from fastapi import Request
from starlette.responses import JSONResponse, RedirectResponse

from yuanboot import Configuration, ServiceCollection
from yuanboot.web import ApplicationBuilder
from yuanboot.web.endpoints import use_actuator

from .controllers import TaskController
from .database import DatabaseInitializer, DatabaseSession
from .repository import TaskRepository
from .services import TaskNotFoundError, TaskService


class Startup:
    def __init__(self, configuration: Configuration):
        self.configuration = configuration

    def configure_services(self, services: ServiceCollection):
        if self.configuration.get("yuanboot.datasource.mysql") is not None:
            from .cloud import CachedTaskService, MySqlSchemaInitializer, MySqlTaskRepository

            services.add_hosted_service(MySqlSchemaInitializer)
            services.add_scoped(TaskRepository, MySqlTaskRepository)
            services.add_scoped(TaskService, CachedTaskService)
        else:
            services.add_hosted_service(DatabaseInitializer)
            services.add_scoped(DatabaseSession)
            services.add_scoped(TaskRepository)
            services.add_scoped(TaskService)

    def configure(self, app: ApplicationBuilder):
        app.use_endpoints(use_actuator)
        app.use_mvc(lambda mvc: mvc.add_controller(TaskController))

        @app.router.get("/", include_in_schema=False)
        def index():
            return RedirectResponse("/docs")

        @app.router.get("/api/runtime", tags=["运行配置"])
        def runtime():
            return {
                "profile": self.configuration.profile,
                "message": self.configuration.get_string("demo.message", "Taskboard is running"),
                "configuration_version": self.configuration.version,
            }

        @app.app.exception_handler(TaskNotFoundError)
        async def not_found(request: Request, exc: TaskNotFoundError):
            return JSONResponse(
                {"success": False, "message": "任务不存在", "data": None}, status_code=404
            )
