# 合并到 config_fat.yml / config_uat.yml / config_pro.yml；连接信息从环境读取。
yuanboot:
  datasource:
    mysql:
      host: "${MYSQL_HOST}"
      port: 3306
      database: "${MYSQL_DATABASE}"
      username: "${MYSQL_USERNAME}"
      password: "${MYSQL_PASSWORD}"
    redis:
      url: "${REDIS_URL:redis://127.0.0.1:6379}"
      password: "${REDIS_PASSWORD}"
      db: 0
      prefix: "__PROJECT__:"
admin:
  cache_prefix: "__PROJECT__:"
