# 项目架构梳理

## 概述

nas-md 是一个**纯 Python 标准库**构建的个人知识管理系统。所有数据以 `.md` 文件存储在本地，通过 Telegram Bot 和 PWA 前端双入口访问。项目零第三方依赖，设计目标是一个人（或一个 LLM）能装下整个项目的全部逻辑。

## 架构分层

```
┌──────────────────────────────────────────────────────┐
│                     入口层                           │
│                                                      │
│   Telegram Bot (server/)    PWA Web (web/)           │
│   CLI 命令行 (cli/)                                  │
├──────────────────────────────────────────────────────┤
│                     服务层                           │
│                                                      │
│   HTTP Server (webserver/)    Sync API (sync/)       │
│   - 挂载 API (CRUD)           - LCS 文件合并         │
│   - 静态文件服务              - fslog 操作日志        │
│                               - Token 认证           │
├──────────────────────────────────────────────────────┤
│                     业务层                           │
│                                                      │
│   FS (fs/)           Journal (journal/)              │
│   - 用户隔离文件系统   - 按月日记管理                  │
│   - OS/内存双后端     - 时间戳记录                    │
│   - 路径安全校验      - Emoji 追加                    │
│                                                      │
│   Habits (habits/)   Stats (stats/)                  │
│   - 年度 Emoji 热力图  - 今日完成报告                 │
│   - 周视图            - 归档统计                      │
│                                                      │
│   UserConfig (userconfig/)  Worker (worker/)         │
│   - JSON 用户配置         - 定时任务调度               │
│   - 时区/模式/快捷按钮    - 到期任务移动               │
│                           - 已完成项清理               │
│                                                      │
│   Plugins (plugins/)                                 │
│   - WorldClock 世界时钟插件                           │
├──────────────────────────────────────────────────────┤
│                     基础层                           │
│                                                      │
│   DB (db/)           Config (config/)                │
│   - 内存键值存储       - 环境变量加载                  │
│   - 临时文件持久化     - 配置单例                      │
│                                                      │
│   Search (search/)   i18n (i18n/)   pkg/             │
│   - FTS5 全文搜索     - Emoji 关键词映射              │
│   - 对象索引器         - txt/ 文本处理                │
│   - 结构化查询API      - tg/ Telegram 类型定义        │
│                      - slice/ 分片工具                │
└──────────────────────────────────────────────────────┘
```

## 核心模块详解

### 1. FS 文件系统 (`nas_md/fs/`)

整个项目的基石。提供**用户隔离**的文件系统抽象。

**设计要点：**

- **双后端**：`backend="os"` 用于生产环境，`backend="mem"` 用于测试。内存后端用 `dict[bytes, bytes]` 模拟文件系统，所有操作完全隔离。
- **路径安全**：`safe_path()` 方法通过 `_is_local()` 检测路径穿越（`..` 逃逸），所有文件操作都经过此校验。
- **文件名清洗**：`FORBIDDEN_CHARS` 映射表将非法字符替换为全角等价字符（如 `<` → `＞`），保证跨平台兼容。
- **用户隔离**：每个 Telegram 用户 ID 对应 `storage/<user_id>/` 下的独立目录树。

**核心数据结构：**

```python
@dataclass
class File:
    name: str          # 原始文件名
    hash: str          # MD5 前 11 位（安全引用）
    display_name: str  # 去掉 .md 后缀的友好名称
    ctime: int         # 创建时间（毫秒）
    is_multiline: bool # 是否多行
    is_dir: bool       # 是否为目录
    parent_dir: str    # 父目录
```

**文件名哈希**：使用 MD5 前 11 位作为文件名的安全引用，避免在 Telegram callback data（64 字节限制）中暴露真实文件名。

### 2. Server Telegram Bot (`nas_md/server/`)

项目中最庞大的模块（~1588 行），处理所有 Telegram 交互。

**命令路由机制：**

```python
handlers = {
    CMD_HOME: self._cmd_home,
    CMD_DONE: self._cmd_done,
    CMD_DEL: self._cmd_del,
    # ... 50+ 命令
}
```

**状态管理：** 通过 `DB` 存储"输入期望"（input_expectation）。例如用户触发搜索后，服务端记录 `CMD_SEARCH_NOTES`，下一条消息即被当作搜索关键词处理。

**内联键盘：** 所有 Bot 交互通过 `Keyboard` + `Btn` + `Cmd` 的回调体系完成。每个按钮携带一个序列化的命令（名称 + 参数），用户点击时回传给 Bot 处理。

**消息流：**

```
用户消息 → handle() → 插件检查(WorldClock)
                   → 命令路由(_handle_command)
                   → 普通消息处理(_handle_message)
                   → 输入期望检查(DB.input_expectation)
```

### 3. Webserver HTTP 服务器 (`nas_md/webserver/`)

基于 Python 标准库 `HTTPServer` + `SimpleHTTPRequestHandler`，同时服务两类请求：

**挂载 API**：将服务器上的任意目录暴露为 RESTful API，支持完整的 CRUD 操作。路径安全通过 `os.path.realpath()` + 前缀校验保证。

**认证模型**：
- Token 写在配置文件（`WEB_AUTH_TOKEN` 环境变量），非随机生成，禁止注册
- 公开挂载点（`public=true`）的 tree/file 读取无需认证
- 游客挂载的目录自动设为 `public=true`
- 所有写操作需要认证

**静态文件服务**：服务 PWA 前端（`web/` 目录），所有前端库 vendored，无构建步骤。

**Gzip 压缩**：当客户端 `Accept-Encoding` 包含 `gzip` 时，自动压缩响应体。

### 4. Sync 同步引擎 (`nas_md/sync/`)

**LCS Merge**：使用最长公共子序列算法合并两个版本的文件。核心逻辑：

```
lines1 = s1.split("\n")
lines2 = s2.split("\n")
# 构建 DP 表 → 回溯 → 合并结果
```

这个算法假设文件差异主要是行的增删改，对于笔记类场景是合理的。

**fslog**：文件系统操作日志，记录所有 rename/delete 操作。格式：

```
<timestamp> <op> <url_encoded_old_path> <url_encoded_new_path>
```

用于跨设备同步时追踪文件变更。

**Token 认证**：

```
一次性令牌(10分钟过期) → 交换 → 永久令牌(SHA-256+salt 存储)
```

IP 暴力破解防护：连续提交无效令牌会封禁 IP 10 分钟。

### 5. Journal 日记系统 (`nas_md/journal/`)

按月存储日记文件（`journal/2026.06 June.md`），每天一个二级标题：

```markdown
## 3 June, Monday
`14:30` 今天开始写架构文档
`15:00` 完成了翻译工作 ✅
```

**并发安全**：使用用户级别的 `Lock` 防止同一用户的并发写入冲突。

**Emoji 追加**：支持向当天记录追加 Emoji，自动合并到日期标题行。

### 6. Habits 习惯追踪 (`nas_md/habits/`)

用 Emoji 网格可视化一年的习惯完成情况：

```
### June
🟢🟢⚪️🟢🟢🟢🟡 Exercise
⚪️⚪️🟢⚪️🟢⚪️⚪️ Reading
```

- 🟢 工作日完成
- 🟡 周末完成
- ⚪️ 跳过
- Mood 习惯使用 6 级 Emoji 量表（🤕 😔 😐 🙂 😊）

数据按年存储在 `insights/2026 Habits.md`。

### 7. Worker 定时任务 (`nas_md/worker/`)

两个核心任务：

1. **到期任务移动**：将计划中到期的任务自动移到用户的 `Chat.md` 收件箱
2. **已完成项清理**：将 `Chat.md` 和 `Later.md` 中已完成的 checklist 项归档到 `Done.md`，并写入日记

### 8. UserConfig 用户配置 (`nas_md/userconfig/`)

以 JSON 文件形式存储在用户根目录（`config.json`），支持：

- 显示模式（Full / Notes / Tasks / Journal / Chat）
- 时区设置
- 快捷按钮和移动目标按钮
- 计划任务调度
- 番茄钟时长
- 双 Emoji 开关
- 快速习惯开关

### 9. Plugins 插件系统 (`nas_md/plugins/`)

当前内置 **WorldClockPlugin**：自动识别消息中的日期/时间/时间戳，转换为多个时区显示。

```
输入: 03.06.2026
输出:
🕰 03.06.2026 00:00:00 UTC
🏝 03.06.2026 03:00:00 CY
⛰ 03.06.2026 02:00:00 ME
🔺 03.06.2026 03:00:00 MSK
```

### 10. Search 搜索与索引 (`nas_md/search/`)

基于 SQLite FTS5 的全文搜索 + 结构化对象索引模块。

**核心组件：**

- **`__init__.py`** — 数据库管理、索引流程、查询函数
  - `init_db()` — 初始化 FTS5 虚拟表 + 对象表（tags/tasks/headings）
  - `index_file(path, content)` — 单文件索引（全文 + 对象提取，单事务）
  - `rebuild_index(directories)` — 全量重建索引
  - `search(query, limit)` — FTS5 全文搜索
  - `query_tasks(status)` / `query_tags(name)` / `query_headings(page_path)` — 结构化查询

- **`extract.py`** — 纯函数提取器（无副作用，无 IO）
  - `extract_frontmatter(content)` — PyYAML 解析 YAML frontmatter
  - `extract_headings(content)` — `# ~ ######` 标题提取
  - `extract_tags(content, frontmatter)` — `#tag` + frontmatter tags（去重，frontmatter 优先）
  - `extract_tasks(content)` — `- [ ]` / `- [x]` 任务提取

**数据库表结构：**

```
pages          — 页面索引（path, title, content, frontmatter JSON）
pages_fts      — FTS5 全文搜索虚拟表
tags           — 标签索引（name, source: body|frontmatter）
tasks          — 任务索引（content, done, line_number）
headings       — 标题索引（level, text, line_number）
links          — 链接索引（target, display_text, line_number）
```

所有对象表通过 `ON DELETE CASCADE` 关联 pages 表，删除页面时自动清理。

**索引流程：**

```
文件保存 → extract_frontmatter → extract_headings/tags/tasks/links
         → UPSERT pages（含 frontmatter JSON）
         → DELETE 旧对象 → INSERT 新对象 → COMMIT（单事务）
```

**API 端点：**

- `GET /api/search?q=keyword` — 全文搜索
- `GET /api/query?type=task|tag|heading|link` — 结构化查询
- `GET /api/backlinks?page=xxx` — 反链查询
- `GET /api/stats` — 统计数据（文件数、任务完成率、标签数等）
- `GET /api/graph` — 图谱数据（节点+边，用于 D3.js 可视化）

## Web 前端架构

### 技术选型

| 组件 | 选择 | 说明 |
|------|------|------|
| 语言 | 原生 JavaScript | 无框架，零构建步骤 |
| 编辑器 | Vditor | Markdown 编辑器，vendored 到 `web/lib/vditor/` |
| 布局 | CSS Flexbox | `.layout` 容器 `display: flex`，侧边栏 + 主内容区 |
| 状态管理 | 全局 `state` 对象 | 集中式，无响应式绑定 |
| 事件绑定 | `onclick` HTML 属性 | 直接绑定到全局函数 |
| DOM 操作 | 原生 DOM API | `getElementById` / `innerHTML` / `style.display` |

### 文件结构

```
web/
├── index.html              # 入口页（SPA 外壳）
├── app.js                  # 应用主逻辑（状态管理、页面路由、DOM 操作）
├── files.js                # 文件浏览 + API 封装
├── editor.js               # Vditor 编辑器封装
├── app.css                 # 应用样式（布局、侧边栏、编辑器、Modal）
└── lib/
    └── vditor/             # Vditor Markdown 编辑器（vendored）
```

### 状态管理

全局 `state` 对象统一管理所有前端状态：

```javascript
const state = {
  token: null,              // 认证 token
  sidebarCollapsed: false,  // 侧边栏折叠状态
  mounts: [],               // 挂载点列表
  expandedMounts: [],       // 已展开的挂载点 ID（含目录路径）
  treeData: {},             // 递归树缓存 { mountId: { path: DirEntry } }
                          //   DirEntry: { name, path, isDir, hasMd, children, ... }
  currentPath: null,        // 当前打开的文件路径
  currentMountId: null,     // 当前文件所属挂载点
  editorMode: 'ir',         // 编辑器模式 (ir | sv | wysiwyg)
  dirty: false,             // 是否有未保存修改
  searchResults: [],        // 搜索结果
  recentFiles: [],          // 最近修改文件
  showSettings: false,      // 是否显示设置页
};
```

页面切换通过 `showPage('welcome' | 'editor' | 'settings')` 实现，通过 `display` 属性切换三个面板的可见性。

### 布局结构

```
<div class="layout">              ← display: flex, height: 100vh
  <aside id="sidebar">            ← width: 280px, height: 100vh
    ├── .sidebar-header           ← Logo + 折叠按钮
    ├── .search-box               ← 搜索输入框 + 结果下拉
    ├── #file-tree                ← 文件树（flex: 1, overflow-y: auto）
    └── .sidebar-footer           ← 首页/设置/登录按钮
  </aside>
  <main class="main">             ← flex: 1, min-width: 0
    <header class="topbar">        ← 面包屑 + 编辑器模式 + 保存
    </header>
    <div class="editor-area">     ← flex: 1, overflow: hidden
      ├── #welcome-page           ← 欢迎页 Hero + 打开目录 + 最近修改
      ├── #editor-container       ← Vditor 编辑器
      └── #settings-page          ← 设置页
    </div>
  </main>
</div>
```

### 关键设计决策

**为什么不用 Alpine.js：**

Alpine 3.14.3 的 `x-data="app()"` 表达式在 `with(scope)` 中评估时，Alpine 的 `has` trap 会阻止 `with` 沿作用域链向上查找全局变量，导致表达式返回 `undefined`。调试数小时后决定放弃，改用原生 JS。

**为什么需要 `.layout` 容器：**

`.sidebar` 和 `.main` 需要并排显示，必须有一个父容器设置 `display: flex`。没有这个容器时，两个块级元素按正常文档流上下排列，侧边栏把主内容区挤到下面。

**侧边栏高度：**

`.sidebar` 必须显式设置 `height: 100vh`，否则只被内容撑开，在内容少时侧边栏只有顶部一小部分。

**Modal 显示/隐藏：**

CSS 中 `.modal-overlay` 默认 `display: none`，通过添加 `.active` 类切换为 `display: flex`。不能直接在 CSS 中设 `display: flex`，否则 Modal 默认可见。

### 各文件职责

**index.html**：页面骨架
- `.layout` 容器（flex 行布局）
- `#sidebar` 侧边栏（可折叠）
- `.main` 主内容区（顶部栏 + 编辑器区域）
- 欢迎页 / 编辑器 / 设置页（通过 `display` 切换）
- 登录 Modal / 新建文件 Modal
- 脚本加载顺序：vditor → files.js → editor.js → app.js（同步，无 defer）

**app.js**：应用主逻辑
- 全局 `state` 对象
- `showPage(page)` — 页面切换
- `renderSidebar()` — 侧边栏渲染（文件树递归）
- `loadMounts()` / `openDirectory()` / `toggleMountPublic()` — 挂载点管理
- `openFile(path)` / `saveFile()` / `confirmNewFile()` — 文件操作
- `showLogin()` / `login()` / `logout()` — 认证
- `navigateHome()` / `showSettings()` — 导航
- `doSearch()` — 搜索

**files.js**：API 层
- `API.request(path, options)` — 统一 fetch 封装（自动附加 Authorization header）
- `API.getMounts()` / `API.getPublicMounts()` — 挂载点列表
- `API.getTree(mountId, path)` — 递归目录树（tree-recursive API）
- `API.findMountPath(dirName)` — 后端搜索目录完整路径
- `API.getFile()` / `API.putFile()` / `API.deleteFile()` — 文件 CRUD
- `API.rename()` / `API.mkdir()` — 文件操作
- `API.search(query)` — 全文搜索
- 辅助函数：`loadMounts()` / `loadTree()` / `findMountForPath()` / `_treeHasPath()`

**editor.js**：编辑器封装
- `initEditor(content, mode, readonly, cursorOffset)` — 初始化 Vditor 实例（仅创建，不对外暴露）
- `window._getVditor()` — 暴露 Vditor 实例给 app.js
- `window._reinitEditor(mode)` — 销毁当前实例并用新模式重建（Vditor 3.x 无 `setMode()`）
- `getEditorContent()` / `getCurrentFileInfo()` — 内容/文件信息获取
- `isDirty()` / `markSaved()` — 脏检查
- `setFileInfo(mountId, relPath)` — 当前文件信息
- **模式切换机制**：Vditor 3.x 不支持运行时 `setMode()`，切换模式必须 destroy + reinit。`_reinitEditor` 在销毁前保存 scrollTop 和 cursor text offset，新实例渲染后通过 `requestAnimationFrame` 恢复两者，保证切换编辑模式时滚动位置和光标不丢失

**app.css**：样式系统
- CSS 变量（颜色、间距、阴影、圆角）
- 亮色主题 + 暗色主题（`prefers-color-scheme: dark`）
- Flexbox 布局（`.layout` / `.sidebar` / `.main`）
- 侧边栏折叠动画（`transition: all 0.2s ease`）
- Modal 样式（overlay + 居中卡片）
- 响应式（移动端侧边栏变为绝对定位）

## 数据流全景

```
                    ┌─────────────┐
                    │  Telegram   │
                    │    User     │
                    └──────┬──────┘
                           │ 消息/命令
                    ┌──────▼──────┐
                    │   Server    │
                    │  (server/)  │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
        ┌─────▼─────┐ ┌───▼───┐ ┌─────▼─────┐
        │    FS     │ │  DB   │ │ UserConfig│
        │ (文件读写) │ │(状态) │ │  (配置)   │
        └─────┬─────┘ └───────┘ └───────────┘
              │
        ┌─────▼─────────────────────────────┐
        │         storage/<user_id>/         │
        │  Chat.md / Later.md / Done.md     │
        │  journal/  habits/  insights/     │
        │  archive/  media/  config.json    │
        └───────────────────────────────────┘

                    ┌─────────────────────────────┐
                    │        Browser (Web)         │
                    │  index.html + app.js +      │
                    │  files.js + editor.js        │
                    │  (原生 JS，无框架)            │
                    └──────────────┬──────────────┘
                                   │ HTTP
                    ┌──────────────▼──────────────┐
                    │       Webserver             │
                    │     (webserver/)            │
                    └──────────────┬──────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
        ┌─────▼─────┐      ┌──────▼──────┐     ┌──────▼──────┐
        │ Mount API │      │ Static Files│     │  Sync API   │
        │(CRUD目录) │      │ (web/lib/)  │     │(文件同步)   │
        └───────────┘      └─────────────┘     └─────────────┘

        Web 前端内部结构：
        ┌──────────────────────────────────────────┐
        │ .layout (display: flex, height: 100vh)    │
        │ ┌────────────┐  ┌───────────────────────┐│
        │ │  #sidebar   │  │      .main            ││
        │ │  (280px)    │  │  ┌─────────────────┐ ││
        │ │ ┌────────┐ │  │  │   .topbar       │ ││
        │ │ │搜索框  │ │  │  │ (面包屑+保存)   │ ││
        │ │ ├────────┤ │  │  ├─────────────────┤ ││
        │ │ │文件树  │ │  │  │  .editor-area   │ ││
        │ │ │        │ │  │  │ ┌─────────────┐ │ ││
        │ │ │        │ │  │  │ │ 欢迎页      │ │ ││
        │ │ │        │ │  │  │ │ 编辑器      │ │ ││
        │ │ │        │ │  │  │ │ 设置页      │ │ ││
        │ │ │        │ │  │  │ └─────────────┘ │ ││
        │ │ ├────────┤ │  │  └─────────────────┘ ││
        │ │ │底部按钮│ │  │                       ││
        │ │ └────────┘ │  └───────────────────────┘│
        │ └────────────┘                            │
        └──────────────────────────────────────────┘
```

## 文件存储结构

```
storage/
├── fslog                          # 文件系统操作日志（全局）
├── <user_id>/                     # 用户隔离目录
│   ├── config.json                # 用户配置
│   ├── Chat.md                    # 聊天/收件箱（任务入口）
│   ├── Later.md                   # 稍后处理
│   ├── Done.md                    # 已完成归档
│   ├── Read.md                    # 阅读清单
│   ├── Watch.md                   # 观影清单
│   ├── Shop.md                    # 购物清单
│   ├── Project.md                 # 项目笔记
│   ├── brain/                     # 知识库
│   │   └── Note.md
│   ├── journal/                   # 日记
│   │   └── 2026.06 June.md
│   ├── habits/                    # 习惯定义
│   │   └── Exercise.md            # 内容是习惯对应的 Emoji
│   ├── insights/                  # 习惯数据
│   │   └── 2026 Habits.md
│   ├── archive/                   # 归档目录
│   └── media/                     # 媒体文件
└── tokens/                        # 认证令牌
    └── <sha256_hash>              # 内容是 user_id
```

## 安全设计

| 威胁 | 防护措施 |
|------|----------|
| 路径穿越 | `FS.safe_path()` + `_is_local()` 双重校验；Mount API 使用 `realpath` + 前缀匹配 |
| 文件名注入 | `FORBIDDEN_CHARS` 全角替换 |
| 令牌暴力破解 | IP 封禁 10 分钟；SHA-256(salt+token) 存储 |
| 跨域请求 | CORS 头 `Access-Control-Allow-Origin: *` |
| 隐藏文件泄露 | 目录列表自动过滤 `.` 开头的文件 |
| 并发写入冲突 | 用户级别 `Lock`（Journal 模块） |

## 测试策略

- **272 个测试**，覆盖所有核心模块
- **Fake 而非 Mock**：使用 `FakeTG`、`FakeDB`、内存 `FS` 实现完全隔离的单元测试
- **临时目录**：文件操作测试使用 `tempfile.mkdtemp()`，测试后自动清理
- **双后端验证**：FS 模块的所有操作在 OS 后端和内存后端上行为一致

## 设计哲学

1. **纯文件即数据库**：没有 ORM，没有迁移脚本，文件系统就是数据库
2. **纯标准库**：零第三方依赖，Python 3.11+ 开箱即用
3. **对 LLM 友好**：代码结构清晰，命名直观，一个上下文窗口能装下整个项目
4. **可移植性优先**：文件名跨平台安全，路径分隔符统一处理，无平台特定代码
5. **减法设计**：没有前端构建系统，没有微服务，没有消息队列 —— 只有文件和打开文件的软件
