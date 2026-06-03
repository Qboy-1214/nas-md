# nas-md

一个私密的、安静的个人思考空间。一个管理 `.md` 文件的简单应用。

个人知识管理系统 —— 笔记、日记、习惯、清单，全部以纯 `.md` 文件存储，本地优先，对 LLM 友好。**隐私优先 —— 你的数据只留在你的设备上。**

> 以纯本地文件的形式拥有自己的数据。
> 拥有打开这些文件的软件。
> 用文件和自己的大脑积累知识。
> **纯文件和自主可控的软件，才能穿越时间。**

## 功能特性

- **笔记** —— 纯 Markdown 文件，一个想法一条笔记
- **日记** —— 按日记录，存储在 `journal/YYYY.MM Month.md`
- **习惯** —— 用热力图可视化追踪每日习惯
- **清单** —— `Read.md`、`Watch.md`、`Shop.md` 等
- **任务** —— 快速收集到 `Later.md`
- **Telegram Bot** —— 随时随地访问你的文件
- **Web 前端** —— 原生 JS + Vditor 编辑器，零框架，零构建，打开即用
  - 多目录挂载（游客限 1 个，登录用户不限）
  - 目录树智能过滤（只显示包含 md 文件的目录）
  - 访客模式（无需登录即可浏览公开目录）
  - 三种编辑模式（即时渲染 / 分屏预览 / 所见即所得）
  - Edge/Firefox 路径自动定位（后端搜索常见位置）
- **挂载点** —— 浏览服务器上的任意目录（读写）
- **Docker 支持** —— 使用 Docker Compose 部署
- **跨平台** —— Windows / Linux / macOS

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

# 挂载额外目录（分号分隔）
WEB_PORT=9000 MOUNT_DIRS="/home/user/notes;/home/user/docs" python3 start.py

# Windows
set WEB_PORT=9000 && python start.py
```

#### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `WEB_PORT` | `8080` | HTTP 服务端口 |
| `WEB_HOST` | `127.0.0.1` | HTTP 服务绑定地址 |
| `WEB_ROOT` | `./web` | PWA 前端目录 |
| `STORAGE_DIR` | `./storage` | 文件存储目录 |
| `TOKENS_DIR` | `./tokens` | 认证令牌目录 |
| `MOUNT_DIRS` | *(空)* | 分号分隔的绝对路径列表，作为可浏览的挂载点 |
| `BOT_API_TOKEN` | *(空)* | Telegram Bot API 令牌（可选） |
| `APP_URL` | *(空)* | Web 应用的公开 URL |
| `API_URL` | *(空)* | 同步 API 的公开 URL |

### 方式二：Docker Compose

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

#### 手动构建 Docker 镜像并运行

```bash
# 构建镜像
docker build -t nas-md .

# 运行容器
docker run --rm -it -p 80:8080 \
  -v nas-md-storage:/app/storage \
  -v nas-md-tokens:/app/tokens \
  -e APP_URL=http://localhost \
  nas-md
```

## 挂载点（浏览服务器目录）

挂载点允许你通过 Web UI 浏览服务器上的目录。每个挂载的目录在侧边栏选择器中显示为独立条目。

**功能：**
- 浏览嵌套的目录树
- 查看和编辑 Markdown 文件
- 预览媒体文件（图片、音频、视频）
- 创建、重命名、删除文件和目录
- 路径穿越保护（无法逃逸出挂载根目录）

**API 接口：**

| 方法 | 接口 | 说明 |
|------|------|------|
| `GET` | `/api/mounts` | 列出所有挂载点（需认证） |
| `GET` | `/api/mounts/public` | 公开挂载点（无需认证） |
| `POST` | `/api/mounts` | 添加挂载点 |
| `DELETE` | `/api/mounts/{id}` | 删除挂载点 |
| `PUT` | `/api/mounts/{id}` | 更新挂载点（名称/公开） |
| `GET` | `/api/mounts/{id}/tree?path=/` | 列出目录内容（单层） |
| `GET` | `/api/mounts/{id}/tree-recursive?path=/` | 递归目录树（含 `hasMd` 标记） |
| `GET` | `/api/mounts/{id}/file?path=/file.md` | 读取文件 |
| `PUT` | `/api/mounts/{id}/file?path=/file.md` | 写入/创建文件 |
| `PUT` | `/api/mounts/{id}/rename?oldPath=/a.md&newPath=/b.md` | 重命名/移动文件或目录 |
| `PUT` | `/api/mounts/{id}/mkdir?path=/newdir` | 创建目录 |
| `DELETE` | `/api/mounts/{id}/file?path=/file.md` | 删除文件或目录 |
| `GET` | `/api/find-path?name=xxx` | 搜索目录完整路径（无需认证） |
| `GET` | `/api/search?q=关键词` | 全文搜索（UI 就绪，后端待实现） |

## 文件结构

你不需要操心结构 —— 它是预定义的。当然，你也可以使用任何你喜欢的结构。

- 聊天：`Chat.md`
- 笔记：`brain/Note.md`、`<category>/*.md`
- 项目：`Project.md`、`*.md`
- 清单：`Read.md`、`Watch.md`、`Shop.md`
- 日记：`journal/2024.08 August.md`
- 任务：`Later.md`
- 习惯：`habits/Ate consciously.md`、`habits/*.md`
- 图片：`media/*`（png、jpg、webp、gif）
- 归档：`archive/*.md`
- 配置：`config.json`

## 快捷键

| 快捷键 | 操作 |
|--------|------|
| `[` | 插入文件链接 |
| `Cmd+K` / `Ctrl+K` | 打开文件搜索弹窗 |
| `Cmd+N` / `Ctrl+N` | 新建文件 |
| `Cmd+M` / `Ctrl+M` | 移动文件 |
| `Cmd+D` / `Ctrl+D` | 删除文件 |
| `Cmd+Enter` / `Ctrl+Enter` | 打开聊天 |
| `Cmd+Shift+Enter` / `Ctrl+Shift+Enter` | 切换聊天对话框 |
| `Cmd+[` / `Ctrl+[` | 切换到上一个文件 |
| `Cmd+]` / `Ctrl+]` | 切换到下一个文件 |
| `Cmd+~` / `Ctrl+~` | 切换侧边栏 |
| `T` | 切换主题（自动/亮色/暗色） |
| `L` | 切换布局（自动/横屏/竖屏） |
| `Cmd+B` / `Ctrl+B` | 切换**粗体** |
| `Cmd+I` / `Ctrl+I` | 切换*斜体* |
| `Cmd+Y` / `Ctrl+Y` | 插入复选框 |
| `Cmd/Ctrl` + `Click` | 复制内联文本 / 打开链接 |

## 文档

- [部署到自己的服务器](docs/your-own-server.md)
- [挂载 API 参考](docs/mount-api.md)
- [项目架构梳理](docs/architecture.md)
- [项目规划](docs/planning.md) — 分阶段实施计划
- [Web 前端需求](docs/web-frontend-requirements.md) — 前端组件规格

## 仓库结构

```
nas-md/
├── start.py              # 一键启动脚本（跨平台）
├── compose.yaml          # Docker Compose 配置
├── Dockerfile            # Docker 镜像定义
├── pyproject.toml        # Python 项目配置（black、ruff、pytest）
├── nas_md/               # Python 包
│   ├── cli/              # CLI 入口
│   │   ├── __init__.py   # 命令实现
│   │   └── __main__.py   # python3 -m nas_md.cli 支持
│   ├── config/           # 配置（环境变量）
│   ├── webserver/        # HTTP 服务器 + 挂载 API
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
│       └── txt/          # 文本处理（哈希、时间戳等）
├── web/                  # Web 前端
│   ├── index.html        # 入口
│   ├── app.js            # 主应用逻辑（状态管理、路由、DOM）
│   ├── files.js          # 文件浏览器 + API 封装
│   ├── editor.js         # Vditor 编辑器封装
│   ├── app.css           # 应用样式（布局 + 组件 + 主题）
│   └── lib/
│       ├── vditor/       # Vditor 编辑器核心（vendored）
│       └── vditor-cdn/   # Vditor 外部资源（lute、i18n、图标、主题）
│                           # vendored 以防止浏览器 Tracking Prevention 拦截 CDN 请求
├── tests/                # 测试套件（272 个测试）
└── docs/                 # 文档
```

## 运行测试

```bash
# 运行全部测试
PYTHONPATH=. python3 -m pytest tests/ -v

# 带覆盖率运行
PYTHONPATH=. python3 -m pytest tests/ -v --cov=nas_md --cov-report=term-missing
```

## 后端开发规范

- 编写**测试**
- 禁止 panic，错误是业务逻辑的一部分
- 如果要忽略错误，必须留下注释说明原因
- 始终包装错误，附加上下文信息
- 优先使用真实实现或 Fake，而非 Mock 和 Stub
- **一切以可移植性为前提，全部存储在纯 `.md` 文件中**
- 代码库设计为对 LLM 友好 —— 一个人或一个 LLM 能装下整个项目

## 前端开发规范

- 不使用构建系统 —— 10 年后打开 `/web/index.html` 应该直接能用
- 所有前端库都 vendored 在 `web/lib/` 中
- 前端使用原生 JavaScript，无框架依赖
- 避免脆弱的测试 —— 竞态条件是最常见的 bug 来源

## 许可证

详见 [LICENSE](LICENSE)。
