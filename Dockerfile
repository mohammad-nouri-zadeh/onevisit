# syntax=docker/dockerfile:1.7
# Un'unica immagine per tutti i servizi: cambia solo il comando di avvio (vedi compose.yaml).

ARG PYTHON_VERSION=3.13

# ---------------------------------------------------------------- base
FROM python:${PYTHON_VERSION}-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /uvx /usr/local/bin/
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"
WORKDIR /app

# ---------------------------------------------------------------- build
FROM base AS build
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --all-packages

# ---------------------------------------------------------------- runtime
FROM base AS runtime
RUN groupadd --system --gid 1000 onevisit \
 && useradd --system --uid 1000 --gid onevisit --home-dir /app onevisit
COPY --from=build --chown=onevisit:onevisit /opt/venv /opt/venv
COPY --from=build --chown=onevisit:onevisit /app /app
USER onevisit
EXPOSE 8000
CMD ["uvicorn", "assistant_web.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ---------------------------------------------------------------- test
# Dipendenze di sviluppo incluse: lint, tipi, test. Usata da `make test` e dalla CI.
FROM base AS test
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --all-packages
CMD ["sh", "scripts/check.sh"]

# ---------------------------------------------------------------- e2e
# Come test, piu' Playwright e Chromium per il percorso demo (storia D4).
FROM test AS e2e
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --all-packages --group e2e \
 && uv run playwright install --with-deps chromium
CMD ["uv", "run", "pytest", "-m", "e2e", "e2e"]
