# 版本号驱动的段落级协同编辑架构设计

**日期**: 2026-07-07
**状态**: 设计确认中
**背景**: 替换现有基于mtime的多套冲突机制，统一为单一数据流

## 1. 问题背景

当前系统有4套互相打架的机制：
1. **mtime乐观锁** — 客户端发送`expected_mtime`，不匹配则创建`.conflict.md`
2. **mtime轮询** — `pollCurrentFile` 每2秒fetch文件，mtime变了就覆盖编辑器
3. **SSE推送** — 服务器广播段落diff给其他客户端
4. **版本历史** — 服务器在写入时记录段落diff

根本问题：mtime是"全局时钟"，每个客户端各自缓存，永远在追赶服务器。保存改了mtime → 轮询误判为"外部修改" → 覆盖编辑器 → 触发新保存 → expected_mtime过期 → 冲突。竞态条件防不胜防。

## 2. 使用场景

- **多人实时协同编辑**：2+人同时编辑同一文件，需实时看到对方编辑
- **段落级合并**：不同段落编辑直接合并；同段落编辑后写覆盖（接受可能丢失）
- **偶尔外部修改**：有时用VSCode等工具直接改文件，需检测并同步
- **两种挂载**：服务器挂载（host=True，本地磁盘）和用户本机挂载（File System Access API）

## 3. 核心设计

### 3.1 文件版本号（fileVersion）

每个文件维护一个单调递增的整数版本号，存在内存中并持久化到版本历史JSON。这是**唯一真相来源**，替代mtime。

### 3.2 单一写入路径

所有修改（本地编辑、远程合并、外部修改重载）都通过 `POST /api/mounts/{id}/changes` 提交段落级changes，不再有"整文件PUT + mtime检查"路径。

### 3.3 数据流

**正常编辑（无冲突）**：
```
用户输入 → 防抖1.5s → 客户端对比baseContent计算changes
  → POST /changes {baseVersion: V, changes: [...]}
  → 服务器: baseVersion == 当前版本?
      是 → 应用changes到文件, 版本号 V→V+1, 记录版本历史, 广播SSE给他人
      否 → 进入合并流程
  → 返回 {newVersion: V+1, applied: true, content: "完整内容"}
  → 客户端更新baseVersion = V+1, baseContent = 新内容
```

**段落级合并（并发编辑）**：
```
客户端A baseVersion=V 提交changes_A
  → 服务器: 当前版本已是V+1（B刚改了第3段）
  → 检查changes_A涉及的段落 vs 已应用的changes涉及的段落:
      无重叠（A改第1段，B改第3段）→ 合并! 应用A的changes, 版本→V+2, 广播
      有重叠（A和B都改第3段）→ 后写覆盖该段, 版本→V+2, 广播
  → 返回 {newVersion: V+2, applied: true, merged: true, content: "合并后完整内容"}
  → 广播合并结果给A和B
```

**外部修改检测（仅服务器挂载）**：
```
watchdog检测到文件被外部工具修改
  → 服务器读取文件新内容, 与内存中当前内容做diff
  → 自己写入的过滤: 如果新内容 == 内存content → 跳过（自己的写）
  → 版本号 V→V+1, 记录为"system"作者的版本
  → SSE广播 {type: "external_reload", newVersion, changes} 给所有客户端
  → 客户端: 如有未提交编辑, 保留并在下次提交时合并; 否则直接应用
```

## 4. 要移除的机制

| 机制 | 处置 |
|------|------|
| `expected_mtime` 乐观锁 | 移除 — 改用 `baseVersion` |
| `pollCurrentFile` 每2秒fetch覆盖 | 移除 — 改由SSE驱动 |
| `.conflict.md` 副本创建 | 移除 — 段落级合并不需要 |
| `performSync` 中的mtime比较 | 移除 — 不再需要 |
| `state.fileMtimes` | 移除 — 改用 `state.fileVersions` |
| `_lastSavedContent` | 保留但改用途 — 作为客户端baseContent |

## 5. 服务器端变更

### 5.1 新增模块：`file_version_store.py`

```python
# 内存维护 file_key -> {version, content, lock}
# 持久化版本号到版本历史JSON（复用现有 version_history.py）
# 核心方法:
def apply_changes(file_key, base_version, changes, author) -> dict:
    """应用changes，返回 {newVersion, applied, merged, content}"""
    # 1. 加锁
    # 2. 获取当前版本和内容
    # 3. 如果 base_version == 当前版本:
    #      直接应用changes到content
    #    否则:
    #      合并changes到当前content（段落级合并）
    # 4. 写文件
    # 5. 版本号+1, 记录版本历史
    # 6. 广播SSE
    # 7. 返回结果
```

段落合并逻辑（`merge_changes`）：
- 提取新旧changes涉及的paraIdx集合
- 无交集 → 直接应用新changes
- 有交集 → 对重叠段落，新changes覆盖（后写覆盖）
- insert/delete可能导致paraIdx偏移，需重新计算

### 5.2 新增API：`POST /api/mounts/{id}/changes`

```python
# 请求体
{
    "path": "/file.md",
    "baseVersion": 5,
    "changes": [
        {"type": "replace", "paraIdx": 2, "content": "新内容"},
        {"type": "insert", "paraIdx": 5, "content": "新段落"}
    ],
    "authorName": "WildBear41",
    "authorColor": "#3498db"
}

# 响应
{
    "status": "ok",
    "newVersion": 6,
    "applied": true,
    "merged": false,
    "content": "完整文件内容"
}
```

### 5.3 新增模块：`file_watcher.py`

基于watchdog，仅监听 `host=True` 的服务器挂载目录：
- 用 `WindowsApiObserver`（Windows）/ `inotify`（Linux），事件驱动零延迟
- 自己写入的过滤：写文件后标记"预期内容"，收到事件时对比，相同则跳过
- 防抖：收到事件后等200ms再读文件，避免读到编辑器临时文件中间状态
- 检测到外部修改 → 读取新内容 → diff → `apply_changes` 以system作者提交 → SSE广播

### 5.4 修改现有端点

- `_handle_write_file`（PUT /file）：标记deprecated，内部转换为 `apply_changes(baseVersion=当前版本, changes=全文replace)`，保持向后兼容
- 版本历史记录逻辑从 `_handle_write_file` 移到 `apply_changes` 内部

## 6. 客户端变更

### 6.1 `app.js` 保存逻辑重写

```javascript
async function saveFile({ silent = false } = {}) {
  if (_saveInProgress) return;
  _saveInProgress = true;
  try {
    if (!state.currentPath || !state.currentMountId || !window._vditor) return;

    const content = window._vditor.getValue();
    const changes = computeParagraphDiff(state.baseContent, content);
    if (changes.length === 0) { markClean(); return; }

    // 服务器挂载：走新的changes API
    const mount = state.mounts.find(m => m.id === state.currentMountId);
    if (mount && !mount._local) {
      const resp = await API.submitChanges(
        state.currentMountId, state.currentPath,
        state.baseVersion, changes,
        state.authorName, state.authorColor
      );
      if (resp.applied) {
        state.baseVersion = resp.newVersion;
        state.baseContent = resp.content;
        window._originalContent = resp.content;
        markClean();
        if (resp.merged) showToast('已合并保存');
        else if (!silent) showToast('已保存');
        else showToast('自动保存完成');
      }
    } else {
      // 本机挂载：保持现有File System Access API逻辑
      // ...
    }
  } finally { _saveInProgress = false; }
}
```

### 6.2 移除的客户端逻辑

- `pollCurrentFile` 函数 — 完全移除
- `startFilePoll` / `stopFilePoll` — 移除
- `state.fileMtimes` 相关所有引用 — 替换为 `state.fileVersions`
- `sync_layer.js` 中更新 `fileMtimes` 的代码 — 移除

### 6.3 `sync_layer.js` 简化

SSE收到 `remote_edit` 时：
- applyChanges到编辑器（现有逻辑保留）
- 更新 `state.baseVersion = data.newVersion`
- 更新 `state.baseContent = 合并后的完整内容`
- 无需再维护mtime同步

SSE收到 `external_reload` 时：
- 如果用户有未提交编辑：保留编辑，下次save时走合并流程
- 如果无编辑：直接setValue新内容，更新baseVersion和baseContent

### 6.4 文件加载时初始化版本号

打开文件时，从服务器获取当前版本号：
```
GET /api/mounts/{id}/file?path=/file.md
响应头: X-File-Version: 5
```
客户端初始化 `state.baseVersion = 5`, `state.baseContent = 文件内容`。

## 7. 需要保留的

- `paragraph_diff.py` 的 `compute_diff` — 核心合并引擎，客户端和服务器都用
- `version_history.py` — 版本历史记录，与版本号机制天然契合
- `sse_handler.py` — SSE推送基础设施
- `sync_layer.js` 的段落应用逻辑和协作通知
- 本机挂载的File System Access API路径

## 8. 迁移兼容

- 文件首次通过新API访问时，如果版本历史中已有记录，取最新版本号作为起始；否则版本号=0并记录初始版本
- 旧的PUT `/file` 端点保留但标记deprecated，内部转换为 `apply_changes`
- 版本历史JSON格式不变，新增 `version` 字段记录版本号

## 9. 边界情况

| 情况 | 处理 |
|------|------|
| 客户端baseVersion远落后于服务器 | 服务器返回当前完整内容，客户端重置baseContent |
| SSE断连期间有修改 | 重连后客户端用baseContent计算diff一次性提交 |
| 外部工具删除文件 | watchdog检测 → SSE通知 → 客户端显示"文件已被删除" |
| 两段相同的insert合并 | 按时间顺序应用，可能出现重复段落 → 可接受 |
| 同段并发编辑 | 后写覆盖该段（接受可能丢失） |
| 用户本机挂载 | 不走版本号机制，保持File System Access API |
| watchdog不可用（网络挂载） | 降级为每10秒对比mtime的低频轮询 |

## 10. 改动范围

**服务器端**：
- 新增 `file_version_store.py`（版本号管理+合并逻辑）
- 新增 `file_watcher.py`（watchdog文件监听）
- 新增 `POST /changes` API端点
- 修改 `_handle_write_file` 为deprecated包装
- 修改 `version_history.py` 增加 `version` 字段

**客户端**：
- 重写 `app.js` 的 `saveFile`
- 移除 `pollCurrentFile` 及相关轮询
- 修改 `sync_layer.js` 移除mtime同步
- 修改 `files.js` 增加 `submitChanges` 方法
- 文件加载时获取并初始化版本号
