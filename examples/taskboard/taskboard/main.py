from pathlib import Path

from yuanboot import Configuration, ConfigurationBuilder
from yuanboot.web import WebHostBuilder

from .startup import Startup


def create_app(configuration: Configuration | None = None):
    if configuration is None:
        directory = Path.cwd()
        source_project = Path(__file__).resolve().parent.parent
        if not (directory / "config.yml").is_file() and (source_project / "config.yml").is_file():
            directory = source_project
        builder = ConfigurationBuilder(directory).add_yaml_file("config").add_environment()
        bootstrap = builder.build()
        configuration = (
            builder.add_nacos().build()
            if bootstrap.get_string("yuanboot.cloud.nacos.data_id")
            else bootstrap
        )
    return (
        WebHostBuilder(
            configuration,
            description="基于 yuanboot MVC 的任务管理服务，支持 SQLite / MySQL / Redis / Nacos",
        )
        .use_components()
        .use_startup(Startup(configuration))
        .build()
        .app
    )


app = create_app()


if __name__ == "__main__":
    app.state.host.run()
