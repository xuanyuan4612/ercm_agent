# 赫尔墨斯（Hermes）开发环境部署手册

> 适用场景：**Windows 用 IDE 写代码 → 虚拟机跑 Docker（数据库/中间件）→ IDE 直连数据库**
>
> 虚拟机：VMware Workstation + CentOS 7.6
> 开发机：Windows 10/11

---

## 一、整体架构（先看懂要搭什么）

```
┌───────────────── Windows 开发机 ─────────────────┐
│                                                    │
│  VS Code / PyCharm                                 │
│  ├── hermes 源码（Python/FastAPI）                  │
│  ├── 运行 uvicorn，代码在本地跑                     │
│  └── .env 里数据库地址 = 虚拟机 IP                   │
│                                                    │
│  DataGrip / DBeaver / Navicat                      │
│  └── 连接 虚拟机IP:5432 → 直接看表、写SQL           │
│                                                    │
└────────────────────┬───────────────────────────────┘
                     │ 通过虚拟机 IP 访问（如 192.168.137.130）
                     ▼
┌─────────── VMware 虚拟机 (CentOS 7) ──────────────┐
│                                                    │
│  Docker Compose 一键启动这些服务：                   │
│  ┌──────────┬──────────┬──────────────────┐        │
│  │ postgres │ redis    │ elasticsearch    │        │
│  │ :5432    │ :6379    │ :9200            │        │
│  ├──────────┼──────────┼──────────────────┤        │
│  │ rabbitmq │ minio    │ kibana           │        │
│  │ :5672    │ :9000    │ :5601            │        │
│  └──────────┴──────────┴──────────────────┘        │
│                                                    │
└────────────────────────────────────────────────────┘
```

**一句话总结**：虚拟机当"服务器"只跑数据库和中间件，Windows 跑代码连过去用。

---

## 二、虚拟机环境准备

### 2.1 确认虚拟机能上网

```bash
# 在虚拟机终端里执行，看能不能 ping 通外网
ping -c 3 baidu.com
```

- 如果能通 → 跳到 §2.2
- 如果不通 → 检查 VMware 网络设置：虚拟机 → 设置 → 网络适配器 → 选 **NAT 模式**

### 2.2 查看并记下虚拟机 IP

```bash
# 执行这个命令，记下显示的 IP 地址（后面配置会反复用到）
ip addr show | grep -E 'inet .* (ens|eth)'
```

通常会看到类似 `192.168.xxx.xxx` 的地址，**把这个 IP 记下来**，后面所有配置都用它。下文用 `192.168.204.200` 代替。

### 2.3 Windows 测试能否连通虚拟机

在 Windows 的 PowerShell 或 CMD 里执行：

```powershell
ping 192.168.204.200
```

能通就说明网络没问题，继续往下。

### 2.4 关闭 CentOS 7 防火墙（最简单，虚拟机内网使用）

> 注意：这是虚拟机内网环境，关防火墙不影响安全。如果是云服务器不要关。

```bash
# 停掉并禁用防火墙
sudo systemctl stop firewalld
sudo systemctl disable firewalld
```

### 2.5 设置 Docker 需要的系统参数

```bash
# Elasticsearch 需要这个参数，必须设置
sudo sysctl -w vm.max_map_count=262144
echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf

# 让系统生效
sudo sysctl -p
```

---

## 三、在虚拟机上安装 Docker

以下是 CentOS 7 的完整安装步骤。每一条命令都能直接复制粘贴执行。

### 3.1 安装 Docker Engine

```bash
# 第1步：安装必要工具
sudo yum install -y yum-utils

# 第2步：添加 Docker 官方仓库
sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo

# 第3步：安装 Docker Engine
sudo yum install -y docker-ce docker-ce-cli containerd.io

# 第4步：安装 docker-compose（独立二进制版本，CentOS 7 最稳妥）
sudo curl -L "https://github.com/docker/compose/releases/download/v2.32.0/docker-compose-linux-x86_64" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 第5步：启动 Docker 并设置开机自启
sudo systemctl enable --now docker

# 第6步：验证安装（两项都要看到版本号）
docker --version
docker-compose --version
```

两项都输出版本号就成功。预期类似：`Docker version 27.x.x` + `Docker Compose version v2.32.0`

> **注意**：文档所有命令用 `docker-compose`（带中划线），和 `docker-compose`（空格）效果一样，但兼容性更好。

### 3.2 把自己加入 docker 组（不用每次都 sudo）

```bash
sudo usermod -aG docker $USER

# 退出终端重新登录，或者执行下面命令立即生效
newgrp docker
```

验证一下：

```bash
docker ps
```

没有报错（显示一行表头）就 OK。

### 3.3 配置镜像加速（国内必须，不然拉不了镜像）

```bash
sudo mkdir -p /etc/docker

sudo tee /etc/docker/daemon.json << 'EOF'
{
  "registry-mirrors": [
    "https://mirror.ccs.tencentyun.com",
    "https://docker.m.daocloud.io",
    "https://hub-mirror.c.163.com"
  ]
}
EOF

# 重启 Docker 让配置生效
sudo systemctl daemon-reload
sudo systemctl restart docker
```

### 3.4 测试拉取镜像（验证加速器是否生效）

```bash
# 拉一个小镜像测试网络
docker pull hello-world
docker run hello-world
```

看到 `Hello from Docker!` 就说明一切正常。

---

## 四、在虚拟机上启动基础服务

### 4.1 创建部署目录

```bash
mkdir -p ~/hermes-vm && cd ~/hermes-vm
```

### 4.2 创建 docker-compose.yml

这个文件只包含**基础服务**（数据库、缓存、消息队列、搜索引擎、文件存储），不包括 API 和 Worker（那些在 Windows 上跑）。

```bash
cat > docker-compose.yml << 'EOF'
version: "3.8"

services:
  # ========== 1. PostgreSQL 数据库 ==========
  postgres:
    image: pgvector/pgvector:pg16
    container_name: hermes-postgres
    ports:
      - "0.0.0.0:5432:5432"       # 0.0.0.0 表示允许外部（Windows）连接
    environment:
      POSTGRES_DB: hermes
      POSTGRES_USER: hermes
      POSTGRES_PASSWORD: hermes    # 测试密码，可以改成自己的
    volumes:
      - pgdata:/var/lib/postgresql/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U hermes"]
      interval: 5s
      timeout: 3s
      retries: 5

  # ========== 2. Redis 缓存 ==========
  redis:
    image: redis:7-alpine
    container_name: hermes-redis
    ports:
      - "0.0.0.0:6379:6379"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  # ========== 3. RabbitMQ 消息队列 ==========
  rabbitmq:
    image: rabbitmq:3.13-management-alpine
    container_name: hermes-rabbitmq
    ports:
      - "0.0.0.0:5672:5672"        # 程序连接端口
      - "0.0.0.0:15672:15672"      # Web 管理界面端口
    environment:
      RABBITMQ_DEFAULT_USER: guest
      RABBITMQ_DEFAULT_PASS: guest
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "check_port_connectivity"]
      interval: 10s
      timeout: 5s
      retries: 5

  # ========== 4. Elasticsearch 搜索引擎 ==========
  elasticsearch:
    image: elasticsearch:8.15.0
    container_name: hermes-elasticsearch
    ports:
      - "0.0.0.0:9200:9200"
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
      - "ES_JAVA_OPTS=-Xms512m -Xmx512m"
    volumes:
      - esdata:/usr/share/elasticsearch/data
    restart: unless-stopped

  # ========== 5. Kibana（ES 可视化） ==========
  kibana:
    image: kibana:8.15.0
    container_name: hermes-kibana
    ports:
      - "0.0.0.0:5601:5601"
    environment:
      ELASTICSEARCH_HOSTS: http://elasticsearch:9200
      I18N_LOCALE: zh-CN
    depends_on:
      - elasticsearch
    restart: unless-stopped

  # ========== 6. MinIO 文件存储 ==========
  minio:
    image: minio/minio:latest
    container_name: hermes-minio
    ports:
      - "0.0.0.0:9000:9000"        # API 端口
      - "0.0.0.0:9001:9001"        # Web 管理界面端口
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    command: server /data --console-address ":9001"
    volumes:
      - miniodata:/data
    restart: unless-stopped

volumes:
  pgdata:
  esdata:
  miniodata:
EOF
```

### 4.3 拉取镜像并启动

```bash
cd ~/hermes-vm

# 拉取所有镜像（第一次比较慢，后面就快了）
docker-compose pull

# 启动所有服务
docker-compose up -d
```

### 4.4 确认所有服务都启动了

```bash
docker-compose ps
```

应该看到 6 个服务，Status 都是 `Up` 或 `healthy`。

如果某个服务没起来，查看日志：

```bash
docker-compose logs 服务名
# 例如: docker-compose logs elasticsearch
```

---

## 五、Windows 端配置

### 5.1 准备环境变量文件

在你的项目目录（比如 `E:\pythonProject\ercm_agent`）下，复制一份：

```powershell
copy .env.example .env
```

### 5.2 修改 .env，指向虚拟机

用 VS Code 或记事本打开 `.env`，把下面这些改成虚拟机的 IP：

```bash
# 把 localhost 全部改成你的虚拟机 IP，比如 192.168.137.130

# 数据库
DB_HOST_WRITE=192.168.204.200
DB_HOST_READ=192.168.204.200
DB_PORT=5432
DB_NAME=hermes
DB_USER=hermes
DB_PASSWORD=hermes

# Redis
REDIS_CLUSTER_NODES=redis://192.168.204.200:6379/0

# RabbitMQ
RABBITMQ_HOST=192.168.204.200
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest

# Elasticsearch
ES_HOSTS=http://192.168.204.200:9200

# MinIO
MINIO_ENDPOINT=192.168.204.200:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=hermes

# LLM（填你自己的 Key）
LLM_API_BASE=https://api.deepseek.com
LLM_API_KEY=sk-你的key
LLM_MODEL=deepseek-v4-pro
```

> 如果你不知道怎么批量替换，在 VS Code 里按 `Ctrl+H`，查找 `localhost`，替换为你的虚拟机 IP，点"全部替换"即可。

### 5.3 验证 Windows 能连通虚拟机上的服务

在 Windows PowerShell 里执行以下命令测试：

```powershell
# 测试 PostgreSQL（需要提前装 psql，或者用下一步的 IDE 测试也行）
# 跳过这步也可以，直接在 5.4 用 IDE 测

# 测试端口是否通（PowerShell）
Test-NetConnection 192.168.204.200 -Port 5432
Test-NetConnection 192.168.204.200 -Port 6379
Test-NetConnection 192.168.204.200 -Port 9200
Test-NetConnection 192.168.204.200 -Port 5672
Test-NetConnection 192.168.204.200 -Port 5601
```

每一条都应该显示 `TcpTestSucceeded : True`。如果某个不通，检查虚拟机的防火墙是否已按 §2.4 关闭。

### 5.4 用 IDE 连接数据库

以 DataGrip 为例（DBeaver、Navicat 操作类似）：

1. 打开 DataGrip，点左上角 `+` → **Data Source** → **PostgreSQL**
2. 填写连接信息：**Host**=`192.168.204.200`，**Port**=`5432`，**Database**=`hermes`，**User**=`hermes`，**Password**=`hermes`
3. 点 **Test Connection**，看到 "Succeeded" 后点 OK

如果提示下载驱动，点 Download 就行。连接成功后就能在 IDE 里看到数据库里的表和数据了。

---

## 六、在 Windows 上运行代码

### 6.1 启动后端

在项目目录打开终端（PowerShell 或 Git Bash）：

```powershell
cd E:\pythonProject\ercm_agent

# 安装依赖（如果还没装）
uv sync

# 数据库迁移（创建表）
uv run alembic upgrade head

# 启动 API 服务
uv run uvicorn hermes.main:app --host 0.0.0.0 --port 8000 --reload
```

看到这个就说明启动成功了：

```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 6.2 启动前端

前端是 Vue 3 + Vite + Element Plus 项目，单独启动：

```powershell
cd E:\pythonProject\ercm_agent\frontend

# 安装前端依赖（如果还没装，只需要执行一次）
npm install

# 启动前端开发服务器
npm run dev
```

看到这个就说明启动成功了：

```
  VITE v6.x.x  ready in xxx ms

  ➜  Local:   http://localhost:5173/
  ➜  Network: use --host to expose
```

### 6.3 访问系统

前端已配置 API 代理，开发时前端请求会自动转发到后端：

| 地址 | 用途 |
|------|------|
| `http://localhost:5173` | 前端界面（用户入口） |
| `http://localhost:8000/docs` | 后端 Swagger API 文档 |
| `http://localhost:8000/health` | 后端健康检查 |

虚拟机上的 Web 管理界面：

| 地址 | 用途 | 默认账号/密码 |
|------|------|---------------|
| `http://192.168.204.200:15672` | RabbitMQ 管理界面 | guest / guest |
| `http://192.168.204.200:9001` | MinIO 控制台 | minioadmin / minioadmin |
| `http://192.168.204.200:5601` | Kibana（ES 可视化） | 无需登录 |

> 前端 `vite.config.ts` 中配置了 `/api` → `http://localhost:8000` 的代理，所以前端代码里请求 `/api/xxx` 会自动转发到后端，不会跨域。

---

## 七、常用操作速查

### 虚拟机相关

```bash
# 登录虚拟机，进入部署目录
cd ~/hermes-vm

# 查看所有服务状态
docker-compose ps

# 查看某个服务的日志
docker-compose logs -f postgres
docker-compose logs -f redis

# 重启某个服务
docker-compose restart postgres

# 停止所有服务（数据不丢失）
docker-compose down

# 重新启动
docker-compose up -d

# ⚠️ 停止并删除所有数据（慎用！）
docker-compose down -v
```

### Windows 相关

```powershell
# 数据库迁移
uv run alembic upgrade head

# 生成新的迁移文件（改了 model 后）
uv run alembic revision --autogenerate -m "描述你的改动"

# 启动后端（带热重载，改代码自动重启）
uv run uvicorn hermes.main:app --host 0.0.0.0 --port 8000 --reload

# 启动前端（另一个终端窗口）
cd frontend
npm install    # 第一次运行需要
npm run dev    # 启动前端开发服务器 → http://localhost:5173
```

### 每天开始工作

```bash
# 1. 虚拟机：启动服务（如果之前 down 了）
cd ~/hermes-vm && docker-compose up -d

# 2. Windows 终端1：启动后端
cd E:\pythonProject\ercm_agent
uv run uvicorn hermes.main:app --host 0.0.0.0 --port 8000 --reload

# 3. Windows 终端2：启动前端
cd E:\pythonProject\ercm_agent\frontend
npm run dev
```

---

## 八、常见问题

### Q1：虚拟机重启后 IP 变了怎么办？

VMware NAT 模式下，虚拟机的 IP 通常是固定的。如果确实变了：

1. 在虚拟机里重新 `ip addr` 查看新 IP
2. 修改 Windows 上项目 `.env` 文件里的 IP
3. IDE 数据库连接也要改 IP

**建议设置静态 IP**，一劳永逸：

```bash
# 在虚拟机里执行，把 IP 固定下来
# 假设你要固定为 192.168.137.130，网关是 192.168.137.2
sudo nmcli con mod ens33 ipv4.addresses 192.168.137.130/24
sudo nmcli con mod ens33 ipv4.gateway 192.168.137.2
sudo nmcli con mod ens33 ipv4.dns "8.8.8.8 114.114.114.114"
sudo nmcli con mod ens33 ipv4.method manual
sudo nmcli con up ens33
```

### Q2：Docker 镜像拉不下来？

换成国内镜像源试试，编辑 `/etc/docker/daemon.json`：

```bash
sudo tee /etc/docker/daemon.json << 'EOF'
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://dockerhub.timeweb.cloud",
    "https://docker.rainbond.cc"
  ]
}
EOF
sudo systemctl restart docker
```

如果都不行，只能开代理或者让同事把镜像打包传给你（tar 文件导入）。

### Q3：部署文档里面提到阿里云 ACR 是什么？

那是用来做自动构建发布的，你现在**不需要**。目前你是在 Windows 上直接跑代码，虚拟机只跑数据库。等你代码稳定了，想把整个系统部署到服务器上让别人也能访问时，才需要用到 ACR。

### Q4：端口连接测试不通？

1. 确认虚拟机防火墙已关：`sudo systemctl status firewalld` 显示 `inactive (dead)`
2. 确认服务已启动：`docker-compose ps` 看到所有服务 Up
3. 确认 Windows 能 ping 通虚拟机：`ping 192.168.204.200`
4. VMware 网络模式是否为 NAT

### Q5：Elasticsearch 启动失败？

```bash
# 确认这个参数已设置
sudo sysctl vm.max_map_count
# 应该输出 262144，如果不是，执行：
sudo sysctl -w vm.max_map_count=262144
```

### Q6：别人也想连我的虚拟机数据库？

同一局域网内的同事，只要把 IP 改成你虚拟机的 IP，就能连接。注意两边都要把防火墙关了，或者只开放对应端口。

---

## 九、ngrok 内网穿透（让公网也能访问）

ngrok 可以给虚拟机和 Windows 上的服务生成**公网临时域名**，适合：
- 给外部人员演示系统
- 接收第三方 Webhook 回调（如企业微信、钉钉）
- 不在公司内网时远程调试

### 9.1 注册 ngrok 账号

1. 打开 [https://ngrok.com](https://ngrok.com)，用 GitHub/Google 账号注册（免费）
2. 登录后在 [dashboard](https://dashboard.ngrok.com/get-started/your-authtoken) 复制你的 **authtoken**

### 9.2 在虚拟机上安装 ngrok

```bash
# 下载 ngrok（CentOS 7 用 Linux amd64 版本）
cd /tmp
wget https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz
tar xzf ngrok-v3-stable-linux-amd64.tgz
sudo mv ngrok /usr/local/bin/

# 验证安装
ngrok version

# 配置你的 authtoken（替换成你自己的 token）
ngrok config add-authtoken 3FDnC58wRKxO3xdhibFVpftnqF6_61MyG3sqyxqg7L8QvmRyT
```

### 9.3 配置 ngrok

创建配置文件，同时暴露多个端口：

```bash
mkdir -p ~/.ngrok2
cat > ~/.ngrok2/ngrok.yml << 'EOF'
version: "3"
agent:
  authtoken: 3FDnC58wRKxO3xdhibFVpftnqF6_61MyG3sqyxqg7L8QvmRyT
tunnels:
  # 后端 API（Windows 上的服务，通过虚拟机宿主机 IP 转发）
  api:
    proto: http
    addr: http://192.168.204.2:8000
  # 前端
  frontend:
    proto: http
    addr: http://192.168.204.2:5173
  # Kibana
  kibana:
    proto: http
    addr: http://localhost:5601
  # RabbitMQ 管理界面
  rabbitmq:
    proto: http
    addr: http://localhost:15672
EOF
```

> **注意**：后端（`:8000`）和前端（`:5173`）跑在 Windows 上，在虚拟机里要用 Windows 在 NAT 网络中的 IP（通常 `192.168.xxx.1`，也就是虚拟机的网关地址）。
>
> ```bash
> # 在虚拟机里查看网关（即 Windows 宿主机在 NAT 中的 IP）
> ip route | grep default | awk '{print $3}'
> # 或者
> netstat -rn | grep UG | awk '{print $2}'
> ```

### 9.4 启动 ngrok

```bash
# 后台启动所有隧道
ngrok start --all --config ~/.ngrok2/ngrok.yml > /dev/null &

# 查看公网地址
# 查看公网地址（任选一种）
# 方式一：浏览器打开 http://虚拟机IP:4040 直接看
# 方式二：命令行
curl -s http://127.0.0.1:4040/api/tunnels | grep -o '"public_url":"[^"]*"' | cut -d'"' -f4
```

更直观的方式——浏览器打开 `http://虚拟机的IP:4040`（ngrok 本地管理界面），可以看到每个隧道的公网 URL 和请求日志。

### 9.5 仅暴露虚拟机上的服务（简化版）

如果只需要在外网访问**虚拟机上的 Web 管理界面**（Kibana、RabbitMQ、MinIO），用配置文件一次性启动：

```bash
# 创建简化配置
cat > ~/.ngrok2/ngrok-simple.yml << 'EOF'
version: "3"
agent:
  authtoken: 你的authtoken
tunnels:
  kibana:
    proto: http
    addr: http://localhost:5601
  rabbitmq:
    proto: http
    addr: http://localhost:15672
  minio:
    proto: http
    addr: http://localhost:9001
EOF

# 后台启动所有隧道
nohup ngrok start --all --config ~/.ngrok2/ngrok-simple.yml > /tmp/ngrok.log 2>&1 &

# 等几秒后查看公网地址
sleep 3
curl -s http://127.0.0.1:4040/api/tunnels | grep -o '"public_url":"[^"]*"' | cut -d'"' -f4
```

或者只暴露单个端口：

```bash
nohup ngrok http 5601 > /dev/null 2>&1 &
curl -s http://127.0.0.1:4040/api/tunnels | grep -o '"public_url":"[^"]*"' | cut -d'"' -f4
```

### 9.6 使用 Docker 运行 ngrok（可选）

如果不想直接装在虚拟机上，也可以用 Docker：

```bash
# 添加到 docker-compose.yml 或单独运行
docker run -d --name ngrok \
  -e NGROK_AUTHTOKEN=你的authtoken \
  --network host \
  ngrok/ngrok:latest http 5601 15672 9001

# 查看公网地址
curl http://127.0.0.1:4040/api/tunnels 2>/dev/null
```

### 9.7 注意事项

1. **免费限制**：ngrok 免费版每次启动域名随机变化，且有速率限制（~40 req/min）。正式使用建议升级付费版或自建 [frp](https://github.com/fatedier/frp) 替代
2. **安全**：ngrok 会把服务暴露到公网，务必确保：
   - 生产密码不要写在 .env 里
   - Kibana 和 MinIO 控制台加上访问密码
   - 用完后及时关闭 ngrok
3. **后台运行**：关闭终端后 ngrok 会停止。可以用 `nohup` 或 `screen` 保持后台运行

---

## 十、部署流水线（CI + 手动部署）

### 整体流程

```
Windows 写代码 ──git push──▶ GitHub
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
              GitHub Actions          GitHub Actions
              (lint + test)          (build Docker image)
                                        │
                                        ▼
                                   阿里云 ACR
                                   (镜像仓库)
                                        │
                          ┌─────────────┘
                          ▼
              虚拟机手动运行 vm-deploy.sh
              ┌────────────────────────────┐
              │  git pull 拉最新代码        │
              │  docker login ACR          │
              │  docker compose pull api   │
              │  docker compose up -d api  │
              │  alembic upgrade head      │
              │  curl /health 健康检查      │
              └────────────────────────────┘
```

### 10.1 前置条件

虚拟机上需要安装：

```bash
# Git
sudo yum install -y git

# Docker（如果还没装，回到 §三）
# 已经装过的话可以跳过
```

### 10.2 首次部署：克隆仓库

```bash
# 把代码克隆到虚拟机（只需执行一次）
git clone https://github.com/xuanyuan4612/ercm_agent.git ~/hermes-app
cd ~/hermes-app

# 创建 .env 文件（从模板复制，然后修改）
cp .env.example .env
vim .env   # 修改数据库密码、JWT_SECRET、LLM_API_KEY 等
```

### 10.3 部署命令

以后每次更新，直接在虚拟机上执行一条命令：

```bash
bash /opt/hermes/scripts/vm-deploy.sh
```

脚本自动完成 6 步：

| 步骤 | 操作 | 说明 |
|------|------|------|
| 1/6 | 前置检查 | 确认 Docker、Git 已安装 |
| 2/6 | `git pull` | 拉取最新代码和配置 |
| 3/6 | `docker login` | 登录阿里云 ACR（首次需输入凭据） |
| 4/6 | `docker compose up -d` | 仅重建 app 容器，基础设施不动 |
| 5/6 | `alembic upgrade head` | 数据库迁移 |
| 6/6 | `curl /health` | 健康检查（最多等 60s） |

### 10.4 设置 ACR 凭据环境变量

每次部署都要输入 ACR 用户名密码比较麻烦，可以写进 `~/.bashrc`：

```bash
echo 'export ACR_USER=你的ACR用户名' >> ~/.bashrc
echo 'export ACR_PASS=你的ACR密码' >> ~/.bashrc
source ~/.bashrc
```

这样之后再跑 `bash vm-deploy.sh` 就全程无需交互了。

### 10.5 常用运维命令

```bash
cd ~/hermes-app

# 查看所有服务状态
docker compose -f docker-compose.prod.yml ps

# 查看 app 日志
docker compose -f docker-compose.prod.yml logs -f api

# 查看最新 100 行
docker compose -f docker-compose.prod.yml logs --tail 100 api

# 重启 app（不拉新镜像）
docker compose -f docker-compose.prod.yml restart api

# 重启所有服务
docker compose -f docker-compose.prod.yml restart

# 停止所有
docker compose -f docker-compose.prod.yml down

# 启动所有
docker compose -f docker-compose.prod.yml up -d

# 查看 app 使用的镜像版本
docker inspect hermes-api 2>/dev/null | grep -A1 '"Image"' | tail -1
```

### 10.6 首次部署检查清单

- [ ] 虚拟机已安装 Docker §三
- [ ] 虚拟机已安装 Git (§10.1)
- [ ] 代码已 clone 到 `~/hermes-app` (§10.2)
- [ ] `.env` 文件已配置（数据库密码、JWT、LLM Key 等）
- [ ] `ACR_USER` / `ACR_PASS` 已设置（§10.4）
- [ ] 首次运行 `bash vm-deploy.sh`
- [ ] 确认 `curl http://localhost:8000/health` 返回 `{"status":"ok"}`
- [ ] （可选）配置 ngrok 暴露端口 8000 到公网（§九）
