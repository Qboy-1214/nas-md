# 实时协同编辑设计

> Date: 2026-06-16
> Status: Draft

## 1. 目标

两个人同时编辑同一个 MD 文件时：
- A 在编辑中，B 保存后 A 能在亚秒级看到改动
- 能看到是谁改的（改动者标注）
- A 正在编辑的段落不被远程更新打断
- 冲突时走乐观锁兜底

## 2. 设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 传输协议 | SSE | 单向推送 + 自动重连 + HTTP 兼容 + 实现量 ~30 行 |
| 冲突处理 | 编辑中保护 + 乐观锁兜底 | 不打断正在编辑的用户，冲突走现有 .conflict.md 机制 |
| 段落定义 | 空行（`\n\n`）分隔 | 最自然的段落语义，与 MD 源文本一致 |
| 改动标注 | 5 秒后自动褪色 | 信息已传达，不打扰 |
| 更新方式 | `setValue()` 全量（后续迭代局部替换） | 三种模式统一处理，功能正确优先 |

## 3. 整体架构

```
┌─────────────────────────────────────────────────────┐
│                    前端（浏览器）                      │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────┐  │
│  │ 身份管理  │  │ SSE 客户端│  │ 同步层             │  │
│  │ identity │  │ EventSource│ │  - 段落 diff 应用  │  │
│  │ .js      │  │ sse_     │  │  - 编辑中保护      │  │
│  │          │  │ client.js│  │  - 暂存队列        │  │
│  └──────────┘  └─────┬────┘  │  - 段落高亮        │  │
│                      │        └───────────────────┘  │
│                      │   HTTP POST                   │
│                      │   (保存/读取)                  │
├──────────────────────┼──────────────────────────────┤
│              后端（Python 标准库）                     │
│                      │                               │
│  ┌──────────┐  ┌─────┴────┐  ┌───────────────────┐  │
│  │ SSE 推送  │  │ HTTP API │  │ 段落级 diff 引擎   │  │
│  │ sse_     │  │ (已有)   │  │ paragraph_        │  │
│  │ handler  │  │          │  │ diff.py           │  │
│  │ .py      │  │ 文件读写  │  │                    │  │
│  │          │  │ 乐观锁   │  │ difflib            │  │
│  │ 连接管理  │  │          │  │ SequenceMatcher    │  │
│  │ 事件广播  │  │          │  │                    │  │
│  └──────────┘  └──────────┘  └───────────────────┘  │
└─────────────────────────────────────────────────────┘
```

## 4. 数据流

### 4.1 B 保存 → A 看到改动

```
1. B 编辑并保存 → HTTP POST /api/mounts/{id}/file
2. 后端 _handle_write_file 保存成功
3. 计算段落级 diff：paragraph_diff.compute(old_content, new_content)
4. SSE 广播给所有看同一文件的客户端
5. A 的 SSE 客户端收到事件 → 同步层处理
6. 遍历每个 change：
   a. 光标在该段落 && 正在编辑（2 秒内有 input） → 暂存
   b. 否则 → 立即应用更新
7. 应用更新：getValue() → split by \n\n → 修改段落 → setValue()
8. 恢复光标位置（现有 doRestore 逻辑）
9. 高亮标注该段落（5 秒后 CSS transition 褪色）
10. 光标离开暂存段落时 → 应用暂存更新
```

### 4.2 SSE 断线兜底

现有的 `performSync()` 30 秒轮询保留。SSE 断线期间靠轮询恢复。SSE 重连后 `EventSource` 自动处理。

## 5. 后端设计

### 5.1 SSE Handler（`sse_handler.py`）

**连接管理：**

```python
# 全局状态
# "mountId:path" -> [(response_writer, client_id, author_name, author_color)]
_sse_clients: dict[str, list[tuple]] = {}
```

**SSE 端点：**

```
GET /api/events?file=mountId:path
Headers: Cookie: nasmd_sid=xxx
Accept: text/event-stream
```

响应：
```
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive

data: {"type":"connected","clientId":"abc-123"}

data: {"type":"remote_edit","authorId":"abc-123","authorName":"Fox","authorColor":"#e74c3c","mountId":"work","path":"/334.md","changes":[{"type":"replace","paraIdx":3,"content":"..."},{"type":"insert","paraIdx":7,"content":"..."}]}

data: {"type":"ping"}
```

**事件类型：**

| 类型 | 方向 | 用途 |
|------|------|------|
| `connected` | 服务端 → 客户端 | 连接建立，返回 clientId |
| `remote_edit` | 服务端 → 客户端 | B 保存后的段落级 diff |
| `ping` | 服务端 → 客户端 | 心跳，每 30 秒 |

**广播触发点：**

在 `_handle_write_file` 中，保存成功后、返回响应前：

```python
# 文件保存成功后
if old_content is not None and old_content != new_content:
    changes = paragraph_diff.compute(old_content, new_content)
    if changes:
        sse_broadcast(
            mount_id, path,
            author_id=session_id,
            author_name=author_name,
            author_color=author_color,
            changes=changes,
        )
```

**连接生命周期：**

- 客户端打开 SSE 连接 → 加入 `_sse_clients["mountId:path"]`
- 客户端切换文件 → 发 `{"type":"switch_file","mountId":"x","path":"/y.md"}` → 从旧文件移除，加入新文件
- 客户端断开 → 从所有文件列表移除
- 心跳：每 30 秒发 `data: {"type":"ping"}\n\n`

**线程模型：**

每个 SSE 连接占一个线程（`ThreadingHTTPServer` 默认行为）。nas-md 是小工具，同时看同一篇文档的人通常不超过 5 个。

### 5.2 段落级 diff 引擎（`paragraph_diff.py`）

```python
from difflib import SequenceMatcher

def split_paragraphs(text: str) -> list[str]:
    """以空行分割，保留段落内容"""
    paragraphs = text.split('\n\n')
    while paragraphs and paragraphs[-1].strip() == '':
        paragraphs.pop()
    return paragraphs

def compute_diff(old_text: str, new_text: str) -> list[dict]:
    """计算段落级 diff
    
    返回: [{"type": "replace"|"insert"|"delete", "paraIdx": int, "content": str}]
    
    paraIdx 含义：
    - replace/delete: 要替换/删除的第 N 个段落（0-indexed）
    - insert: 在第 N 个段落之前插入（0-indexed，paraIdx=0 表示插入到最前面）
    """
    old_paras = split_paragraphs(old_text)
    new_paras = split_paragraphs(new_text)
    
    sm = SequenceMatcher(None, old_paras, new_paras)
    changes = []
    
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'replace':
            for i, j in zip(range(i1, i2), range(j1, j2)):
                changes.append({
                    'type': 'replace',
                    'paraIdx': i,
                    'content': new_paras[j]
                })
            # 处理不等长替换
            if (i2 - i1) > (j2 - j1):
                for i in range(i1 + (j2 - j1), i2):
                    changes.append({'type': 'delete', 'paraIdx': i})
            elif (j2 - j1) > (i2 - i1):
                for j in range(j1 + (i2 - i1), j2):
                    changes.append({'type': 'insert', 'paraIdx': i2, 'content': new_paras[j]})
        elif tag == 'delete':
            for i in range(i1, i2):
                changes.append({'type': 'delete', 'paraIdx': i})
        elif tag == 'insert':
            for j in range(j1, j2):
                changes.append({'type': 'insert', 'paraIdx': i1, 'content': new_paras[j]})
    
    return changes
```

**边界情况：**

| 场景 | 处理 |
|------|------|
| B 在末尾新增段落 | `insert`，`paraIdx` = 末尾位置 |
| B 删除段落 | `delete`，只标记索引 |
| 内容完全一样 | 不广播（调用前检查） |
| 文件很大（1000+ 段落） | SequenceMatcher O(N²)，但 MD 文件通常不大，够用 |

## 6. 前端设计

### 6.1 身份管理（`identity.js`）

```js
(function() {
    const STORAGE_KEY = 'nasmd_identity';
    
    function generateIdentity() {
        const adjectives = ['Swift', 'Calm', 'Bold', 'Keen', 'Wise', 'Bright', 'Silent', 'Wild'];
        const animals = ['Fox', 'Owl', 'Cat', 'Bear', 'Wolf', 'Raven', 'Crane', 'Deer'];
        const colors = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c', '#e67e22', '#34495e'];
        
        const name = adjectives[Math.floor(Math.random() * adjectives.length)] + 
                     animals[Math.floor(Math.random() * animals.length)] + 
                     Math.floor(Math.random() * 100);
        const color = colors[Math.floor(Math.random() * colors.length)];
        
        return { id: crypto.randomUUID(), name, color };
    }
    
    function getIdentity() {
        try {
            const stored = localStorage.getItem(STORAGE_KEY);
            if (stored) return JSON.parse(stored);
        } catch (_) {}
        const id = generateIdentity();
        localStorage.setItem(STORAGE_KEY, JSON.stringify(id));
        return id;
    }
    
    window.nasmdIdentity = { get: getIdentity };
})();
```

身份持久化在 localStorage，同一浏览器始终同一身份。API 请求通过 `X-Client-Id` 和 `X-Client-Name` header 传递。

### 6.2 SSE 客户端（`sse_client.js`）

```js
class SSEClient {
    constructor() {
        this.es = null;
        this.identity = nasmdIdentity.get();
        this.handlers = {};
        this._reconnectDelay = 1000;
    }
    
    connect(mountId, path) {
        this.disconnect();
        const url = `/api/events?file=${encodeURIComponent(mountId + ':' + path)}`;
        this.es = new EventSource(url);
        
        this.es.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (this.handlers[data.type]) {
                    this.handlers[data.type](data);
                }
            } catch (_) {}
        };
        
        this.es.onerror = () => {
            // EventSource 自动重连，但可以在这里加逻辑
            if (this.handlers['error']) this.handlers['error']();
        };
    }
    
    on(type, handler) { this.handlers[type] = handler; }
    
    disconnect() {
        if (this.es) { this.es.close(); this.es = null; }
    }
    
    switchFile(mountId, path) {
        this.connect(mountId, path);
    }
}
```

### 6.3 同步层（`sync_layer.js`）

**编辑状态追踪：**

```js
let _lastInputTime = 0;
let _cursorParaIdx = -1;
let _pendingUpdates = [];

// 复用现有的 onEditorInput
const _origOnEditorInput = window.onEditorInput;
window.onEditorInput = function() {
    _lastInputTime = Date.now();
    _cursorParaIdx = getCursorParagraphIndex();
    if (_origOnEditorInput) _origOnEditorInput();
};

function isActivelyEditing() {
    return Date.now() - _lastInputTime < 2000;
}
```

**段落索引：**

```js
function getCursorParagraphIndex() {
    if (!window._vditor) return -1;
    const sel = window.getSelection();
    if (!sel.rangeCount) return -1;
    const range = sel.getRangeAt(0);
    const node = range.startContainer;
    const el = node.nodeType === 3 ? node.parentElement : node;
    
    // 获取所有段落级 DOM 元素
    const vditorEl = document.getElementById('vditor');
    const paraSelectors = 'p, h1, h2, h3, h4, h5, h6, pre, blockquote, ul, ol, table, hr';
    const allParas = Array.from(vditorEl.querySelectorAll(paraSelectors));
    
    for (let i = 0; i < allParas.length; i++) {
        if (allParas[i].contains(el) || allParas[i] === el) return i;
    }
    return -1;
}
```

**远程编辑处理：**

```js
function handleRemoteEdit(data) {
    for (const change of data.changes) {
        const isProtected = isActivelyEditing() && change.paraIdx === _cursorParaIdx;
        
        if (isProtected) {
            // 正在编辑的段落被改了 → 暂存
            _pendingUpdates.push({
                type: change.type,
                paraIdx: change.paraIdx,
                content: change.content,
                author: { id: data.authorId, name: data.authorName, color: data.authorColor }
            });
        } else {
            // 直接更新
            applyRemoteChange(change, data);
        }
    }
}

function applyRemoteChange(change, author) {
    // 获取当前 MD 源文本
    const currentContent = window._vditor.getValue();
    const paragraphs = currentContent.split('\n\n');
    
    switch (change.type) {
        case 'replace':
            if (change.paraIdx < paragraphs.length) {
                paragraphs[change.paraIdx] = change.content;
            }
            break;
        case 'delete':
            if (change.paraIdx < paragraphs.length) {
                paragraphs.splice(change.paraIdx, 1);
            }
            break;
        case 'insert':
            paragraphs.splice(change.paraIdx, 0, change.content);
            break;
    }
    
    const newContent = paragraphs.join('\n\n');
    
    // 保存光标位置
    const savedPos = saveCursorScrollToStorage();
    
    // 全量替换
    window._vditor.setValue(newContent);
    window._originalContent = window._vditor.getValue();
    
    // 恢复光标
    if (savedPos) {
        window._pendingRestore = savedPos;
        // doRestore 会在 initEditor 的 after 回调里执行
        // 但 setValue 不会触发 after 回调，所以需要手动恢复
        setTimeout(() => restoreCursorScrollFromStorage(), 100);
    }
    
    // 高亮标注
    highlightParagraph(change.paraIdx, author.name, author.color);
}
```

**暂存队列应用：**

```js
// 光标移动时检查暂存更新
setInterval(() => {
    if (_pendingUpdates.length === 0) return;
    const newParaIdx = getCursorParagraphIndex();
    if (newParaIdx !== _cursorParaIdx) {
        _cursorParaIdx = newParaIdx;
        const pending = [..._pendingUpdates];
        _pendingUpdates = [];
        for (const update of pending) {
            applyRemoteChange(update, update.author);
        }
    }
}, 500);
```

### 6.4 高亮标注（`highlight.css`）

```css
/* 段落高亮 */
.paragraph-highlight {
    background-color: var(--highlight-color, rgba(52, 152, 219, 0.15));
    border-left: 3px solid var(--author-color, #3498db);
    transition: background-color 5s ease-out, border-color 5s ease-out;
    border-radius: 2px;
    padding-left: 4px;
    margin-left: -7px;
    position: relative;
}

/* 改动者标注 */
.paragraph-highlight .author-label {
    position: absolute;
    right: 8px;
    top: 2px;
    font-size: 11px;
    color: var(--author-color, #3498db);
    opacity: 0.8;
    font-weight: 500;
    transition: opacity 5s ease-out;
}
```

高亮通过动态添加 CSS class 实现。5 秒后 CSS transition 自动褪色。

## 7. 新增文件清单

| 文件 | 位置 | 职责 |
|------|------|------|
| `sse_handler.py` | `nas_md/webserver/` | SSE 连接管理 + 事件广播 |
| `paragraph_diff.py` | `nas_md/webserver/` | 段落分割 + diff 计算 |
| `sse_client.js` | `web/` | EventSource 封装 |
| `sync_layer.js` | `web/` | 段落更新 + 编辑中保护 + 暂存队列 |
| `identity.js` | `web/` | 匿名身份生成 + 持久化 |
| `highlight.css` | `web/` | 段落高亮 + 改动者标注样式 |

## 8. 修改现有文件

| 文件 | 改动内容 |
|------|----------|
| `webserver/__init__.py` | 添加 SSE handler 路由、连接管理全局变量、在 `_handle_write_file` 中调用 `sse_broadcast` |
| `app.js` | 引入 sse_client.js、sync_layer.js、identity.js、highlight.css；在初始化时启动 SSE 连接 |
| `files.js` | API 请求添加 `X-Client-Id`、`X-Client-Name` header |
| `index.html` | 添加 `<script>` 引用新文件 |

## 9. 复用现有模块

| 模块 | 位置 | 用途 |
|------|------|------|
| `_handle_write_file` | `webserver/__init__.py:1306` | 文件保存 + 乐观锁 |
| `_handle_file` | `webserver/__init__.py:1262` | 文件读取 + `X-Mod-Time` |
| `doRestore` | `editor.js:611` | 光标/滚动恢复 |
| `onEditorInput` | `app.js:2776` | 编辑状态追踪（扩展） |
| `fileMtimes` | `app.js:38` | 乐观锁 mtime 记录 |
| `performSync` | `app.js:3237` | 30 秒轮询（SSE 断线兜底） |
| `saveCursorScrollToStorage` | `app.js:2497` | 光标位置保存 |

## 10. 后续迭代

### 10.1 局部 DOM 替换

当前方案用 `setValue()` 全量替换。后续可以改为 DOM 局部替换：

1. 实验：在 IR/SV/WYSIWYG 三种模式下查看 Vditor 的实际 DOM 结构
2. 根据实验结果实现三种模式各自的段落定位和替换逻辑
3. 目标：只替换变化的段落 DOM 节点，其他段落完全不动

### 10.2 自定义昵称

当前方案是随机匿名身份。后续可以加一个入口让用户设置昵称。

### 10.3 光标位置广播

当前方案不广播光标位置。后续可以广播"谁在编辑哪段"，在侧边栏或编辑器里显示。
