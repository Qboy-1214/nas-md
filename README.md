# nas-md

轻量级 Markdown 笔记服务，专为 NAS 和自托管场景设计。Docker 一键部署，HTTPS 开箱即用，你的数据只留在你的设备上。

## 功能特性

- **Vditor 编辑器** —— 三种模式：即时渲染 / 分屏预览 / 所见即所得
- **多目录挂载** —— 同时挂载多个目录，无数量限制
- **多用户隔离** —— 免登录，Cookie 自动识别，各用户挂载点完全隔离
- **Docker 自签名 HTTPS** —— 容器启动自动生成证书，局域网 IP 访问也能用上 File System Access API
- **宿主机目录挂载** —— 挂载到 `/mnt/` 下自动扫描，Admin 可直接读写
- **相对路径图片** —— Markdown 中引用的同目录图片自动解析显示
- **全文搜索** —— 基于 SQLite FTS5，毫秒级检索
- **知识图谱** —— D3.js 可视化笔记链接关系
- **数据看板** —— 笔记数、任务完成率、标签统计
- **暗色模式** —— 亮色/暗色主题一键切换
- **自动保存** —— 默认开启，编辑即保存
- **零依赖启动** —— Python 标准库 + 原生 JS，无框架，无构建

## 快速开始

### Docker 部署（推荐）

```bash
docker pull ghcr.io/qboy-1214/nas-md:latest

docker run -d --name nas-md \
  -p 443:8080 \
  -v nas-md-storage:/app/storage \
  -v /home/user/notes:/mnt/notes \
  -v /home/user/docs:/mnt/docs \
  -e DOCKER_MODE=1 \
  --restart unless-stopped \
  ghcr.io/qboy-1214/nas-md:latest
```

访问 `https://localhost` 即可使用。容器自动生成自签名 HTTPS 证书，局域网内通过 IP 访问（如 `https://10.10.77.91`）同样生效。

> 首次访问时浏览器会提示证书不受信任，点击「继续访问」即可。

#### Docker Compose

```yaml
services:
  nas-md:
    image: ghcr.io/qboy-1214/nas-md:latest
    ports:
      - "443:8080"       # HTTPS 自动启用
    volumes:
      - storage:/app/storage
      - /home/user/notes:/mnt/notes   # 侧边栏显示为 "notes"
      - /home/user/docs:/mnt/docs     # 侧边栏显示为 "docs"
    environment:
      DOCKER_MODE: "1"
    restart: unless-stopped

volumes:
  storage:
```

```bash
docker compose up -d
```

#### 443 端口被占用？

映射到其他端口即可，HTTPS 依然生效：

```yaml
ports:
  - "2443:8080"
```

访问 `https://localhost:2443`。

### 本地运行

需要 **Python 3.11+**，无其他依赖。

```bash
git clone https://github.com/Qboy-1214/nas-md.git
cd nas-md
python start.py
```

服务将在 `http://127.0.0.1:8080` 上运行。

#### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `WEB_PORT` | `8080` | 服务端口 |
| `WEB_HOST` | `127.0.0.1` | 绑定地址 |
| `STORAGE_DIR` | `./storage` | 内置存储目录 |
| `MOUNT_DIRS` | *(空)* | 宿主机挂载点（仅 Admin 可见可写），Docker 模式自动扫描 `/mnt/` |
| `PUBLIC_MOUNT_DIRS` | *(空)* | 公开宿主机挂载点（所有人可见可读写），分号分隔 |
| `PUBLIC_MOUNTS` | *(空)* | Docker 自动扫描模式下，指定 `/mnt/` 中哪些子目录公开（逗号分隔目录名） |
| `DOCKER_MODE` | `0` | 设为 `1` 启用自签名 HTTPS 和 Docker 特有逻辑 |
| `TZ` | `UTC` | 时区配置，影响定时任务和日期显示（如 `Asia/Shanghai`） |

## 访问模式

### 普通用户（默认）

- 访问 `https://host:port/` 即可使用
- 通过浏览器挂载本地目录（需 HTTPS 环境）
- 只能看到自己的挂载目录和公开目录

### Admin 用户

- 访问 `https://host:port/admin` 进入 Admin 模式
- 可读写宿主机挂载点（通过 Docker volumes 挂载到 `/mnt/` 的目录）
- 无法访问其他用户的挂载目录

### 可见性规则

| 挂载点类型 | 普通用户 | Admin |
|-----------|---------|-------|
| 内置存储 | 只读 | 只读 |
| 宿主机私有挂载（`MOUNT_DIRS`） | 不可见 | 读写 |
| 宿主机公开挂载（`PUBLIC_MOUNT_DIRS`） | 读写 | 读写 |
| 自己的浏览器挂载 | 读写 | 读写 |
| 其他用户的挂载 | 不可见 | 不可见 |

## 挂载方式

### 方式一：宿主机目录（Docker）

在 Docker Compose 的 `volumes` 中将宿主机目录挂载到 `/mnt/` 下，应用自动扫描。默认仅 Admin 可见可写，可通过 `PUBLIC_MOUNTS` 设为公开：

```yaml
volumes:
  - /home/user/notes:/mnt/notes      # 默认仅 Admin 可见
  - /home/user/docs:/mnt/docs        # 默认仅 Admin 可见
  - /home/user/shared:/mnt/shared    # 加入 PUBLIC_MOUNTS 后所有人可见
environment:
  PUBLIC_MOUNTS: "shared"             # /mnt/shared 对所有人可见可读写
```

也可用 `PUBLIC_MOUNT_DIRS` 指定非 `/mnt/` 下的公开目录：

```yaml
environment:
  PUBLIC_MOUNT_DIRS: "/home/user/shared;/home/user/photos"
```

### 方式二：浏览器挂载（File System Access API）

在欢迎页点击「浏览…」按钮，选择本地目录即可挂载。需要 HTTPS 环境（Docker 模式自动提供）。

- **HTTPS 环境**：使用 `showDirectoryPicker` API，支持读写
- **HTTP 环境**：降级为 `webkitdirectory`，仅只读

### 方式三：手动输入路径

在欢迎页的输入框中输入服务器上的目录路径，点击「挂载」。

## API 接口

| 方法 | 接口 | 说明 |
|------|------|------|
| `GET` | `/api/mounts` | 列出当前用户可见的挂载点 |
| `POST` | `/api/mounts` | 添加挂载点 |
| `DELETE` | `/api/mounts/{id}` | 删除挂载点 |
| `GET` | `/api/mounts/{id}/tree?path=/` | 列出目录内容 |
| `GET` | `/api/mounts/{id}/file?path=/file.md` | 读取文件 |
| `PUT` | `/api/mounts/{id}/file?path=/file.md` | 写入文件 |
| `GET` | `/api/search?q=关键词` | 全文搜索 |
| `GET` | `/api/graph` | 知识图谱数据 |
| `GET` | `/api/stats` | 统计信息 |
| `GET` | `/api/backlinks?page=xxx` | 反向链接 |
| `GET` | `/api/tags` | 标签列表 |
| `POST` | `/api/sync` | 增量文件同步 |
| `GET` | `/api/health` | 健康检查 |

## 快捷键

| 快捷键 | 操作 |
|--------|------|
| `Ctrl+K` | 搜索文件 |
| `Ctrl+S` | 保存当前文件 |
| `Ctrl+N` | 新建文件 |
| `Ctrl+[` / `Ctrl+]` | 上一个 / 下一个文件 |
| `Ctrl+~` | 切换侧边栏 |
| `Ctrl+B` | 粗体 |
| `Ctrl+I` | 斜体 |

## 项目结构

```
nas-md/
├── start.py              # 一键启动脚本
├── compose.yaml          # Docker Compose 配置
├── Dockerfile            # Docker 镜像定义
├── nas_md/               # Python 后端
│   ├── cli/              # CLI 入口
│   ├── webserver/        # HTTP 服务器 + API
│   ├── search/           # 全文搜索（SQLite FTS5）
│   ├── sync/             # 同步 API
│   └── ...
├── web/                  # Web 前端（原生 JS）
│   ├── index.html
│   ├── app.js            # 主应用逻辑
│   ├── files.js          # 文件浏览器 + API
│   ├── editor.js         # Vditor 编辑器封装
│   ├── app.css           # 样式 + 主题
│   └── lib/              # 第三方库（vendored）
├── storage/              # 内置存储（含 欢迎.md）
└── tests/                # 测试套件
```

## 开发

```bash
# 后端测试
PYTHONPATH=. python -m pytest tests/ -v

# 前端代码检查
npm run lint && npm run format:check

# 前端 E2E 测试
npx playwright install --with-deps chromium
npm test
```

## 许可证

详见 [LICENSE](LICENSE)。
