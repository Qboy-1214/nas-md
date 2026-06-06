# nas-md

浏览和编辑服务器上的 Markdown 文件。本地优先，零依赖启动。**你的数据只留在你的设备上。**

## 功能特性

- **Web 前端** —— 原生 JS + Vditor 编辑器，零框架，零构建，打开即用
  - 多用户隔离（免登录，Cookie 自动会话，各用户挂载点完全隔离）
  - 多目录挂载（无数量限制）
  - 目录树智能过滤（只显示包含 md 文件的目录）
  - 三种编辑模式（即时渲染 / 分屏预览 / 所见即所得）
  - Edge/Firefox 路径自动定位（后端搜索常见位置）
  - 最近访问记录（按访问时间排序，卸载挂载点自动清理）
  - 亮色/暗色主题切换
- **Admin 模式** —— 通过 `/admin` 路径访问，可读写宿主机挂载点
- **Docker 支持** —— 使用 Docker Compose 部署
- **跨平台** —— Windows / Linux / macOS

## 多用户与访问模式

nas-md 采用免登录设计，通过浏览器 Cookie 自动分配 UUID 识别用户身份。不同用户的挂载目录完全隔离。

### 普通用户（默认）

- 访问 `http://host:port/` 即可使用
- 只能看到自己挂载的目录和公开目录
- 可以挂载多个目录（无数量限制）
- 挂载点绑定到当前浏览器会话，重启浏览器后仍然有效

### Admin 用户

- 访问 `http://host:port/admin` 进入 Admin 模式
- 除自己的挂载目录外，还能看到并读写宿主机挂载点（通过 `MOUNT_DIRS` 环境变量配置）
- 无法访问其他普通用户的挂载目录

### 可见性规则

| 挂载点类型 | 普通用户 | Admin |
|-----------|---------|-------|
| 内置存储（builtin-storage） | 可见（只读） | 可见（只读） |
| 宿主机挂载点（MOUNT_DIRS） | 不可见 | 可见（读写） |
| 自己的挂载点 | 可见（读写） | 可见（读写） |
| 其他用户的挂载点 | 不可见 | 不可见 |
| 遗留挂载点（无 owner，非 host） | 可见 | 可见 |

## 快速开始

### 方式一：一键启动（无需 Docker）

需要 **Python 3.11+**，无其他依赖 —— 项目仅使用 Python 标准库。

```bash
# 克隆仓库
git clone https://github.com/Qboy-1214/nas-md.git
cd nas-md

# 启动服务
python3 start.py
```

服务将在 `http://127.0.0.1:8080` 上运行，浏览器会自动打开。

#### 自定义配置

```bash
# 自定义端口
WEB_PORT=9000 python3 start.py

# 配置宿主机挂载点（分号分隔，仅 Admin 可见）
MOUNT_DIRS="/home/user/notes;/home/user/docs" python3 start.py

# Windows
set WEB_PORT=9000 && python start.py
```

#### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `WEB_PORT` | `8080` | HTTP 服务端口 |
| `WEB_HOST` | `127.0.0.1` | HTTP 服务绑定地址 |
| `WEB_ROOT` | `./web` | 前端静态文件目录 |
| `STORAGE_DIR` | `./storage` | 内置存储目录（只读挂载点） |
| `MOUNT_DIRS` | *(空)* | 分号分隔的绝对路径列表，作为宿主机挂载点（仅 Admin 可见可写） |
| `BOT_API_TOKEN` | *(空)* | Telegram Bot API 令牌（可选，仅 Bot 模式需要） |
| `APP_URL` | *(空)* | Web 应用的公开 URL（可选） |
| `API_URL` | *(空)* | 同步 API 的公开 URL（可选） |

### 方式二：Docker Pull（推荐）

直接拉取预构建镜像，无需克隆仓库。

```bash
# 拉取镜像
docker pull ghcr.io/qboy-1214/nas-md:latest

# 运行容器
docker run -d --name nas-md \
  -p 80:8080 \
  -v nas-md-storage:/app/storage \
  -v nas-md-tokens:/app/tokens \
  -v /path/to/notes:/mnt/notes \
  -e MOUNT_DIRS="/mnt/notes" \
  --restart unless-stopped \
  ghcr.io/qboy-1214/nas-md:latest
```

服务将在 `http://localhost` 上运行。访问 `/admin` 进入 Admin 模式。

**常用操作：**

```bash
# 查看日志
docker logs -f nas-md

# 停止
docker stop nas-md

# 更新到最新版
docker pull ghcr.io/qboy-1214/nas-md:latest
docker stop nas-md && docker rm nas-md
# 然后重新运行上面的 docker run 命令
```

### 方式三：Docker Compose

需要 [Docker](https://docs.docker.com/get-docker/) 和 [Docker Compose](https://docs.docker.com/compose/install/)。

```bash
# 启动服务
docker compose up -d

# 查看日志
docker compose logs -f

# 停止
docker compose down
```

服务将在 `http://localhost` 上运行。数据持久化在 Docker 命名卷（`storage` 和 `tokens`）中。

#### Docker Compose 挂载目录

编辑 `compose.yaml` 挂载额外的主机目录：

```yaml
services:
  nas-md:
    # ... 现有配置 ...
    volumes:
      - storage:/app/storage
      - tokens:/app/tokens
      - /path/to/notes:/mnt/notes     # 挂载主机目录
      - /path/to/docs:/mnt/docs       # 挂载主机目录
    environment:
      # ... 现有环境变量 ...
      MOUNT_DIRS: /mnt/notes;/mnt/docs
```

然后启动：

```bash
docker compose up -d
```

### 方式四：本地构建 Docker 镜像

```bash
# 构建镜像
docker build -t nas-md .

# 运行容器
docker run --rm -it -p 80:8080 \
  -v nas-md-storage:/app/storage \
  -v nas-md-tokens:/app/tokens \
  -e MOUNT_DIRS=/mnt/notes \
  nas-md
```

## 挂载点

挂载点允许你通过 Web UI 浏览服务器上的目录。每个挂载的目录在侧边栏选择器中显示为独立条目。

**功能：**
- 浏览嵌套的目录树
- 查看和编辑 Markdown 文件
- 预览媒体文件（图片、音频、视频）
- 路径穿越保护（无法逃逸出挂载根目录）

**API 接口：**

| 方法 | 接口 | 说明 |
|------|------|------|
| `GET` | `/api/mounts` | 列出当前用户可见的挂载点 |
| `GET` | `/api/mounts/public` | 公开挂载点（无需认证） |
| `POST` | `/api/mounts` | 添加挂载点（绑定到当前会话） |
| `DELETE` | `/api/mounts/{id}` | 删除挂载点（仅所有者） |
| `PUT` | `/api/mounts/{id}` | 更新挂载点（名称/公开） |
| `GET` | `/api/mounts/{id}/tree?path=/` | 列出目录内容（单层） |
| `GET` | `/api/mounts/{id}/tree-recursive?path=/` | 递归目录树（含 `hasMd` 标记） |
| `GET` | `/api/mounts/{id}/file?path=/file.md` | 读取文件 |
| `PUT` | `/api/mounts/{id}/file?path=/file.md` | 写入文件 |
| `GET` | `/api/find-path?name=xxx` | 搜索目录完整路径 |
| `GET` | `/api/search?q=关键词` | 全文搜索 |
| `GET` | `/api/stats` | 统计信息（按用户可见范围过滤） |
| `GET` | `/api/graph` | 知识图谱数据（按用户可见范围过滤） |
| `GET` | `/api/query?type=task|tag|heading|link` | 结构化查询 |
| `GET` | `/api/backlinks?page=xxx` | 反向链接 |
| `GET` | `/api/tags[?name=xxx]` | 标签列表或标签下的页面 |
| `GET` | `/api/orphans` | 孤立页面（无入链出链） |
| `POST` | `/api/sync` | 增量文件同步 |
| `GET` | `/api/plugins` | 已加载插件列表 |
| `GET` | `/api/health` | 健康检查 |

## 快捷键

| 快捷键 | 操作 |
|--------|------|
| `Cmd+K` / `Ctrl+K` | 搜索文件 |
| `Cmd+S` / `Ctrl+S` | 保存当前文件 |
| `Cmd+N` / `Ctrl+N` | 新建文件 |
| `Cmd+[` / `Ctrl+[` | 切换到上一个文件 |
| `Cmd+]` / `Ctrl+]` | 切换到下一个文件 |
| `Cmd+~` / `Ctrl+~` | 切换侧边栏 |
| `Cmd+B` / `Ctrl+B` | 切换**粗体** |
| `Cmd+I` / `Ctrl+I` | 切换*斜体* |

## 文档

- [部署到自己的服务器](docs/your-own-server.md)
- [挂载 API 参考](docs/mount-api.md)
- [多用户隔离设计](docs/multi-user-isolation-design.md)
- [项目架构梳理](docs/architecture.md)
- [项目规划](docs/planning.md) — 分阶段实施计划
- [Web 前端需求](docs/web-frontend-requirements.md) — 前端组件规格
- [设计系统](docs/DESIGN.md) — UI 设计规范

## 仓库结构

```
nas-md/
├── start.py              # 一键启动脚本（跨平台）
├── compose.yaml          # Docker Compose 配置
├── Dockerfile            # Docker 镜像定义
├── pyproject.toml        # Python 项目配置（black、ruff、pytest）
├── package.json          # 前端工具配置（ESLint、Prettier、Playwright）
├── eslint.config.js      # ESLint 配置
├── .prettierrc           # Prettier 配置
├── playwright.config.js  # Playwright 配置
├── nas_md/               # Python 包
│   ├── cli/              # CLI 入口
│   ├── config/           # 配置（环境变量）
│   ├── webserver/        # HTTP 服务器 + 挂载 API
│   ├── search/           # 全文搜索（SQLite FTS5）
│   ├── server/           # Telegram Bot 服务器
│   ├── sync/             # 同步 API
│   ├── fs/               # 文件系统工具
│   ├── db/               # 数据库（SQLite）
│   ├── habits/           # 习惯追踪
│   ├── journal/          # 日记管理
│   ├── stats/            # 统计
│   ├── worker/           # 定时任务
│   ├── plugins/          # 插件系统
│   ├── i18n/             # 国际化
│   ├── userconfig/       # 用户配置
│   └── pkg/              # 共享工具包
│       ├── slice/        # 切片工具
│       ├── tg/           # Telegram 工具
│       └── txt/          # 文本处理（哈希、时间戳、Markdown 等）
├── web/                  # Web 前端
│   ├── index.html        # 入口
│   ├── app.js            # 主应用逻辑（状态管理、路由、DOM）
│   ├── files.js          # 文件浏览器 + API 封装
│   ├── editor.js         # Vditor 编辑器封装
│   ├── app.css           # 应用样式（布局 + 组件 + 主题）
│   └── lib/
│       ├── vditor/       # Vditor 编辑器核心（vendored）
│       ├── vditor-cdn/   # Vditor 外部资源（lute、i18n、图标、主题）
│       ├── d3/           # D3.js（知识图谱，vendored）
│       └── fonts/        # Inter 字体（vendored 变量字体）
├── tests/                # 测试套件
│   ├── test_*.py         # Python 单元测试（423 个）
│   └── e2e/              # Playwright 端到端测试（12 个）
└── docs/                 # 文档
```

## 运行测试

### 后端测试（pytest）

```bash
# 运行全部测试
PYTHONPATH=. python3 -m pytest tests/ -v

# 带覆盖率运行
PYTHONPATH=. python3 -m pytest tests/ -v --cov=nas_md --cov-report=term-missing
```

### 前端代码质量（ESLint + Prettier）

```bash
# 安装前端依赖（首次）
npm install

# 代码检查
npm run lint

# 自动修复 lint 问题
npm run lint:fix

# 格式化代码
npm run format

# 格式检查（CI 用）
npm run format:check
```

### 前端端到端测试（Playwright）

```bash
# 安装 Playwright 浏览器（首次）
npx playwright install --with-deps chromium

# 运行 e2e 测试
npm test

# 运行 e2e 测试（带浏览器界面）
npm run test:headed
```

## CI 流程

GitHub Actions 自动运行以下检查：

| Job | 工具 | 说明 |
|-----|------|------|
| `quality` | ruff + black | Python 代码检查和格式验证 |
| `frontend-quality` | ESLint + Prettier | 前端代码检查和格式验证 |
| `test` | pytest | Python 单元测试（423 个） |
| `frontend-test` | Playwright | 前端端到端测试（12 个） |

## 开发规范

- 编写**测试**
- 禁止 panic，错误是业务逻辑的一部分
- 如果要忽略错误，必须留下注释说明原因
- 始终包装错误，附加上下文信息
- 优先使用真实实现或 Fake，而非 Mock 和 Stub
- 代码库设计为对 LLM 友好 —— 一个人或一个 LLM 能装下整个项目
- 前端不使用构建系统 —— 10 年后打开 `/web/index.html` 应该直接能用
- 所有前端库都 vendored 在 `web/lib/` 中
- 前端使用原生 JavaScript，无框架依赖
- 提交前运行 `npm run lint && npm run format:check` 确保代码质量

## 许可证

详见 [LICENSE](LICENSE)。
