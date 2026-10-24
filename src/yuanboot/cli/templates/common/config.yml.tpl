yuanboot:
  application:
    name: __PROJECT__
    server:
      address: ":8080"
  logging:
    log_type: zap
    level: INFO
    json: false
    console: true
greeting:
  message: "Hello from __PROJECT__"
