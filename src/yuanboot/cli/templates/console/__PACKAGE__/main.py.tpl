from pathlib import Path

from yuanboot import ConfigurationBuilder
from yuanboot.console import HostBuilder

from .worker import Worker


def create_host():
    builder = (
        ConfigurationBuilder(Path.cwd())
        .add_yaml_file("config")
        .add_environment()
    )
    bootstrap = builder.build()
    configuration = (builder.add_nacos().build()
                     if bootstrap.get_string("yuanboot.cloud.nacos.data_id") else bootstrap)
    return (
        HostBuilder(configuration)
        .use_components()
        .configure_services(lambda services: services.add_hosted_service(Worker))
        .build()
    )


if __name__ == "__main__":
    create_host().run()
