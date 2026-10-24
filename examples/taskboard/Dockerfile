FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE /framework/
COPY src /framework/src
COPY examples/taskboard /app
RUN pip install --no-cache-dir /framework \
    && pip install --no-cache-dir --no-deps . \
    && useradd --create-home appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app/data
USER appuser
ENV YUANBOOT_PROFILE=prod
EXPOSE 8080
CMD ["yuanbootctl", "run"]
