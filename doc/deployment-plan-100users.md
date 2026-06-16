# 赫尔墨斯（Hermes）部署手册 — 100 用户 / 5TB

> 版本：v4.0 | 目标：Linux 虚拟机 Docker Compose 单机部署 | 容量：100 用户测试规模 / 5TB 数据
>
> 适用范围：本地开发、测试环境、PoC、演示。本文不构成生产部署方案，不承诺生产 SLA、RPO/RTO 或等保合规；生产部署以 `doc/architecture-design.md` 的 P1 K8s 高可用架构为准。

---

## 一、部署架构

### 1.1 整体流程

```
┌──────────┐   git push    ┌─────────────────┐   构建镜像    ┌──────────────────┐
│ 开发机    │ ────────────→ │  GitHub Actions  │ ────────────→ │  阿里云 ACR       │
│ (Windows) │              │  (.github/       │              │  (容器镜像服务)    │
└──────────┘              │   workflows/     │              └────────┬─────────┘
                          │   deploy.yml)    │                       │
                          └─────────────────┘                       │ docker pull
                                                                     ▼
┌─────────────────────────── CentOS / Ubuntu 虚拟机 ─────────────────────────────┐
│  CPU: ≥8 核 | 内存: ≥16GB | 磁盘: ≥200GB                                      │
│                                                                                │
│  ┌──────────────────── Docker Compose ───────────────────────────────┐        │
│  │                                                                    │        │
│  │  api (:8000) ──→ celery worker                                    │        │
│  │    │                                                                │        │
│  │    ├── postgres:5432  (pgvector)                                   │        │
│  │    ├── redis:6379     (缓存 / Session / Checkpointer)              │        │
│  │    ├── elasticsearch:9200  (全文检索)                              │        │
│  │    ├── rabbitmq:5672  (消息队列)                                   │        │
│  │    └── minio:9000     (对象存储, console :9001)                    │        │
│  │                                                                    │        │
│  └────────────────────────────────────────────────────────────────────┘        │
└────────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 两个 Compose 文件

| 文件 | 用途 | API 镜像来源 |
|------|------|-------------|
| `docker-compose.yml` | 本地开发、快速验证 | `build: .` 从源码构建 |
| `docker-compose.prod.yml` | 测试/演示环境 | 从阿里云 ACR 拉取预构建镜像 |

日常开发用 `docker-compose.yml`，部署到虚拟机用 `docker-compose.prod.yml`。

### 1.3 容器资源分配

| 容器 | CPU | 内存 | 说明 |
|------|-----|------|------|
| api | 2 核 | 2GB | FastAPI + LangGraph |
| celery | 2 核 | 4GB | Celery Worker |
| postgres | 4 核 | 8GB | PostgreSQL 16 + pgvector |
| redis | 1 核 | 2GB | 缓存 + Session |
| elasticsearch | 4 核 | 4GB | 全文检索，单节点 |
| rabbitmq | 2 核 | 4GB | 消息队列 |
| minio | 2 核 | 2GB | 对象存储 |
| **合计** | **~17 核** | **~26GB** | 推荐服务器 ≥ 8 核 / 16GB |

### 1.4 存储规划

| 数据类型 | 存储位置 | 预估大小 | 建议介质 |
|----------|----------|----------|----------|
| PostgreSQL 业务+向量数据 | Docker Volume `pgdata` | 300-800GB | SSD |
| Elasticsearch 索引 | Docker Volume `esdata` | 300-800GB | SSD |
| MinIO 文件 | Docker Volume `miniodata` | 2-4TB | HDD（大容量） |
| Redis AOF | 容器内 | 2-5GB | SSD |

---

## 二、环境准备

### 2.1 虚拟机最低配置

- **操作系统**：CentOS 7.6+ / Ubuntu 20.04+
- **CPU**：≥ 8 核（推荐 16 核）
- **内存**：≥ 16GB（推荐 32GB）
- **系统盘**：≥ 50GB 可用（Docker 镜像 + 日志）
- **数据盘**：根据存储规划挂载独立磁盘

### 2.2 系统参数

```bash
# Elasticsearch 虚拟内存要求（必须）
sudo sysctl -w vm.max_map_count=262144
echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf

# 文件描述符上限
echo "fs.file-max=65536" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

### 2.3 安装 Docker

#### 方案 A：在线安装（服务器能访问外网）

```bash
# CentOS 7
sudo yum install -y yum-utils
sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo yum install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Ubuntu
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo tee /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# 启动
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
newgrp docker
```

#### 方案 B：离线安装（服务器无法访问外网）

在外网机器上下载并打包，再传到服务器导入。略，详见旧版手册 §2.3 方案 B。

### 2.4 配置 Docker 镜像加速（国内服务器）

```bash
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json << 'EOF'
{
  "registry-mirrors": [
    "https://docker.1ms.run",
    "https://docker.xuanyuan.me"
  ]
}
EOF
sudo systemctl daemon-reload
sudo systemctl restart docker
```

---

## 三、配置文件

### 3.1 环境变量（`.env`）

在虚拟机部署目录创建 `.env`，以下为必须修改的项：

```bash
# ==================== 安全（必须修改）====================
JWT_SECRET=<生成至少32字符的随机字符串>
ENCRYPTION_KEY=<生成32字节Base64编码的AES密钥>

# ==================== 数据库密码 ====================
DB_PASSWORD=<你的数据库密码>

# ==================== LLM（必须填入真实 Key）====================
LLM_API_KEY=sk-xxxxxxxx
LLM_API_BASE=https://api.deepseek.com
LLM_MODEL=deepseek-v4-pro

# LLM 备用
LLM_BACKUP_API_KEY=sk-xxxxxxxx
LLM_BACKUP_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_BACKUP_MODEL=qwen3.7-plus

# Embedding
EMBEDDING_API_KEY=sk-xxxxxxxx
EMBEDDING_API_BASE=https://api.lingyaai.cn/v1
EMBEDDING_MODEL=text-embedding-3-large
```

> 模板文件 `docker-compose.prod.yml` 通过 `env_file: .env` 读取以上变量。数据库、Redis、RabbitMQ、ES、MinIO 的容器内部连接地址已写在 Compose 文件中，无需修改。

---

## 四、部署

### 4.1 开发环境（本机构建）

开发机本地调试，API 镜像从源码构建：

```bash
# 1. 准备配置
cp .env.example .env
vi .env   # 填入 LLM Key 等

# 2. 启动所有服务
docker compose up -d

# 3. 初始化数据库
docker compose exec api alembic upgrade head

# 4. 验证
curl http://localhost:8000/health
```

### 4.2 虚拟机部署（从阿里云 ACR 拉取镜像）

这是标准的测试/演示环境部署方式：

```bash
# 1. 创建部署目录
mkdir -p /opt/hermes && cd /opt/hermes

# 2. 放入文件
#    将以下文件从仓库复制到 /opt/hermes/：
#    - docker-compose.prod.yml
#    - .env（按 §3.1 填写）

# 3. 登录阿里云 ACR
docker login crpi-qs5r9se4bsjpdlz0.cn-shanghai.personal.cr.aliyuncs.com \
  -u <ACR用户名> \
  -p <ACR密码>

# 4. 拉取镜像并启动
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d

# 5. 等待基础服务就绪
sleep 30

# 6. 数据库迁移
docker compose -f docker-compose.prod.yml exec api alembic upgrade head

# 7. 验证
curl http://localhost:8000/health
```

### 4.3 验证清单

| 检查项 | 命令 | 预期 |
|--------|------|------|
| 所有容器运行 | `docker compose -f docker-compose.prod.yml ps` | 全部 Up |
| API 健康 | `curl http://localhost:8000/health` | `{"status":"ok"}` |
| PG 连接 | `docker compose -f docker-compose.prod.yml exec postgres pg_isready -U hermes` | accepting connections |
| Redis | `docker compose -f docker-compose.prod.yml exec redis redis-cli ping` | PONG |
| ES 健康 | `curl http://localhost:9200/_cluster/health` | status: green/yellow |
| RabbitMQ | `docker compose -f docker-compose.prod.yml exec rabbitmq rabbitmq-diagnostics check_running` | OK |
| MinIO | `curl http://localhost:9000/minio/health/live` | 200 OK |

---

## 五、CI/CD 自动构建

### 5.1 流程说明

```
开发机 git push main → GitHub Actions 自动构建 → 推送镜像到阿里云 ACR
                                                    ↓
                                          虚拟机手动 docker pull + up -d
```

当前 CI 负责 **构建 + 推送镜像**，部署到虚拟机仍需手动执行（适合测试环境，避免自动更新破坏测试状态）。

### 5.2 GitHub Actions 配置（已完成）

Workflow 文件：`.github/workflows/deploy.yml`

触发条件：推送到 `main` 分支，或手动触发（`workflow_dispatch`）。

### 5.3 需要的 GitHub Secrets

在仓库 Settings → Secrets and variables → Actions 中配置：

| Secret | 说明 |
|--------|------|
| `ACR_USERNAME` | 阿里云 ACR 用户名 |
| `ACR_PASSWORD` | 阿里云 ACR 密码 |

### 5.4 镜像地址

```
crpi-qs5r9se4bsjpdlz0.cn-shanghai.personal.cr.aliyuncs.com/xuanyuan111/ercm-agent:latest
```

每次 push 同时打 `latest` 和 `git commit sha` 两个 tag。

### 5.5 日常更新流程

```bash
# 1. 开发机推送代码
git add .
git commit -m "feat: xxx"
git push origin main

# 2. 等待 GitHub Actions 构建完成（约 3-5 分钟）
#    浏览器打开: https://github.com/<user>/<repo>/actions

# 3. 虚拟机拉取最新镜像并重启
ssh user@VM_IP
cd /opt/hermes
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d --remove-orphans
docker compose -f docker-compose.prod.yml exec api alembic upgrade head

# 4. 验证
curl http://localhost:8000/health
```

---

## 六、运维管理

### 6.1 常用命令

```bash
cd /opt/hermes

# 服务管理
docker compose -f docker-compose.prod.yml ps                    # 查看状态
docker compose -f docker-compose.prod.yml logs -f --tail=100 api  # API 日志
docker compose -f docker-compose.prod.yml restart api            # 重启 API
docker compose -f docker-compose.prod.yml down                   # 停止（数据保留）
docker compose -f docker-compose.prod.yml up -d                  # 启动
docker compose -f docker-compose.prod.yml down -v                # ⚠️ 停止并删除所有数据

# 进入数据库
docker compose -f docker-compose.prod.yml exec postgres psql -U hermes -d hermes

# 磁盘使用
docker system df
df -h
```

### 6.2 备份

| 数据 | 方式 | 命令 |
|------|------|------|
| PostgreSQL | `pg_dump` | `docker compose -f docker-compose.prod.yml exec -T postgres pg_dump -U hermes -d hermes --format=custom > backup_$(date +%Y%m%d).dump` |
| Elasticsearch | Snapshot API | `curl -X PUT "localhost:9200/_snapshot/hermes_backup/$(date +%Y%m%d)?wait_for_completion=true"` |
| MinIO 文件 | `rsync` | `rsync -avz /var/lib/docker/volumes/hermes_miniodata/_data/ /backup/minio/` |
| 配置文件 | 手动备份 | 备份 `docker-compose.prod.yml`、`.env`（.env 不入 Git） |

**快速备份脚本**：

```bash
#!/bin/bash
# /opt/hermes/backup.sh
set -e
BACKUP_DIR="${BACKUP_DIR:-/opt/hermes-backups}"
DATE=$(date +%Y%m%d)
mkdir -p "$BACKUP_DIR"

cd /opt/hermes

echo "[$(date)] Starting backup..."

# PostgreSQL
docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U hermes -d hermes --format=custom --compress=9 \
  > "$BACKUP_DIR/hermes_${DATE}.dump"
echo "  PG backup: $(du -h $BACKUP_DIR/hermes_${DATE}.dump | cut -f1)"

# 配置文件
gpg --symmetric --cipher-algo AES256 --output "$BACKUP_DIR/env_${DATE}.gpg" .env 2>/dev/null || \
  tar czf "$BACKUP_DIR/config_${DATE}.tar.gz" docker-compose.prod.yml .env

# 清理 30 天前
find "$BACKUP_DIR" -name "*.dump" -mtime +30 -delete

echo "[$(date)] Backup done"
```

```bash
# crontab 每日凌晨 2 点自动备份
# crontab -e
# 0 2 * * * bash /opt/hermes/backup.sh >> /var/log/hermes-backup.log 2>&1
```

### 6.3 故障排查

| 问题 | 排查 |
|------|------|
| 容器无法启动 | `docker compose -f docker-compose.prod.yml logs <service>` 查看日志 |
| ES 启动失败 | `sudo sysctl -w vm.max_map_count=262144` |
| 端口冲突 | `ss -tlnp \| grep -E '8000\|5432\|6379\|9200\|5672\|9000\|9001\|15672'` |
| 磁盘不足 | `docker system prune -a` 清理无用镜像 |
| 镜像拉取失败 | 确认已 `docker login` 阿里云 ACR |
| LLM 调用失败 | 检查 `.env` 中 `LLM_API_KEY`，确认 API 额度 |
| 权限错误 | `groups $USER` 确认在 docker 组中 |

### 6.4 扩容建议

当前单机部署适用于 100 用户测试规模。如需扩容：

| 扩容项 | 当前 | 加强 |
|--------|------|------|
| 内存 | 16GB | 32GB+ |
| Postgres 存储 | Docker Volume | 绑定挂载独立 SSD |
| MinIO 存储 | Docker Volume | 绑定挂载独立 HDD（≥8TB RAID1）|
| ES 内存 | 512MB | 2-4GB（修改 `ES_JAVA_OPTS`）|
| 备份 | 手动 | crontab 自动 + 异地 |

> 正式生产部署（K8s 集群、PostgreSQL 主从、RabbitMQ quorum queues 等）请参考 `doc/architecture-design.md`。

---

## 附录

### A. 端口映射速查

| 服务 | 容器内端口 | 宿主机端口 | 外部访问 |
|------|-----------|-----------|----------|
| API | 8000 | 8000 | `http://VM_IP:8000` |
| PostgreSQL | 5432 | 5432 | 建议仅 localhost |
| Redis | 6379 | 6379 | 建议仅 localhost |
| Elasticsearch | 9200 | 9200 | 建议仅 localhost |
| RabbitMQ AMQP | 5672 | 5672 | 建议仅 localhost |
| RabbitMQ UI | 15672 | 15672 | 管理界面 |
| MinIO API | 9000 | 9000 | 建议仅 localhost |
| MinIO Console | 9001 | 9001 | 管理界面 |

### B. 清理与重置

```bash
cd /opt/hermes
docker compose -f docker-compose.prod.yml down -v   # 停止并删除所有数据
# ⚠️ 以上命令会删除 PostgreSQL、ES、MinIO 的所有数据，谨慎执行
```

### C. 与架构文档对照

| 项目 | 本手册 (Docker Compose) | 生产环境 (architecture-design.md) |
|------|------------------------|----------------------------------|
| 部署方式 | Docker Compose 单机 | K8s 集群 |
| 可用性 | 单机（无 HA）| 99.9%（多副本 + 自动故障转移）|
| 存储 | Docker Volume | SSD + HDD RAID + NAS 冷归档 |
| 监控 | 无 | Prometheus + Grafana + Jaeger |
| Worker | 单实例 | 多池独立 HPA |

### D. 参考文档

| 文档 | 路径 | 说明 |
|------|------|------|
| 系统架构设计 | `doc/architecture-design.md` | 完整架构 |
| API 设计 | `doc/api-design.md` | REST API 规范 |
| 数据设计 | `doc/data-design.md` | 数据库表结构 |
