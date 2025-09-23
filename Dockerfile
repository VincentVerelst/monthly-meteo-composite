# syntax=docker/dockerfile:1.6

# -------- Build stage --------
FROM ghcr.io/astral-sh/uv:0.8-debian-slim AS build
SHELL ["sh", "-exc"]

ARG pythonVersion=python3.11

WORKDIR /app

# uv environment
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON=${pythonVersion} \
    UV_HTTP_TIMEOUT=1000 \
    UV_PYTHON_INSTALL_DIR=/app \
    UV_PYTHON_PREFERENCE=only-managed \
    UV_INDEX_URL=https://pypi.org/simple

# --- deps only (good layer cache) ---
# Use secrets for private index creds; don't keep them as ARG/ENV.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=/app/uv.lock,ro \
    --mount=type=bind,source=pyproject.toml,target=/app/pyproject.toml,ro \
    --mount=type=secret,id=VITO_USER \
    --mount=type=secret,id=VITO_TOKEN \
    sh -exc '\
      export UV_INDEX_VITO_ARTIFACTORY_USERNAME="$(cat /run/secrets/VITO_USER 2>/dev/null || true)"; \
      export UV_INDEX_VITO_ARTIFACTORY_PASSWORD="$(cat /run/secrets/VITO_TOKEN 2>/dev/null || true)"; \
      uv sync --locked --no-install-project --no-group dev \
    '

# --- add source and install the project into the venv ---
COPY src /app/src

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=/app/uv.lock,ro \
    --mount=type=bind,source=pyproject.toml,target=/app/pyproject.toml,ro \
    --mount=type=secret,id=VITO_USER \
    --mount=type=secret,id=VITO_TOKEN \
    sh -exc '\
      export UV_INDEX_VITO_ARTIFACTORY_USERNAME="$(cat /run/secrets/VITO_USER 2>/dev/null || true)"; \
      export UV_INDEX_VITO_ARTIFACTORY_PASSWORD="$(cat /run/secrets/VITO_TOKEN 2>/dev/null || true)"; \
      uv sync --locked --no-group dev \
    '

# -------- Runtime stage --------
FROM ghcr.io/osgeo/gdal:ubuntu-small-3.11.3 AS production
SHELL ["sh", "-exc"]
WORKDIR /app

# Copy the fully managed Python + venv + project
COPY --from=build /app /app

ENV VIRTUAL_ENV=/app/.venv
ENV PATH=/app/.venv/bin:$PATH
