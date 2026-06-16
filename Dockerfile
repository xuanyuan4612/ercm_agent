# 赫尔墨斯（Hermes）Docker 镜像 — 前后端合一
# 多阶段构建：Python依赖 + Node前端 → 统一运行时

# ── Stage 1: Python Builder ──────────────────────────────────
FROM python:3.11-slim-bookworm AS python-builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev libffi-dev curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
RUN mkdir -p hermes && touch hermes/__init__.py
RUN uv pip install --system --no-cache .

# ── Stage 2: 前端构建 ────────────────────────────────────────
FROM node:22-alpine AS frontend-builder
WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --frozen-lockfile

COPY frontend/ ./
RUN npm run build -- --outDir /frontend/dist

# ── Stage 3: Runtime ─────────────────────────────────────────
FROM python:3.11-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# 从 python-builder 复制 Python 依赖
COPY --from=python-builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=python-builder /usr/local/bin /usr/local/bin

# 复制后端源码
COPY . .

# 复制前端构建产物
COPY --from=frontend-builder /frontend/dist /app/frontend-dist

RUN useradd -m -u 1000 hermes && chown -R hermes:hermes /app
USER hermes

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "hermes.main:app", "--host", "0.0.0.0", "--port", "8000"]
