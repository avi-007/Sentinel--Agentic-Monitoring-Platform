# Build context is repo root (see docker-compose.yml) so this can COPY common/.
FROM python:3.12-slim

WORKDIR /app

COPY requirements-common.txt ./
COPY services/generator/requirements.txt ./requirements-service.txt
RUN pip install --no-cache-dir -r requirements-common.txt -r requirements-service.txt

COPY common/ ./common/
COPY services/generator/app/ ./app/

CMD ["python", "-m", "app.main"]
