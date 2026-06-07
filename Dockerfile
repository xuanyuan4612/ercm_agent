# 赫尔墨斯（Hermes）Docker 镜像
# 多阶段构建：builder 安装依赖 → runtime 运行
# docker build -t ghcr.io/<username>/hermes-api:latest .

# ── Stage 1: Builder ──────────────────────────────────────────
FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev libffi-dev curl \
    && rm -rf /var/lib/apt/lists/*

# 使用 uv 管理依赖（速度比 pip 快 10-100 倍）
RUN pip install --no-cache-dir uv

# 先复制依赖文件，利用 Docker 层缓存
COPY pyproject.toml ./

# 创建占位包以便 uv 解析 pyproject.toml 中的所有依赖
RUN mkdir -p hermes && touch hermes/__init__.py

# 安装项目及其所有依赖到 site-packages
RUN uv pip install --system --no-cache .

# ── Stage 2: Runtime ─────────────────────────────────────────
FROM python:3.11-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# 从 builder 复制已安装的依赖
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 复制应用源码
COPY . .

# 非 root 用户运行
RUN useradd -m -u 1000 hermes && chown -R hermes:hermes /app
USER hermes

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "hermes.main:app", "--host", "0.0.0.0", "--port", "8000"]
