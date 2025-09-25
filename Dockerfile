# -------- Build stage --------
FROM ghcr.io/astral-sh/uv:0.8-debian-slim AS build

SHELL ["sh", "-exc"]
ARG pythonVersion=python3.11

WORKDIR /app

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON=${pythonVersion} \
    UV_HTTP_TIMEOUT=1000 \
    UV_PYTHON_INSTALL_DIR=/app \
    UV_PYTHON_PREFERENCE=only-managed \
    UV_INDEX_URL=https://pypi.org/simple

# --- deps only (good layer cache) ---
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock,ro \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml,ro \
    uv sync --locked --no-install-project --no-dev

# --- add source and install the project into the venv ---
COPY src /app/src

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock,ro \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml,ro \
    uv sync --locked --no-dev

# -------- Runtime stage --------
FROM ghcr.io/osgeo/gdal:ubuntu-small-3.11.3 AS production
SHELL ["sh", "-exc"]
WORKDIR /app

COPY --from=build /app /app

ENV VIRTUAL_ENV=/app/.venv
ENV PATH=/app/.venv/bin:$PATH