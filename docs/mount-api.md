# 挂载 API 参考

挂载 API 允许通过 Web UI 浏览、读取和管理服务器端目录上的文件。挂载点通过 `MOUNT_DIRS` 环境变量配置（分号分隔的绝对路径），也可通过 Web UI 动态挂载。

## 多用户隔离

系统通过 Cookie 自动会话实现免登录多用户隔离。每个用户首次访问时自动分配 UUID session ID，后续请求浏览器自动携带 Cookie 识别身份。

**隔离规则：**

| 挂载点类型 | 可见性 | 操作权限 |
|-----------|--------|---------|
| 内置存储（`builtin-storage`） | 所有用户 | 只读 |
| 宿主机挂载点（`MOUNT_DIRS`） | 仅 Admin | Admin 可读写 |
| 用户挂载点（Web UI 添加） | 仅创建者 | 仅创建者可操作 |
| 遗留挂载点（升级前已存在） | 所有用户 | 任何用户可操作 |

- 用户挂载目录无数量限制
- Admin 只能看到自己的本机挂载点和宿主机挂载点，无法访问其他用户的挂载点
- 搜索、统计、结构化查询结果均按用户可见性过滤

**会话 Cookie：**
- 名称：`nasmd_sid`
- 有效期：1 年（`Max-Age=31536000`）
- 重启浏览器和电脑后仍然有效

## 配置

### 环境变量

```
MOUNT_DIRS=/path/to/dir1;/path/to/dir2;/path/to/dir3
```

每个目录成为一个独立的挂载点，标识为 `mount-0`、`mount-1`，以此类推。

### Docker Compose 示例

```yaml
services:
  nas-md:
    volumes:
      - /home/user/notes:/mnt/notes
      - /home/user/docs:/mnt/docs
    environment:
      MOUNT_DIRS: /mnt/notes;/mnt/docs
```

## 数据类型

### MountEntry（挂载点）

```json
{
  "id": "mount-0",
  "name": "notes",
  "path": "/mnt/notes",
  "host": false,
  "public": false,
  "readonly": false,
  "owner": "uuid-session-id"
}
```

- `id` —— 挂载点唯一标识
- `name` —— 显示名称
- `path` —— 服务器上的绝对路径
- `host` —— 是否为宿主机挂载点（`MOUNT_DIRS` 配置）
- `public` —— 是否公开可见
- `readonly` —— 是否只读
- `owner` —— 创建者的 session UUID，空字符串表示遗留或宿主机挂载点

### DirEntry（目录项）

```json
{
  "name": "Projects",
  "path": "/Projects",
  "isDir": true,
  "size": 0,
  "modTime": 1719993600000,
  "hasMd": true,
  "children": [
    {
      "name": "README.md",
      "path": "/Projects/README.md",
      "isDir": false,
      "size": 1234,
      "modTime": 1719993600000,
      "hasMd": true
    }
  ]
}
```

- `name` —— 文件或目录名称
- `path` —— 相对于挂载根目录的路径（以 `/` 开头）
- `isDir` —— 是否为目录
- `size` —— 文件大小（字节），目录为 0
- `modTime` —— 修改时间（毫秒时间戳）
- `hasMd` —— 该子树是否包含 `.md` 文件（目录为递归计算，叶子 md 文件为 true）
- `children` —— 子项（仅在递归树形响应中的目录上存在）

## 接口

### 列出所有挂载点

```
GET /api/mounts
```

返回当前用户可见的挂载点。基于 Cookie 会话自动过滤，每个用户只能看到自己拥有的挂载点、内置存储、宿主机挂载点（仅 Admin）和遗留挂载点。

**响应 200：**
```json
[
  { "id": "mount-0", "name": "notes", "path": "/mnt/notes" },
  { "id": "mount-1", "name": "docs", "path": "/mnt/docs" }
]
```

**响应 200（无挂载点）：**
```json
[]
```

---

### 列出公开挂载点

```
GET /api/mounts/public
```

返回所有标记为 `public=true` 的挂载点。无需认证。

**响应 200：**
```json
[
  { "id": "builtin-storage", "name": "nas-md", "path": "/app/storage", "public": true, "readonly": true },
  { "id": "mount-1", "name": "work_TEST", "path": "/Documents/work_TEST", "public": true, "readonly": false }
]
```

---

### 添加挂载点

```
POST /api/mounts
```

动态添加新的挂载点。新挂载点自动绑定当前用户的 session（`owner` = 当前 session ID），无数量限制。

**请求体：**
```json
{ "path": "/home/user/notes", "name": "我的笔记" }
```

**响应 200：**
```json
{ "id": "mount-2", "name": "我的笔记", "path": "/home/user/notes", "public": true, "readonly": false }
```

**响应 400：** 路径不存在或缺少参数。

---

### 删除挂载点

```
DELETE /api/mounts/{id}
```

删除挂载点。只能删除自己拥有的挂载点（`owner` 匹配当前 session）。内置挂载点（`builtin-storage`）不能删除。

**响应 200：**
```json
{ "status": "ok" }
```

**响应 403：** 内置挂载点不能删除，或非挂载点所有者。

---

### 更新挂载点

```
PUT /api/mounts/{id}
```

更新挂载点属性（名称、公开状态）。需要认证。

**请求体：**
```json
{ "name": "新名称", "public": true }
```

**响应 200：**
```json
{ "id": "mount-1", "name": "新名称", "path": "/Documents/work_TEST", "public": true, "readonly": false }
```

---

### 搜索目录路径

```
GET /api/find-path?name=xxx
```

在常见位置（用户目录、文档、桌面、所有驱动器根目录及 Documents 子目录）搜索匹配的目录名，返回完整路径。无需认证。用于 Edge/Firefox 无法通过 `files[0].path` 获取完整路径时的自动定位。

**响应 200（找到）：**
```json
{ "path": "E:\\Documents\\work_TEST", "name": "work_TEST" }
```

**响应 200（未找到）：**
```json
{ "path": null, "name": "work_TEST" }
```

---

### 列出目录内容

```
GET /api/mounts/{id}/tree?path=/
```

返回指定目录的直接子项。

**参数：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `path` | `/` | 相对于挂载根目录的路径 |

**响应 200：**
```json
[
  { "name": "Projects", "path": "/Projects", "isDir": true, "size": 0, "modTime": 1719993600000 },
  { "name": "Welcome.md", "path": "/Welcome.md", "isDir": false, "size": 512, "modTime": 1719993600000 }
]
```

**响应 404：** 挂载点不存在或路径不存在。

---

### 递归目录树

```
GET /api/mounts/{id}/tree-recursive?path=/
```

返回完整的目录树，最多 10 层。

**参数：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `path` | `/` | 相对于挂载根目录的路径 |

**响应 200：**
```json
{
  "name": "notes",
  "path": "/",
  "isDir": true,
  "size": 0,
  "modTime": 1719993600000,
  "hasMd": true,
  "children": [
    {
      "name": "Projects",
      "path": "/Projects",
      "isDir": true,
      "size": 0,
      "modTime": 1719993600000,
      "hasMd": true,
      "children": [
        {
          "name": "README.md",
          "path": "/Projects/README.md",
          "isDir": false,
          "size": 1234,
          "modTime": 1719993600000,
          "hasMd": true
        }
      ]
    }
  ]
}
```

**响应 404：** 挂载点不存在。
**响应 500：** 无法构建目录树（如权限不足）。

> 公开挂载点的 `tree-recursive` 和 `file` 读取无需认证。

---

### 读取文件

```
GET /api/mounts/{id}/file?path=/file.md
```

返回文件的原始内容。

**参数：**

| 参数 | 必填 | 说明 |
|------|------|------|
| `path` | 是 | 文件的相对路径 |

**响应 200：** 原始文件内容，附带正确的 `Content-Type` 头。

文本文件（`.md`、`.txt`、`.json`、`.html`、`.css`、`.js` 等）以 `charset=utf-8` 编码返回。

**响应 400：** 缺少 path 参数。
**响应 403：** 路径逃逸出挂载根目录。
**响应 404：** 文件不存在。
**响应 500：** 读取错误。

---

### 写入文件

```
PUT /api/mounts/{id}/file?path=/file.md
```

创建或覆盖文件。自动创建父目录。

**参数：**

| 参数 | 必填 | 说明 |
|------|------|------|
| `path` | 是 | 文件的相对路径 |

**请求体：** 原始文件内容（二进制）。

**响应 200：**
```json
{
  "status": "ok",
  "modTime": 1719993600000,
  "size": 1234
}
```

**响应 400：** 缺少 path 参数。
**响应 403：** 路径逃逸出挂载根目录。
**响应 404：** 挂载点不存在。

---

### 重命名 / 移动

```
PUT /api/mounts/{id}/rename?oldPath=/old-name.md&newPath=/new-name.md
```

在同一挂载点内重命名或移动文件或目录。

**参数：**

| 参数 | 必填 | 说明 |
|------|------|------|
| `oldPath` | 是 | 当前相对路径 |
| `newPath` | 是 | 新相对路径 |

**响应 200：**
```json
{ "status": "ok" }
```

**响应 400：** 缺少 oldPath 或 newPath。
**响应 403：** 任一端路径逃逸出挂载根目录。
**响应 404：** 挂载点不存在。

---

### 创建目录

```
PUT /api/mounts/{id}/mkdir?path=/new-directory
```

创建新目录。自动创建父目录。

**参数：**

| 参数 | 必填 | 说明 |
|------|------|------|
| `path` | 是 | 新目录的相对路径 |

**响应 200：**
```json
{ "status": "ok" }
```

**响应 400：** 缺少 path 参数。
**响应 403：** 路径逃逸出挂载根目录。
**响应 404：** 挂载点不存在。

---

### 删除

```
DELETE /api/mounts/{id}/file?path=/file.md
```

删除文件或目录。目录将被递归删除（包括所有内容）。

**参数：**

| 参数 | 必填 | 说明 |
|------|------|------|
| `path` | 是 | 文件或目录的相对路径 |

**响应 200：**
```json
{ "status": "ok" }
```

**响应 400：** 缺少 path 参数。
**响应 403：** 路径逃逸出挂载根目录。
**响应 404：** 挂载点不存在。

---

### 提交段落级变更（协同编辑）

```
POST /api/mounts/{id}/changes?path=/file.md
```

提交段落级 diff 变更，用于协同编辑。基于版本号乐观锁：客户端提交 `baseVersion`，服务器检查是否匹配当前版本，匹配则直接应用，不匹配则尝试段落级合并。

**参数：**

| 参数 | 必填 | 说明 |
|------|------|------|
| `path` | 是 | 文件的相对路径 |

**请求头：**

| Header | 说明 |
|--------|------|
| `X-Client-Id` | 客户端 session ID（自动生成） |
| `X-Author-Name` | 作者显示名称（如 "CalmWolf60"） |
| `X-Author-Color` | 作者颜色（十六进制，如 "#3498db"） |

**请求体：**

```json
{
  "baseVersion": 5,
  "changes": [
    { "type": "replace", "index": 2, "content": "新段落内容" },
    { "type": "insert", "index": 5, "content": "插入的新段落" },
    { "type": "delete", "index": 7 }
  ],
  "authorName": "CalmWolf60",
  "authorColor": "#3498db",
  "os": "Windows 10",
  "browser": "Chrome"
}
```

**变更类型：**

| type | 说明 |
|------|------|
| `replace` | 替换指定索引的段落内容 |
| `insert` | 在指定索引前插入新段落 |
| `delete` | 删除指定索引的段落 |

**响应 200（直接应用）：**

```json
{
  "status": "ok",
  "newVersion": 6,
  "applied": true,
  "merged": false,
  "content": "合并后的完整文件内容"
}
```

**响应 200（段落合并）：**

```json
{
  "status": "ok",
  "newVersion": 7,
  "applied": true,
  "merged": true,
  "content": "合并后的完整文件内容"
}
```

**响应 409（版本冲突，需客户端重新加载）：**

```json
{
  "status": "conflict",
  "currentVersion": 10,
  "content": "服务器当前完整内容"
}
```

---

### 获取版本历史

```
GET /api/mounts/{id}/version-history?path=/file.md
```

返回文件的编辑历史记录，包含每次编辑的作者、时间戳、段落 diff 和客户端信息。

**参数：**

| 参数 | 必填 | 说明 |
|------|------|------|
| `path` | 是 | 文件的相对路径 |

**响应 200：**

```json
{
  "versions": [
    {
      "version": 1,
      "timestamp": 1782317046.0,
      "author_id": "session-uuid",
      "author_name": "CalmWolf60",
      "author_color": "#3498db",
      "changes": [
        { "type": "replace", "index": 0, "content": "新内容" }
      ],
      "content_snapshot": "文件完整内容快照",
      "client_ip": "10.10.77.91",
      "client_os": "Windows 10",
      "client_browser": "Chrome",
      "user_agent": "Mozilla/5.0..."
    }
  ],
  "current_version": 5
}
```

---

## 远程文件代理 API

远程文件代理允许 nas-md 作为编辑器代理，读写局域网其他服务中的 MD 文件。文件不存储在 nas-md 中，所有修改直接回写远程服务。

### 代理读取远程文件

```
GET /api/remote/file?src=<远程服务URL>&path=<文件路径>
```

从远程服务器代理读取文件内容。

**参数：**

| 参数 | 必填 | 说明 |
|------|------|------|
| `src` | 是 | 远程服务基础 URL（如 `https://10.10.77.91:9000`） |
| `path` | 是 | 远程文件路径（如 `/docs/readme.md`） |

**请求头：**

| Header | 说明 |
|--------|------|
| `X-Remote-Key` | 远程服务的 API Key，用于认证 |

**响应 200：**

```json
{
  "content": "# 文件标题\n\n文件内容...",
  "status": "ok"
}
```

**响应 502：** 远程服务器错误（不可达、认证失败等）。

### 代理写入远程文件

```
PUT /api/remote/file?src=<远程服务URL>&path=<文件路径>
```

将文件内容代理写入远程服务器。

**参数：**

| 参数 | 必填 | 说明 |
|------|------|------|
| `src` | 是 | 远程服务基础 URL |
| `path` | 是 | 远程文件路径 |

**请求头：**

| Header | 说明 |
|--------|------|
| `X-Remote-Key` | 远程服务的 API Key |
| `Content-Type` | `text/markdown; charset=utf-8` |

**请求体：** 文件原始内容（text）。

**响应 200：**

```json
{
  "status": "ok"
}
```

**响应 502：** 远程服务器错误。

### 远程服务需实现的 API

远程服务需要提供以下两个接口供 nas-md 代理调用：

| 方法 | 接口 | 说明 |
|------|------|------|
| `GET` | `/api/files?path=<path>` | 返回文件原始内容，通过 `X-API-Key` header 认证 |
| `PUT` | `/api/files?path=<path>` | 接收文件内容并保存，通过 `X-API-Key` header 认证 |

### 深链 URL 格式

前端通过 URL fragment 传递远程文件参数：

```
https://nas-md-host/#remote=<base64url编码的JSON>
```

JSON 内容：

```json
{
  "src": "https://remote-host:port",
  "path": "/docs/readme.md",
  "key": "your-api-key"
}
```

API Key 在 URL fragment 中传递，浏览器不会将其发送到 HTTP 请求中，nas-md 也不存储或记录 API Key。

---

## 搜索与查询 API

### 全文搜索

```
GET /api/search?q=keyword&limit=20
```

使用 SQLite FTS5 进行全文搜索。需要认证。

**参数：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `q` | 必填 | 搜索关键词 |
| `limit` | 20 | 返回结果数量上限 |

**响应 200：**
```json
[
  {"path": "notes/todo.md", "title": "Todo", "snippet": "...matching text..."},
  ...
]
```

---

### 结构化查询

```
GET /api/query?type=task|tag|heading|link
```

查询结构化对象（任务、标签、标题、链接）。需要认证。

#### 查询任务

```
GET /api/query?type=task&status=pending
```

**参数：**

| 参数 | 说明 |
|------|------|
| `type` | 必填，固定为 `task` |
| `status` | 可选，`pending` 或 `done`，不传则返回全部 |

**响应 200：**
```json
{
  "tasks": [
    {"content": "Buy groceries", "done": false, "page": "notes/todo.md", "line": 5},
    ...
  ]
}
```

#### 查询标签

```
GET /api/query?type=tag
GET /api/query?type=tag&name=project
```

**参数：**

| 参数 | 说明 |
|------|------|
| `type` | 必填，固定为 `tag` |
| `name` | 可选，指定标签名则返回含该标签的页面列表 |

**响应 200（无 name，返回标签列表）：**
```json
{
  "tags": [
    {"name": "project", "count": 5},
    {"name": "python", "count": 3},
    ...
  ]
}
```

**响应 200（有 name，返回页面列表）：**
```json
{
  "pages": [
    {"path": "notes/a.md", "title": "A"},
    ...
  ]
}
```

#### 查询标题

```
GET /api/query?type=heading&page=notes/a.md
```

**参数：**

| 参数 | 说明 |
|------|------|
| `type` | 必填，固定为 `heading` |
| `page` | 可选，指定页面路径则返回该页面的标题列表 |

**响应 200：**
```json
{
  "headings": [
    {"level": 2, "text": "Section", "line": 10, "page": "notes/a.md"},
    ...
  ]
}
```

**响应 400：** 无效的查询类型。

#### 查询链接

```
GET /api/query?type=link&page=notes/a.md
```

**参数：**

| 参数 | 说明 |
|------|------|
| `type` | 必填，固定为 `link` |
| `page` | 可选，指定页面路径则返回该页面的出链列表 |

**响应 200：**
```json
{
  "links": [
    {"target": "Project Notes", "display_text": "项目笔记", "line": 5},
    {"target": "TODO", "display_text": null, "line": 12}
  ]
}
```

### 反链查询

```
GET /api/backlinks?page=notes/a.md
```

查询哪些页面链接到指定页面。需要认证。

**参数：**

| 参数 | 说明 |
|------|------|
| `page` | 必填，目标页面路径 |

**响应 200：**
```json
{
  "backlinks": [
    {"path": "notes/b.md", "title": "Note B", "line": 3, "target": "a", "display_text": null}
  ]
}
```

**响应 400：** 缺少 `page` 参数。

### 统计数据

```
GET /api/stats
```

获取索引统计信息。需要认证。

**响应 200：**
```json
{
  "file_count": 42,
  "task_total": 15,
  "task_done": 8,
  "tag_count": 12,
  "link_count": 30,
  "last_rebuild": "2026-06-04T10:00:00",
  "recent_pages": [
    {"path": "notes/a.md", "title": "Note A", "updated_at": 1749000000000}
  ]
}
```

### 图谱数据

```
GET /api/graph
```

获取知识图谱数据（节点+边），用于前端 D3.js 力导向图渲染。需要认证。

**响应 200：**
```json
{
  "nodes": [
    {"id": 1, "path": "notes/a.md", "title": "Note A"},
    {"id": 2, "path": "notes/b.md", "title": "Note B"}
  ],
  "edges": [
    {"source": 1, "target": 2}
  ]
}
```

### 增量同步

```
POST /api/sync?mount={mountId}
```

客户端发送本地文件列表（path + mtime），服务端返回差异。需要认证。

**请求体：**
```json
{
  "files": {
    "notes/a.md": 1749000000000,
    "notes/b.md": 1749001000000
  }
}
```

**响应 200：**
```json
{
  "download": [
    {"path": "notes/a.md", "mtime": 1749005000000}
  ],
  "upload": [
    {"path": "notes/b.md", "mtime": 1749001000000}
  ],
  "delete": [
    {"path": "notes/old.md"}
  ],
  "server_time": 1749006000000
}
```

- `download`：服务端有更新版本，客户端应下载
- `upload`：客户端有更新版本，服务端确认
- `delete`：文件已在服务端删除

### 同步状态

```
GET /api/sync/status?mount={mountId}
```

获取挂载点的同步状态信息。需要认证。

**响应 200：**
```json
{
  "mount_id": "default",
  "file_count": 42,
  "total_size": 1048576,
  "latest_mtime": 1749006000000
}
```

### 冲突检测与版本管理

协同编辑场景下，冲突检测基于**版本号**而非 mtime：

1. **写入文件时**（`PUT /api/mounts/{id}/file`）：可通过 `expected_mtime` 参数做基础冲突检测，不匹配时创建 `.conflict.md` 副本（向后兼容）
2. **协同编辑时**（`POST /api/mounts/{id}/changes`）：基于 `baseVersion` 版本号乐观锁，不匹配时尝试段落级合并，同段落冲突采用"后写覆盖"策略，不再创建 `.conflict.md`

推荐使用 `POST /changes` 进行协同编辑，避免 mtime 竞态条件。

---

## 错误响应

所有错误均返回 JSON：

```json
{ "error": "问题描述" }
```

| 状态码 | 含义 |
|--------|------|
| 400 | 请求错误（缺少参数） |
| 401 | 未认证（需要 Bearer Token） |
| 403 | 禁止访问（路径逃逸出挂载根目录） |
| 404 | 不存在（挂载点或文件不存在） |
| 405 | 方法不允许 |
| 500 | 服务器内部错误 |

## 安全

- **路径穿越防护：** 所有路径都经过 realpath 解析，并校验确保在挂载根目录内。试图逃逸的请求（如 `../../etc/passwd`）返回 403。
- **隐藏文件：** 以 `.` 开头的文件和目录不会出现在目录列表中。
- **CORS：** 所有 API 响应都包含 `Access-Control-Allow-Origin: *`。
- **Gzip 压缩：** 当客户端支持时，响应自动进行 gzip 压缩。

## 示例：JavaScript 客户端

```javascript
const API = 'http://localhost:8080';

// 列出挂载点
const mounts = await fetch(`${API}/api/mounts`).then(r => r.json());

// 浏览目录
const tree = await fetch(`${API}/api/mounts/mount-0/tree?path=/`).then(r => r.json());

// 读取文件
const content = await fetch(`${API}/api/mounts/mount-0/file?path=/notes.md`).then(r => r.text());

// 写入文件
await fetch(`${API}/api/mounts/mount-0/file?path=/new.md`, {
  method: 'PUT',
  body: '# 你好\n\n新笔记内容',
});

// 创建目录
await fetch(`${API}/api/mounts/mount-0/mkdir?path=/Projects`, { method: 'PUT' });

// 重命名
await fetch(`${API}/api/mounts/mount-0/rename?oldPath=/old.md&newPath=/new.md`, { method: 'PUT' });

// 删除
await fetch(`${API}/api/mounts/mount-0/file?path=/trash.md`, { method: 'DELETE' });
```
