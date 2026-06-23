FROM node:22-alpine AS frontend

WORKDIR /ui

COPY package.json package-lock.json* ./
RUN npm ci

COPY frontend ./frontend
COPY tsconfig.json tsconfig.app.json vite.config.ts tailwind.config.js postcss.config.js eslint.config.js ./
RUN npm run build

FROM frontend AS frontend-check
RUN npm run lint

FROM python:3.13-slim AS monitor

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir \
    --trusted-host pypi.org \
    --trusted-host files.pythonhosted.org \
    -r requirements.txt

COPY CHANGELOG.md codex_usage.py codex_usage_*.py monitor_service.py prices.json ./
COPY codex_monitor ./codex_monitor
COPY --from=frontend /ui/static ./static
COPY scripts ./scripts
COPY sql ./sql

ENV CODEX_HOME=/codex
ENV MONITOR_DB=/data/monitor.sqlite3
ENV MONITOR_HOST=127.0.0.1
ENV MONITOR_PORT=8787

EXPOSE 8787

CMD ["./scripts/run-api"]
