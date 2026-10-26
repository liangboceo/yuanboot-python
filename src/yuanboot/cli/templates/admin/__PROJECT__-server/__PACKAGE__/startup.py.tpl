from yuanboot import ServiceCollection
from yuanboot.web import ApplicationBuilder
from yuanboot.web.endpoints import use_actuator

from .cache import Cache
from .controllers import configure_errors, router
from .database import Database, DatabaseLifecycle
from .security import Security
from .services import SystemLifecycle, SystemService


class Startup:
    def configure_services(self, services: ServiceCollection):
        services.add_singleton(Database)
        services.add_singleton(Cache)
        services.add_singleton(Security)
        services.add_singleton(SystemService)
        services.add_hosted_service(DatabaseLifecycle)
        services.add_hosted_service(SystemLifecycle)

    def configure(self, app: ApplicationBuilder):
        app.use_endpoints(use_actuator)
        app.app.include_router(router)
        configure_errors(app.app)
