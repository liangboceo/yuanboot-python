FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home appuser
USER appuser
ENV YUANBOOT_PROFILE=pro
EXPOSE 8080
CMD ["yuanbootctl-python", "run"]
