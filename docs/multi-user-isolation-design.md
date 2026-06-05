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

**实现细节：**

- `_get_session_id()` 方法从 Cookie 读取 session ID，若不存在则生成新 UUID
- `_pending_cookie` 属性暂存待发送的 `Set-Cookie` 头，避免在 `send_response()` 之前调用 `send_header()` 导致头信息发送失败
- `_flush_session_cookie()` 在 `_send_json()`、`_handle_file()`、`_serve_static()` 中统一发送 Cookie 头

### 2. 挂载点隔离

`MountEntry` 新增 `owner` 字段（值为 session UUID）：

```python
@dataclass
class MountEntry:
    id: str
    name: str
    path: str
    host: bool = False      # True = 宿主机挂载点（MOUNT_DIRS 配置）
    public: bool = False
    readonly: bool = False
    owner: str = ""         # 创建者的 session UUID，空字符串表示遗留/宿主机挂载点
```

**挂载点分类：**

| 类型 | `host` | `owner` | 说明 |
|------|--------|---------|------|
| 内置存储 | False | 空 | `builtin-storage`，所有人可见，只读 |
| 宿主机挂载点 | True | 空 | 由 `MOUNT_DIRS` 配置，仅 Admin 可见 |
| 用户挂载点 | False | session UUID | 用户通过 Web UI 添加，仅创建者可见 |
| 遗留挂载点 | False | 空 | 升级前已存在的挂载点，对所有用户可见 |

**可见性规则（`_visible_mounts()`）：**

| 用户类型 | 可见的挂载点 |
|---------|------------|
| 普通用户 | 内置存储 + 自己挂载的本机目录 + 遗留挂载点 |
| Admin | 内置存储 + 宿主机挂载点（读写）+ 自己挂载的本机目录 + 遗留挂载点 |

**关键：Admin 看不到其他用户的挂载点，用户之间完全隔离。**

**所有权校验（`_owns_mount()`）：**

| 挂载点类型 | 谁可以操作（写/删/重命名） |
|-----------|------------------------|
| 内置存储 | 无人（只读） |
| 宿主机挂载点 | 仅 Admin |
| 用户挂载点 | 仅创建者（owner 匹配） |
| 遗留挂载点 | 任何用户 |

### 3. API 变更

- `GET /api/mounts`：返回当前用户可见的挂载点
- `POST /api/mounts`：新挂载点绑定当前 session（`owner` = 当前 session ID），无数量限制
- `DELETE /api/mounts/{id}`：只能删除自己拥有的挂载点
- 所有文件操作（读取、写入、删除、重命名、新建目录）：验证当前用户是否拥有该挂载点
- 请求头 `X-Admin` 保留，用于标识 admin 请求
- `GET /api/search`：搜索结果仅包含当前用户可见挂载点内的文件
- `GET /api/stats`：统计数据仅统计当前用户可见挂载点
- `GET /api/query`：结构化查询结果按可见性过滤

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
- **向后兼容**：旧格式（`MountEntry` 列表）在加载时自动迁移为新格式，无 `owner` 且非 `host` 的挂载点对所有用户可见

### 5. 路径可见性检查

`_path_visible()` 和 `_visible_mount_paths()` 统一处理跨平台路径分隔符：

```python
def _visible_mount_paths(self, session_id: str) -> list[str]:
    visible = self._visible_mounts(session_id)
    return [
        m.path.lower().rstrip("\\/").replace("\\", os.sep).replace("/", os.sep)
        for m in visible
    ]

def _path_visible(self, file_path: str, mount_paths: list[str]) -> bool:
    fp = file_path.lower().replace("\\", os.sep).replace("/", os.sep)
    return any(fp == mp or fp.startswith(mp + os.sep) for mp in mount_paths)
```

确保 Windows（`\`）和 Linux（`/`）环境下路径比较一致。

### 6. 搜索隔离

- 搜索结果只包含当前用户可见的挂载点内的文件
- 看板统计只统计当前用户可见的挂载点
- 结构化查询（任务、标签、标题、链接）按可见性过滤

### 7. 前端变更

- 前端无需感知 session 机制（Cookie 浏览器自动处理）
- `state.isAdmin` 逻辑不变（通过 `/admin` URL 判断）
- 侧边栏只显示当前用户可见的挂载点
- `files.js` 中 API 请求自动附加 `X-Admin` 头信息

### 8. 边界情况

- **同一浏览器多标签页**：共享同一 session，行为一致
- **无痕模式**：关闭后 Cookie 丢失，下次访问为新 session
- **Cookie 被清除**：新 session，旧挂载点可通过"恢复挂载"功能找回（列出 mounts.json 中无活跃 session 的挂载点供选择）
- **挂载点路径被删除**：启动时跳过，与当前行为一致
- **升级兼容**：旧版 `mounts.json`（列表格式）自动迁移为按用户分组格式，无 owner 的挂载点对所有用户可见

### 9. 测试覆盖

39 个测试用例覆盖以下场景（`tests/test_multi_user_isolation.py`）：

| 测试类 | 用例数 | 覆盖内容 |
|--------|--------|---------|
| TestSessionManagement | 4 | Cookie 生成、保持、区分、有效期 |
| TestMountVisibility | 4 | 内置存储、宿主机、用户、遗留挂载点可见性 |
| TestMountOwnership | 6 | 读写权限、删除权限、遗留挂载点兼容、Admin 宿主机写权限 |
| TestFileOperationIsolation | 5 | 树浏览、文件读取、重命名、新建目录、删除文件隔离 |
| TestMountsPersistence | 2 | 按用户分组存储、旧格式迁移 |
| TestMountEntryOwner | 4 | to_dict/from_dict 序列化、默认值、缺失字段 |
| TestPathVisibilityHelpers | 3 | 路径规范化、前缀匹配、跨平台分隔符 |
| TestOwnsMount | 4 | 内置/宿主机/用户/遗留挂载点所有权 |
| TestVisibleMounts | 5 | 各类型挂载点可见性组合 |
| TestCompleteIsolation | 2 | 端到端双用户隔离、无数量限制 |
