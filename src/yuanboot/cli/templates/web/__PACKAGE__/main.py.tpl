from pathlib import Path

from yuanboot import ConfigurationBuilder
from yuanboot.web import WebHostBuilder

from .startup import Startup

ROOT = Path.cwd()


def create_app():
    builder = (
        ConfigurationBuilder(ROOT)
        .add_yaml_file("config")
        .add_environment()
    )
    bootstrap = builder.build()
    configuration = (builder.add_nacos().build()
                     if bootstrap.get_string("yuanboot.cloud.nacos.data_id") else bootstrap)
    return WebHostBuilder(configuration).use_components().use_startup(Startup()).build().app


app = create_app()


if __name__ == "__main__":
    app.state.host.run()
