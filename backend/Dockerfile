# Production Dockerfile for DToxOut FastAPI backend
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/appuser \
    PRISMA_BINARY_CACHE_DIR=/home/appuser/.cache/prisma-python

# System deps: Tesseract OCR engine, libpq, curl (healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-eng libpq5 curl ca-certificates \
        libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Non-root user (created before prisma so its binaries live in appuser's cache)
RUN useradd -m -u 10001 appuser
WORKDIR /app

COPY requirements.txt requirements-cloud.txt ./
ARG STORAGE_EXTRAS=""
RUN pip install -r requirements.txt \
    && if [ "$STORAGE_EXTRAS" = "azure" ]; then pip install azure-storage-blob; fi \
    && if [ "$STORAGE_EXTRAS" = "s3" ]; then pip install boto3; fi

COPY --chown=appuser:appuser . .
RUN mkdir -p uploads && chown -R appuser:appuser /app \
    && chmod +x docker-entrypoint.sh

USER appuser

# Generate Prisma client + download query engine as appuser
RUN prisma generate

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:${PORT:-8000}/health/live || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
