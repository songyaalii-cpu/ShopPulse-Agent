FROM ghcr.io/astral-sh/uv:0.8-python3.11-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
COPY requirements-prod.txt ./
RUN uv venv /app/.venv \
    && uv pip install --python /app/.venv/bin/python -r requirements-prod.txt
COPY pyproject.toml README.md ./
COPY shoppulse ./shoppulse
COPY tools ./tools
COPY agents ./agents
COPY deployments ./deployments
COPY evaluators ./evaluators
RUN uv pip install --python /app/.venv/bin/python --no-deps --no-build-isolation .

FROM python:3.11-slim-bookworm AS runtime
RUN groupadd --system shoppulse && useradd --system --gid shoppulse --home /app shoppulse
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --chown=shoppulse:shoppulse . .
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER shoppulse
EXPOSE 8000
CMD ["uvicorn", "shoppulse.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
