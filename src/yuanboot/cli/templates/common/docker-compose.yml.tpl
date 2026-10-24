services:
  app:
    build: .
    ports:
      - "8080:8080"
    environment:
      YUANBOOT_PROFILE: prod
    init: true
    stop_grace_period: 30s
