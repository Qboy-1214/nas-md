# 远程文件代理编辑功能

## Context

用户有另一个自研服务（存储 MD 文件 + 版本管理），需要查看和编辑功能但不想重复造编辑器轮子。希望像 Nextcloud 调用 OnlyOffice 那样，通过深链跳转到 nas-md 打开远程文件，编辑后回写，nas-md 不持久化文件。

已确认：
- 只做深链跳转模式（方式B），不做侧边栏浏览
- 不需要协同编辑
- 认证用 API Key
- 远程服务器负责版本管理
- nas-md 先搭框架（远程 API 尚未开发）

## 设计方案

### URL 格式

```
https://nas-md-host/#remote=<base64_url_safe_json>
```

JSON 内容：`{"src": "https://remote-host", "path": "/docs/readme.md", "key": "api-key-xxx"}`

用 URL fragment（`#` 后）传递参数，浏览器不会将其发送到服务器，API Key 不暴露在 HTTP 请求中。base64 编码避免 URL 转义问题。

### 远程服务 API 契约（nas-md 需要对远程服务调用的接口）

```
GET {src}/api/files?path={path}
  Header: X-API-Key: {key}
  Response: 200, body = file content (raw text)
  Response: 404 if not found

PUT {src}/api/files?path={path}
  Header: X-API-Key: {key}, Content-Type: text/markdown
  Body: file content (raw text)
  Response: 200, body = {"status": "ok"}
```

## 实施步骤

### 1. 后端：新增远程文件代理 API

**文件**: `nas_md/webserver/__init__.py`

在 `do_GET` 中新增路由：
```
if path == "/api/remote/file":
    self._handle_remote_file(qs)
```

在 `do_PUT` 中新增路由：
```
if path == "/api/remote/file":
    self._handle_remote_write(qs)
```

新增两个处理函数：

`_handle_remote_file(qs)`:
- 从 `qs` 获取 `src` 和 `path` 参数
- 从请求头 `X-Remote-Key` 获取 API Key
- 用 `urllib.request` 向 `{src}/api/files?path={path}` 发 GET 请求，带 `X-API-Key` header
- 将远程响应内容返回给前端
- 错误处理：远程返回 404/403/500 时转发对应状态码

`_handle_remote_write(qs)`:
- 从 `qs` 获取 `src` 和 `path` 参数
- 从请求头 `X-Remote-Key` 获取 API Key
- 读取请求 body（文件内容）
- 用 `urllib.request` 向 `{src}/api/files?path={path}` 发 PUT 请求，带 `X-API-Key` header 和 body
- 将远程响应返回给前端

安全考虑：
- 验证 `src` 是合法的 http/https URL
- 请求超时设置（10 秒）
- 不记录 API Key 到日志

### 2. 前端：新增远程文件 API 调用

**文件**: `web/files.js`

新增两个函数：

```javascript
async getRemoteFile(src, path, apiKey) {
  // GET /api/remote/file?src=...&path=...
  // Header: X-Remote-Key: apiKey
  // 返回 { content, status }
}

async putRemoteFile(src, path, content, apiKey) {
  // PUT /api/remote/file?src=...&path=...
  // Header: X-Remote-Key: apiKey
  // Body: content
  // 返回 { status }
}
```

### 3. 前端：URL 解析和远程文件加载

**文件**: `web/app.js`

#### 3a. 新增 `_parseRemoteHash()` 函数

在 `_parseShareHash()` 旁边新增，解析 `#remote=<base64>` 格式的 hash：
- 解码 base64，解析 JSON
- 返回 `{ src, path, key }` 或 null

#### 3b. 新增 `state.remoteFile` 状态

在 `state` 对象中新增：
```javascript
remoteFile: null, // { src, path, key } when in remote proxy mode
```

#### 3c. 修改初始化流程

在 `init()` 函数中（`_parseShareHash` 检查之后）新增远程文件检查：
- 调用 `_parseRemoteHash()`
- 如果有远程文件参数，调用 `openRemoteFile(src, path, key)`

#### 3d. 新增 `openRemoteFile(src, path, key)` 函数

- 设置 `state.remoteFile = { src, path, key }`
- 调用 `API.getRemoteFile(src, path, key)` 获取文件内容
- 隐藏侧边栏、文件树、版本历史等 UI（远程模式不需要）
- 显示远程文件信息（面包屑显示 `远程服务名 / path`）
- 初始化编辑器（与现有 `initEditor` 一致）
- 不连接 SSE（无协同编辑）
- 不启动文件轮询（无外部修改检测）
- 设置 `state.dirty = false`

### 4. 前端：修改保存逻辑

**文件**: `web/app.js` 的 `saveFile()` 函数

在函数开头新增远程模式分支：
```javascript
if (state.remoteFile) {
  content = window._vditor.getValue();
  const resp = await API.putRemoteFile(
    state.remoteFile.src,
    state.remoteFile.path,
    content,
    state.remoteFile.key
  );
  if (resp && resp.status === 'ok') {
    markClean();
    if (!silent) showToast('已保存');
  } else {
    showToast('保存失败');
  }
  return;
}
```

远程模式跳过：FileVersionStore、段落 diff、版本历史、SSE 广播。

### 5. 前端：UI 调整

**文件**: `web/app.js`

在 `openRemoteFile()` 中：
- 隐藏侧边栏（`#sidebar`）
- 隐藏文件树相关按钮
- 隐藏版本历史按钮（`#history-top-btn`）
- 隐藏重命名/删除按钮（远程文件不允许在 nas-md 中重命名）
- 保留：编辑器、保存按钮、自动保存开关、暗色模式切换、下载
- 面包屑显示：`远程 / path/to/file.md`

### 6. 自动保存

远程模式下复用现有的 `scheduleAutoSave()` 和 `onEditorInput()` 机制，因为它们最终调用 `saveFile()`，而 `saveFile()` 会检测 `state.remoteFile` 走远程分支。

## 关键文件清单

| 文件 | 改动 |
|------|------|
| `nas_md/webserver/__init__.py` | 新增 `/api/remote/file` GET/PUT 路由和处理函数 |
| `web/files.js` | 新增 `getRemoteFile` / `putRemoteFile` 函数 |
| `web/app.js` | 新增 `_parseRemoteHash` / `openRemoteFile`，修改 `saveFile` 和初始化流程 |

## 验证方案

1. **单元测试**：后端新增 `_handle_remote_file` / `_handle_remote_write` 的单元测试，mock 远程 HTTP 请求
2. **手动测试**（远程 API 未就绪时）：
   - 用 Python 起一个简单的 mock 远程服务（提供 GET/PUT /api/files）
   - 访问 `https://nas-md-host/#remote=<base64>`
   - 验证文件加载、编辑、保存、自动保存
3. **集成测试**（远程 API 就绪后）：真实远程服务 + nas-md 端到端测试
