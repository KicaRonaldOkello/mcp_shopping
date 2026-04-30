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

# --- Runtime ---
FROM python:3.12-slim
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
COPY --from=frontend-build /frontend/dist/frontend/browser ./static/browser
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
