# 挂载 API 参考

挂载 API 允许通过 Web UI 浏览、读取和管理服务器端目录上的文件。挂载点通过 `MOUNT_DIRS` 环境变量配置（分号分隔的绝对路径），也可通过 Web UI 动态挂载。

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
  "path": "/mnt/notes"
}
```

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

返回所有已配置的挂载点。

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

动态添加新的挂载点。游客可挂载 1 个目录，登录用户不限。游客挂载的目录自动设为 `public=true`。

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

删除挂载点。内置挂载点（`builtin-storage`）不能删除。需要认证。

**响应 200：**
```json
{ "status": "ok" }
```

**响应 401：** 未认证。
**响应 403：** 内置挂载点不能删除。

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
