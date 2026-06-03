# 部署到自己的服务器

## 使用 start.py 快速启动（推荐用于测试）

最简单的本地运行方式：

```bash
python3 start.py
```

服务将在 `http://127.0.0.1:8080` 上运行，使用合理的默认配置。配置选项详见主 [README](../README.md)。

## 容器化部署（Docker/Podman）

### Docker Compose（推荐用于生产）

```bash
# 前台启动
docker compose up

# 后台启动
docker compose up -d

# 查看日志
docker compose logs -f

# 停止
docker compose down
```

服务将在 `http://localhost` 上运行。数据持久化在 Docker 命名卷（`storage` 和 `tokens`）中。

### 启用 HTTPS

在 `compose.yaml` 中：将 `CERT_DIR` 设置为持久化路径，取消 `"443:443"` 端口的注释。

### 使用 Podman

所有 Docker 命令都可以用 Podman 直接替代：

```bash
# 构建
podman build -t nas-md .

# 运行
podman run --rm -it -p 80:8080 \
  -v nas-md-storage:/app/storage \
  -e APP_URL=http://localhost \
  nas-md

# Compose
podman-compose up -d
```

## 手动部署到自己的服务器

### 前置条件

- **Python 3.11+**（不需要其他依赖）
- Linux 服务器（推荐 Debian/Ubuntu）

### 第一步：克隆并启动

```bash
git clone https://github.com/Qboy-1214/nas-md.git
cd nas-md

# 直接启动
python3 start.py
```

### 第二步：配置环境变量

在项目根目录创建 `.env` 文件：

```env
WEB_PORT=8080
WEB_HOST=0.0.0.0
STORAGE_DIR=/home/user/nas-md-storage
TOKENS_DIR=/home/user/nas-md-tokens
WEB_ROOT=/home/user/nas-md/web
APP_URL=https://yourdomain.com
API_URL=https://api.yourdomain.com
BOT_API_TOKEN=你的-telegram-bot-令牌
MOUNT_DIRS=/mnt/notes;/mnt/docs
```

### 第三步：配置为 Systemd 服务（Linux）

创建 `/etc/systemd/system/nas-md.service`：

```ini
[Unit]
Description=nas-md 个人知识管理系统
After=network.target

[Service]
Type=simple
User=你的用户名
WorkingDirectory=/home/你的用户名/nas-md
Environment=PYTHONPATH=/home/你的用户名/nas-md
ExecStart=/usr/bin/python3 /home/你的用户名/nas-md/start.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

启用并启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable nas-md
sudo systemctl start nas-md

# 查看状态
sudo systemctl status nas-md

# 查看日志
sudo journalctl -u nas-md -f
```

## 运行你自己的 Telegram Bot

1. 通过 [@BotFather](https://t.me/BotFather) 注册一个新的 Telegram Bot
2. 在 `.env` 文件中添加 `BOT_API_TOKEN=<你的 Telegram API 令牌>`
3. 重启服务

Bot 的数据可以在 `./storage/<用户ID>` 目录中查看。

## 关联新设备

1. 打开 Telegram Bot
2. 发送 `/app`
3. 在浏览器中打开链接
4. 设备已关联

## 在本地电脑上运行 Bot

你可以在本地电脑上运行 Bot。它不会向外部暴露任何端口（除非你使用习惯功能）。它通过轮询 API 与 Telegram 通信。

为了方便，可以创建一个指向你现有 `.md` 文件目录的软链接：

```bash
ln -s <你现有的包含 MD 文件的目录> storage/<用户ID>
```

## 迁移文件到另一台服务器

1. 备份数据（`storage/` 目录）
2. 确保所有客户端应用已与服务器完全同步
3. 在旧服务器上停止 Bot
4. 压缩：`tar -czvf storage.tar.gz storage`
5. 传输到新服务器：`scp storage.tar.gz user@newserver:/path/to/nas-md/`
6. 在新服务器上解压：`tar -xzvf storage.tar.gz`
7. 将 `BOT_API_TOKEN` 传输到新服务器的 `.env` 文件
8. 在新服务器上启动服务
9. 在 PWA 应用中更新 API 地址：`localStorage.setItem('ApiHost', '你的新 API 地址');`

## 维护笔记

### 每日 Git 备份

在 crontab 中添加（`crontab -e`）：

```
0 0 * * * cd /app/storage/<你的Telegram ID> && git add . && git commit -m "$(date +\%d.\%m.\%Y)"
```

先在存储目录中初始化 git：

```bash
cd storage/<你的Telegram ID>
git init
```

### 文件名中的非 ASCII 字符

如果文件名包含非 ASCII 字符，关闭路径引用：

```bash
git config --global core.quotePath false
```

### 查找文件名中的非法字符

```bash
find . -name '*[<>:\"|\\?*]*'
```

### 清除文件名中的非法字符

```bash
find . -type f -name '*[<>:\"|\\?*]*' -print0 | while IFS= read -r -d '' f; do
  dir=$(dirname "$f")
  base=$(basename "$f")
  newbase="${base//[<>:\"|\\\\?*]/}"
  [ "$base" != "$newbase" ] && [ -n "$newbase" ] && mv -n -- "$f" "$dir/$newbase"
done
```
