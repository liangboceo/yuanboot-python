FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir . && useradd --create-home appuser \
    && mkdir -p /app/data && chown -R appuser:appuser /app
USER appuser
ENV YUANBOOT_PROFILE=pro
EXPOSE 8090
CMD ["yuanbootctl-python", "run"]
