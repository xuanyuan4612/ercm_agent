# 赫尔墨斯（Hermes）测试 / 本地部署手册 — 100 用户 / 5TB

> 版本：v3.1 | Profile：D0 Docker Compose 本地/测试/PoC | 目标：Linux 7.6 单机 Docker Compose | 容量：100 用户测试规模 / 5TB 测试或脱敏数据

> 适用范围：本地开发、测试环境、PoC、演示和容量验证。本文不作为正式生产部署方案，不承诺生产 SLA、RPO/RTO 或等保上线能力；生产部署以 `doc/architecture-design.md` 的 P1 K8s 高可用架构为准。

---

## 一、部署架构概述

### 1.1 拓扑（单机 Docker Compose）

```
┌─────────────────── CentOS 7.6 服务器 ───────────────────────┐
│  CPU: ≥16 核 | 内存: ≥32GB | 磁盘: ≥200GB 可用              │
│                                                              │
│  ┌──────────────── Docker Compose ──────────────────────┐   │
│  │                                                       │   │
│  │  nginx (:8080) ──→ api (:8000) ──→ celery (1池合并)  │   │
│  │                       │                               │   │
│  │         ┌─────────────┼─────────────┐                │   │
│  │         ▼             ▼             ▼                │   │
│  │   postgres:5432   redis:6379   elasticsearch:9200   │   │
│  │   (+pgvector)     (AOF)        (单节点, IK分词)     │   │
│  │                                                       │   │
│  │   rabbitmq:5672        minio:9000 (+console :9001)   │   │
│  │   (管理界面 :15672)     (S3 兼容对象存储)              │   │
│  │                                                       │   │
│  │   prometheus:9090     grafana:3000                   │   │
│  │   (+node-exporter)    (监控仪表板, 可选)              │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                              │
│  对外端口（测试环境建议）:                                    │
│  :8080/443 → Nginx (API 入口)                               │
│  :3000/:9001/:15672 → 仅堡垒机/VPN/localhost 可访问          │
└──────────────────────────────────────────────────────────────┘
```

如测试数据需要长期保留，可选配备份磁盘或备份主机：用于 PostgreSQL 备份恢复演练、MinIO `rsync` 和配置文件加密备份。该备份能力仅用于测试数据保护，不代表生产高可用。

### 1.2 容器资源分配（10 个核心服务 + 可选监控）

| 容器 | CPU | 内存 | 说明 |
|------|-----|------|------|
| nginx | 1 核 | 1GB | 反向代理 (HTTP) |
| api | 2 核 | 2GB | FastAPI + LangGraph，可 `--scale` 水平扩展 |
| celery | 2 核 | 4GB | 合并 Worker 池 (doc/llm/report/sync/a2a/kb) |
| postgres | 4 核 | 8GB | PostgreSQL 16 + pgvector |
| redis | 1 核 | 2GB | 缓存 + Session + Checkpointer |
| elasticsearch | 4 核 | 4GB | 全文检索，单节点 |
| rabbitmq | 2 核 | 4GB | 消息队列 |
| minio | 2 核 | 2GB | 对象存储 |
| prometheus | 1 核 | 2GB | 指标采集（可选） |
| grafana | 1 核 | 1GB | 监控仪表板（可选） |
| **合计** | **~20 核** | **~30GB** | 推荐服务器 ≥ 16 核 / 32GB |

### 1.3 存储规划（支撑 5TB 文件）

| 数据类型 | 存储路径 | 预估大小 | 存储介质建议 |
|----------|----------|----------|-------------|
| PostgreSQL 业务数据 | Docker Volume | 200-500GB | SSD |
| PostgreSQL 向量数据 | Docker Volume (同上) | 100-300GB | SSD |
| Elasticsearch 索引 | Docker Volume | 300-800GB | SSD |
| Redis AOF | Docker Volume | 2-5GB | SSD |
| MinIO 文件存储 | Docker Volume 或 绑定挂载 | 2-4TB | HDD（大容量） |
| Docker 镜像 & 日志 | 系统盘 | 20-50GB | 系统盘 |

测试/开发可使用 Docker Volume（默认 `/var/lib/docker/volumes/`）。如测试数据接近 TB 级或需要反复压测，建议将 PostgreSQL、Elasticsearch 和 MinIO 绑定挂载到独立磁盘；MinIO 可使用 ≥8TB RAID1/HDD，PostgreSQL 使用 SSD。

### 1.4 开发 / 部署模式选择

| 模式 | 适用场景 | 代码运行位置 | 基础组件运行位置 | 推荐阶段 |
|------|----------|--------------|------------------|----------|
| **本机开发模式** | 开发者本地调试 API、前端和 Agent 逻辑 | 开发机（Windows/Mac/Linux） | 虚拟机 Docker Compose | 日常开发、联调 |
| **虚拟机完整单机模式** | 第一次部署、多人测试、演示 | 虚拟机 Docker Compose | 虚拟机 Docker Compose | 首次联调、测试环境 |
| **自动化部署模式** | 代码已稳定，需要 push 后自动更新测试环境 | CI 构建镜像，虚拟机拉取运行 | 虚拟机 Docker Compose | 后续迭代 |

推荐顺序：

1. 先按 §2.4 让开发机代码能连接虚拟机上的 PostgreSQL、Redis、RabbitMQ、Elasticsearch 和 MinIO。
2. 再按 §3.5 把代码第一次上传到虚拟机，完成完整单机部署和数据库迁移。
3. 手动部署稳定后，再按 §3.6 接入 GitHub Actions 或 GitLab CI/CD。

> 容器内部访问使用服务名，例如 `postgres`、`redis`、`rabbitmq`、`elasticsearch`、`minio:9000`。开发机访问虚拟机组件时不能使用这些服务名，必须使用虚拟机 IP 或 SSH 隧道端口。

---

## 二、环境准备

### 2.1 确认系统环境

```bash
# 1. 确认操作系统
cat /etc/redhat-release
# 预期: CentOS Linux release 7.6.1810 (Core)

# 2. 确认 CPU 和内存
lscpu | grep -E '^CPU\(s\)|Model name'
free -h
# CPU ≥ 8 核（推荐 16 核），内存 ≥ 16GB（推荐 32GB+）

# 3. 确认磁盘可用空间
df -h /
# 至少 50GB 可用（用于 Docker 镜像和基础数据）

# 4. 确认内核版本
uname -r
# 3.10.x (CentOS 7 标准内核)

# 5. 确认时区
timedatectl
# Time zone: Asia/Shanghai
```

### 2.2 系统参数调优

```bash
# ES 虚拟内存要求
sudo sysctl -w vm.max_map_count=262144
echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf

# 允许 Docker 网络转发
sudo sysctl -w net.ipv4.ip_forward=1

# 文件描述符上限
echo "fs.file-max=65536" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

### 2.3 安装 Docker（CentOS 7）

> **两种方案的核心区别**：
> - **方案 A（在线）**：服务器能访问外网 → `yum` 直接装 Docker → 镜像由部署脚本自动从 Docker Hub 拉取
> - **方案 B（离线）**：服务器不能访问外网 → 在外网机器下载 Docker 二进制 + 拉取镜像打包 → 传到服务器导入
> - **镜像获取**：在线方案不需要手动 `docker pull`，部署脚本会自动拉；离线方案必须提前在外网机器拉好再导入

```bash
# ======== 先测试外网连通性 ========
curl -sI https://download.docker.com 2>&1 | head -1

# 如果返回 HTTP/1.1 200 之类 → 使用方案 A（在线安装）
# 如果返回 Could not fetch / TCP connection reset → 使用方案 B（离线安装）
```

#### 方案 A：在线安装（Docker + 镜像都从外网获取）

```bash
# 1. 安装 Docker Engine + Docker Compose
sudo yum install -y yum-utils
sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo yum install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# 2. 【重要】配置 Docker 镜像加速器（国内服务器必须！）
#    使用阿里云镜像加速器，否则极大概率拉镜像超时
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json << 'EOF'
{
  "registry-mirrors": [
    "https://docker.1ms.run",
    "https://docker.xuanyuan.me"
  ]
}
EOF

# 3. 启动 Docker
sudo systemctl enable --now docker
sudo systemctl daemon-reload
sudo systemctl restart docker
sudo usermod -aG docker $USER
newgrp docker

docker --version
docker-compose --version

# 4. 验证加速器是否生效
docker info | grep -A5 "Registry Mirrors"

# 5. 镜像不需要手动操作！
#    部署脚本（§3.1）执行时会自动 docker-compose pull 拉取所有镜像
```

#### 方案 B：离线安装（Docker 二进制 + 镜像全部离线导入）

> 适用于服务器无法访问 `download.docker.com` 和 `registry-1.docker.io` 的内网环境。

```bash
# ======== 步骤1：在外网机器（Windows/Mac开发机）上执行 ========

# 1.1 下载 Docker 静态二进制
wget https://download.docker.com/linux/static/stable/x86_64/docker-27.3.1.tgz

# 1.2 下载 docker-compose 插件
wget https://github.com/docker/compose/releases/download/v2.32.0/docker-compose-linux-x86_64

# 1.3 拉取全部 8 个容器镜像
IMAGES=(
  "nginx:1.26-alpine"
  "pgvector/pgvector:pg16"
  "redis:7-alpine"
  "docker.elastic.co/elasticsearch/elasticsearch:8.17.0"
  "rabbitmq:3.13-management-alpine"
  "minio/minio:RELEASE.2025-04-08T15-41-24Z"
  "prom/prometheus:v3.1.0"
  "grafana/grafana:11.4.0"
)
for img in "${IMAGES[@]}"; do
  echo "Pulling: $img"
  docker pull "$img"
done

# 1.4 导出镜像为一个 tar 文件
docker save "${IMAGES[@]}" -o hermes-base-images.tar

# 1.5 打包所有文件（约 2-4GB）
tar czf hermes-docker-offline.tar.gz \
  docker-27.3.1.tgz \
  docker-compose-linux-x86_64 \
  hermes-base-images.tar

# 1.6 传输到 CentOS 7 服务器（U盘 / scp / 内网共享）
# scp hermes-docker-offline.tar.gz hermes@10.x.x.11:~/

# ======== 步骤2：在 CentOS 7.6 服务器上执行 ========

cd ~
tar xzf hermes-docker-offline.tar.gz

# 2.1 安装 Docker 引擎（静态二进制）
tar xzf docker-27.3.1.tgz
sudo cp docker/* /usr/bin/
rm -rf docker/

# 2.2 创建 systemd 服务
sudo tee /etc/systemd/system/docker.service << 'UNITEOF'
[Unit]
Description=Docker Engine
After=network-online.target
Wants=network-online.target

[Service]
Type=notify
ExecStart=/usr/bin/dockerd
ExecReload=/bin/kill -s HUP $MAINPID
TimeoutStartSec=0
RestartSec=2
Restart=always
LimitNOFILE=infinity
LimitNPROC=infinity
LimitCORE=infinity

[Install]
WantedBy=multi-user.target
UNITEOF

sudo groupadd docker 2>/dev/null || true
sudo usermod -aG docker $USER
sudo systemctl daemon-reload
sudo systemctl enable --now docker

# 2.3 安装 docker-compose
sudo cp docker-compose-linux-x86_64 /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 2.4 导入所有镜像（这是关键步骤！）
docker load -i hermes-base-images.tar
docker images
# 应看到 8 个镜像

# 2.5 刷新用户组
newgrp docker
docker --version && docker-compose --version
```

### 2.4 开发机连接虚拟机组件

本节用于“开发机运行代码，虚拟机只跑基础组件”的场景。开发机可以运行：

```bash
# 后端
cp .env.example .env.local-vm
# 按下面直连或 SSH 隧道示例修改 .env.local-vm 后：

# PowerShell
$env:ENV="local-vm"; uv run uvicorn hermes.main:app --host 0.0.0.0 --port 8000

# Bash / Git Bash
ENV=local-vm uv run uvicorn hermes.main:app --host 0.0.0.0 --port 8000

# 如果不想设置 ENV，也可以把 .env.local-vm 复制为 .env

# 前端（如需要）
cd frontend
npm install
npm run dev
```

#### 方案 A：直连虚拟机 IP

适用于本地虚拟机、内网测试机或安全组只对开发机开放的环境。假设虚拟机 IP 为 `VM_IP=192.168.56.20`：

```bash
# .env.local-vm
ENV=local-vm
DEBUG=true
CORS_ORIGINS=["*"]

# PostgreSQL
DB_HOST_WRITE=192.168.56.20
DB_HOST_READ=192.168.56.20
DB_PORT=5432
DB_NAME=hermes
DB_USER=hermes
DB_PASSWORD=hermes_test_pwd

# Redis
REDIS_CLUSTER_NODES=redis://192.168.56.20:6379/0
REDIS_PASSWORD=

# RabbitMQ
RABBITMQ_HOST=192.168.56.20
RABBITMQ_PORT=5672
RABBITMQ_USER=hermes
RABBITMQ_PASSWORD=hermes_test_pwd

# Elasticsearch
ES_HOSTS=http://192.168.56.20:9200

# MinIO
MINIO_ENDPOINT=192.168.56.20:9000
MINIO_ACCESS_KEY=hermes
MINIO_SECRET_KEY=hermes_test_pwd
MINIO_BUCKET=hermes
MINIO_SECURE=false
```

直连模式需要虚拟机防火墙、安全组或 NAT 端口映射允许开发机访问以下端口。若使用 §3.1 的一键脚本，需先把虚拟机 `.env` 中的 `BIND_ADDR=127.0.0.1` 改为 `BIND_ADDR=0.0.0.0` 或指定 VM 内网地址，再执行 `docker-compose up -d`。不要把这些端口暴露到公网。

| 组件 | 开发机访问地址 | 容器内部地址 | 验证方式 |
|------|----------------|--------------|----------|
| API/Nginx | `http://VM_IP:8080/api/v1/health` | `nginx:80` / `api:8000` | `curl http://VM_IP:8080/api/v1/health` |
| PostgreSQL | `VM_IP:5432` | `postgres:5432` | `psql "postgresql://hermes:hermes_test_pwd@VM_IP:5432/hermes"` |
| Redis | `redis://VM_IP:6379/0` | `redis:6379` | `redis-cli -h VM_IP -p 6379 ping` |
| RabbitMQ AMQP | `VM_IP:5672` | `rabbitmq:5672` | `nc -vz VM_IP 5672` |
| RabbitMQ UI | `http://VM_IP:15672` | `rabbitmq:15672` | 浏览器登录 `hermes / hermes_test_pwd` |
| Elasticsearch | `http://VM_IP:9200` | `elasticsearch:9200` | `curl http://VM_IP:9200/_cluster/health` |
| MinIO API | `VM_IP:9000` | `minio:9000` | `curl http://VM_IP:9000/minio/health/live` |
| MinIO Console | `http://VM_IP:9001` | `minio:9001` | 浏览器登录 `hermes / hermes_test_pwd` |

#### 方案 B：SSH 隧道

适用于不想开放数据库和中间件端口的环境。虚拟机只需要开放 SSH；开发机通过本机端口访问虚拟机组件。

```bash
VM_USER=hermes
VM_IP=192.168.56.20

ssh -N \
  -L 15432:localhost:5432 \
  -L 16379:localhost:6379 \
  -L 15673:localhost:5672 \
  -L 115672:localhost:15672 \
  -L 19200:localhost:9200 \
  -L 19000:localhost:9000 \
  -L 19001:localhost:9001 \
  ${VM_USER}@${VM_IP}
```

SSH 隧道模式下开发机 `.env.local-vm` 使用本机端口：

```bash
# .env.local-vm
ENV=local-vm
DEBUG=true
CORS_ORIGINS=["*"]

# PostgreSQL
DB_HOST_WRITE=127.0.0.1
DB_HOST_READ=127.0.0.1
DB_PORT=15432
DB_NAME=hermes
DB_USER=hermes
DB_PASSWORD=hermes_test_pwd

# Redis
REDIS_CLUSTER_NODES=redis://127.0.0.1:16379/0
REDIS_PASSWORD=

# RabbitMQ
RABBITMQ_HOST=127.0.0.1
RABBITMQ_PORT=15673
RABBITMQ_USER=hermes
RABBITMQ_PASSWORD=hermes_test_pwd

# Elasticsearch
ES_HOSTS=http://127.0.0.1:19200

# MinIO
MINIO_ENDPOINT=127.0.0.1:19000
MINIO_ACCESS_KEY=hermes
MINIO_SECRET_KEY=hermes_test_pwd
MINIO_BUCKET=hermes
MINIO_SECURE=false
```

隧道验证命令：

```bash
psql "postgresql://hermes:hermes_test_pwd@127.0.0.1:15432/hermes"
redis-cli -h 127.0.0.1 -p 16379 ping
curl http://127.0.0.1:19200/_cluster/health
curl http://127.0.0.1:19000/minio/health/live

# 浏览器:
# RabbitMQ UI: http://127.0.0.1:115672
# MinIO Console: http://127.0.0.1:19001
```

---

## 三、一键部署

### 3.1 部署脚本

将以下脚本保存到服务器上执行（`bash hermes-deploy.sh`）：

```bash
#!/bin/bash
# hermes-deploy.sh — Hermes 测试环境一键部署
# 用法: bash hermes-deploy.sh
set -e

HERMES_HOME="${HERMES_HOME:-$HOME/hermes-test}"

echo "========================================"
echo "  Hermes 测试环境部署"
echo "  目标: ${HERMES_HOME}"
echo "========================================"

# ---- 第1步：创建目录 ----
echo "[1/7] 创建目录结构..."
mkdir -p ${HERMES_HOME}/{nginx,rabbitmq,prometheus/rules,grafana/{dashboards,datasources},init-scripts,backup}
cd ${HERMES_HOME}

# ---- 第2步：生成 .env ----
echo "[2/7] 生成配置文件..."
cat > .env << 'ENVEOF'
# ==================== 密钥（测试环境默认值）====================
JWT_SECRET=hermes-test-jwt-secret-change-in-production
ENCRYPTION_KEY=hermes-test-encryption-key-change-in-prod
DB_PASSWORD=hermes_test_pwd
DB_USER=hermes
RABBITMQ_PASSWORD=hermes_test_pwd
RABBITMQ_USER=hermes
MINIO_ACCESS_KEY=hermes
MINIO_SECRET_KEY=hermes_test_pwd
MINIO_BUCKET=hermes
GRAFANA_PASSWORD=admin123

# ==================== LLM 配置（必须填入真实 Key）====================
LLM_API_KEY=sk-b4d23d30813c4235ae2c3a3df6328657
LLM_API_BASE=https://api.deepseek.com
LLM_MODEL=deepseek-v4-pro
LLM_BACKUP_API_KEY=sk-af2058f6af7f499ea5d53e25d5e7885e
LLM_BACKUP_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_BACKUP_MODEL=qwen3.7-plus

# ==================== Embedding 配置 ====================
EMBEDDING_API_KEY=sk-xb1e95TJCLJBKwZpCfUYqKFk2oL43OCptAZllDZH9RXiYkxF
EMBEDDING_API_BASE=https://api.lingyaai.cn/v1
EMBEDDING_MODEL=text-embedding-3-large

# ==================== 服务地址（Docker 内部网络，无需修改）====================
DB_HOST_WRITE=postgres
DB_HOST_READ=postgres
DB_PORT=5432
DB_NAME=hermes
REDIS_CLUSTER_NODES=redis://redis:6379/0
ES_HOSTS=http://elasticsearch:9200
RABBITMQ_HOST=rabbitmq
RABBITMQ_PORT=5672
RABBITMQ_VHOST=/
MINIO_ENDPOINT=minio:9000
MINIO_SECURE=false

# ==================== 端口绑定与部署标识 ====================
# 默认仅绑定到虚拟机本机，供 SSH 隧道访问；如需开发机通过 VM_IP 直连，改为 0.0.0.0 并限制来源 IP
BIND_ADDR=127.0.0.1
HERMES_VERSION=latest
COMPOSE_PROJECT_NAME=hermes-test
ENVEOF

# ---- 第3步：生成 docker-compose.yml ----
echo "[3/7] 生成 docker-compose.yml..."
cat > docker-compose.yml << 'COMPOSEEOF'
services:
  # ============ Nginx（HTTP 模式）============
  nginx:
    image: nginx:1.26-alpine
    ports:
      - "8080:80"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - api
    restart: unless-stopped
    networks:
      - hermes-net
    logging:
      driver: "json-file"
      options:
        max-size: "50m"
        max-file: "3"

  # ============ API 服务 ============
  api:
    image: hermes-api:latest
    environment:
      - DB_HOST_WRITE=${DB_HOST_WRITE}
      - DB_HOST_READ=${DB_HOST_READ}
      - DB_PORT=${DB_PORT}
      - DB_NAME=${DB_NAME}
      - DB_USER=${DB_USER}
      - DB_PASSWORD=${DB_PASSWORD}
      - REDIS_CLUSTER_NODES=${REDIS_CLUSTER_NODES}
      - ES_HOSTS=${ES_HOSTS}
      - RABBITMQ_HOST=${RABBITMQ_HOST}
      - RABBITMQ_PORT=${RABBITMQ_PORT}
      - RABBITMQ_USER=${RABBITMQ_USER}
      - RABBITMQ_PASSWORD=${RABBITMQ_PASSWORD}
      - MINIO_ENDPOINT=${MINIO_ENDPOINT}
      - MINIO_ACCESS_KEY=${MINIO_ACCESS_KEY}
      - MINIO_SECRET_KEY=${MINIO_SECRET_KEY}
      - MINIO_BUCKET=${MINIO_BUCKET}
      - MINIO_SECURE=${MINIO_SECURE}
      - LLM_API_KEY=${LLM_API_KEY}
      - LLM_API_BASE=${LLM_API_BASE}
      - LLM_MODEL=${LLM_MODEL}
      - LLM_BACKUP_API_KEY=${LLM_BACKUP_API_KEY}
      - LLM_BACKUP_API_BASE=${LLM_BACKUP_API_BASE}
      - LLM_BACKUP_MODEL=${LLM_BACKUP_MODEL}
      - EMBEDDING_API_KEY=${EMBEDDING_API_KEY}
      - EMBEDDING_API_BASE=${EMBEDDING_API_BASE}
      - EMBEDDING_MODEL=${EMBEDDING_MODEL}
      - JWT_SECRET=${JWT_SECRET}
      - ENCRYPTION_KEY=${ENCRYPTION_KEY}
    env_file:
      - .env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - hermes-net
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s

  # ============ Celery Worker（合并池）============
  celery:
    image: hermes-worker:latest
    command: celery -A hermes.worker worker -Q doc,llm,report,sync,a2a,kb -c 2 --loglevel=info
    environment:
      - DB_HOST_WRITE=${DB_HOST_WRITE}
      - DB_HOST_READ=${DB_HOST_READ}
      - DB_PORT=${DB_PORT}
      - DB_NAME=${DB_NAME}
      - DB_USER=${DB_USER}
      - DB_PASSWORD=${DB_PASSWORD}
      - REDIS_CLUSTER_NODES=${REDIS_CLUSTER_NODES}
      - ES_HOSTS=${ES_HOSTS}
      - RABBITMQ_HOST=${RABBITMQ_HOST}
      - RABBITMQ_PORT=${RABBITMQ_PORT}
      - RABBITMQ_USER=${RABBITMQ_USER}
      - RABBITMQ_PASSWORD=${RABBITMQ_PASSWORD}
      - MINIO_ENDPOINT=${MINIO_ENDPOINT}
      - MINIO_ACCESS_KEY=${MINIO_ACCESS_KEY}
      - MINIO_SECRET_KEY=${MINIO_SECRET_KEY}
      - MINIO_BUCKET=${MINIO_BUCKET}
      - MINIO_SECURE=${MINIO_SECURE}
      - LLM_API_KEY=${LLM_API_KEY}
      - LLM_API_BASE=${LLM_API_BASE}
      - LLM_MODEL=${LLM_MODEL}
      - LLM_BACKUP_API_KEY=${LLM_BACKUP_API_KEY}
      - LLM_BACKUP_API_BASE=${LLM_BACKUP_API_BASE}
      - LLM_BACKUP_MODEL=${LLM_BACKUP_MODEL}
      - EMBEDDING_API_KEY=${EMBEDDING_API_KEY}
      - EMBEDDING_API_BASE=${EMBEDDING_API_BASE}
      - EMBEDDING_MODEL=${EMBEDDING_MODEL}
    env_file:
      - .env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - hermes-net

  # ============ PostgreSQL 16 + pgvector ============
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      - POSTGRES_DB=hermes
      - POSTGRES_USER=${DB_USER}
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    ports:
      - "${BIND_ADDR}:5432:5432"
    volumes:
      - pg_data:/var/lib/postgresql/data
      - ./init-scripts:/docker-entrypoint-initdb.d:ro
    restart: unless-stopped
    networks:
      - hermes-net
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U hermes -d hermes"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s

  # ============ Redis ============
  redis:
    image: redis:7-alpine
    ports:
      - "${BIND_ADDR}:6379:6379"
    command: >
      redis-server
      --appendonly yes
      --maxmemory 2gb
      --maxmemory-policy allkeys-lru
      --save 900 1
      --save 300 10
    volumes:
      - redis_data:/data
    restart: unless-stopped
    networks:
      - hermes-net
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  # ============ Elasticsearch（单节点）============
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.17.0
    ports:
      - "${BIND_ADDR}:9200:9200"
    environment:
      - discovery.type=single-node
      - ES_JAVA_OPTS=-Xms2g -Xmx2g
      - xpack.security.enabled=false
    volumes:
      - es_data:/usr/share/elasticsearch/data
    restart: unless-stopped
    networks:
      - hermes-net
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:9200/_cluster/health | grep -vq '\"status\":\"red\"'"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 60s

  # ============ RabbitMQ ============
  rabbitmq:
    image: rabbitmq:3.13-management-alpine
    ports:
      - "${BIND_ADDR}:5672:5672"
      - "${BIND_ADDR}:15672:15672"
    environment:
      - RABBITMQ_DEFAULT_USER=${RABBITMQ_USER}
      - RABBITMQ_DEFAULT_PASS=${RABBITMQ_PASSWORD}
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq
      - ./rabbitmq/definitions.json:/etc/rabbitmq/definitions.json:ro
    restart: unless-stopped
    networks:
      - hermes-net
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "check_running"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 20s

  # ============ MinIO ============
  minio:
    image: minio/minio:RELEASE.2025-04-08T15-41-24Z
    command: server /data --console-address ":9001"
    ports:
      - "${BIND_ADDR}:9000:9000"
      - "${BIND_ADDR}:9001:9001"
    environment:
      - MINIO_ROOT_USER=${MINIO_ACCESS_KEY}
      - MINIO_ROOT_PASSWORD=${MINIO_SECRET_KEY}
    volumes:
      - minio_data:/data
    restart: unless-stopped
    networks:
      - hermes-net
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s

  # ============ Prometheus + Grafana（可选监控）============
  prometheus:
    image: prom/prometheus:v3.1.0
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./prometheus/rules:/etc/prometheus/rules:ro
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=7d'
    restart: unless-stopped
    networks:
      - hermes-net

  grafana:
    image: grafana/grafana:11.4.0
    ports:
      - "${BIND_ADDR}:3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}
      - GF_AUTH_ANONYMOUS_ENABLED=true
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/datasources:/etc/grafana/provisioning/datasources:ro
    restart: unless-stopped
    networks:
      - hermes-net

networks:
  hermes-net:
    driver: bridge

volumes:
  pg_data:
  redis_data:
  es_data:
  rabbitmq_data:
  minio_data:
  prometheus_data:
  grafana_data:
COMPOSEEOF

# ---- 第4步：生成辅助配置 ----
echo "[4/7] 生成辅助配置..."

# Nginx 配置
cat > nginx/nginx.conf << 'NGINXEOF'
upstream api_backend {
    server api:8000 max_fails=3 fail_timeout=30s;
}

server {
    listen 80;
    server_name _;
    client_max_body_size 500m;
    proxy_read_timeout 300s;

    location / {
        return 200 '{"status":"ok","message":"Hermes API is running. Use /api/v1/ for API requests."}';
        add_header Content-Type application/json;
    }

    location /api/ {
        proxy_pass http://api_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/v1/ws {
        proxy_pass http://api_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400s;
    }

    location /files/ {
        proxy_pass http://minio:9000/;
        proxy_set_header Host $host;
    }
}
NGINXEOF

# RabbitMQ 队列定义
cat > rabbitmq/definitions.json << 'RABBITEOF'
{
  "queues": [
    {"name": "doc", "vhost": "/", "durable": true, "auto_delete": false,
     "arguments": {"x-dead-letter-exchange": "hermes.dlx", "x-max-priority": 10}},
    {"name": "llm", "vhost": "/", "durable": true, "auto_delete": false,
     "arguments": {"x-dead-letter-exchange": "hermes.dlx", "x-max-priority": 10}},
    {"name": "report", "vhost": "/", "durable": true, "auto_delete": false,
     "arguments": {"x-dead-letter-exchange": "hermes.dlx"}},
    {"name": "sync", "vhost": "/", "durable": true, "auto_delete": false,
     "arguments": {"x-dead-letter-exchange": "hermes.dlx"}},
    {"name": "a2a", "vhost": "/", "durable": true, "auto_delete": false,
     "arguments": {"x-dead-letter-exchange": "hermes.dlx"}},
    {"name": "kb", "vhost": "/", "durable": true, "auto_delete": false,
     "arguments": {"x-dead-letter-exchange": "hermes.dlx"}},
    {"name": "hermes.dlq", "vhost": "/", "durable": true, "auto_delete": false}
  ],
  "exchanges": [
    {"name": "hermes.dlx", "vhost": "/", "type": "direct", "durable": true, "auto_delete": false}
  ],
  "bindings": []
}
RABBITEOF

# PostgreSQL 初始化脚本
cat > init-scripts/01-init.sql << 'SQLEOF'
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;
SQLEOF

# Prometheus 配置
cat > prometheus/prometheus.yml << 'PROMEOF'
global:
  scrape_interval: 30s
scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']
PROMEOF

# Grafana 数据源
cat > grafana/datasources/prometheus.yml << 'GRAFEOF'
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
GRAFEOF

# ---- 第5步：拉取基础镜像并启动基础设施 ----
echo "[5/7] 启动基础设施服务..."

# 先拉取（如果离线导入已完成则会跳过）
docker-compose pull 2>/dev/null || true

# 启动底层服务
docker-compose up -d postgres redis elasticsearch rabbitmq minio

echo "等待基础设施就绪..."
sleep 60
for i in $(seq 1 12); do
  HEALTHY=$(docker-compose ps --format json 2>/dev/null | grep -c '"Health":"healthy"' || true)
  echo "  就绪: ${HEALTHY}/5 (${i}/12)"
  if [ "$HEALTHY" -ge 5 ]; then
    echo "  基础设施全部就绪！"
    break
  fi
  sleep 5
done

# 导入 RabbitMQ 队列定义
docker-compose exec -T rabbitmq rabbitmqctl import_definitions /etc/rabbitmq/definitions.json 2>/dev/null || true

# ---- 第6步：启动应用 ----
echo "[6/7] 启动应用服务..."
docker-compose up -d

# ---- 第7步：验证 ----
echo "[7/7] 验证服务状态..."
sleep 5

echo ""
echo "========================================"
echo "  服务状态"
echo "========================================"
docker-compose ps --format "table {{.Name}}\t{{.Status}}"

SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$SERVER_IP" ] && SERVER_IP="localhost"
BIND_ADDR=$(grep '^BIND_ADDR=' .env | cut -d= -f2-)

echo ""
echo "========================================"
echo "  关键访问地址"
echo "========================================"
echo "  API:           http://${SERVER_IP}:8080/api/v1/"
echo "  API 健康检查:  http://${SERVER_IP}:8080/api/v1/health"
if [ "${BIND_ADDR}" = "127.0.0.1" ]; then
  echo "  管理端口默认仅 VM 本机可访问；开发机访问请参考 §2.4 SSH 隧道"
  echo "  MinIO Console: http://127.0.0.1:9001 (hermes / hermes_test_pwd)"
  echo "  Grafana:       http://127.0.0.1:3000 (admin / admin123)"
  echo "  RabbitMQ:      http://127.0.0.1:15672 (hermes / hermes_test_pwd)"
else
  echo "  MinIO Console: http://${SERVER_IP}:9001 (hermes / hermes_test_pwd)"
  echo "  Grafana:       http://${SERVER_IP}:3000 (admin / admin123)"
  echo "  RabbitMQ:      http://${SERVER_IP}:15672 (hermes / hermes_test_pwd)"
fi
echo ""
echo "========================================"
echo "  部署后操作"
echo "========================================"
echo "  1. 修改 LLM Key:    vim .env  然后 docker-compose restart api celery"
echo "  2. 初始化数据库:     docker-compose run --rm api alembic upgrade head"
echo "  3. 初始化 ES 索引:   docker-compose run --rm api python -m hermes.scripts.init_es_indexes"
echo "  4. 创建管理员:       docker-compose run --rm api python -m hermes.scripts.create_admin --username admin --password <密码> --role group"
echo "  5. 查看日志:         docker-compose logs -f api"
echo ""
echo "========================================"
echo "  部署完成！"
echo "========================================"
```

### 3.2 执行部署

```bash
# 1. 将脚本复制到服务器
# 2. 编辑 .env 中的 LLM_API_KEY、EMBEDDING_API_KEY 为真实值
#    （可以先不修改，等基础设施跑通后再改）
# 3. 默认 BIND_ADDR=127.0.0.1，仅支持 VM 本机和 SSH 隧道访问中间件
#    如确需开发机直连 VM_IP:5432/6379/5672/9200/9000，改为 BIND_ADDR=0.0.0.0，并用防火墙限制来源 IP

# 4. 运行部署
chmod +x hermes-deploy.sh
bash hermes-deploy.sh
```

### 3.3 部署后初始化

```bash
cd ~/hermes-test

# 确认所有容器正常
docker-compose ps

# 数据库迁移
docker-compose run --rm api alembic upgrade head

# 初始化 Elasticsearch 索引模板
docker-compose run --rm api python -m hermes.scripts.init_es_indexes

# 创建管理员
docker-compose run --rm api python -m hermes.scripts.create_admin \
  --username admin \
  --password "YourAdminPassword123!" \
  --role group

# 验证 API
curl http://localhost:8080/api/v1/health
```

### 3.4 验证清单

| 检查项 | 命令 | 预期 |
|--------|------|------|
| 所有容器运行 | `docker-compose ps` | 10 个容器全部 Up |
| API 健康 | `curl http://localhost:8080/api/v1/health` | `{"status":"ok"}` |
| PG 连接 | `docker-compose exec postgres pg_isready` | accepting connections |
| Redis 连接 | `docker-compose exec redis redis-cli ping` | PONG |
| ES 健康 | `curl localhost:9200/_cluster/health` | status: green/yellow |
| RabbitMQ | `docker-compose exec rabbitmq rabbitmq-diagnostics check_running` | OK |
| MinIO | `curl localhost:9000/minio/health/live` | 200 OK |
| 管理员登录 | POST `/api/v1/auth/login` | 返回 access_token |

### 3.5 第一次上传代码到虚拟机

首次部署建议先走手动路径，确认代码、数据库迁移和基础组件都能跑通后，再接入 §3.6 自动化部署。`.env` 只在虚拟机本地维护，不随代码压缩包上传，不提交 Git。

#### 3.5.1 路径 A：虚拟机能访问 Git 仓库

适用于虚拟机能访问 GitHub、GitLab、极狐或公司内网 Git 的环境：

```bash
# 在虚拟机上执行
sudo mkdir -p /opt/hermes
sudo chown -R $USER:$USER /opt/hermes

git clone <你的仓库地址> /opt/hermes
cd /opt/hermes

cp .env.example .env
vi .env
# 至少修改：JWT_SECRET、ENCRYPTION_KEY、LLM_API_KEY、EMBEDDING_API_KEY
# 如果使用仓库自带 docker-compose.yml，至少把组件连接改成下面这组容器内部地址
```

仓库自带 `docker-compose.yml` 的最小连接配置如下；它使用该 Compose 文件里的默认测试账号：

```bash
# PostgreSQL
DB_HOST_WRITE=postgres
DB_HOST_READ=postgres
DB_PORT=5432
DB_NAME=hermes
DB_USER=hermes
DB_PASSWORD=hermes

# Redis
REDIS_CLUSTER_NODES=redis://redis:6379/0

# RabbitMQ
RABBITMQ_HOST=rabbitmq
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest

# Elasticsearch
ES_HOSTS=http://elasticsearch:9200

# MinIO
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=hermes
MINIO_SECURE=false
```

```bash

docker compose build api
docker compose up -d
docker compose exec api alembic upgrade head

curl http://localhost:8000/health
```

如系统只安装了旧版 Compose，把上面的 `docker compose` 改成 `docker-compose`。

后续更新代码：

```bash
cd /opt/hermes
git pull
docker compose build api
docker compose up -d --remove-orphans
docker compose exec api alembic upgrade head
```

#### 3.5.2 路径 B：虚拟机不能访问 Git，开发机打包上传

在开发机仓库根目录执行。推荐用 `git archive`，它只打包 Git 已跟踪文件，不会把 `.env`、`.venv`、`node_modules`、缓存和 `.git` 一起传上去：

```bash
# 开发机执行
git archive --format=tar.gz -o hermes-src.tar.gz HEAD
scp hermes-src.tar.gz hermes@VM_IP:/tmp/

# 虚拟机执行
sudo mkdir -p /opt/hermes
sudo chown -R $USER:$USER /opt/hermes
tar xzf /tmp/hermes-src.tar.gz -C /opt/hermes
cd /opt/hermes

cp .env.example .env
vi .env
# 按 §3.5.1 的“仓库自带 docker-compose.yml 的最小连接配置”修改组件地址和测试账号

docker compose build api
docker compose up -d
docker compose exec api alembic upgrade head

curl http://localhost:8000/health
```

如果当前代码还没有全部纳入 Git，可临时使用压缩包，但必须排除本地环境和密钥：

```bash
# 开发机执行（Linux/macOS/Git Bash）
tar --exclude='.git' \
    --exclude='.env' \
    --exclude='.env.*' \
    --exclude='.venv' \
    --exclude='node_modules' \
    --exclude='frontend/node_modules' \
    --exclude='__pycache__' \
    --exclude='.pytest_cache' \
    --exclude='logs' \
    -czf hermes-src.tar.gz .

scp hermes-src.tar.gz hermes@VM_IP:/tmp/
```

#### 3.5.3 路径 C：已运行 `hermes-deploy.sh`

如果已经按 §3.1 生成了 `~/hermes-test/docker-compose.yml`，该编排会引用 `hermes-api:latest` 和 `hermes-worker:latest` 两个本地镜像。此时上传源码到 `~/hermes-test/app`，在虚拟机上构建镜像后再启动：

```bash
# 虚拟机执行
mkdir -p ~/hermes-test/app
tar xzf /tmp/hermes-src.tar.gz -C ~/hermes-test/app

cd ~/hermes-test/app
docker build -t hermes-api:latest .
docker tag hermes-api:latest hermes-worker:latest

cd ~/hermes-test
docker-compose up -d
docker-compose run --rm api alembic upgrade head
curl http://localhost:8080/api/v1/health
```

更新代码时重复上传压缩包并重新构建镜像即可。确认手动部署稳定后，再切换到 §3.6 的 CI/CD 镜像构建和自动拉取。

### 3.6 自动化部署（GitHub Actions 默认，GitLab/极狐可选）

当前仓库已包含 `.github/workflows/deploy.yml` 和 `docker-compose.prod.yml`，默认自动化链路为：**本地 `git push` → GitHub Actions 构建镜像 → 推送 GHCR → SSH 到虚拟机执行 `docker-compose -f docker-compose.prod.yml pull/up`**。

接入前先完成 §3.5 的首次手动部署，并在虚拟机部署目录放好 `docker-compose.prod.yml` 和虚拟机本地 `.env`：

```bash
# 虚拟机执行
mkdir -p /opt/hermes
cp docker-compose.prod.yml /opt/hermes/
cp .env.example /opt/hermes/.env
vi /opt/hermes/.env
```

GitHub 仓库需要配置这些 Actions Secrets：

| Secret | 说明 |
|--------|------|
| `VM_HOST` | 虚拟机 IP 或域名 |
| `VM_USER` | SSH 用户 |
| `VM_SSH_PRIVATE_KEY` | 可登录虚拟机的私钥 |
| `VM_DEPLOY_PATH` | 虚拟机部署目录，例如 `/opt/hermes` |

后续日常流程：

```bash
git add .
git commit -m "feat: update hermes"
git push origin main
```

GitHub Actions 成功后，虚拟机会拉取 `ghcr.io/xuanyuan4612/ercm_agent:latest` 并重启服务。若使用自己的仓库或镜像命名空间，需要同步修改 `.github/workflows/deploy.yml` 中的 `IMAGE_NAME` 和 `docker-compose.prod.yml` 中的 `api.image`。

#### 3.6.1 GitLab / 极狐 CI/CD 替代方案

> 以下方案实现：**本地 `git push` → GitLab 自动构建镜像 → 服务器自动拉取并部署**。
> 
> 核心优势：
> - **不再依赖 Docker Hub**：基础镜像和业务镜像都走 GitLab Container Registry
> - **全自动**：推送代码后无需手动 SSH 操作
> - **可回滚**：GitLab 上保留历史镜像，出问题随时回退

#### 3.6.2 GitLab 自动化架构

```
┌──────────────┐     git push      ┌─────────────────────┐
│  本地开发机   │ ────────────────→ │  GitLab / 极狐       │
│  (Windows)   │                   │  (gitlab.com 或      │
└──────────────┘                   │   自建 GitLab)       │
                                   │                      │
                                   │  ┌────────────────┐  │
                                   │  │ GitLab CI/CD   │  │
                                   │  │ 1. 构建镜像     │  │
                                   │  │ 2. 推送到       │  │
                                   │  │    Container    │  │
                                   │  │    Registry     │  │
                                   │  └───────┬────────┘  │
                                   └──────────┼───────────┘
                                              │ Webhook / GitLab Runner
                                              ▼
                                   ┌──────────────────────┐
                                   │  CentOS 7.6 服务器    │
                                   │                      │
                                   │  部署脚本:            │
                                   │  1. docker login      │
                                   │  2. docker-compose    │
                                   │     pull (从 GitLab)  │
                                   │  3. docker-compose    │
                                   │     up -d             │
                                   └──────────────────────┘
```

#### 3.6.3 GitLab 项目代码结构（完整）

```
hermes/                          # Git 仓库根目录
├── .gitlab-ci.yml               # GitLab CI/CD 流水线定义
├── docker-compose.yml           # 服务器上的编排文件（使用 GitLab Registry 镜像）
├── .env.example                 # 环境变量模板
├── deploy/
│   └── auto-deploy.sh           # 服务器上的自动部署脚本
├── src/                         # Hermes API 源码
│   ├── Dockerfile               # API 镜像构建文件
│   └── ...
├── worker/                      # Celery Worker 源码
│   ├── Dockerfile               # Worker 镜像构建文件
│   └── ...
├── nginx/
│   └── nginx.conf
├── init-scripts/
│   └── 01-init.sql
└── ...
```

#### 3.6.4 GitLab CI/CD 流水线配置

在仓库根目录创建 `.gitlab-ci.yml`：

```yaml
# .gitlab-ci.yml — Hermes CI/CD 流水线
# 触发条件：推送到 main 分支自动执行

stages:
  - build
  - deploy

variables:
  # GitLab Container Registry 地址
  REGISTRY: ${CI_REGISTRY}                    # 自动变量，指向项目的 Container Registry
  API_IMAGE: ${CI_REGISTRY}/hermes-api
  WORKER_IMAGE: ${CI_REGISTRY}/hermes-worker
  # 使用 docker-in-docker 构建
  DOCKER_HOST: tcp://docker:2375
  DOCKER_TLS_CERTDIR: ""

# ============================================================
# 阶段 1：构建并推送 Docker 镜像
# ============================================================
build-api:
  stage: build
  image: docker:27-dind
  services:
    - docker:27-dind
  script:
    - docker login -u ${CI_REGISTRY_USER} -p ${CI_REGISTRY_PASSWORD} ${CI_REGISTRY}
    - docker build -t ${API_IMAGE}:${CI_COMMIT_SHORT_SHA} -t ${API_IMAGE}:latest -f src/Dockerfile .
    - docker push ${API_IMAGE}:${CI_COMMIT_SHORT_SHA}
    - docker push ${API_IMAGE}:latest
  only:
    - main
  tags:
    - hermes-runner                          # 使用注册的 Runner

build-worker:
  stage: build
  image: docker:27-dind
  services:
    - docker:27-dind
  script:
    - docker login -u ${CI_REGISTRY_USER} -p ${CI_REGISTRY_PASSWORD} ${CI_REGISTRY}
    - docker build -t ${WORKER_IMAGE}:${CI_COMMIT_SHORT_SHA} -t ${WORKER_IMAGE}:latest -f worker/Dockerfile .
    - docker push ${WORKER_IMAGE}:${CI_COMMIT_SHORT_SHA}
    - docker push ${WORKER_IMAGE}:latest
  only:
    - main
  tags:
    - hermes-runner

# ============================================================
# 阶段 2：触发服务器自动部署
# ============================================================
trigger-deploy:
  stage: deploy
  image: curlimages/curl:latest
  script:
    # 通过 SSH 在服务器上执行部署脚本
    - |
      curl -X POST \
        -H "X-Deploy-Token: ${DEPLOY_SECRET_TOKEN}" \
        https://你的服务器IP:8443/deploy/hook
  only:
    - main
  needs:
    - build-api
    - build-worker
```

#### 3.6.5 docker-compose.yml（使用 GitLab Registry）

部署时不再依赖 Docker Hub，业务镜像从 GitLab Registry 拉取，基础镜像通过 GitLab 的 Dependency Proxy 拉取：

```yaml
# docker-compose.yml — 服务器上的编排文件
services:
  nginx:
    image: ${GITLAB_REGISTRY}/hermes-dependency-proxy/nginx:1.26-alpine
    # ... 其余配置同 §3.1

  api:
    image: ${GITLAB_REGISTRY}/hermes-api:latest        # ← 从 GitLab 拉取！
    # ... 其余配置同 §3.1

  celery:
    image: ${GITLAB_REGISTRY}/hermes-worker:latest      # ← 从 GitLab 拉取！
    # ... 其余配置同 §3.1

  postgres:
    image: ${GITLAB_REGISTRY}/hermes-dependency-proxy/pgvector/pgvector:pg16
    # ...

  redis:
    image: ${GITLAB_REGISTRY}/hermes-dependency-proxy/redis:7-alpine
    # ...

  elasticsearch:
    image: ${GITLAB_REGISTRY}/hermes-dependency-proxy/elasticsearch:8.17.0
    # ...

  rabbitmq:
    image: ${GITLAB_REGISTRY}/hermes-dependency-proxy/rabbitmq:3.13-management-alpine
    # ...

  minio:
    image: ${GITLAB_REGISTRY}/hermes-dependency-proxy/minio:RELEASE.2025-04-08T15-41-24Z
    # ...

  prometheus:
    image: ${GITLAB_REGISTRY}/hermes-dependency-proxy/prometheus:v3.1.0
    # ...

  grafana:
    image: ${GITLAB_REGISTRY}/hermes-dependency-proxy/grafana:11.4.0
    # ...

# volumes 和 networks 配置同 §3.1
```

> **GitLab Dependency Proxy**（依赖代理）会缓存 Docker Hub 镜像到你 GitLab 的 Container Registry 中，
> 服务器只需要访问 GitLab 一个地址即可拉取所有镜像，彻底摆脱 Docker Hub。

#### 3.6.6 服务器端自动部署脚本

在服务器上创建 `~/hermes-test/deploy/auto-deploy.sh`：

```bash
#!/bin/bash
# auto-deploy.sh — 服务器端自动部署（由 GitLab CI 或 Webhook 触发）
set -e

HERMES_HOME="${HERMES_HOME:-$HOME/hermes-test}"
cd ${HERMES_HOME}

GITLAB_REGISTRY="registry.gitlab.com"          # 或你的自建 GitLab 域名
GITLAB_REGISTRY_USER="gitlab-ci-token"
GITLAB_REGISTRY_TOKEN="${GITLAB_REGISTRY_TOKEN}"  # 从环境变量读取

echo "=========================================="
echo "  Hermes 自动部署"
echo "  时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

# ---- 1. 登录 GitLab Container Registry ----
echo "[1/5] 登录 GitLab Container Registry..."
echo "${GITLAB_REGISTRY_TOKEN}" | docker login ${GITLAB_REGISTRY} -u ${GITLAB_REGISTRY_USER} --password-stdin

# ---- 2. 拉取最新配置（如果 docker-compose.yml 在 Git 仓库里）----
echo "[2/5] 拉取最新配置..."
git pull origin main 2>/dev/null || echo "  (跳过 git pull，使用当前配置)"

# ---- 3. 拉取所有镜像 ----
echo "[3/5] 拉取最新镜像..."
docker-compose pull

# ---- 4. 滚动更新（不停机）----
echo "[4/5] 滚动更新服务..."
docker-compose up -d --remove-orphans

# ---- 5. 清理旧镜像 ----
echo "[5/5] 清理旧镜像..."
docker image prune -f

echo ""
echo "=========================================="
echo "  部署完成！"
echo "=========================================="
docker-compose ps
```

#### 3.6.7 服务器端 Webhook 接收器（可选：纯自动部署）

如果你希望 GitLab CI 跑完后自动触发服务器部署（不需要手动操作），在服务器上部署一个轻量 Webhook 接收器：

```bash
# 在服务器上创建 webhook-server.py
cat > ~/hermes-test/deploy/webhook-server.py << 'PYEOF'
"""轻量 Webhook 服务 — 接收 GitLab CI 的部署触发请求"""
import subprocess
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler

DEPLOY_TOKEN = os.environ.get("DEPLOY_SECRET_TOKEN", "change-me-in-production")
DEPLOY_SCRIPT = os.path.expanduser("~/hermes-test/deploy/auto-deploy.sh")
PORT = 8443

class DeployHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        token = self.headers.get("X-Deploy-Token", "")
        if token != DEPLOY_TOKEN:
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b'{"status":"error","message":"Invalid token"}')
            return

        self.log_message("Deploy triggered — executing %s", DEPLOY_SCRIPT)
        try:
            result = subprocess.run(
                ["bash", DEPLOY_SCRIPT],
                capture_output=True, text=True, timeout=600
            )
            if result.returncode == 0:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')
            else:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(
                    f'{{"status":"error","stderr":"{result.stderr[-200:]}"}}'.encode()
                )
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f'{{"status":"error","message":"{str(e)}"}}'.encode())

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {format % args}")

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), DeployHandler)
    print(f"Webhook server listening on :{PORT}")
    sys.stdout.flush()
    server.serve_forever()
PYEOF

# 安装为 systemd 服务，开机自启
sudo tee /etc/systemd/system/hermes-webhook.service << 'UNITEOF'
[Unit]
Description=Hermes Deploy Webhook
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/hermes-test
Environment="DEPLOY_SECRET_TOKEN=your-secure-random-token"
ExecStart=/usr/bin/python3 /root/hermes-test/deploy/webhook-server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNITEOF

sudo systemctl daemon-reload
sudo systemctl enable --now hermes-webhook
```

#### 3.6.8 GitLab 完整自动化流程（日常使用）

```bash
# ========== 开发者日常工作流 ==========

# 1. 本地修改代码后
git add .
git commit -m "feat: 新增XX功能"
git push origin main

# 2. GitLab 自动执行（无需人工干预）：
#    a. CI/CD Pipeline 启动
#    b. 构建 hermes-api 和 hermes-worker 镜像
#    c. 推送到 GitLab Container Registry
#    d. 调用服务器 Webhook

# 3. 服务器自动执行：
#    a. docker-compose pull 拉取最新镜像
#    b. docker-compose up -d 滚动更新
#    c. 清理旧镜像

# ========== 查看结果 ==========
# 查看 GitLab Pipeline 状态：浏览器打开 GitLab 项目 → CI/CD → Pipelines
# 查看服务器状态：
ssh root@服务器IP "cd ~/hermes-test && docker-compose ps"
```

#### 3.6.9 GitLab 国内加速配置

> **如果你的 GitLab 托管在 gitlab.com**（服务器在国外），国内服务器拉镜像也可能慢。
> 推荐以下方案的任意组合：

| 方案 | 说明 | 推荐度 |
|------|------|--------|
| **极狐 GitLab (jihulab.com)** | GitLab 国内官方合作伙伴，服务器在国内，免费个人版 | ★★★★★ |
| **自建 GitLab CE** | 在公司内网部署 GitLab，零延迟 | ★★★★ |
| **阿里云 ACR + GitLab CI** | GitLab CI 构建后推到阿里云容器镜像服务，服务器从阿里云拉 | ★★★★ |
| **GitLab Dependency Proxy** | GitLab 自带的镜像缓存功能，缓存 Docker Hub 镜像 | ★★★ |

**推荐的极狐 GitLab 流程：**

```bash
# 1. 在 jihulab.com 上创建项目（免费）
# 2. 本地仓库添加 remote
git remote add jihulab https://jihulab.com/你的用户名/hermes.git

# 3. 推送代码
git push jihulab main

# 4. 服务器配置 GitLab Registry 为 jihulab.com
#    docker-compose.yml 中的 GITLAB_REGISTRY=registry.jihulab.com

# 5. 之后就跟 §3.6.8 的流程一样了
```

#### 3.6.10 GitLab 前置条件速查

| 前置条件 | 说明 |
|----------|------|
| GitLab 项目 | gitlab.com 或 jihulab.com（极狐）免费账号即可 |
| GitLab Runner | 需要有可用的 Runner（GitLab.com 提供 Shared Runner 免费额度 400分钟/月） |
| GitLab Container Registry | 每个项目自带，无需额外配置 |
| 服务器 Docker | 需安装并配置好 `docker-compose` |
| 服务器到 GitLab 网络 | 能 ping 通 gitlab.com 或 jihulab.com（极狐在国内更好访问） |

---

## 四、运维管理

### 4.1 常用命令

```bash
cd ~/hermes-test

# 服务管理
docker-compose ps                                    # 查看状态
docker-compose logs -f --tail=100 api                # API 日志
docker-compose logs -f --tail=100 celery             # Worker 日志
docker-compose restart api                           # 重启 API
docker-compose up -d --scale api=2                   # API 扩容为 2 实例
docker-compose down                                  # 停止（数据保留）
docker-compose up -d                                 # 重新启动
docker-compose down -v                               # ⚠️ 停止并删除所有数据

# 数据库
docker-compose exec postgres psql -U hermes -d hermes    # 进 PG
docker-compose exec postgres pg_dump -U hermes hermes > backup.sql  # 手动备份

# 磁盘
docker system df                                     # Docker 磁盘使用
df -h                                                # 系统磁盘
```

### 4.2 备份策略

本节用于保护本地/测试数据和演练恢复流程，不构成生产 RPO/RTO 承诺。正式生产备份与恢复以 P1 K8s 高可用架构（Patroni + pgBackRest + WAL 归档）为准。

| 数据 | 方式 | 频率 | 命令 |
|------|------|------|------|
| PostgreSQL | `pg_dump` | 每日 | `docker-compose exec -T postgres pg_dump -U hermes -d hermes --format=custom > backup_$(date +%Y%m%d).dump` |
| Elasticsearch | Snapshot API | 每日 | `curl -X PUT "localhost:9200/_snapshot/hermes_backup/$(date +%Y%m%d)?wait_for_completion=true"` |
| MinIO 文件 | `rclone` 或 `rsync` | 每日 | `rsync -avz /var/lib/docker/volumes/hermes-test_minio_data/_data/ /backup/minio/` |
| 配置文件 | Git + 加密备份 | 每次变更 | `git add docker-compose.yml nginx/ rabbitmq/ init-scripts/ && git commit -m "config: update"`；`.env` 不入 Git，使用 `gpg`/企业密钥库加密备份 |

**快速备份脚本**：

```bash
#!/bin/bash
# ~/hermes-test/backup/backup.sh
cd ~/hermes-test
BACKUP_DIR="${BACKUP_DIR:-$HOME/hermes-backups}"
DATE=$(date +%Y%m%d)
mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting backup..."

# PG
docker-compose exec -T postgres pg_dump -U hermes -d hermes --format=custom --compress=9 \
  > "$BACKUP_DIR/hermes_${DATE}.dump"
echo "  PG backup: $(du -h $BACKUP_DIR/hermes_${DATE}.dump | cut -f1)"

# 配置文件（.env 含密钥，必须加密；普通配置可进入 Git）
tar czf "$BACKUP_DIR/config_${DATE}.tar.gz" docker-compose.yml nginx/ rabbitmq/ init-scripts/
gpg --symmetric --cipher-algo AES256 --output "$BACKUP_DIR/env_${DATE}.gpg" .env

# 清理 30 天前的备份（生产清理前需确认已有异地副本）
find "$BACKUP_DIR" -name "*.dump" -mtime +30 -delete

echo "[$(date)] Backup done"
```

```bash
# 添加 crontab 每日自动备份
# crontab -e
# 0 2 * * * bash ~/hermes-test/backup/backup.sh >> /var/log/hermes-backup.log 2>&1
```

### 4.3 故障排查

| 问题 | 排查步骤 |
|------|----------|
| **服务无法启动** | `docker-compose ps -a` 查看故障容器 → `docker-compose logs <service>` |
| **ES 启动失败** | `sudo sysctl -w vm.max_map_count=262144`（内核参数不够） |
| **端口冲突** | `ss -tlnp \| grep -E '8080\|5432\|6379\|9200\|5672\|9001\|3000\|15672'` |
| **磁盘不足** | `docker system prune -a` 清理无用镜像 → 检查 MinIO 数据量 |
| **LLM 调用失败** | 检查 `.env` 中的 `LLM_API_KEY` → 验证 API 是否欠费 |
| **镜像拉取失败** | 内网环境参考 §2.3 方案 B 离线导入 |
| **权限错误** | 确认用户已加入 docker 组: `groups $USER`，否则 `sudo usermod -aG docker $USER` |
| **容器名冲突** | `docker-compose down` 后再 `docker-compose up -d` |

### 4.4 扩容路径

当前 D0 Profile 可用于 100 用户 / 5TB 量级的测试、PoC 或容量验证：

| 扩容项 | 当前测试环境 | 加强配置 |
|--------|-------------|-------------|
| API 实例数 | 1 | `--scale api=3` |
| ES 内存 | 2GB | 4GB |
| Redis 内存 | 2GB | 4GB |
| MinIO 存储 | Docker Volume | 绑定挂载独立 HDD (≥8TB RAID1) |
| PG 存储 | Docker Volume | 绑定挂载 SSD |
| 备份 | 手动 / crontab | 自动化 + 异地 + 定期恢复演练（测试数据） |
| 监控 | Prometheus + Grafana | + node-exporter + Alertmanager |
| 密钥 | `.env` 明文 | 文件权限 `600` + 加密备份 + 180 天轮换 |
| 管理端口 | 直接暴露 | 仅堡垒机/VPN/localhost 访问 |

如需正式生产部署（K8s 集群、Patroni、pgBackRest、RabbitMQ quorum queues、Vault/External Secrets 等），请参考 `doc/architecture-design.md` 的 P1 Profile。

---

## 附录 A：故障排查速查

### A.1 清理与重置

```bash
# 完全清理测试环境（删除所有数据）
cd ~/hermes-test
docker-compose down -v
rm -rf ~/hermes-test   # ⚠️ 彻底删除

# 仅重启所有服务
docker-compose restart
```

### A.2 端口冲突处理

如果服务器上已有服务占用了默认端口，编辑 `docker-compose.yml` 修改左侧端口号：

```yaml
# 例如: 8080 端口冲突，改为 8081
nginx:
  ports:
    - "8081:80"

# 例如: 3000 端口冲突，改为 3001
grafana:
  ports:
    - "3001:3000"
```

### A.3 CentOS 7 特定问题

| 问题 | 解决 |
|------|------|
| `docker` 命令未找到 | 离线安装后执行 `newgrp docker` 或重新登录 |
| `overlay2` 不支持 | CentOS 7.6 内核 3.10 支持 overlay2，检查 `lsmod \| grep overlay` |
| firewall-cmd 未安装 | `sudo yum install -y firewalld && sudo systemctl start firewalld` |
| `hostname -I` 返回空 | 手动设置 `SERVER_IP` 环境变量 |

## 附录 B：与架构文档的对照

| 项目 | 本地/测试环境 (D0) | 生产环境 (architecture-design.md P1) |
|------|-----------|----------------------------------|
| 部署方式 | Docker Compose 单机 | K8s 集群 |
| 服务器 | 1 台，CentOS 7.6 | 3M+5W+2GPU 节点 |
| 可用性 | 单机（无 HA） | 99.9%（多副本 + 自动故障转移） |
| 存储 | Docker Volume | SSD + HDD RAID + NAS 冷归档 |
| 安全 | 基础防火墙 | HTTPS + firewalld + fail2ban + SSH 加固 + 管理端口内网/VPN 限制 |
| 监控 | Prometheus + Grafana | + Jaeger + LangFuse + Alertmanager |
| Worker | 1 个合并池 | 9 类独立 HPA 池 |
| ES | 单节点 2GB | 3 节点集群 4GB/节点 |

## 附录 C：参考文档

| 文档 | 路径 | 说明 |
|------|------|------|
| 系统架构设计 | `doc/architecture-design.md` | 完整架构（10K 用户版） |
| 数据设计 | `doc/data-design.md` | ~40 张表结构 |
| API 设计 | `doc/api-design.md` | REST API 规范 |
| 需求文档 | `doc/hermes-requirements.md` | 8 大模块需求 |
| 应急预案 | `doc/architecture-design.md` §8.20 | 故障处理 SOP |
| 知识库初始化 | `doc/architecture-design.md` §8.19 | 冷启动策略 |
