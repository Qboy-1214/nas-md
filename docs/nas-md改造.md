## 方案一：本机挂载文件内容轮询同步

### 问题

本机挂载点（File System Access API）的 md 文件在浏览器外部被修改后，编辑器内容不会更新。

### 思路

在现有的 `refreshTree()` 每 5 秒轮询目录树的基础上，增加对**当前打开文件内容**的轮询。只针对本机挂载点，因为宿主机挂载点需要多人协作场景，用方案二的乐观锁更合适。

### 需要修改的地方

**1. 新增 `state.fileMtimes` 存储**

```js
// 在 state 初始化中添加
fileMtimes: {},  // "mountId:path" → { mtime, size }
```

**2. 修改 `openFile()` — 读取时记录 mtime**

在读取文件内容成功后，记录该文件的 mtime 和 size：

```js
// openFile 中，读取内容成功后
const mtimeInfo = { mtime: Date.now(), size: content.length };
if (mount._local) {
  // 本机挂载：获取真实 mtime
  const fileHandle = await getLocalFileHandle(...)
  const file = await fileHandle.getFile();
  mtimeInfo.mtime = file.lastModified;
  mtimeInfo.size = file.size;
}
state.fileMtimes[mount.id + ':' + path] = mtimeInfo;
```

**3. 修改 `refreshTree()` — 增加文件内容轮询**

在现有目录树轮询逻辑之后，追加当前文件的检查：

```js
// 在 refreshTree() 的 try 块末尾、finally 之前
await pollCurrentFile();
```

**4. 新增 `pollCurrentFile()` 函数**

```js
async function pollCurrentFile() {
  // 只在有打开文件、且是本机挂载、且编辑器已初始化时执行
  if (!state.currentPath || !state.currentMountId || !window._vditor) return;
  const mount = state.mounts.find((m) => m.id === state.currentMountId);
  if (!mount || !mount._local) return;
  // 如果编辑器有未保存的修改，跳过（避免覆盖用户正在写的内容）
  if (window._vditor.getValue() !== window._originalContent) return;

  try {
    const key = state.currentMountId + ':' + state.currentPath;
    const prev = state.fileMtimes[key];
    if (!prev) return;

    // 从磁盘读取最新内容
    const handle = await getLocalFileHandle(state.localMounts[state.currentMountId].handle, state.currentPath);
    if (!handle) return;
    const file = await handle.getFile();
    const newMtime = file.lastModified;
    const newSize = file.size;

    // 如果 mtime 没变，跳过
    if (prev.mtime === newMtime && prev.size === newSize) return;

    // 文件被外部修改了，重新加载内容
    const newContent = await file.text();
    window._vditor.setValue(newContent);
    window._originalContent = newContent;

    // 更新记录
    state.fileMtimes[key] = { mtime: newMtime, size: newSize };
  } catch (_e) {
    // 文件可能已被删除，忽略
  }
}
```

**5. 修改 `saveFile()` — 保存成功后刷新 mtime 记录**

```js
// saveFile 中，本机挂载保存成功后
if (mount._local) {
  const handle = await getLocalFileHandle(state.localMounts[mount.id].handle, state.currentPath);
  if (handle) {
    const file = await handle.getFile();
    state.fileMtimes[mount.id + ':' + state.currentPath] = {
      mtime: file.lastModified,
      size: content.length,
    };
  }
}
```

### 注意事项

* 编辑器有未保存修改时静默跳过，不打断用户
* 不引入新的定时器，复用现有的 5 秒 `refreshTree` 周期
* 只针对本机挂载点，宿主机挂载点走方案二

---

## 方案二：宿主机挂载乐观锁

### 问题

多人同时编辑同一个 md 文件，后保存的人会覆盖先保存的人的内容。

### 现状

后端 `_handle_write_file` **已经实现了乐观锁**：

```python
# 后端已有逻辑
expected_mtime = qs.get("expected_mtime", [None])[0]
if expected_mtime and os.path.isfile(abs_path):
    actual_mtime = int(os.path.getmtime(abs_path) * 1000)
    if actual_mtime != int(expected_mtime):
        # 创建 .conflict.md 副本
        shutil.copy2(abs_path, conflict_path)
```

后端保存成功后返回新 mtime：

```python
self._send_json({"status": "ok", "modTime": int(st.st_mtime * 1000), "size": st.st_size})
```

**问题只在于前端没有传 `expected_mtime`，也没有处理冲突。**

### 需要修改的地方

**1. 新增 `state.fileMtimes` 存储**（与方案一共享）

```js
fileMtimes: {},  // "mountId:path" → { mtime, size }
```

**2. 修改 `openFile()` — 读取时记录 mtime**

```js
// openFile 中，读取内容成功后
if (mount._local) {
  // 本机挂载：获取 File 对象的真实 mtime
  const fileHandle = await getLocalFileHandle(...)
  const file = await fileHandle.getFile();
  state.fileMtimes[key] = { mtime: file.lastModified, size: file.size };
} else {
  // 宿主机挂载：从 API 响应中获取 mtime
  // 需要后端在响应中返回 mtime（见下方后端修改）
}
```

**3. 修改 `API.putFile()` — 传递 `expected_mtime`**

```js
async putFile(mountId, path, content, expectedMtime) {
  let url = `/api/mounts/${mountId}/file?path=${encodeURIComponent(path)}`;
  if (expectedMtime) {
    url += `&expected_mtime=${expectedMtime}`;
  }
  const r = await this.request(url, {
    method: 'PUT',
    body: content,
  });
  return r ? r.json() : null;
}
```

**4. 修改 `saveFile()` — 传递 mtime + 处理冲突**

```js
async function saveFile({ silent = false } = {}) {
  // ... 现有代码 ...

  try {
    if (mount._local) {
      // 本机挂载：同以前
    } else {
      // 宿主机挂载：带上 expected_mtime
      const key = state.currentMountId + ':' + state.currentPath;
      const expectedMtime = state.fileMtimes[key]?.mtime || null;

      const resp = await API.putFile(
        state.currentMountId,
        state.currentPath,
        content,
        expectedMtime
      );

      if (resp && resp.error) {
        throw new Error(resp.error);
      }

      // 保存成功后，用后端返回的新 mtime 更新记录
      if (resp && resp.modTime) {
        state.fileMtimes[key] = { mtime: resp.modTime, size: content.length };
      }

      // 检查是否生成了冲突文件
      if (resp && resp.conflict) {
        showToast('文件在外部已被修改，已创建冲突副本');
      }
    }
  } catch (e) {
    // ... 现有错误处理 ...
  }
}
```

**5. 后端修改 — `_handle_file` GET 响应中返回 mtime**

当前 GET 文件接口只返回原始内容，没有返回元数据。两种改法：

**改法 A：用 HTTP Header（最小改动）**

在 `_handle_file` 的 GET 响应中添加 `Last-Modified` header：

```python
# _handle_file GET 中，在 end_headers 之前
mtime = int(os.path.getmtime(abs_path) * 1000)
self.send_header("X-Mod-Time", str(mtime))
```

前端在 `API.getFile()` 中读取这个 header：

```js
async getFile(mountId, path) {
  const r = await this.request(`/api/mounts/${mountId}/file?path=${encodeURIComponent(path)}`);
  if (!r || !r.ok) return null;
  const content = await r.text();
  const mtime = parseInt(r.headers.get('X-Mod-Time') || '0', 10);
  return { content, mtime };  // 改为返回对象
}
```

**改法 B：用 JSON 包装响应（更规范但改动大）**

把 GET 文件接口改为返回 JSON：`{"content": "...", "modTime": 1234567890, "size": 1024}`

但这需要改 `API.getFile()` 的所有调用方，以及 `_handle_file` 的 Content-Type。改动面大，不推荐。

**推荐改法 A。**

**6. 修改 `openFile()` — 从 GET 响应中提取 mtime**

```js
// openFile 中，读取宿主机文件时
const result = await API.getFile(mount.id, path);
if (result === null) { ... }
const content = result.content;
const mtime = result.mtime;
state.fileMtimes[mount.id + ':' + path] = { mtime, size: content.length };
```

### 完整链路

```
打开文件 → GET /api/mounts/{id}/file → 返回内容 + X-Mod-Time header
         → 记录 mtime 到 state.fileMtimes

编辑文件 → 用户编辑 → 编辑器内容 !== originalContent

保存文件 → PUT /api/mounts/{id}/file?path=xxx&expected_mtime=12345
         → 后端检查 mtime 是否匹配
         → 匹配：写入成功，返回新 mtime → 更新 state.fileMtimes
         → 不匹配：创建 .conflict.md → 前端提示"文件已被他人修改"
```

### 冲突时的用户体验

后端检测到冲突时会创建 `.conflict.md` 副本，保证数据不丢失。前端收到冲突后：

1. toast 提示：“文件在外部已被修改，已创建冲突副本（[xxx.conflict.md](http://xxx.conflict.md)）”
2. 用户需要手动决定：用自己的版本覆盖，还是重新加载别人的版本

---

## 两个方案的共用部分

两个方案共享 `state.fileMtimes` 存储和 `openFile()` 中的 mtime 记录逻辑。实施时可以先做方案二的后端 + 前端改动（因为后端已经有大部分逻辑），再做方案一的轮询。
