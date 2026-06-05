# 多用户隔离设计（免登录）

## 背景

当前架构所有挂载点全局共享，无法支持多用户各自挂载互不影响。需要实现用户级隔离，且必须免登录。

## 核心方案：Cookie 自动会话

用户首次访问时，服务器自动生成 UUID 作为 session ID，通过 Cookie 下发。后续请求浏览器自动携带，服务器据此识别用户。

## 详细设计

### 1. 会话管理

- Cookie 名称：`nasmd_sid`
- 值：UUID v4
- 属性：`HttpOnly; Path=/; Max-Age=31536000`（1 年有效期，SameSite=Lax）
- 首次请求（无 Cookie）：服务器生成 UUID，`Set-Cookie` 下发
- 后续请求：读取 Cookie 识别用户
- Cookie 丢失：分配新 session，旧挂载点数据仍在磁盘，可通过恢复功能找回

### 2. 挂载点隔离

- `MountEntry` 新增 `owner` 字段（值为 session UUID）
- 宿主机挂载点（`host=True`）：`owner` 为空，由 `MOUNT_DIRS` 配置
- 内置存储挂载点（`builtin-storage`）：`owner` 为空，所有人可见但只读
- 用户挂载点（`host=False`）：`owner` 为创建者的 session UUID

**可见性规则：**

| 用户类型 | 可见的挂载点 |
|---------|------------|
| 普通用户 | 内置存储 + 自己挂载的本机目录 |
| Admin | 内置存储 + 宿主机挂载点（读写）+ 自己挂载的本机目录 |

**关键：Admin 看不到其他用户的挂载点，用户之间完全隔离。**

### 3. API 变更

- `GET /api/mounts`：返回当前用户可见的挂载点
- `POST /api/mounts`：新挂载点绑定当前 session（`owner` = 当前 session ID）
- `DELETE /api/mounts/{id}`：只能删除自己拥有的挂载点
- 所有文件操作（读取、写入、删除、重命名、新建目录）：验证当前用户是否拥有该挂载点
- 请求头 `X-Admin` 保留，用于标识 admin 请求

### 4. 数据持久化

`mounts.json` 结构改为按用户分组存储：

```json
{
  "_host": [
    {"id": "mount-0", "name": "data", "path": "/data", "host": true, "owner": ""}
  ],
  "uuid-user-a": [
    {"id": "mount-1", "name": "work", "path": "/home/user-a/work", "host": false, "owner": "uuid-user-a"}
  ],
  "uuid-user-b": [
    {"id": "mount-2", "name": "docs", "path": "/home/user-b/docs", "host": false, "owner": "uuid-user-b"}
  ]
}
```

- `_host` 键存储宿主机挂载点
- 每个 session UUID 键存储该用户的挂载点
- 服务器重启后自动恢复所有用户的挂载点

### 5. 搜索隔离

- 搜索结果只包含当前用户可见的挂载点内的文件
- 看板统计只统计当前用户可见的挂载点

### 6. 前端变更

- 前端无需感知 session 机制（Cookie 浏览器自动处理）
- `state.isAdmin` 逻辑不变（通过 `/admin` URL 判断）
- 侧边栏只显示当前用户可见的挂载点

### 7. 实现要点

**后端（`nas_md/webserver/__init__.py`）：**
- 新增 `_get_session_id()` 方法：从 Cookie 读取或生成新 session ID
- 修改 `MountManager`：挂载点按 owner 过滤
- 修改所有 API handler：注入 session 上下文
- 修改 `_save_mounts_to_disk` / `_load_saved_mounts`：按用户分组存储

**前端（`web/app.js`）：**
- 无需改动（Cookie 自动携带）
- 侧边栏自然只显示当前用户的挂载点

### 8. 边界情况

- **同一浏览器多标签页**：共享同一 session，行为一致
- **无痕模式**：关闭后 Cookie 丢失，下次访问为新 session
- **Cookie 被清除**：新 session，旧挂载点可通过"恢复挂载"功能找回（列出 mounts.json 中无活跃 session 的挂载点供选择）
- **挂载点路径被删除**：启动时跳过，与当前行为一致
