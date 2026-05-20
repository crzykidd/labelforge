# TODO: Slice N — add a multi-stage frontend build stage (node:lts-alpine, npm ci + npm run build)
#        before this runtime stage, then COPY --from=frontend /app/frontend/dist /app/frontend/dist
#        and mount it via FastAPI StaticFiles.

FROM python:3.12-slim

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

RUN chown -R labelforge:labelforge /app
USER labelforge

EXPOSE 8000

CMD ["uvicorn", "labelforge.main:app", "--host", "0.0.0.0", "--port", "8000"]
