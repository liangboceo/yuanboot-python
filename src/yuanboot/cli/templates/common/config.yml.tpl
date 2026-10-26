yuanboot:
  application:
    name: __PROJECT__
    server:
      address: ":8080"
  logging:
    log_type: zap
    color: auto
    banner: true
    level: INFO
    json: false
    console: true
greeting:
  message: "Hello from __PROJECT__"
