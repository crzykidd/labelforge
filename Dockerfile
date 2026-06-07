FROM node:lts-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.14-slim

# Unbuffered stdout/stderr so startup logs appear immediately (critical for
# diagnosing a crash-on-start) and never get lost in a buffer on a fast restart.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# System fonts required by render/text.py; Pillow wheels include libjpeg/zlib.
RUN apt-get update && apt-get install -y --no-install-recommends \
        fonts-dejavu-core \
        fonts-liberation2 \
        fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

# Non-root runtime user (uid 1000).
RUN useradd -u 1000 -m labelforge

WORKDIR /app

# Install Python dependencies + the labelforge package (editable so the source
# at /app/backend/labelforge/ is authoritative — enables bind-mount hot-reload
# in compose.dev.yml without rebuilding the image).
COPY pyproject.toml README.md ./
COPY backend/ backend/
RUN pip install --no-cache-dir -e .

# Default label catalog shipped in the image.  At startup, if
# ${DATA_DIR}/labels.yml is absent, main.py copies this into the volume.
COPY labels.yml /app/labels.yml
COPY --from=frontend /app/frontend/dist /app/frontend/dist

# Create the data dir and hand it to the runtime user. A *named volume* inherits
# this ownership (uid 1000), so it works out of the box. A *bind mount* keeps the
# host directory's ownership — that host path must be writable by uid 1000, or
# startup will fail with a clear "DATA_DIR not writable" message.
RUN mkdir -p /data && chown -R labelforge:labelforge /app /data

USER labelforge

EXPOSE 8000

CMD ["uvicorn", "labelforge.main:app", "--host", "0.0.0.0", "--port", "8000"]
