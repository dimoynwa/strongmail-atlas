# StrongMail Agent Studio — FastAPI
#
# Default config comes from .env (copied from .env.example at build time).
# Override at runtime with -e VAR=value or by mounting a different env file:
#
#   docker build -t strongmail-api .
#   docker run --rm -p 8000:8000 strongmail-api
#
#   docker run --rm -p 8000:8000 --env-file .env strongmail-api
#   docker run --rm -p 8000:8000 -e DATABASE_URL=postgresql://... strongmail-api
#   docker run --rm -p 8000:8000 -e ENV_FILE=/config/.env -v $(pwd)/.env:/config/.env:ro strongmail-api
#
# Build with your local .env as the baked default (requires BuildKit; .env is gitignored):
#   DOCKER_BUILDKIT=1 docker build --secret id=env,src=.env --build-arg ENV_SOURCE=/run/secrets/env -t strongmail-api .
# Or mount at runtime (recommended):
#   docker run -v $(pwd)/.env:/app/.env:ro ...

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    ENV_FILE=/app/.env \
    PORT=8000 \
    HOST=0.0.0.0 \
    OTEL_SDK_DISABLED=true

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install uv and project dependencies from lockfile.
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv \
    && uv sync --frozen
ENV PATH="/app/.venv/bin:${PATH}"

# Application code
COPY api ./api
COPY shared ./shared
COPY template_assistant ./template_assistant
COPY general_agent ./general_agent
COPY docker/api-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Default env file (.env is gitignored — use .env.example unless ENV_SOURCE is passed).
ARG ENV_SOURCE=.env.example
COPY ${ENV_SOURCE} .env

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:8000/health" | grep -q '"status"' || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
