# --- Python dependencies ---
FROM python:3.12-slim AS backend-deps
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# --- Angular production build ---
FROM node:20-bookworm-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build -- --configuration=production

# --- Runtime: API only (ECS when Angular is on S3 + CloudFront) ---
FROM python:3.12-slim AS runtime-api
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
COPY --from=backend-deps /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
COPY pyproject.toml uv.lock ./
COPY main.py config.py logging_config.py middleware.py ./
COPY agents ./agents
COPY routers ./routers
# Hugging Face Spaces run the process as UID 1000; ensure venv and app tree are usable.
RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# --- Runtime: API + built SPA in image (local / single-container deploys) ---
FROM runtime-api AS runtime-full
COPY --chown=appuser:appuser --from=frontend-build /frontend/dist/frontend/browser ./static/browser
