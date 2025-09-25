# syntax=docker/dockerfile:1

############################
# Builder: create venv & sync
############################
FROM python:3.11-slim AS builder
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /build

# Minimal build tools (add build-essential if native wheels are needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
 && ln -s /root/.local/bin/uv /usr/local/bin/uv

# Create a fixed-path venv so shebangs remain valid after copying
RUN uv venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

# Copy only project metadata first for better caching of deps
COPY pyproject.toml README.md ./

# Copy source (needed to install the project itself)
COPY src ./src

# Install project + runtime deps into the venv (no dev group)
# Use --frozen if you commit uv.lock and want to fail on changes.
RUN uv sync --no-dev

#####################
# Runtime: minimal
#####################
FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}"
WORKDIR /app

# Copy the prebuilt virtualenv only
COPY --from=builder /opt/venv /opt/venv

# (No source code needed—package is installed in the venv)
# Drop privileges
RUN useradd -m -u 10001 appuser
USER appuser

# CMD ["python", "-c", "import monthly_meteo_composite as m; print('installed:', getattr(m,'__version__','unknown'))"]

