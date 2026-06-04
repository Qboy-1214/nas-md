# nas-md 项目规划

> 日期：2026-06-03
> 定位：Web 前端为主要入口，Telegram Bot 为辅助
> 核心方向：知识网络（双向链接 + 内容索引 + 结构化查询）

---

## 一、现状诊断

### 项目优势

- 架构清晰，分层合理（入口层 / 服务层 / 业务层 / 基础层）
- 纯 Python stdlib，零第三方依赖，部署极简
- FS 双后端（OS / Mem）设计，测试隔离彻底
- 271 个测试覆盖核心模块
- 双入口设计（Telegram Bot + Web）有前瞻性

### 核心问题

| # | 问题 | 影响 |
|---|------|------|
| 1 | Server 模块 1588 行，50+ 命令集中在单文件 | 新增命令必须改巨文件，维护成本高 |
| 2 | 没有内容索引，搜索只能按文件名 | 无法做全文搜索和跨文件查询 |
| 3 | 笔记没有元数据层 | 无法结构化查询，笔记是"静态文档"而非"知识节点" |
| 4 | 同步机制是半成品 | `_handle_sync_filenames` 返回空数据 |
| 5 | Mount API 没有认证 | 任何人都能 CRUD 服务器文件 |
| 6 | Worker 定时任务没有调度入口 | 定义了 Worker 类但无启动机制 |

---

## 二、技术选型决策

### 前端编辑器：Vditor

**选择理由：**

Vditor 是一款成熟的浏览器端 Markdown 编辑器（TypeScript 实现），支持三种编辑模式：

- **所见即所得（WYSIWYG）**：对不熟悉 Markdown 的用户友好
- **即时渲染（IR）**：类似 Typora，输入即渲染，最优雅的编辑体验
- **分屏预览（SV）**：传统双栏模式，适合大屏

关键特性：
- 支持 CommonMark + GFM 规范
- 支持 YAML Front Matter（与元数据需求完美契合）
- 支持流程图、甘特图、时序图（Mermaid）、数学公式（KaTeX / MathJax）
- 支持任务列表、脚注、目录（ToC）
- 内置代码高亮（36 套主题），多主题切换
- 支持中文语境优化（中西文自动空格、标点修正）
- 思源笔记（siyuan-note，GitHub 30K+ stars）同款编辑器

**引入方式：** vendored 到 `web/lib/vditor/`

### 全文搜索：SQLite FTS5

**选择理由：**
- Python stdlib 自带 `sqlite3`，零额外依赖
- FTS5 扩展内置，支持中文分词
- 性能优秀，百万级文件无压力
- 与现有技术栈一致（db/ 模块已有 SQLite 使用经验）

### 前端框架：原生 JavaScript

**选择理由：**
- 零依赖，零构建系统
- 10 年后打开 `/web/index.html` 仍然直接能用
- 参考 files.md（Go + 原生 JS 的本地优先文件管理器）的实践
- 所有交互通过 `onclick` 绑定 + 直接 DOM 操作

**放弃 Alpine.js 的原因：**

Alpine 3.14.3 的 `x-data="app()"` 表达式在 `with(scope)` 中评估时，`app` 函数不在 scope 的 Proxy 中，且 Alpine 的 `has` trap 会阻止 `with` 沿作用域链向上查找全局变量，导致表达式返回 `undefined`。调试数小时后决定放弃，改用原生 JS。

### 索引器：自研 Python

**选择理由：**
- 扫描 .md 文件，提取 Task / Tag / Link / Frontmatter
- 结果存入 SQLite，供查询 API 使用
- 纯 Python 实现，逻辑可控

---

## 三、Phase 1 实施记录（已完成）

### 1.1 Web 前端搭建

**创建时间：** 2026-06-03

**技术栈：**
- Vditor（Markdown 编辑器，vendored）
- 原生 JavaScript（无框架）
- Python stdlib HTTPServer（后端）

**文件结构：**

```
web/
├── index.html        # 入口页（侧边栏 + 主编辑区）
├── app.js            # 应用主逻辑（路由、状态、DOM 操作）
├── files.js          # 文件浏览 + API 封装
├── editor.js         # Vditor 编辑器封装
├── app.css           # 应用样式（含布局、侧边栏、编辑器）
└── lib/
    └── vditor/       # Markdown 编辑器（vendored）
```

**前端架构说明：**

- **无框架**：不使用 Alpine.js / Vue / React，纯原生 JS + DOM API
- **全局状态**：`state` 对象统一管理所有状态（token、mounts、当前文件、编辑器模式等）
- **页面切换**：`showPage('welcome' | 'editor' | 'settings')` 通过 `display` 切换
- **DOM 操作**：`renderSidebar()` 等函数直接操作 DOM 更新 UI
- **事件绑定**：HTML 中 `onclick="function()"` 方式绑定

**关键踩坑记录：**

1. **Alpine 3 `x-data` 初始化失败**
   - 根因：Alpine 3 的 `d("data")` handler 用 `with(scope)` 评估表达式，`has` trap 阻止了全局变量查找
   - 修复：放弃 Alpine，改用原生 JS

2. **`.layout` 容器缺失**
   - 问题：`.sidebar` 和 `.main` 是 `<body>` 的直接子元素，没有父容器做 flex 行布局
   - 现象：侧边栏把主内容区挤到下面
   - 修复：加 `<div class="layout">` 包裹，`display: flex` 生效

3. **`.sidebar` 高度不足**
   - 问题：侧边栏没有显式高度，只被内容撑开
   - 修复：`.sidebar { height: 100vh }`

4. **Modal 默认 `display: flex`**
   - 问题：CSS 中 `.modal-overlay { display: flex }` 导致 Modal 默认可见
   - 修复：改为 `display: none` + `.modal-overlay.active { display: flex }`，通过 class 切换

**已实现功能：**

- [x] 欢迎页（Hero + 打开目录输入框 + 最近修改）
- [x] 登录/退出（Token 验证，localStorage 存储）
- [x] 侧边栏（可折叠，文件树挂载点列表）
- [x] 挂载目录（游客限 1 个，登录用户不限）
- [x] 文件树（展开/折叠，点击打开文件）
- [x] 编辑器（Vditor，三种模式切换：IR / SV / WYSIWYG）
- [x] 文件保存
- [x] 设置页（API 地址 + 挂载点列表）
- [x] 搜索框（UI 已就绪，后端搜索待实现）
- [x] E2E 测试（21/21 通过：游客 + 认证 + 静态文件）

---

## 四、分阶段实施计划

### Phase 1：基础建设 ✅ 已完成

**目标：** Web 前端成为可用的笔记编辑器

**交付物：**
- ✅ 可用的 Web 笔记编辑器（Vditor，三种模式：IR/SV/WYSIWYG）
- ✅ 登录认证（Token 写在配置文件，非随机生成，禁止注册）
- ✅ 多目录挂载（游客可挂载 1 个目录，登录用户不限）
- ✅ 文件树（递归展开/折叠，按 md 文件存在性过滤目录）
- ✅ 内置欢迎文件（`storage/` 自动挂载为 `builtin-storage`，公开只读）
- ✅ 访客模式（无需登录即可浏览公开目录和内置文件）
- ✅ 公开目录标记（游客挂载的目录自动设为公开）
- ✅ 目录自动定位（Edge/Firefox 无法获取完整路径时，后端搜索常见位置）
- ✅ 只读保护（前端隐藏编辑工具 + 后端 403 拦截写操作）
- ✅ 卸载挂载点
- ✅ 全文搜索功能（FTS5 后端 + UI 已实现）

---

### Phase 2：元数据 + 对象索引 + 双向链接 ✅ 已完成

**目标：** 让笔记从"静态文档"变成"知识节点"

**2.1 Frontmatter 元数据** ✅ 已完成
- FS 层支持 YAML frontmatter 解析（使用 PyYAML）
  ```yaml
  ---
  title: 我的笔记
  tags: [project, active]
  aliases: [别名1, 别名2]
  created: 2026-06-03
  ---
  ```
- Frontmatter title 优先于 heading title 和文件名
- 编辑器支持 frontmatter 编辑（Vditor 原生支持）
- 对没有 frontmatter 的文件完全兼容（自动从文件名推断 title）

**2.2 对象索引器** ✅ 已完成（扩展 search 模块，非独立 indexer 模块）
- 扩展 `nas_md/search/` 模块，新增 `extract.py` 提取器
  - `extract.py` — 纯函数提取器：frontmatter / headings / tags / tasks
  - 数据库扩展：`tags` / `tasks` / `headings` 表 + `pages.frontmatter` 列
  - 级联删除：`ON DELETE CASCADE` 自动清理关联对象
- 索引对象类型：
  - **Page**：页面（文件名、frontmatter、修改时间）
  - **Task**：任务项（`- [ ]` / `- [x]`，所属页面、完成状态）
  - **Tag**：标签（`#tag` 语法 + frontmatter tags）
  - **Heading**：标题（`## Heading`，用于大纲）
- 实时索引：文件保存时立即提取并更新，单事务保证一致性

**2.3 双向链接 + 反链** ✅ 已完成
- 解析 `[[Page Name]]` 语法，建立链接关系
- 维护反链索引：`{page: [backlinks]}`
- 前端展示：
  - 页面底部显示"反向链接"面板（可折叠）
  - 点击跳转到来源页面

**2.4 查询 API** ✅ 已完成
- `GET /api/query?type=task&status=pending` — 查询未完成任务
- `GET /api/query?type=tag&name=project` — 查询带某标签的页面
- `GET /api/query?type=heading&page=xxx` — 查询某页面的标题列表
- `GET /api/query?type=link&page=xxx` — 查询某页面的所有链接 ✅ 已实现
- `GET /api/backlinks?page=xxx` — 查询某页面的反链 ✅ 已实现

**交付物：**
- ✅ 笔记支持 YAML frontmatter（PyYAML 解析）
- ✅ 自动对象索引（Task / Tag / Heading / Link）
- ✅ 双向链接 + 反链展示
- ✅ 结构化查询 API（/api/query + /api/backlinks）

---

### Phase 3：知识图谱 + 数据看板 ✅ 已完成

**目标：** 让知识网络可视化，提供数据洞察

**3.1 知识图谱视图** ✅ 已完成
- 前端新增"图谱"页面
- 使用 D3.js 力导向图渲染节点关系
- 节点 = 页面，边 = 链接关系
- 支持点击节点跳转到页面
- 支持缩放和拖拽

**3.2 数据看板** ✅ 已完成
- 新增"看板"页面，展示：
  - 笔记总数
  - 任务完成率
  - 标签数 / 链接数
  - 最近修改的页面

**3.3 图谱交互** ❌ 待实现（后续迭代）
- 搜索框支持 `[[` 触发链接补全
- 新建页面时自动建议已有页面链接
- 孤立页面提醒（没有任何链接的页面）

**交付物：**
- ✅ 知识图谱可视化（D3.js 力导向图）
- ✅ 数据看板（统计卡片 + 最近修改）
- ❌ 链接自动补全（后续迭代）

---

### Phase 4：同步机制完善 ✅ 已完成

**目标：** 多端数据一致性

**4.1 同步引擎** ✅ 已完成
- 完善 `sync/` 模块
- 客户端文件列表 + 时间戳 → 与服务端对比 → 增量同步
- 冲突处理：检测到冲突时创建副本（`filename.conflict.md`），用户手动合并
- 同步日志（fslog）用于追踪变更

**4.2 前端同步** ✅ 已完成
- Web 前端定期轮询同步（30 秒）
- 当前编辑的文件更频繁同步
- 同步状态指示器（顶部栏）

**4.3 离线支持** ✅ 已完成
- 编辑内容 localStorage 缓存
- 断网时可继续编辑，恢复连接后自动同步

**交付物：**
- ✅ 完整的双向同步（/api/sync POST）
- ✅ 冲突检测 + 副本策略（.conflict.md）
- ✅ 离线编辑支持（localStorage 缓存 + 恢复）

---

### Phase 5：插件系统扩展 ✅ 已完成

**目标：** 让社区和用户能扩展功能

**5.1 插件接口设计** ✅ 已完成
- 定义插件基类 `Plugin`：
  ```python
  class Plugin:
      name: str
      version: str
      def on_file_saved(self, path, content): ...
      def on_file_deleted(self, path): ...
      def register_routes(self, app): ...
      def register_commands(self, server): ...
  ```
- 插件目录：`plugins/`（用户放置 .py 文件即可自动加载）
- 插件配置：在 config.json 中启用/禁用

**5.2 内置插件** ✅ 已完成
- **WorldClockPlugin**（已有，迁移到新接口）
- **DailyTemplatePlugin**：新建日记时自动套用模板
- **WordCountPlugin**：字数统计和写作目标
- **RandomNotePlugin**：随机回顾一条笔记

**5.3 社区插件（远期）** ❌ 待实现
- 插件市场页面
- 插件安装/卸载/更新
- 插件权限沙箱

**交付物：**
- ✅ 插件接口 + 自动加载（PluginManager）
- ✅ 4 个内置插件
- ✅ 外部插件目录加载
- ❌ 社区插件市场（远期）

---

### Phase 6：Telegram Bot 智能化

**目标：** 把 Telegram 变成轻量知识管理入口

**6.1 命令拆分**
- 将 1588 行的 `server/__init__.py` 拆分为：
  - `server/commands/note.py` — 笔记相关命令
  - `server/commands/task.py` — 任务相关命令
  - `server/commands/search.py` — 搜索相关命令
  - `server/commands/habit.py` — 习惯相关命令
  - `server/commands/settings.py` — 设置相关命令
  - `server/router.py` — 命令路由器
- 使用装饰器注册命令

**6.2 Bot 增强**
- 支持 `[[wiki-link]]` 自动创建页面
- 支持 `#tag` 自动索引
- 搜索结果直接返回页面链接
- 支持查看反链

**6.3 AI 集成（远期）**
- 接入 LLM API（可选配置）
- 自然语言搜索
- 自动标签建议
- 笔记摘要生成

**交付物：**
- 模块化命令系统
- Bot 支持知识网络操作
- 可选 AI 集成

---

## 五、数据模型设计

### SQLite 索引表

```sql
-- 页面索引
CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,          -- 相对路径
    filename TEXT NOT NULL,             -- 文件名
    title TEXT,                         -- frontmatter title 或文件名
    created_at INTEGER,                 -- 创建时间 (ms)
    updated_at INTEGER,                 -- 修改时间 (ms)
    content_hash TEXT,                  -- 内容哈希（用于增量索引）
    frontmatter TEXT                    -- JSON 格式
);

-- FTS5 全文搜索虚拟表
CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
    path,
    title,
    content,
    content='pages',
    tokenize='unicode61'
);

-- 标签索引
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    page_path TEXT NOT NULL,
    FOREIGN KEY (page_path) REFERENCES pages(path)
);

-- 链接索引
CREATE TABLE IF NOT EXISTS links (
    id INTEGER PRIMARY KEY,
    source_path TEXT NOT NULL,          -- 来源页面
    target_path TEXT NOT NULL,          -- 目标页面
    link_text TEXT,                     -- 链接显示文本
    FOREIGN KEY (source_path) REFERENCES pages(path),
    FOREIGN KEY (target_path) REFERENCES pages(path)
);

-- 任务索引
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY,
    page_path TEXT NOT NULL,
    line_number INTEGER,
    content TEXT NOT NULL,
    done INTEGER DEFAULT 0,
    FOREIGN KEY (page_path) REFERENCES pages(path)
);

-- 索引元数据
CREATE TABLE IF NOT EXISTS index_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
```

### Frontmatter 示例

```yaml
---
title: 项目规划
tags: [project, planning, active]
aliases: [规划, 项目计划]
created: 2026-06-03
due: 2026-06-30
status: in-progress
---
```

---

## 六、前端页面结构（已实现）

```
web/
├── index.html              # 入口页（SPA 外壳）
├── app.js                  # 应用主逻辑（路由、状态、DOM）
├── files.js                # 文件浏览 + API 封装
├── editor.js               # Vditor 编辑器封装
├── app.css                 # 应用样式（布局 + 组件）
└── lib/
    └── vditor/             # Markdown 编辑器（vendored）
```

### 页面路由

| 路径 | 页面 | 说明 | 状态 |
|------|------|------|------|
| `/` | 首页 | 欢迎页 + 打开目录入口 + 最近修改 | ✅ |
| `/editor` | 编辑器 | Vditor 编辑/预览（三种模式） | ✅ |
| `/settings` | 设置 | 挂载点管理 | ✅ |
| `/search?q=xxx` | 搜索结果 | 全文搜索 | ✅ |

### 认证模型

- **无注册**：Token 写在配置文件 `WEB_AUTH_TOKEN` 中
- **可选登录**：任何人访问都看到欢迎页，右上角登录按钮
- **访客模式**：无需登录即可浏览公开目录和内置文件
- **游客限制**：最多挂载 1 个目录，登录用户不限
- **公开目录**：游客挂载的目录自动设为 `public=true`

### 前端状态管理

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

---

## 七、API 扩展

在现有 Mount API 基础上新增：

| 方法 | 接口 | 说明 | Phase | 状态 |
|------|------|------|-------|------|
| `GET` | `/api/health` | 健康检查 | 1 | ✅ |
| `GET` | `/api/mounts` | 所有挂载点（需认证） | 1 | ✅ |
| `GET` | `/api/mounts/public` | 公开挂载点（无需认证） | 1 | ✅ |
| `POST` | `/api/mounts` | 添加挂载点 | 1 | ✅ |
| `DELETE` | `/api/mounts/{id}` | 删除挂载点 | 1 | ✅ |
| `PUT` | `/api/mounts/{id}` | 更新挂载点（名称/公开） | 1 | ✅ |
| `GET` | `/api/mounts/{id}/tree?path=/` | 目录树（单层） | 1 | ✅ |
| `GET` | `/api/mounts/{id}/tree-recursive?path=/` | 递归目录树 | 1 | ✅ |
| `GET` | `/api/mounts/{id}/file?path=/xxx` | 读取文件 | 1 | ✅ |
| `PUT` | `/api/mounts/{id}/file?path=/xxx` | 写入文件 | 1 | ✅ |
| `PUT` | `/api/mounts/{id}/rename` | 重命名/移动 | 1 | ✅ |
| `PUT` | `/api/mounts/{id}/mkdir` | 创建目录 | 1 | ✅ |
| `DELETE` | `/api/mounts/{id}/file?path=/xxx` | 删除文件 | 1 | ✅ |
| `GET` | `/api/find-path?name=xxx` | 搜索目录路径（无需认证） | 1 | ✅ |
| `GET` | `/api/search?q=关键词` | 全文搜索 | 1 | ✅ 已实现 |
| `GET` | `/api/query?type=task\|tag\|heading` | 结构化查询 | 2 | ✅ 已实现 |
| `GET` | `/api/backlinks?page=xxx` | 反链查询 | 2 | ✅ |
| `GET` | `/api/query?type=link&page=xxx` | 出链查询 | 2 | ✅ |
| `GET` | `/api/tags` | 标签列表 | 2 | ❌ |
| `GET` | `/api/stats` | 统计数据 | 3 | ✅ |
| `GET` | `/api/graph` | 图谱数据（节点+边） | 3 | ✅ |
| `POST` | `/api/sync` | 增量同步 | 4 | ✅ |
| `GET` | `/api/sync/status` | 同步状态 | 4 | ✅ |
| `GET` | `/api/plugins` | 插件列表 | 5 | ✅ |

---

## 八、参考项目总结

### files.md（https://github.com/zakirullin/files.md）

**可借鉴：**
- Go + 原生 JS 的本地优先文件管理器
- 零框架，零构建系统
- 打开 `index.html` 即可使用
- `onclick` 事件绑定 + 直接 DOM 操作
- `renderSidebar()` 等函数直接操作 DOM

**已采纳：** 前端架构完全参考此项目

### SilverBullet（https://github.com/silverbulletmd/silverbullet）

**可借鉴：**
- 对象索引 + 跨文件查询（Frontmatter → Object Index → LIQ 三层递进）
- 双向链接 + 反链
- 离线优先 + Service Worker 同步
- Plug 扩展系统

**不借鉴：**
- IndexedDB 客户端存储（我们服务端存储）
- Space Lua（引入脚本语言增加复杂度）

### Vditor（https://github.com/Vanessa219/vditor）

**可借鉴：**
- 三种编辑模式（即时渲染 / 分屏预览 / 所见即所得）
- YAML Front Matter 原生支持
- 任务列表、脚注、目录
- 代码高亮 + 多主题
- 中文语境优化

**使用方式：** vendored 到 `web/lib/vditor/`

---

## 九、风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| Vditor 体积较大 | vendored，离线可用 |
| FTS5 中文分词效果 | 测试 unicode61 tokenizer；必要时自定义分词 |
| 索引性能（大量文件） | 增量索引 + 后台异步重建 |
| 前端代码组织 | 按功能拆分为独立 JS 文件 |

---

## 十、里程碑

| Phase | 预计周期 | 核心交付 | 状态 |
|-------|----------|----------|------|
| Phase 1 | 3 天 | Web 编辑器 + 登录认证 | ✅ 已完成 |
| Phase 2 | 3-4 周 | Frontmatter + 对象索引 + 双向链接 | ✅ 已完成 |
| Phase 3 | 2-3 周 | 知识图谱 + 数据看板 | ✅ 已完成 |
| Phase 4 | 2-3 周 | 同步机制 + 离线支持 | ✅ 已完成 |
| Phase 5 | 2-3 周 | 插件系统 | ✅ 已完成 |
| Phase 6 | 3-4 周 | Bot 模块化 + AI 集成 | 待开始 |
