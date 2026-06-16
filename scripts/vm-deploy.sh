#!/bin/bash
# vm-deploy.sh — 虚拟机端部署脚本（前后端合一镜像）
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
PULL_TIMEOUT="${PULL_TIMEOUT:-60}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# ==================== 前置检查 ====================
if ! command -v docker &>/dev/null; then
    log "[ERROR] docker 未安装"; exit 1
fi
if [ ! -f "$DEPLOY_DIR/$COMPOSE_FILE" ]; then
    log "[ERROR] $COMPOSE_FILE 不存在于 $DEPLOY_DIR"; exit 1
fi

# 自动检测 docker compose 命令（兼容新旧版本）
if docker compose version &>/dev/null; then
    DOCKER_COMPOSE="docker compose"
elif command -v docker-compose &>/dev/null; then
    DOCKER_COMPOSE="docker-compose"
else
    log "[ERROR] docker compose 未安装（需要 docker compose 插件或 docker-compose 独立二进制）"
    exit 1
fi

cd "$DEPLOY_DIR" || { log "[ERROR] 无法进入 $DEPLOY_DIR"; exit 1; }

# ==================== 1. 登录 ACR ====================
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

# ==================== 2. 拉取镜像 ====================
log "检查镜像更新..."
OLD_DIGEST=$(docker inspect "$IMAGE_FULL" --format '{{index .RepoDigests 0}}' 2>/dev/null || echo "")

if timeout "$PULL_TIMEOUT" $DOCKER_COMPOSE -f "$COMPOSE_FILE" pull api; then
    log "镜像拉取完成"
else
    PULL_EXIT=$?
    if [ "$PULL_EXIT" = "124" ]; then
        log "[WARN] 镜像拉取超时（${PULL_TIMEOUT}s），将使用本地镜像继续"
    else
        log "[WARN] 镜像拉取失败（exit=$PULL_EXIT），将使用本地镜像继续"
    fi
fi

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

# 镜像没变 → 检查容器是否在跑，没跑就启动
if [ "$IMAGE_CHANGED" != "true" ]; then
    if $DOCKER_COMPOSE -f "$COMPOSE_FILE" ps api | grep -q 'Up'; then
        log "跳过部署（镜像无变化，容器已在运行）"
        exit 0
    else
        log "镜像无变化，但容器未运行，直接启动..."
    fi
fi

# ==================== 3. 重启服务 ====================
log "重启容器..."
$DOCKER_COMPOSE -f "$COMPOSE_FILE" up -d --no-deps --force-recreate api
docker image prune -f

# ==================== 4. 数据库迁移 ====================
log "运行数据库迁移..."
sleep 5
if $DOCKER_COMPOSE -f "$COMPOSE_FILE" exec -T api alembic upgrade head 2>/dev/null; then
    log "数据库迁移完成"
else
    log "[WARN] 数据库迁移失败，请检查: $DOCKER_COMPOSE -f $COMPOSE_FILE logs api"
fi

# ==================== 5. 健康检查 ====================
log "健康检查..."
for _i in $(seq 1 $MAX_HEALTH_RETRIES); do
    if curl -sf "$HEALTH_URL" >/dev/null 2>&1; then
        log "部署完成 ✅  $HEALTH_URL 通过"
        log "访问地址: http://localhost:8000"
        exit 0
    fi
    sleep "$HEALTH_RETRY_INTERVAL"
done

log "[ERROR] 健康检查超时！请检查日志: $DOCKER_COMPOSE -f $COMPOSE_FILE logs api --tail 50"
exit 1
