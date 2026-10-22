# syntax=docker/dockerfile:1
# Build from the project root: docker compose build  (or: docker build -f docker/Dockerfile .)
#
# The model is NOT baked in. On start the app downloads it into PII_MODEL_DIR (a named volume
# in compose.yaml) unless it is already there, so later starts and rebuilds reuse it.

FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Python dependencies, pinned by uv.lock. Cached unless pyproject.toml or uv.lock change.
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# /models is created here, owned by the app user, so a fresh named volume inherits that owner.
RUN useradd --create-home --uid 1000 app \
 && mkdir /models && chown app:app /models
USER app

ENV PATH=/app/.venv/bin:$PATH \
    PII_MODEL_DIR=/models \
    PYTHONUNBUFFERED=1 \
    GRADIO_SERVER_NAME=0.0.0.0 \
    GRADIO_SERVER_PORT=7860 \
    GRADIO_ANALYTICS_ENABLED=False

EXPOSE 7860

# Generous start period: the first start downloads the model (~1.6 GB) before serving.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15m \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/', timeout=4)"

CMD ["pii-info-mask"]
