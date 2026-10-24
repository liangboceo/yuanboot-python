from pathlib import Path

import grpc
from google.protobuf.wrappers_pb2 import StringValue

from yuanboot import ConfigurationBuilder
from yuanboot.grpc import GrpcHostBuilder

ROOT = Path.cwd() if (Path.cwd() / "config.yml").is_file() else Path(__file__).resolve().parents[1]


async def hello(request, context):
    return StringValue(value=f"Hello, {request.value}!")


def configure_server(server, services):
    server.add_generic_rpc_handlers((grpc.method_handlers_generic_handler(
        "demo.Greeter", {"Hello": grpc.unary_unary_rpc_method_handler(
            hello, request_deserializer=StringValue.FromString,
            response_serializer=StringValue.SerializeToString)}),))


def create_host():
    config = ConfigurationBuilder(ROOT).add_yaml_file().add_environment().build()
    return GrpcHostBuilder(config).use_components().configure_server(configure_server).build()


if __name__ == "__main__":
    create_host().run()
