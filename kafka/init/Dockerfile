# Build context is repo root (see docker-compose.yml) so this can COPY common/.
FROM python:3.12-slim

WORKDIR /app

COPY requirements-common.txt ./
RUN pip install --no-cache-dir -r requirements-common.txt

COPY common/ ./common/
COPY kafka/init/create_topics.py ./create_topics.py

CMD ["python", "create_topics.py"]
