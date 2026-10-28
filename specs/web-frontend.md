---
id: nas-md-web-frontend
type: module-design
status: draft
title: Web 前端（原生 JS SPA）
parent: nas-md-architecture
depends-on:
  - nas-md-webserver
---

# Web 前端（原生 JS SPA）

## 职责

`web/`（约 1 万行，无框架无构建）。原生 JS SPA：`app.js`（全局 `state` + 页面路由 + 文件树/搜索/最近访问渲染）、`files.js`（API 封装，含远程代理）、`editor.js`（Vditor 封装，模式切换=销毁重建+滚动/光标恢复）、`sync_layer.js`（SSE + 段落 diff 应用 + 编辑中保护）、`sse_client.js`、`version_history.js`、`html_preview.js`（隔离 iframe + 同挂载点相对资源重写 + opaque origin data-URL 内联）、`mermaid_enhancer.js`（图表全屏）、`draft_storage.js`（离线草稿）、`identity.js`（匿名身份）、`graph-viewer.html`（D3 图谱独立页）。

## 不变量

- **零构建零新依赖**：第三方库全部 vendored 在 `web/lib/`（Vditor、Inter 字体）；不引入前端框架。
- **HTML 预览安全模型**：iframe `sandbox=allow-scripts` + opaque origin，本地资源重写为 MIME 正确的 data URL；`base`/`meta refresh` 标签先被剥离；资源路径逃逸挂载点则拒绝（`about:blank` 占位）。
- **侧边栏拖拽**（2026-10-28 定型）：pointer capture（停顿不失事件）+ 拖拽期间禁 width 过渡 + 热区左右扩 10px + 左侧 12px 橡皮筋补按（不拦截可交互元素）；宽度持久化 `localStorage.nasmd_sidebar_width`。HTML 全屏预览状态持久化 `nasmd_html_preview_fs`，Esc 退出。
- 协同编辑前端遵循 [[nas-md-realtime-collab]] 的编辑中保护 + 乐观锁兜底（段落冲突 LWW）。

## 边界

- 只依赖 [[nas-md-webserver]] 的 HTTP API / SSE（契约见 [[nas-md-mount-api]]、[[nas-md-remote-proxy]]）；不直接触达后端其他模块。
- 渲染数据（文件标题/路径/摘要）一律 DOM textContent/属性赋值注入，不经 innerHTML 模板拼接（2026-10-28 起的前端约定）。
