yuanboot:
  application:
    name: __PROJECT__
  grpc:
    address: "127.0.0.1:9090"
    shutdown_grace: 5
  logging:
    log_type: zap
    level: INFO
    console: true
