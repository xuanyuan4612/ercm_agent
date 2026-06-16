#!/bin/bash
# vm-deploy.sh — 虚拟机端部署脚本
# 用法:
#   手动执行:  bash /opt/hermes/scripts/vm-deploy.sh
#   定时检查:  crontab -e 添加下面这行（每 5 分钟检查一次更新）
#               */5 * * * * bash /opt/hermes/scripts/vm-deploy.sh >> /var/log/hermes-deploy.log 2>&1
set -euo pipefail

# ==================== 配置 ====================
ACR_REGISTRY="crpi-qs5r9se4bsjpdlz0.cn-shanghai.personal.cr.aliyuncs.com"
ACR_NAMESPACE="xuanyuan111"
ACR_REPO="ercm-agent"
IMAGE_FULL="${ACR_REGISTRY}/${ACR_NAMESPACE}/${ACR_REPO}:latest"
ACR_USERNAME="${ACR_USERNAME:-}"
ACR_PASSWORD="${ACR_PASSWORD:-}"

DEPLOY_DIR="${DEPLOY_DIR:-/opt/hermes}"
COMPOSE_FILE="docker-compose.prod.yml"
HEALTH_URL="http://localhost:8000/health"
MAX_HEALTH_RETRIES=30
HEALTH_RETRY_INTERVAL=2
GIT_REMOTE="${GIT_REMOTE:-origin}"
GIT_BRANCH="${GIT_BRANCH:-main}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# ==================== 前置检查 ====================
if ! command -v docker &>/dev/null; then
    log "[ERROR] docker 未安装"; exit 1
fi
if ! command -v git &>/dev/null; then
    log "[ERROR] git 未安装"; exit 1
fi
if [ ! -f "$DEPLOY_DIR/$COMPOSE_FILE" ]; then
    log "[ERROR] $COMPOSE_FILE 不存在于 $DEPLOY_DIR"; exit 1
fi

cd "$DEPLOY_DIR" || { log "[ERROR] 无法进入 $DEPLOY_DIR"; exit 1; }

# ==================== 1. 拉取最新代码 ====================
log "git fetch 检测代码更新..."
git fetch "$GIT_REMOTE" "$GIT_BRANCH"
CURRENT=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "$GIT_REMOTE/$GIT_BRANCH")

if [ "$CURRENT" != "$REMOTE" ]; then
    git pull "$GIT_REMOTE" "$GIT_BRANCH"
    log "✅ 代码已更新: ${CURRENT:0:7} → ${REMOTE:0:7}"
    CODE_UPDATED=true
else
    log "代码无变化 (HEAD: ${CURRENT:0:7})"
    CODE_UPDATED=false
fi

# ==================== 2. 登录 ACR ====================
log "登录 ACR..."
if [ -n "$ACR_PASSWORD" ]; then
    echo "$ACR_PASSWORD" | docker login --username "$ACR_USERNAME" --password-stdin "$ACR_REGISTRY" >/dev/null 2>&1
elif docker pull "$IMAGE_FULL" 2>/dev/null >/dev/null; then
    :  # 使用已缓存的登录凭据
else
    log "[ERROR] ACR 登录失败，请先设置 ACR_USERNAME / ACR_PASSWORD 环境变量，"
    log "        或手动执行: docker login --username=你的用户名 $ACR_REGISTRY"
    exit 1
fi

# ==================== 3. 拉取镜像 ====================
log "检查镜像更新..."
OLD_DIGEST=$(docker inspect "$IMAGE_FULL" --format '{{index .RepoDigests 0}}' 2>/dev/null || echo "")
docker compose -f "$COMPOSE_FILE" pull api 2>&1 | tail -1
NEW_DIGEST=$(docker inspect "$IMAGE_FULL" --format '{{index .RepoDigests 0}}' 2>/dev/null || echo "")

IMAGE_CHANGED=false
if [ "$OLD_DIGEST" != "$NEW_DIGEST" ]; then
    log "✅ 镜像已更新"
    IMAGE_CHANGED=true
elif [ -z "$OLD_DIGEST" ]; then
    log "首次部署（无本地镜像缓存）"
    IMAGE_CHANGED=true
else
    log "镜像无变化"
fi

# 代码和镜像都没变 → 跳过
if [ "$CODE_UPDATED" != "true" ] && [ "$IMAGE_CHANGED" != "true" ]; then
    log "跳过部署（代码和镜像均无变化）"
    exit 0
fi

# 代码变了但镜像没变 → GitHub Actions 可能还在构建
if [ "$CODE_UPDATED" == "true" ] && [ "$IMAGE_CHANGED" != "true" ]; then
    log "[WARN] 代码已更新但 ACR 镜像尚未刷新，请等待 GitHub Actions 构建完成"
    log "       查看进度: https://github.com/xuanyuan111/ercm-agent/actions"
fi

# ==================== 4. 重启服务 ====================
log "重启 app 容器..."
docker compose -f "$COMPOSE_FILE" up -d --no-deps --force-recreate api
docker image prune -f

# ==================== 5. 数据库迁移 ====================
log "运行数据库迁移..."
# 等 app 容器完全启动后再迁移
sleep 5
if docker compose -f "$COMPOSE_FILE" exec -T api alembic upgrade head 2>/dev/null; then
    log "数据库迁移完成"
else
    log "[WARN] 数据库迁移失败，请检查: docker compose -f $COMPOSE_FILE logs api"
fi

# ==================== 6. 健康检查 ====================
log "健康检查..."
for _i in $(seq 1 $MAX_HEALTH_RETRIES); do
    if curl -sf "$HEALTH_URL" >/dev/null 2>&1; then
        log "部署完成 ✅  $HEALTH_URL 通过"
        exit 0
    fi
    sleep "$HEALTH_RETRY_INTERVAL"
done

log "[ERROR] 健康检查超时！请检查日志: docker compose -f $COMPOSE_FILE logs api --tail 50"
exit 1
