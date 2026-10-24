import asyncio

import grpc
from google.protobuf.wrappers_pb2 import StringValue
from grpc_health.v1 import health_pb2, health_pb2_grpc

from yuanboot import Configuration
from yuanboot.grpc import GrpcClientFactory, GrpcHostBuilder, GrpcServer


def test_real_grpc_request_health_and_host_shutdown():
    async def scenario():
        async def greet(request, context):
            return StringValue(value=f"hello {request.value}")

        def configure(server, services):
            server.add_generic_rpc_handlers(
                (
                    grpc.method_handlers_generic_handler(
                        "sample.Greeter",
                        {
                            "Hello": grpc.unary_unary_rpc_method_handler(
                                greet,
                                request_deserializer=StringValue.FromString,
                                response_serializer=StringValue.SerializeToString,
                            )
                        },
                    ),
                )
            )

        host = GrpcHostBuilder(Configuration({"yuanboot": {"grpc": {"address": "127.0.0.1:0"}}}))
        host = host.configure_server(configure).build()
        await host.start()
        factory = GrpcClientFactory()
        channel = factory.create(f"127.0.0.1:{host.services.get_service(GrpcServer).port}")
        try:
            call = channel.unary_unary(
                "/sample.Greeter/Hello",
                request_serializer=StringValue.SerializeToString,
                response_deserializer=StringValue.FromString,
            )
            response = await call(StringValue(value="yuanboot"), timeout=2)
            assert response.value == "hello yuanboot"
            status = await health_pb2_grpc.HealthStub(channel).Check(
                health_pb2.HealthCheckRequest(), timeout=2
            )
            assert status.status == health_pb2.HealthCheckResponse.SERVING
        finally:
            await factory.aclose()
            await host.stop()
        assert not host.services._owned

    asyncio.run(scenario())
