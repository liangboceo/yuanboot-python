services:
  app:
    build: .
    ports:
      - "8090:8090"
    environment:
      YUANBOOT_PROFILE: pro
      ADMIN_JWT_SECRET: ${ADMIN_JWT_SECRET:?Set a secret with at least 32 characters}
      ADMIN_PASSWORD: ${ADMIN_PASSWORD:?Set a strong initial administrator password}
    volumes:
      - admin-data:/app/data
    init: true
    stop_grace_period: 30s
volumes:
  admin-data:
