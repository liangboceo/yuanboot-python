from yuanboot import ServiceCollection
from yuanboot.web import ApplicationBuilder

from .endpoints import register_endpoints
from .services import GreetingService


class Startup:
    def configure_services(self, services: ServiceCollection):
        services.add_scoped(GreetingService)

    def configure(self, app: ApplicationBuilder):
        app.use_endpoints(register_endpoints)
