FROM python:3.12-slim

WORKDIR /app

# System deps:
#   - build-essential, libpq-dev: needed by bcrypt + psycopg2 pip wheels
#   - g++, gcc: code executor compiles & runs C++ snippets
#   - nodejs:   code executor runs JavaScript snippets
#   - bash:     code executor runs shell snippets (already in slim, but explicit)
#   - git:      "Import a repository" (workspace_files.import_repo)
#   - curl:     used by container healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev g++ gcc bash git curl ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Docker CLI only (no daemon) — lets the backend manage real per-workspace
# containers through the host's mounted /var/run/docker.sock.
RUN curl -fsSL https://download.docker.com/linux/static/stable/x86_64/docker-27.3.1.tgz \
      -o /tmp/docker.tgz \
    && tar -xzf /tmp/docker.tgz -C /tmp \
    && mv /tmp/docker/docker /usr/local/bin/docker \
    && rm -rf /tmp/docker /tmp/docker.tgz \
    && docker --version

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
