# =============================================================================
# Morphic-Agent Backend — Multi-stage Production Dockerfile
# =============================================================================
# Build:  docker build -t morphic-agent-api .
# Run:    docker run -p 8000:8000 --env-file .env morphic-agent-api
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Build dependencies
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

# Install uv (fast Python package manager)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock CLAUDE.md ./

# Install production dependencies only (no dev extras)
# --frozen ensures uv.lock is respected exactly
RUN uv sync --frozen --no-dev --no-install-project

# Copy source code packages
COPY domain/ domain/
COPY application/ application/
COPY infrastructure/ infrastructure/
COPY interface/ interface/
COPY shared/ shared/
COPY migrations/ migrations/

# Install the project itself (editable is not needed in prod)
RUN uv sync --frozen --no-dev

# ---------------------------------------------------------------------------
# Stage 2: Production runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --gid 1000 morphic \
    && useradd --uid 1000 --gid morphic --create-home morphic

WORKDIR /app

# Copy the virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy source code
COPY --from=builder /app/domain/ domain/
COPY --from=builder /app/application/ application/
COPY --from=builder /app/infrastructure/ infrastructure/
COPY --from=builder /app/interface/ interface/
COPY --from=builder /app/shared/ shared/
COPY --from=builder /app/migrations/ migrations/
COPY --from=builder /app/pyproject.toml pyproject.toml

# Create directories for runtime data
RUN mkdir -p .morphic && chown -R morphic:morphic /app

# Ensure the venv Python is on PATH
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

USER morphic

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8001/api/health || exit 1

CMD ["uvicorn", "interface.api.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "2"]
