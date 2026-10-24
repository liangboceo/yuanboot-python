from yuanboot import ServiceCollection
from yuanboot.web import ApplicationBuilder
from yuanboot.web.endpoints import use_actuator


class Startup:
    def configure_services(self, services: ServiceCollection):
        pass

    def configure(self, app: ApplicationBuilder):
        app.use_endpoints(use_actuator)

        @app.router.get("/")
        def index():
            return {"message": "Hello from __PROJECT__"}
