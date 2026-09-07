# --- frontend build -------------------------------------------------------
FROM node:20-slim AS frontend
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci || npm install
COPY tsconfig.json vite.config.ts ./
COPY js ./js
COPY views ./views
COPY resources ./resources
RUN npm run build

# --- runtime -------------------------------------------------------------
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

# Sillo comes from PyPI in the image; a monorepo build can mount the local
# checkout and `pip install -e` it instead.
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir ".[server,redis,postgres]" || true

COPY app ./app
COPY domain ./domain
COPY database ./database
COPY routes ./routes
COPY realtime ./realtime
COPY observability ./observability
COPY integrations ./integrations
COPY cli ./cli
COPY resources ./resources
COPY --from=frontend /app/static/build ./static/build

RUN pip install --no-cache-dir ".[server,redis,postgres]"
RUN mkdir -p storage

ENV APP_ENV=production VITE_DEV=false DB_GENERATE_SCHEMAS=false
EXPOSE 8000

# Migrations run once from an init container / release step, not here.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
