FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

RUN useradd -r -s /usr/sbin/nologin -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

ENV HOST=0.0.0.0 PORT=8000 UV_NO_SYNC=true
EXPOSE 8000
HEALTHCHECK CMD curl -sf -o /dev/null -w '%{http_code}' http://localhost:8000/ | grep -qE '200|404|406'
CMD ["sh", "-c", "uv run uvicorn mcps.server:jackett --host 0.0.0.0 --port $PORT"]
