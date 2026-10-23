# ==============================================================================
# Multi-stage production Dockerfile for GateForge Gateway
# ==============================================================================

# Stage 1: Build & dependency resolution
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --no-cache-dir --upgrade pip build \
    && python -m build --wheel --outdir dist/

# Stage 2: Minimal hardened runtime
FROM python:3.12-slim AS runtime

LABEL maintainer="GateForge Engineering Team <engineering@gateforge.io>"
LABEL description="High-Throughput API Key Gateway, Auth Cache & Sliding-Window Rate Limiter"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged application user
RUN groupadd -g 10001 gateforge && \
    useradd -u 10001 -g gateforge -s /bin/bash -m gateforge

# Copy and install pre-built wheel from builder stage
COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm -rf /tmp/*.whl

# Copy Alembic migration files for automated startup migrations if enabled
COPY alembic.ini ./
COPY alembic/ ./alembic/

USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health/live || exit 1

ENTRYPOINT ["uvicorn", "gateforge.main:app", "--host", "0.0.0.0", "--port", "8000"]
