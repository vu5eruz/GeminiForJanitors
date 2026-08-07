FROM ghcr.io/astral-sh/uv:0.12.2-python3.13-trixie-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN uv sync --locked --no-dev

COPY gfjproxy ./gfjproxy
COPY presets ./presets

ARG GFJPROXY_BRANCH
ARG GFJPROXY_VERSION

ENV GFJPROXY_BRANCH=${GFJPROXY_BRANCH} \
    GFJPROXY_VERSION=${GFJPROXY_VERSION} \
    PATH="/app/.venv/bin:$PATH" \
    PORT=5000 \
    PYTHONUNBUFFERED=1

EXPOSE 5000

HEALTHCHECK CMD python -c "import httpx2, sys; sys.exit(httpx2.get('http://0.0.0.0:${PORT}/health').is_success)"

CMD exec gunicorn -b 0.0.0.0:${PORT} -k gevent -w 5 -t ${GFJPROXY_PROCESS_TIMEOUT:-300} "gfjproxy.app:create_app()"
