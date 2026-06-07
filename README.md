# Hermes（赫尔墨斯）

风险控制 AI 智能体系统。

## 本地开发

```bash
# 1. 复制环境变量配置
cp .env.example .env
# 编辑 .env，填入实际的 API Key 等配置

# 2. 启动所有服务
docker-compose up -d

# 3. 运行数据库迁移
docker-compose exec api alembic upgrade head

# 4. 检查服务
curl http://localhost:8000/health
```

## 自动部署（GitHub Actions + ghcr.io + 虚拟机）

### 架构

```
本地 git push → GitHub Actions 构建镜像 → 推送 ghcr.io → SSH 虚拟机 → docker-compose up -d
```

### 虚拟机端配置

1. 在虚拟机上创建部署目录，放入 `docker-compose.prod.yml` 和 `.env`：

```bash
mkdir -p /opt/hermes
# 将仓库中的 docker-compose.prod.yml 和你的 .env 复制到此目录
```

2. 生成 SSH Key 供 GitHub Actions 使用：

```bash
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/github_actions
cat ~/.ssh/github_actions.pub >> ~/.ssh/authorized_keys
cat ~/.ssh/github_actions    # 复制此私钥内容
```

### GitHub 仓库设置

在仓库 **Settings → Secrets and variables → Actions** 中添加以下 Secrets：

| Secret | 说明 |
|--------|------|
| `VM_HOST` | 虚拟机的 IP 地址 |
| `VM_USER` | SSH 用户名 |
| `VM_SSH_PRIVATE_KEY` | 上一步生成的私钥内容 |
| `VM_DEPLOY_PATH` | 虚拟机上的部署目录，如 `/opt/hermes` |

### 使用

推送代码到 `main` 分支即可自动部署。也可以在 GitHub Actions 页面手动触发（`workflow_dispatch`）。
