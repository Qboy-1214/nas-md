# 实时协同编辑 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 两个人同时编辑同一个 MD 文件时，亚秒级实时看到对方改动 + 改动者标注，编辑中段落不中断

**Architecture:** 后端 SSE 推送段落级 diff，前端同步层应用更新到编辑器，编辑中保护通过暂存队列实现。段落以空行分隔，diff 用 difflib.SequenceMatcher 计算。

**Tech Stack:** Python 标准库（difflib, http.server, threading），原生 JS（EventSource, CSS transition），零新增依赖

**Spec:** `docs/2026-06-16-realtime-collab-design.md`

---

### Task 1: 段落级 diff 引擎

**Files:**
- Create: `nas_md/webserver/paragraph_diff.py`
- Test: `tests/test_paragraph_diff.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_paragraph_diff.py
import pytest
from nas_md.webserver.paragraph_diff import split_paragraphs, compute_diff

def test_split_paragraphs_basic():
    text = "para one\n\npara two\n\npara three"
    assert split_paragraphs(text) == ["para one", "para two", "para three"]

def test_split_paragraphs_trailing_newline():
    text = "para one\n\npara two\n\n"
    assert split_paragraphs(text) == ["para one", "para two"]

def test_split_paragraphs_empty():
    assert split_paragraphs("") == []

def test_compute_diff_no_change():
    text = "para one\n\npara two"
    assert compute_diff(text, text) == []

def test_compute_diff_replace():
    old = "para one\n\npara two\n\npara three"
    new = "para one\n\nCHANGED\n\npara three"
    changes = compute_diff(old, new)
    assert len(changes) == 1
    assert changes[0]["type"] == "replace"
    assert changes[0]["paraIdx"] == 1
    assert changes[0]["content"] == "CHANGED"

def test_compute_diff_insert():
    old = "para one\n\npara three"
    new = "para one\n\npara two\n\npara three"
    changes = compute_diff(old, new)
    assert any(c["type"] == "insert" for c in changes)

def test_compute_diff_delete():
    old = "para one\n\npara two\n\npara three"
    new = "para one\n\npara three"
    changes = compute_diff(old, new)
    assert any(c["type"] == "delete" for c in changes)

def test_compute_diff_multiple_changes():
    old = "A\n\nB\n\nC\n\nD"
    new = "A\n\nB2\n\nC\n\nE"
    changes = compute_diff(old, new)
    types = {c["type"] for c in changes}
    assert "replace" in types
    assert "insert" in types or "delete" in types
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_paragraph_diff.py -v`
Expected: FAIL - module not found

- [ ] **Step 3: Implement `paragraph_diff.py`**

```python
# nas_md/webserver/paragraph_diff.py
"""Paragraph-level diff engine for real-time collaborative editing."""

from difflib import SequenceMatcher


def split_paragraphs(text: str) -> list[str]:
    """Split text by double newline (paragraph boundary)."""
    paragraphs = text.split('\n\n')
    while paragraphs and paragraphs[-1].strip() == '':
        paragraphs.pop()
    return paragraphs


def compute_diff(old_text: str, new_text: str) -> list[dict]:
    """Compute paragraph-level diff between old and new text.
    
    Returns list of changes:
    - {"type": "replace", "paraIdx": int, "content": str}
    - {"type": "insert", "paraIdx": int, "content": str}
    - {"type": "delete", "paraIdx": int}
    
    paraIdx: 0-indexed paragraph position.
    For insert: insert BEFORE the paragraph at paraIdx.
    For replace/delete: target the paragraph at paraIdx.
    """
    old_paras = split_paragraphs(old_text)
    new_paras = split_paragraphs(new_text)
    
    if old_paras == new_paras:
        return []
    
    sm = SequenceMatcher(None, old_paras, new_paras, autojunk=False)
    changes = []
    
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'replace':
            # Handle potentially unequal length replacements
            old_len = i2 - i1
            new_len = j2 - j1
            paired = min(old_len, new_len)
            
            for k in range(paired):
                changes.append({
                    'type': 'replace',
                    'paraIdx': i1 + k,
                    'content': new_paras[j1 + k],
                })
            
            if old_len > new_len:
                # More old paragraphs than new → extras are deletions
                for k in range(paired, old_len):
                    changes.append({
                        'type': 'delete',
                        'paraIdx': i1 + k,
                    })
            elif new_len > old_len:
                # More new paragraphs than old → extras are insertions
                for k in range(paired, new_len):
                    changes.append({
                        'type': 'insert',
                        'paraIdx': i2,
                        'content': new_paras[j1 + k],
                    })
        elif tag == 'delete':
            for i in range(i1, i2):
                changes.append({'type': 'delete', 'paraIdx': i})
        elif tag == 'insert':
            for j in range(j1, j2):
                changes.append({'type': 'insert', 'paraIdx': i1, 'content': new_paras[j]})
    
    return changes
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_paragraph_diff.py -v`
Expected: 8/8 PASS

- [ ] **Step 5: Commit**

```bash
git add nas_md/webserver/paragraph_diff.py tests/test_paragraph_diff.py
git commit -m "feat: add paragraph-level diff engine for collaborative editing"
```

---

### Task 2: SSE 连接管理 + 广播

**Files:**
- Create: `nas_md/webserver/sse_handler.py`
- Modify: `nas_md/webserver/__init__.py` (add SSE route, connection globals, broadcast call in `_handle_write_file`)
- Test: `tests/test_sse_handler.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sse_handler.py
import pytest
import threading
import time
import socket
from http.server import HTTPServer

from nas_md.webserver.sse_handler import SSEConnectionHandler, sse_broadcast, register_sse_client
from nas_md.webserver.paragraph_diff import compute_diff


def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_compute_diff_basic():
    """Verify diff engine works for SSE use case."""
    old = "# Title\n\nParagraph one.\n\nParagraph two."
    new = "# Title\n\nParagraph one changed.\n\nParagraph two."
    changes = compute_diff(old, new)
    assert len(changes) == 1
    assert changes[0]["type"] == "replace"
    assert changes[0]["paraIdx"] == 1


def test_paragraph_split_preserves_headings():
    text = "# Title\n\n## Section\n\nContent"
    from nas_md.webserver.paragraph_diff import split_paragraphs
    paras = split_paragraphs(text)
    assert paras[0] == "# Title"
    assert paras[1] == "## Section"
    assert paras[2] == "Content"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sse_handler.py -v`
Expected: FAIL - module not found

- [ ] **Step 3: Implement `sse_handler.py`**

```python
# nas_md/webserver/sse_handler.py
"""Server-Sent Events handler for real-time collaborative editing."""

import json
import logging
import threading
import time
from collections import defaultdict

logger = logging.getLogger("webserver.sse")

# Global SSE state (thread-safe via _lock)
_lock = threading.Lock()
# "mountId:path" -> list of SSEConnectionHandler instances
_sse_clients: dict[str, list] = defaultdict(list)
_client_counter = 0


class SSEConnectionHandler:
    """Manages a single SSE connection lifecycle.
    
    Each instance represents one client connected via SSE.
    Stored in the global _sse_clients dict, keyed by "mountId:path".
    """
    
    def __init__(self, handler):
        """handler: the MountHTTPHandler instance managing this SSE connection."""
        global _client_counter
        self.handler = handler
        with _lock:
            _client_counter += 1
            self.client_id = f"client-{_client_counter}"
        self._file_key = None
        self._closed = False
    
    def attach(self, file_key: str, author_name: str, author_color: str):
        """Register this client as watching a specific file."""
        with _lock:
            if self._file_key and self._file_key in _sse_clients:
                # Remove from previous file
                _sse_clients[self._file_key] = [
                    c for c in _sse_clients[self._file_key] if c is not self
                ]
            self._file_key = file_key
            self.author_name = author_name
            self.author_color = author_color
            _sse_clients[file_key].append(self)
    
    def detach(self):
        """Remove this client from all file watchers."""
        with _lock:
            if self._file_key and self._file_key in _sse_clients:
                _sse_clients[self._file_key] = [
                    c for c in _sse_clients[self._file_key] if c is not self
                ]
            self._file_key = None
        self._closed = True
    
    def send_event(self, data: dict) -> bool:
        """Send an SSE event to this client. Returns False if connection closed."""
        if self._closed:
            return False
        try:
            payload = f"data: {json.dumps(data)}\n\n"
            self.handler.wfile.write(payload.encode("utf-8"))
            self.handler.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionResetError, OSError):
            self._closed = True
            return False
    
    @property
    def is_closed(self):
        return self._closed


def register_sse_client(handler, file_key: str, author_name: str, author_color: str) -> SSEConnectionHandler:
    """Create and register a new SSE connection."""
    conn = SSEConnectionHandler(handler)
    conn.attach(file_key, author_name, author_color)
    return conn


def sse_broadcast(file_key: str, exclude_id: str, event: dict):
    """Broadcast an event to all clients watching a file, except the sender.
    
    file_key: "mountId:path"
    exclude_id: client_id of the sender (not broadcast to self)
    event: dict to send as JSON
    """
    with _lock:
        clients = list(_sse_clients.get(file_key, []))
    
    dead = []
    for client in clients:
        if client.client_id == exclude_id:
            continue
        if not client.send_event(event):
            dead.append(client)
    
    # Clean up dead connections
    if dead:
        with _lock:
            for client in dead:
                client.detach()


def get_sse_client_count(file_key: str = None) -> int:
    """Get count of active SSE clients. For testing."""
    with _lock:
        if file_key:
            return len(_sse_clients.get(file_key, []))
        return sum(len(v) for v in _sse_clients.values())
```

- [ ] **Step 4: Add SSE route to `webserver/__init__.py`**

Add the SSE endpoint handler method to `MountHTTPHandler`. Insert after the existing search handler section (~line 1510) and before the generic `_handle_*` methods section.

In `webserver/__init__.py`, add these imports at the top:

```python
# SSE support for collaborative editing (lazy import to avoid circular)
_sse_clients = None  # Will be populated by sse_handler
```

Add the SSE handler method to `MountHTTPHandler`:

```python
def _handle_sse(self, qs: dict):
    """Handle SSE connection for real-time collaborative editing.
    
    GET /api/events?file=mountId:path
    """
    from nas_md.webserver.sse_handler import (
        register_sse_client,
        SSEConnectionHandler,
    )
    
    file_key = qs.get("file", [None])[0]
    if not file_key:
        return self._send_error("Missing file parameter", 400)
    
    # Parse identity from query params (sent by client)
    author_name = qs.get("name", ["Anonymous"])[0]
    author_color = qs.get("color", ["#3498db"])[0]
    
    # Verify session/cookie
    session_id = self._get_session_id()
    
    # Send SSE headers
    self.send_response(200)
    self.send_header("Content-Type", "text/event-stream")
    self.send_header("Cache-Control", "no-cache")
    self.send_header("Connection", "keep-alive")
    self.send_header("X-Accel-Buffering", "no")  # Disable nginx buffering
    self._flush_session_cookie()
    self.end_headers()
    
    # Register SSE connection
    conn = register_sse_client(self, file_key, author_name, author_color)
    
    # Send initial connected event
    conn.send_event({"type": "connected", "clientId": conn.client_id})
    
    # Keep connection alive with periodic pings
    try:
        while not conn.is_closed:
            time.sleep(30)
            conn.send_event({"type": "ping"})
    except Exception:
        pass
    finally:
        conn.detach()
```

Add the SSE route to the `do_GET` method routing table. Find where routes are dispatched (around the `_handle_*` pattern) and add:

```python
if path == "/api/events":
    return self._handle_sse(qs)
```

Add `sse_broadcast` call in `_handle_write_file`, after the file is saved and before the JSON response:

```python
# Broadcast changes to SSE clients (collaborative editing)
from nas_md.webserver.paragraph_diff import compute_diff
from nas_md.webserver.sse_handler import sse_broadcast

old_content = None
if os.path.isfile(abs_path):
    try:
        with open(abs_path, "rb") as f:
            old_content = f.read()
    except OSError:
        pass

# ... (existing write logic) ...

if old_content is not None:
    old_text = old_content.decode("utf-8", errors="replace")
    new_text = body.decode("utf-8", errors="replace")
    if old_text != new_text:
        changes = compute_diff(old_text, new_text)
        if changes:
            sse_broadcast(
                f"{mount_id}:{rel_path}",
                exclude_id=session_id,
                event={
                    "type": "remote_edit",
                    "authorId": session_id,
                    "authorName": "Anonymous",  # Will be enhanced with identity
                    "authorColor": "#3498db",
                    "mountId": mount_id,
                    "path": rel_path,
                    "changes": changes,
                },
            )
```

- [ ] **Step 5: Run all tests**

Run: `pytest tests/test_paragraph_diff.py tests/test_sse_handler.py -v`
Expected: all pass

Run full suite: `pytest tests/ -v` (excluding e2e)
Expected: all pass (no regressions)

- [ ] **Step 6: Commit**

```bash
git add nas_md/webserver/sse_handler.py nas_md/webserver/__init__.py tests/test_sse_handler.py
git commit -m "feat: add SSE connection management and broadcast for collaborative editing"
```

---

### Task 3: 前端身份管理

**Files:**
- Create: `web/identity.js`
- Modify: `web/index.html` (add script tag)

- [ ] **Step 1: Create `web/identity.js`**

```javascript
/**
 * identity.js - Anonymous identity management for collaborative editing
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'nasmd_identity';

  var ADJECTIVES = ['Swift', 'Calm', 'Bold', 'Keen', 'Wise', 'Bright', 'Silent', 'Wild'];
  var ANIMALS = ['Fox', 'Owl', 'Cat', 'Bear', 'Wolf', 'Raven', 'Crane', 'Deer'];
  var COLORS = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c', '#e67e22', '#34495e'];

  function pick(arr) {
    return arr[Math.floor(Math.random() * arr.length)];
  }

  function generateIdentity() {
    var name = pick(ADJECTIVES) + pick(ANIMALS) + Math.floor(Math.random() * 100);
    var color = pick(COLORS);
    var id = crypto.randomUUID();
    return { id: id, name: name, color: color };
  }

  function getIdentity() {
    try {
      var stored = localStorage.getItem(STORAGE_KEY);
      if (stored) return JSON.parse(stored);
    } catch (e) {
      // ignore
    }
    var id = generateIdentity();
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(id));
    } catch (e) {
      // ignore quota errors
    }
    return id;
  }

  window.nasmdIdentity = { get: getIdentity };
})();
```

- [ ] **Step 2: Add script tag to `index.html`**

Add before the `files.js` script tag:

```html
<script src="identity.js"></script>
```

- [ ] **Step 3: Verify no JS errors**

Open browser console on the app, check for errors. The `nasmdIdentity` global should be available.

- [ ] **Step 4: Commit**

```bash
git add web/identity.js web/index.html
git commit -m "feat: add anonymous identity management for collaborative editing"
```

---

### Task 4: 前端 SSE 客户端

**Files:**
- Create: `web/sse_client.js`
- Modify: `web/index.html` (add script tag)

- [ ] **Step 1: Create `web/sse_client.js`**

```javascript
/**
 * sse_client.js - SSE client for real-time collaborative editing
 */
(function () {
  'use strict';

  var _client = null;

  function SSEClient() {
    this.es = null;
    this.identity = window.nasmdIdentity ? window.nasmdIdentity.get() : { id: 'unknown', name: 'Anonymous', color: '#3498db' };
    this.handlers = {};
    this._currentFile = null;
  }

  SSEClient.prototype.connect = function (mountId, path) {
    this.disconnect();
    var fileKey = mountId + ':' + encodeURIComponent(path);
    this._currentFile = mountId + ':' + path;
    var url = '/api/events?file=' + fileKey +
              '&name=' + encodeURIComponent(this.identity.name) +
              '&color=' + encodeURIComponent(this.identity.color);
    this.es = new EventSource(url);

    this.es.onmessage = function (event) {
      try {
        var data = JSON.parse(event.data);
        if (this.handlers[data.type]) {
          this.handlers[data.type](data);
        }
      } catch (e) {
        // ignore malformed events
      }
    }.bind(this);

    this.es.onerror = function () {
      if (this.handlers['error']) {
        this.handlers['error']();
      }
    }.bind(this);
  };

  SSEClient.prototype.on = function (type, handler) {
    this.handlers[type] = handler;
  };

  SSEClient.prototype.disconnect = function () {
    if (this.es) {
      this.es.close();
      this.es = null;
    }
  };

  SSEClient.prototype.switchFile = function (mountId, path) {
    this.connect(mountId, path);
  };

  window.nasmdSSE = new SSEClient();
})();
```

- [ ] **Step 2: Add script tag to `index.html`**

Add after `identity.js`:

```html
<script src="sse_client.js"></script>
```

- [ ] **Step 3: Commit**

```bash
git add web/sse_client.js web/index.html
git commit -m "feat: add SSE client for real-time collaborative editing"
```

---

### Task 5: 前端同步层

**Files:**
- Create: `web/sync_layer.js`
- Modify: `web/index.html` (add script tag)
- Modify: `web/app.js` (integrate SSE, wire up remote edit handling)

- [ ] **Step 1: Create `web/sync_layer.js`**

```javascript
/**
 * sync_layer.js - Remote edit sync with edit-in-progress protection
 */
(function () {
  'use strict';

  var _lastInputTime = 0;
  var _cursorParaIdx = -1;
  var _pendingUpdates = [];
  var _highlightTimers = {};

  // === Edit state tracking ===

  function isActivelyEditing() {
    return Date.now() - _lastInputTime < 2000;
  }

  function getCursorParagraphIndex() {
    if (!window._vditor) return -1;
    var sel = window.getSelection();
    if (!sel.rangeCount) return -1;
    var range = sel.getRangeAt(0);
    var node = range.startContainer;
    var el = node.nodeType === 3 ? node.parentElement : node;

    var vditorEl = document.getElementById('vditor');
    if (!vditorEl) return -1;

    var paraSelectors = 'p, h1, h2, h3, h4, h5, h6, pre, blockquote, ul, ol, table, hr';
    var allParas = vditorEl.querySelectorAll(paraSelectors);
    for (var i = 0; i < allParas.length; i++) {
      if (allParas[i].contains(el) || allParas[i] === el) return i;
    }
    return -1;
  }

  // === Paragraph update application ===

  function applyRemoteChange(change, author) {
    if (!window._vditor) return;

    var currentContent = window._vditor.getValue();
    var paragraphs = currentContent.split('\n\n');

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

    var newContent = paragraphs.join('\n\n');

    // Save cursor/scroll position
    if (window.saveCursorScrollToStorage) {
      window.saveCursorScrollToStorage();
    }

    // Apply to editor
    window._vditor.setValue(newContent);
    window._originalContent = window._vditor.getValue();

    // Restore cursor after a tick for Vditor to finish rendering
    setTimeout(function () {
      if (window.restoreCursorScrollFromStorage) {
        window.restoreCursorScrollFromStorage();
      }
    }, 100);

    // Highlight the changed paragraph
    if (author) {
      highlightParagraph(change.paraIdx, author.name, author.color);
    }
  }

  // === Highlight ===

  function highlightParagraph(paraIdx, authorName, authorColor) {
    var vditorEl = document.getElementById('vditor');
    if (!vditorEl) return;

    var paraSelectors = 'p, h1, h2, h3, h4, h5, h6, pre, blockquote, ul, ol, table, hr';
    var allParas = vditorEl.querySelectorAll(paraSelectors);
    if (paraIdx >= allParas.length) return;

    var el = allParas[paraIdx];
    el.classList.add('paragraph-highlight');
    el.style.setProperty('--author-color', authorColor || '#3498db');
    el.style.setProperty('--highlight-color', (authorColor || '#3498db') + '26');

    // Add author label
    var label = document.createElement('span');
    label.className = 'author-label';
    label.textContent = '\u270E ' + (authorName || 'Anonymous');
    label.style.setProperty('--author-color', authorColor || '#3498db');
    el.style.position = 'relative';
    el.appendChild(label);

    // Auto-remove after 5 seconds
    var timerKey = paraIdx + '_' + Date.now();
    if (_highlightTimers[paraIdx]) {
      clearTimeout(_highlightTimers[paraIdx]);
    }
    _highlightTimers[paraIdx] = setTimeout(function () {
      el.classList.remove('paragraph-highlight');
      if (label.parentNode) label.parentNode.removeChild(label);
      delete _highlightTimers[paraIdx];
    }, 5000);
  }

  // === Pending update queue ===

  function applyPendingUpdates() {
    if (_pendingUpdates.length === 0) return;
    if (isActivelyEditing()) return;

    var pending = _pendingUpdates.slice();
    _pendingUpdates = [];
    for (var i = 0; i < pending.length; i++) {
      applyRemoteChange(pending[i], pending[i].author);
    }
  }

  // === Remote edit handler ===

  function handleRemoteEdit(data) {
    if (!data.changes || !Array.isArray(data.changes)) return;

    var author = { id: data.authorId, name: data.authorName, color: data.authorColor };

    for (var i = 0; i < data.changes.length; i++) {
      var change = data.changes[i];
      var isProtected = isActivelyEditing() && change.paraIdx === _cursorParaIdx;

      if (isProtected) {
        _pendingUpdates.push({
          type: change.type,
          paraIdx: change.paraIdx,
          content: change.content,
          author: author,
        });
      } else {
        applyRemoteChange(change, author);
      }
    }
  }

  // === Initialization ===

  function init() {
    // Hook into onEditorInput to track edit state
    if (window.onEditorInput) {
      var origOnEditorInput = window.onEditorInput;
      window.onEditorInput = function () {
        _lastInputTime = Date.now();
        _cursorParaIdx = getCursorParagraphIndex();
        if (origOnEditorInput) origOnEditorInput();
      };
    }

    // Check for pending updates when cursor moves
    setInterval(function () {
      var newParaIdx = getCursorParagraphIndex();
      if (newParaIdx !== _cursorParaIdx) {
        _cursorParaIdx = newParaIdx;
        applyPendingUpdates();
      }
    }, 500);

    // Connect SSE and register handler
    if (window.nasmdSSE) {
      window.nasmdSSE.on('remote_edit', handleRemoteEdit);
    }
  }

  // Expose
  window.nasmdSync = {
    init: init,
    handleRemoteEdit: handleRemoteEdit,
    applyPendingUpdates: applyPendingUpdates,
  };

  // Auto-init when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
```

- [ ] **Step 2: Add script tag to `index.html`**

Add after `sse_client.js`:

```html
<script src="sync_layer.js"></script>
```

- [ ] **Step 3: Wire up SSE connection in `app.js`**

In the `DOMContentLoaded` handler in `app.js`, after `startFilePoll()` and `startSidebarRefresh()` calls, add SSE connection startup:

```javascript
// Start SSE connection for collaborative editing
if (window.nasmdSSE && state.currentMountId && state.currentPath) {
    window.nasmdSSE.connect(state.currentMountId, state.currentPath);
}
```

Also, in the `openFile()` function, after the file is loaded and editor is initialized, add SSE file switch:

```javascript
// Switch SSE to the new file
if (window.nasmdSSE) {
    window.nasmdSSE.switchFile(mount.id, path);
}
```

- [ ] **Step 4: Commit**

```bash
git add web/sync_layer.js web/index.html web/app.js
git commit -m "feat: add sync layer with edit-in-progress protection and paragraph highlighting"
```

---

### Task 6: 高亮样式

**Files:**
- Create: `web/highlight.css`
- Modify: `web/index.html` (add link tag)

- [ ] **Step 1: Create `web/highlight.css`**

```css
/**
 * highlight.css - Paragraph highlight and author annotation for collaborative editing
 */

/* Paragraph highlight */
.paragraph-highlight {
  background-color: var(--highlight-color, rgba(52, 152, 219, 0.15));
  border-left: 3px solid var(--author-color, #3498db);
  border-radius: 2px;
  padding-left: 4px;
  margin-left: -7px;
  transition: background-color 5s ease-out, border-color 5s ease-out;
  position: relative;
}

/* Author annotation label */
.paragraph-highlight > .author-label {
  position: absolute;
  right: 8px;
  top: 2px;
  font-size: 11px;
  color: var(--author-color, #3498db);
  opacity: 0.8;
  font-weight: 500;
  transition: opacity 5s ease-out;
  pointer-events: none;
  background: var(--c-bg, #fff);
  padding: 1px 4px;
  border-radius: 2px;
}

/* Dark mode support */
.dark .paragraph-highlight > .author-label {
  background: var(--c-bg, #1a1a2e);
}
```

- [ ] **Step 2: Add link tag to `index.html`**

Add in the `<head>` after `app.css`:

```html
<link rel="stylesheet" href="highlight.css" />
```

- [ ] **Step 3: Commit**

```bash
git add web/highlight.css web/index.html
git commit -m "feat: add paragraph highlight and author annotation styles"
```

---

### Task 7: API 请求携带身份 header

**Files:**
- Modify: `web/files.js` (add identity headers to API requests)

- [ ] **Step 1: Modify `files.js`**

In the `API.request()` method, add identity headers:

```javascript
const API = {
  async request(path, options = {}) {
    const headers = { ...options.headers };
    if (options.body && typeof options.body === 'string') {
      headers['Content-Type'] = headers['Content-Type'] || 'text/plain; charset=utf-8';
    }
    if (window.state?.isAdmin) {
      headers['X-Admin'] = '1';
    }
    // Add identity headers for collaborative editing
    if (window.nasmdIdentity) {
      const identity = window.nasmdIdentity.get();
      if (identity) {
        headers['X-Client-Id'] = identity.id;
        headers['X-Client-Name'] = identity.name;
      }
    }
    const resp = await fetch(`${_apiBase}${path}`, { ...options, headers });
    return resp;
```

- [ ] **Step 2: Run full test suite**

Run: `pytest tests/ -v` (excluding e2e)
Expected: all pass

- [ ] **Step 3: Commit**

```bash
git add web/files.js
git commit -m "feat: add identity headers to API requests"
```

---

### Task 8: 端到端验证

**Files:**
- Test: `tests/e2e/collab.spec.js` (optional, if e2e testing is feasible)

- [ ] **Step 1: Manual verification**

1. Open nas-md in two different browsers (or incognito windows)
2. Navigate to the same MD file in both
3. In browser A, start editing a paragraph
4. In browser B, edit a different paragraph and save
5. Verify: browser A sees the change within ~1 second
6. Verify: the changed paragraph has a highlight with author label
7. Verify: the highlight fades after ~5 seconds
8. Verify: browser A's editing is not interrupted
9. In browser B, edit the same paragraph that A is editing and save
10. Verify: browser A's paragraph is NOT immediately updated (edit-in-progress protection)
11. Move browser A's cursor to a different paragraph
12. Verify: the pending update is now applied

- [ ] **Step 2: Run full test suite including e2e**

Run: `pytest tests/ -v`
Expected: all pass

- [ ] **Step 3: Commit any fixes**

---

### Task 9: 清理 + 文档

**Files:**
- Modify: `docs/architecture.md` (add collaborative editing to architecture)

- [ ] **Step 1: Update architecture doc**

Add a new section in `architecture.md` describing the collaborative editing subsystem:

- SSE handler for real-time event broadcast
- Paragraph diff engine for computing changes
- Frontend sync layer for applying changes with edit-in-progress protection
- Identity system for anonymous user identification

- [ ] **Step 2: Final commit**

```bash
git add docs/architecture.md
git commit -m "docs: add collaborative editing to architecture documentation"
```
