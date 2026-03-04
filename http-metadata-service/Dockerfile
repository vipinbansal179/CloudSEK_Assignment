# =============================================================================
# HTTP Metadata Inventory Service — Dockerfile
# Multi-stage build for a lean, secure production image.
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Builder — Install dependencies
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

# Install dependencies in a virtual environment for clean copy
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements first for Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------------------
# Stage 2: Runtime — Lean production image
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

# Metadata labels
LABEL maintainer="developer" \
      description="HTTP Metadata Inventory Service" \
      version="1.0.0"

# Security: run as non-root user
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /home/appuser/service

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Copy application source code
COPY ./app ./app

# Change ownership to non-root user
RUN chown -R appuser:appgroup /home/appuser/service

# Switch to non-root user
USER appuser

# Expose API port
EXPOSE 8000

# Health check — verifies the service is responding
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health')" || exit 1

# Start the application with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]