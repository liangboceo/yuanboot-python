import asyncio

from google.protobuf.wrappers_pb2 import StringValue
from yuanboot.grpc import GrpcClientFactory, GrpcServer

from __PACKAGE__.main import create_host


def test_greeter(monkeypatch):
    monkeypatch.setenv("YUANBOOT_YUANBOOT__GRPC__ADDRESS", "127.0.0.1:0")
    async def run():
        host = create_host()
        await host.start()
        factory = GrpcClientFactory()
        try:
            port = host.services.get_service(GrpcServer).port
            channel = factory.create(f"127.0.0.1:{port}")
            call = channel.unary_unary("/demo.Greeter/Hello",
                request_serializer=StringValue.SerializeToString,
                response_deserializer=StringValue.FromString)
            assert (await call(StringValue(value="yuanboot"), timeout=2)).value == "Hello, yuanboot!"
        finally:
            await factory.aclose()
            await host.stop()
    asyncio.run(run())
