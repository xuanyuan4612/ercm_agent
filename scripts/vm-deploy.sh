#!/bin/bash
# vm-deploy.sh — 虚拟机端部署脚本
# 用法:
#   手动执行:  bash vm-deploy.sh
#   定时检查:  crontab -e 添加下面这行（每 5 分钟检查一次更新）
#               */5 * * * * bash /opt/hermes/scripts/vm-deploy.sh >> /var/log/hermes-deploy.log 2>&1
set -e

# ==================== 配置（按你的环境修改）====================
ACR_REGISTRY="crpi-qs5r9se4bsjpdlz0.cn-shanghai.personal.cr.aliyuncs.com"
ACR_USERNAME="我就是玄渊"
# ACR 密码：优先从环境变量读取，否则写在文件里
# 推荐做法: export ACR_PASSWORD="你的密码"  写到 ~/.bashrc
# 或者在下面直接写（仅限单机测试环境）:
# ACR_PASSWORD="你的密码"
ACR_PASSWORD="${ACR_PASSWORD:-}"

DEPLOY_DIR="${DEPLOY_DIR:-/opt/hermes}"
COMPOSE_FILE="docker-compose.prod.yml"

# ==================== 检查依赖 ====================
if ! command -v docker &>/dev/null; then
    echo "[ERROR] docker 未安装"
    exit 1
fi

cd "$DEPLOY_DIR" || { echo "[ERROR] 目录不存在: $DEPLOY_DIR"; exit 1; }

# ==================== 登录 ACR ====================
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 登录 ACR..."
if [ -n "$ACR_PASSWORD" ]; then
    echo "$ACR_PASSWORD" | docker login --username "$ACR_USERNAME" --password-stdin "$ACR_REGISTRY"
else
    # 如果已经手动 docker login 过，creds 在 ~/.docker/config.json 里
    if ! docker pull "$ACR_REGISTRY/xuanyuan111/ercm-agent:latest" 2>/dev/null; then
        echo "[ERROR] ACR 登录失败，请先手动执行: docker login --username=$ACR_USERNAME $ACR_REGISTRY"
        exit 1
    fi
    echo "  (使用已缓存的登录凭据)"
fi

# ==================== 拉取并重启 ====================
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 检查镜像更新..."

# 记录当前运行的本地 digest
OLD_DIGEST=$(docker inspect crpi-qs5r9se4bsjpdlz0.cn-shanghai.personal.cr.aliyuncs.com/xuanyuan111/ercm-agent:latest --format '{{.RepoDigests}}' 2>/dev/null || echo "")

# 拉取最新镜像
docker-compose -f "$COMPOSE_FILE" pull api

# 获取新的 digest
NEW_DIGEST=$(docker inspect crpi-qs5r9se4bsjpdlz0.cn-shanghai.personal.cr.aliyuncs.com/xuanyuan111/ercm-agent:latest --format '{{.RepoDigests}}' 2>/dev/null || echo "")

# 比较 digest，有变化才重启
if [ "$OLD_DIGEST" != "$NEW_DIGEST" ] || [ -z "$OLD_DIGEST" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 检测到新镜像，重启服务..."
    docker-compose -f "$COMPOSE_FILE" up -d --remove-orphans
    docker image prune -f
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 部署完成"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 镜像无变化，跳过"
fi
