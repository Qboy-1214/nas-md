# Web 前端需求规格

> 更新日期：2026-06-04
> 当前状态：Phase 1 已完成，Phase 2 待开始

## 1. 挂载目录模型

每个挂载点包含四个字段：

| 字段 | 说明 | 示例 |
|------|------|------|
| `id` | 系统自动生成 | `mount-0` |
| `name` | 用户自定义显示名 | `我的文档` |
| `path` | 宿主机真实绝对路径 | `D:\docs` |
| `public` | 是否对游客可见 | `true` / `false` |

### 挂载方式

1. **启动预配置**：通过 `MOUNT_DIRS` 环境变量或配置文件，格式支持：
   - `路径`（自动生成显示名，取目录 basename）
   - `显示名:路径`（如 `项目文档:D:\projects\docs`）
   - 多个用逗号分隔
   - 默认不挂载任何目录

2. **Web 动态挂载**：
   - 游客：最多挂载 1 个目录
   - 登录用户：不限数量（加上启动预配置的，总共能看到多个）
   - 动态挂载的目录重启后消失（仅内存中）

### 持久化规则

| 挂载方式 | 持久化 | 说明 |
|---------|--------|------|
| 启动预配置 | ✅ 持久 | 写入配置文件或环境变量 |
| 登录用户 Web 挂载 | ❌ 临时 | 内存中，重启消失 |
| 游客 Web 挂载 | ❌ 临时 | 内存中，重启消失 |

## 2. 权限模型

### 统一的欢迎页（所有人）

任何人打开网站都看到欢迎页。

### 游客（未登录）

- 看到**欢迎页**：项目介绍 + 使用说明
- 可以挂载 **1 个**本机目录
- 能看到的内容：自己挂载的目录 + 登录用户标记为 `public` 的目录
- 可以搜索（范围 = 自己挂载的 + 被开放的目录）
- 可以浏览和编辑这些目录下的文件
- 侧边栏底部显示「登录」按钮

### 登录用户

- 登录后仍基于欢迎页，但能看到**所有已挂载目录**
- 可以挂载不限数量的额外目录
- 可以将任意已挂载目录标记为 `public`（开放给游客）
- 可以搜索所有目录
- 可以浏览和编辑所有目录下的文件
- 侧边栏底部显示「退出」按钮

### 权限矩阵

| 功能 | 游客（未登录） | 登录用户 |
|------|--------------|---------|
| 欢迎页 | ✅ | ✅（登录后仍是此页，内容扩展） |
| 挂载 1 个目录 | ✅ | ✅（不限） |
| 查看所有预配置目录 | ❌ | ✅ |
| 查看 public 目录 | ✅ | ✅ |
| 设置目录 public | ❌ | ✅ |
| 搜索 | ✅（限制范围） | ✅（全部） |
| 文件读写 | ✅（限制范围） | ✅（全部） |

## 3. 认证机制

- Token 写在配置文件里（非随机生成）
- Docker 部署时写在 `compose.yaml` 的环境变量中
- 禁止注册，禁止密码登录

```yaml
# compose.yaml
services:
  nas-md:
    environment:
      - WEB_AUTH_TOKEN=your-secret-token-here
      - MOUNT_DIRS=我的文档:/host/path/to/docs,/data/storage
```

## 4. 前端技术栈

| 组件 | 选择 | 说明 |
|------|------|------|
| 语言 | 原生 JavaScript | 无框架，零构建步骤 |
| 编辑器 | Vditor | Markdown 编辑器，vendored |
| 布局 | CSS Flexbox | `.layout` 容器 `display: flex` |
| 状态 | 全局 `state` 对象 | 集中式状态管理 |
| 事件 | `onclick` 绑定 | HTML 属性直接绑定 |
| DOM | 原生 DOM API | `getElementById` / `innerHTML` |

### 为什么不用框架

- Alpine.js 3.x 的 `x-data` 响应式存在初始化 bug（`has` trap 阻止全局变量查找），调试数小时无果
- 原生 JS + 直接 DOM 操作是最可靠的方式，零依赖，10 年后仍然能用
- 参考 files.md 的实践：Go 后端 + 原生 JS 前端，零构建系统

## 5. 前端文件结构

```
web/
├── index.html              # 入口页（SPA 外壳）
├── app.js                  # 应用主逻辑（状态管理、页面路由、DOM 操作）
├── files.js                # 文件浏览 + API 封装
├── editor.js               # Vditor 编辑器封装
├── app.css                 # 应用样式（布局、侧边栏、编辑器、Modal）
└── lib/
    ├── vditor/             # Vditor 编辑器核心（vendored）
    └── vditor-cdn/         # Vditor 外部资源（lute、i18n、图标、主题）vendored
```

### 各文件职责

**index.html**：页面结构
- `.layout` 容器（flex 行布局）
- `#sidebar` 侧边栏（可折叠）
- `.main` 主内容区（顶部栏 + 编辑器区域）
- 欢迎页 / 编辑器 / 设置页（通过 `display` 切换）
- 登录 Modal / 新建文件 Modal

**app.js**：应用主逻辑
- 全局 `state` 对象（token、mounts、当前文件、编辑器模式等）
- `showPage(page)` — 页面切换
- `renderSidebar()` — 侧边栏渲染（文件树）
- `loadMounts()` / `openDirectory()` — 挂载点管理
- `openFile(path)` / `saveFile()` — 文件操作
- `showLogin()` / `login()` / `logout()` — 认证

**files.js**：API 封装
- `API.request(path, options)` — 统一 fetch 封装（自动附加 Authorization header）
- `API.getMounts()` / `API.getPublicMounts()` — 挂载点列表
- `API.getTree(mountId, path)` — 目录树
- `API.getFile()` / `API.putFile()` — 文件读写
- `API.search(query)` — 全文搜索

**editor.js**：编辑器封装
- `initEditor(content, mode, readonly, cursorOffset)` — 初始化 Vditor（内部）
- `window._getVditor()` — 暴露 Vditor 实例
- `window._reinitEditor(mode)` — destroy + reinit 切换模式（Vditor 3.x 无 `setMode()`）
- `getEditorContent()` — 内容获取
- `isDirty()` / `markSaved()` — 脏检查
- 模式切换时自动保存/恢复滚动位置和光标

**app.css**：样式
- CSS 变量（颜色、间距、阴影、圆角）
- 亮色主题 + 暗色主题（`prefers-color-scheme: dark`）
- Flexbox 布局（`.layout` / `.sidebar` / `.main`）
- 侧边栏折叠动画
- Modal 样式
- 响应式（移动端侧边栏变为绝对定位）

## 6. 页面流程

### 所有人

```
打开网站
  → 欢迎页（介绍 + 说明 + "打开目录"输入框 + 侧边栏底部登录按钮）
    ├── 不登录：可以挂载 1 个目录，浏览/编辑/搜索该目录
    └── 点登录 → 输入 Token → 登录成功
          → 欢迎页扩展：看到所有目录 + 可以挂载更多 + 设置 public
```

### 目录切换

- 游客：如果有多个目录（自己挂载的 + public），侧边栏显示所有目录
- 登录用户：侧边栏显示所有目录

## 7. 前端组件说明

### 欢迎页

- 项目 Logo / 名称
- 简短介绍（一句话）
- 使用说明（2-3 条）
- "打开目录"输入框（路径输入 + 可选显示名）
- 已挂载目录列表
- 最近修改的文件列表

### 登录 Modal

- Token 输入框
- 登录按钮
- 错误提示
- 取消按钮

### 主界面

- 顶部栏：折叠按钮 + 面包屑 + 编辑器模式切换 + 保存按钮
- 侧边栏：搜索框 + 文件树 + 底部导航按钮
- 主内容区：Vditor 编辑器

### 设置页

- API 地址显示
- 挂载点列表

## 8. 文件树显示规则

### 目录可见性

- **顶层挂载目录**：无论是否包含 md 文件，始终显示
- **子目录**：仅当该目录（含任意嵌套子目录）包含至少一个 `.md` 文件时才显示
- **空目录过滤**：不含 md 文件的目录及其所有不含 md 文件的父目录链都隐藏
- **动态更新**：新增 md 文件后，重新加载树时整条父目录链自动出现

### 实现方式

后端 `DirEntry` 新增 `hasMd` 字段：
- 叶子 `.md` 文件：`hasMd = true`
- 目录：`hasMd = any(child.hasMd for child in children)`

前端 `renderEntries` 过滤 `hasMd === false` 的目录节点。

## 9. 待实施清单

### Phase 1（已完成）

- [x] 后端：挂载点模型加 `name` 和 `public` 字段
- [x] 后端：Token 从配置文件读取（不再随机生成）
- [x] 后端：`GET /api/mounts/public` 端点
- [x] 后端：`PUT /api/mounts/{id}` 端点（修改 public）
- [x] 后端：`GET /api/mounts/{id}/tree-recursive` 递归目录树端点
- [x] 后端：`GET /api/find-path?name=` 目录自动定位端点
- [x] 后端：游客挂载自动设为 `public=true`
- [x] 后端：公开挂载点的 tree/file 读取无需认证
- [x] 后端：`DirEntry.hasMd` 字段（递归树标记是否含 md 文件）
- [x] 后端：修复公开挂载点 GET 文件时 `path.endswith('/file')` 因 query string 导致返回 401 的 bug
- [x] 前端：欢迎页
- [x] 前端：登录 Modal
- [x] 前端：主界面（侧边栏 + 文件树 + 编辑器）
- [x] 前端：挂载对话框（含浏览…按钮 + Edge/Firefox 路径自动定位）
- [x] 前端：游客/登录态切换逻辑
- [x] 前端：递归树渲染 + 目录按 hasMd 过滤
- [x] 前端：目录展开/折叠（递归树数据）
- [x] 前端：Vditor CDN 资源本地化（lute、i18n、图标、主题 vendored 到 `web/lib/vditor-cdn/`，防 Edge Tracking Prevention 拦截）
- [x] 前端：编辑器模式即时切换（destroy + reinit，Vditor 3.x 无 `setMode()`）
- [x] 前端：模式切换时滚动位置/光标保存恢复
- [x] 前端：搜索模块
- [x] 配置：Token 配置方式
- [x] 配置：`.gitignore` 更新，前端文件纳入版本控制
- [x] 测试：E2E 测试覆盖（21/21 通过）

### Phase 2（待开始）

- [ ] 后端：全文搜索（SQLite FTS5）
- [ ] 后端：`GET /api/search?q=` 端点
- [ ] 后端：YAML frontmatter 解析
- [ ] 后端：对象索引器（Page / Task / Tag / Link）
- [ ] 后端：双向链接 + 反链
- [ ] 后端：结构化查询 API
- [ ] 前端：搜索框实时搜索
- [ ] 前端：frontmatter 编辑
- [ ] 前端：双向链接渲染
- [ ] 前端：反链展示
- [ ] 测试：搜索 + 索引 E2E 测试
