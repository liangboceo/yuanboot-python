from pathlib import Path

from yuanboot import ServiceCollection
from yuanboot.web import ApplicationBuilder
from yuanboot.web.endpoints import use_actuator

from .controllers import GreetingController, GreetingService, HomeController

ROOT = Path(__file__).resolve().parent


class Startup:
    def configure_services(self, services: ServiceCollection):
        services.add_scoped(GreetingService)

    def configure(self, app: ApplicationBuilder):
        app.use_endpoints(use_actuator)
        app.use_views(ROOT / "templates")
        app.use_mvc(lambda mvc: mvc.add_controller(GreetingController).add_controller(HomeController))
