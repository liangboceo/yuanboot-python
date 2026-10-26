yuanboot:
  application:
    name: __PROJECT__-server
    server:
      address: ":8090"
  logging:
    log_type: zap
    color: auto
    banner: true
    level: INFO
    json: false
    console: true
greeting:
  message: "Hello from __PROJECT__"

admin:
  database_url: "${ADMIN_DATABASE_URL:sqlite:///./data/admin.db}"
  jwt_secret: "${ADMIN_JWT_SECRET:__ADMIN_JWT_SECRET__}"
  initial_password: "${ADMIN_PASSWORD:admin123}"
  access_ttl: 43200
  refresh_ttl: 604800
  cache_prefix: "__PROJECT__:"
