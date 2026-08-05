FROM python:3.13-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:0.12.2-python3.13-trixie /uv /uvx /bin/

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        redis-server \
    ; \
    apt-get dist-clean

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN uv sync --locked --no-dev

ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

COPY gfjproxy ./gfjproxy
COPY presets ./presets

ENV GFJPROXY_REDIS_URL=redis://127.0.0.1:6379/0 \
    GFJPROXY_XUID_SECRET=TODO_REPLACE_THIS_WITH_A_GENERATED_RANDOM_STRING \
    GFJPROXY_PROCESS_TIMEOUT=300 \
    PORT=5000 \
    PYTHONUNBUFFERED=1

EXPOSE 5000

CMD redis-server --maxmemory-policy allkeys-lru --daemonize yes && \
    exec gunicorn -b 0.0.0.0:${PORT} -k gevent -w 5 -t ${GFJPROXY_PROCESS_TIMEOUT} "gfjproxy.app:create_app()"
