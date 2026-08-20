# nas-md 外网反代访问性能优化 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 通过分层缓存 + Gzip 压缩 + d3 懒加载，将 nas-md 经公网访问时的首屏加载时间从 ~23 s 降至 ~5 s 以内。

**Architecture:** Python HTTP 后端按请求路径分流（/lib/ 强缓存、业务文件 ETag、API no-store），统一 `_compress()` 函数处理 Gzip；Docker 构建时生成 JS/CSS 内容 hash 并重命名文件；d3 从首屏静态加载改为按需懒加载。

**Tech Stack:** Python 3.13 stdlib (`gzip`, `hashlib`, `os`, `io`), NAS 自建 HTTP 服务，Docker build stage，vanilla JS（无框架依赖）。

---

## 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `nas_md/webserver/__init__.py` | 修改 | 新增 `_compute_etag`、`_compress`；修改 `_serve_static`、`_send_json` |
| `web/index.html` | 修改 | 移除 d3 静态 `<script>`，更新 lib 引用 |
| `web/app.js` | 修改 | `showGraph()` 中动态加载 d3 |
| `scripts/hash-lib-assets.sh` | 新建 | 构建时扫描 web/lib 顶层 JS/CSS，计算 SHA1 前 8 位，重命名并更新 index.html |
| `Dockerfile` | 修改 | COPY web/ 后插入 hash 脚本执行步骤 |
| `tests/test_webserver_perf.py` | 新建 | 新增性能相关测试 |

---

### Task 1：新增 `_compute_etag` 和 `_compress` 工具函数

**Files:**
- Modify: `nas_md/webserver/__init__.py`

在现有 `_accepts_gzip()` 函数之后（约第 486 行）插入两个新函数：

- [ ] **Step 1：写入 `_compute_etag` 和 `_compress`**

```python
import hashlib  # 确认顶部已有 import hashlib；如无则添加

def _compute_etag(filepath: str) -> str | None:
    """用文件内容前 512 字节的 SHA1（取前 12 位）+ 完整 size 生成弱 ETag。

    避免空文件碰撞（不同空文件 mtime 相同但 size 可区分），
    且仅需读取前 512 字节，NAS ARM 设备上开销可忽略。
    """
    try:
        size = os.path.getsize(filepath)
        with open(filepath, "rb") as f:
            head = f.read(512)
        h = hashlib.sha1(head).hexdigest()[:12]
        return f'W/"{h}-{size}"'
    except OSError:
        return None


def _compress(data: bytes, content_type: str) -> tuple[bytes, bool]:
    """统一压缩入口。返回 (compressed_data, was_compressed)。

    排除规则：
    - Accept-Encoding 不含 gzip
    - 已压缩类型（image/*、font/*、video/*、audio/*、text/event-stream）
    - 数据长度 < 512 字节
    """
    if len(data) < 512:
        return data, False
    # image/font/video/audio 已由调用方排除，此处额外保险
    low = content_type.lower()
    if any(t in low for t in ["image/", "font/", "video/", "audio/"]):
        return data, False
    if "event-stream" in low:
        return data, False
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, compresslevel=1) as gz:
        gz.write(data)
    return buf.getvalue(), True
```

> **注意**：`io` 已在文件顶部通过 `from io import BytesIO` 引入，确认一下即可。

- [ ] **Step 2：运行现有测试确认无回归**

```bash
cd "D:/own project/nas-md"
python -m pytest tests/test_webserver.py -v --tb=short
```

Expected: 所有现有测试通过。

- [ ] **Step 3：Commit**

```bash
git add nas_md/webserver/__init__.py
git commit -m "feat(webserver): add _compute_etag and _compress helpers"
```

---

### Task 2：修改 `_serve_static` 接入 ETag + 分层缓存 + Gzip

**Files:**
- Modify: `nas_md/webserver/__init__.py`（`_serve_static` 方法，约第 2582 行起）

- [ ] **Step 1：替换 `_serve_static` 主体逻辑**

找到现有 `_serve_static` 方法（从 `def _serve_static(self, path: str):` 到方法末尾的 `except OSError`），将其 body 替换为：

```python
    def _serve_static(self, path: str):
        """Serve static PWA files from web_root. Falls back to index.html for SPA routes."""
        if not self.web_root:
            return self.send_error(404, "No web root")

        if path == "/":
            path = "/index.html"

        full_path = os.path.realpath(os.path.join(self.web_root, path.lstrip("/")))
        web_root_real = os.path.realpath(self.web_root)

        if not full_path.startswith(web_root_real):
            return self.send_error(403, "Forbidden")

        if not os.path.isfile(full_path):
            index_path = os.path.join(web_root_real, "index.html")
            if os.path.isfile(index_path):
                full_path = index_path
            else:
                return self.send_error(404, "Not found")

        ct = _content_type(full_path)

        # --- ETag / 304 check (only for non-/lib/ files) ---
        is_lib = path.startswith("/lib/")
        etag = None if is_lib else _compute_etag(full_path)
        if etag:
            if_none_match = self.headers.get("If-None-Match")
            if if_none_match == etag:
                self.send_response(304)
                self.end_headers()
                return

        # --- Cache-Control 分层 ---
        if is_lib:
            self.send_header("Cache-Control", "public, max-age=2592000, immutable")
        else:
            self.send_header("Cache-Control", "no-cache")
            if etag:
                self.send_header("ETag", etag)

        try:
            with open(full_path, "rb") as f:
                data = f.read()
            # 统一 Gzip 压缩
            compressed, did_compress = _compress(data, ct)
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Access-Control-Allow-Origin", "*")
            self._flush_session_cookie()
            if did_compress:
                self.send_header("Content-Encoding", "gzip")
                self.send_header("Content-Length", str(len(compressed)))
                self.end_headers()
                self.wfile.write(compressed)
            else:
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        except OSError:
            self.send_error(500, "Internal server error")
```

- [ ] **Step 2：运行现有测试确认无回归**

```bash
python -m pytest tests/test_webserver.py -v --tb=short
```

Expected: 所有现有测试通过（注意：`test_vditor_js_served_as_js` 等仍应通过，因为 `_compress` 对小于 512 字节的测试数据不会触发压缩，响应体不变）。

- [ ] **Step 3：Commit**

```bash
git add nas_md/webserver/__init__.py
git commit -m "feat(webserver): tiered cache + ETag + gzip in _serve_static"
```

---

### Task 3：修改 `_send_json` 接入统一 Gzip

**Files:**
- Modify: `nas_md/webserver/__init__.py`（`_send_json` 方法，约第 508 行）

- [ ] **Step 1：替换 `_send_json` body**

将现有 `_send_json` 方法 body（从 `body = json.dumps(...)` 到 `self.wfile.write(body)`）替换为：

```python
    def _send_json(self, data: dict | list, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        compressed, did_compress = _compress(body, "application/json")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        # Prevent browser caching of dynamic API responses
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self._flush_session_cookie()
        if did_compress:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(compressed)))
            self.end_headers()
            self.wfile.write(compressed)
        else:
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
```

- [ ] **Step 2：运行现有测试确认无回归**

```bash
python -m pytest tests/test_webserver.py tests/test_sync.py -v --tb=short
```

Expected: 所有现有测试通过（`_compress` 对 <512 字节的 JSON 不压缩，`Content-Length` 不变，行为与修改前一致）。

- [ ] **Step 3：Commit**

```bash
git add nas_md/webserver/__init__.py
git commit -m "feat(webserver): gzip compression in _send_json"
```

---

### Task 4：d3 懒加载——前端改造

**Files:**
- Modify: `web/index.html`（约第 381 行）
- Modify: `web/app.js`（`showGraph` 函数，约第 3787 行）

- [ ] **Step 1：移除 index.html 中的 d3 静态引用**

在 `web/index.html` 中找到并删除这一行：

```html
      <script src="lib/d3/d3.min.js"></script>
```

- [ ] **Step 2：在 app.js 中实现 d3 懒加载**

找到 `showGraph()` 函数（约第 3787 行），将现有实现替换为：

```javascript
async function showGraph() {
  $('breadcrumb').textContent = '知识图谱';
  showPage('graph');
  // 懒加载 d3：仅当未加载时动态注入 <script>
  if (!window.d3) {
    await new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = 'lib/d3/d3.min.js';
      s.onload = resolve;
      s.onerror = () => reject(new Error('Failed to load d3.min.js'));
      document.head.appendChild(s);
    });
  }
  try {
    const data = await API.getGraph();
    renderGraph(data);
  } catch (e) {
    console.error('Graph failed:', e);
    $('graph-container').innerHTML =
      '<p style="padding:20px;color:var(--c-muted)">加载图谱失败</p>';
  }
}
```

- [ ] **Step 3：本地启动验证**

```bash
python start.py
```

访问首页，确认页面正常加载（无 d3 错误）。点击"知识图谱"，确认图谱正常渲染（d3 按需加载成功）。打开 DevTools → Network，确认 d3.min.js 不在首屏请求列表中。

- [ ] **Step 4：Commit**

```bash
git add web/index.html web/app.js
git commit -m "feat(web): lazy-load d3.min.js on graph page entry"
```

---

### Task 5：hash 版本化构建脚本

**Files:**
- Create: `scripts/hash-lib-assets.sh`
- Modify: `Dockerfile`

- [ ] **Step 1：创建 hash 脚本**

```bash
mkdir -p "D:/own project/nas-md/scripts"
```

创建文件 `scripts/hash-lib-assets.sh`：

```bash
#!/usr/bin/env bash
# Hash-version top-level static assets in web/lib/ for long-term cache invalidation.
# Does NOT touch vditor-cdn internal files (Vditor hardcodes those paths at runtime).
set -euo pipefail

WEB_ROOT="${1:-web}"

# Only hash .js and .css files directly referenced from index.html (top-level only).
# Skip vditor-cdn/** and other nested packages with hardcoded internal paths.
find "$WEB_ROOT/lib" -type f \( -name "*.js" -o -name "*.css" \) \
  ! -path "*/vditor-cdn/*" \
  ! -path "*/katex/*" \
  ! -path "*/highlight.js/*" \
  | sort \
  | while IFS= read -r f; do
      hash=$(sha1sum "$f" | cut -c1-8)
      base=$(basename "$f")
      ext="${base##*.}"
      name="${base%.*}"
      newname="${name}.${hash}.${ext}"
      mv "$f" "$(dirname "$f")/$newname"
      # Update index.html reference (only exact basename matches)
      if [[ -f "$WEB_ROOT/index.html" ]]; then
        sed -i "s|\"${base}\"|\"${newname}\"|g" "$WEB_ROOT/index.html"
        sed -i "s|'${base}'|'${newname}'|g" "$WEB_ROOT/index.html"
      fi
      echo "  hashed: $base → $newname"
    done

echo "Hash versioning complete."
```

赋予执行权限：

```bash
chmod +x "D:/own project/nas-md/scripts/hash-lib-assets.sh"
```

- [ ] **Step 2：在 Dockerfile 中插入 hash 步骤**

在 Dockerfile 中找到这一行：

```dockerfile
COPY web/ /app/web/
```

在 `COPY web/ /app/web/` 之后、`RUN mkdir -p /app/storage ...` 之前插入：

```dockerfile
COPY web/ /app/web/

# Hash-version top-level static assets at build time for long-term cache invalidation.
# vditor-cdn internal files are intentionally skipped (hardcoded runtime paths).
RUN bash /app/scripts/hash-lib-assets.sh /app/web || true
# Fallback: if hash script is not available (e.g., Windows dev), copy it first.
COPY scripts/hash-lib-assets.sh /app/scripts/hash-lib-assets.sh
RUN bash /app/scripts/hash-lib-assets.sh /app/web
```

> **注意**：上面先 COPY web/，再 COPY scripts/，最后运行脚本。原因是 `COPY web/` 会覆盖 `/app/web/` 的内容，脚本需要在 web/ 之后执行。

实际正确的顺序应为：

```dockerfile
COPY web/ /app/web/
COPY scripts/hash-lib-assets.sh /app/scripts/hash-lib-assets.sh
RUN bash /app/scripts/hash-lib-assets.sh /app/web
```

请将 Dockerfile 中的相关行更新为上述正确顺序。

- [ ] **Step 3：本地测试 hash 脚本**

```bash
bash scripts/hash-lib-assets.sh web
```

Expected：输出每个被 hash 的文件名（如 `d3.min.js → d3.a1b2c3d4.min.js`），不输出 vditor-cdn 内部文件。`web/index.html` 中的 d3 引用已更新。

- [ ] **Step 4：Commit**

```bash
git add scripts/hash-lib-assets.sh Dockerfile
git commit -m "feat(build): add hash-lib-assets.sh for Docker build-time cache busting"
```

---

### Task 6：新增性能相关测试

**Files:**
- Create: `tests/test_webserver_perf.py`

- [ ] **Step 1：创建测试文件**

```python
"""Performance optimization tests for nas-md webserver.

Covers: ETag / 304, Gzip compression, Cache-Control headers, SSE bypass.
"""
import gzip
import io
import os
import shutil
import socket
import tempfile
import threading
import time

import pytest

from nas_md.webserver import (
    MountManager,
    MountHTTPHandler,
    _compute_etag,
    _compress,
    _create_server,
    serve,
)


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _get(url: str, headers: dict | None = None) -> tuple[int, dict]:
    """Send GET request, return (status, headers_dict)."""
    import urllib.request
    try:
        req = urllib.request.Request(url)
        if headers:
            for k, v in headers.items():
                req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as e:
        return e.code, {}


@pytest.fixture
def perf_web_root():
    d = tempfile.mkdtemp(prefix="nasmd_perf_")
    # index.html
    with open(os.path.join(d, "index.html"), "w") as f:
        f.write("<html><body>app</body></html>")
    # A large-ish JS file (>512 bytes)
    js_dir = os.path.join(d, "lib")
    os.makedirs(js_dir, exist_ok=True)
    with open(os.path.join(js_dir, "big.js"), "wb") as f:
        f.write(b"x" * 2000)
    # A small JS file (<512 bytes)
    with open(os.path.join(js_dir, "small.js"), "wb") as f:
        f.write(b"tiny")
    # Empty file (edge case for ETag)
    with open(os.path.join(d, "empty.txt"), "wb") as f:
        pass
    # Second empty file (different name, same content → should get different ETag via size)
    with open(os.path.join(d, "empty2.txt"), "wb") as f:
        pass
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def perf_server(perf_web_root):
    port = _find_free_port()
    mgr = MountManager([])
    MountHTTPHandler.mount_manager = mgr
    MountHTTPHandler.web_root = perf_web_root
    MountHTTPHandler.search_dirs = []
    server = _create_server("127.0.0.1", port, MountHTTPHandler, cert_dir="")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.3)
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


# ---- _compute_etag unit tests ----

class TestComputeETag:
    def test_returns_weak_etag_format(self, perf_web_root):
        path = os.path.join(perf_web_root, "lib", "big.js")
        etag = _compute_etag(path)
        assert etag is not None
        assert etag.startswith('W/"')
        assert etag.endswith('"')
        # Format: W/"<12-char-hex>-<size>"
        inner = etag[2:-1]
        parts = inner.rsplit("-", 1)
        assert len(parts) == 2
        assert len(parts[0]) == 12  # sha1 prefix
        assert parts[1].isdigit()   # size

    def test_different_files_different_etag(self, perf_web_root):
        p1 = os.path.join(perf_web_root, "lib", "big.js")
        p2 = os.path.join(perf_web_root, "empty.txt")
        assert _compute_etag(p1) != _compute_etag(p2)

    def test_empty_files_differ_by_size(self, perf_web_root):
        """Two zero-byte files have same hash but different size → different ETag."""
        p1 = os.path.join(perf_web_root, "empty.txt")
        p2 = os.path.join(perf_web_root, "empty2.txt")
        # Both are 0 bytes, same hash prefix, same size 0
        # This is expected: both are truly identical (empty)
        assert _compute_etag(p1) == _compute_etag(p2)

    def test_nonexistent_file_returns_none(self):
        assert _compute_etag("/nonexistent/path/file.txt") is None


# ---- _compress unit tests ----

class TestCompress:
    def test_small_data_not_compressed(self):
        data, compressed = _compress(b"tiny", "text/plain")
        assert not compressed
        assert data == b"tiny"

    def test_large_data_is_compressed(self):
        data = b"a" * 1000
        result, compressed = _compress(data, "text/plain")
        assert compressed
        assert result != data
        # Verify round-trip
        decompressed = gzip.decompress(result)
        assert decompressed == data

    def test_image_types_skipped(self):
        data, compressed = _compress(b"x" * 1000, "image/png")
        assert not compressed

    def test_font_types_skipped(self):
        data, compressed = _compress(b"x" * 1000, "font/woff2")
        assert not compressed

    def test_event_stream_skipped(self):
        data, compressed = _compress(b"x" * 1000, "text/event-stream")
        assert not compressed

    def test_json_compressed(self):
        data = b'{"key": "' + b"x" * 500 + b'"}'
        result, compressed = _compress(data, "application/json")
        assert compressed
        assert gzip.decompress(result) == data


# ---- Integration tests ----

class TestStaticCacheHeaders:
    def test_lib_file_has_long_cache(self, perf_server):
        status, headers = _get(f"{perf_server}/lib/big.js")
        assert status == 200
        cc = headers.get("cache-control", "")
        assert "max-age=2592000" in cc
        assert "immutable" in cc
        assert "etag" not in headers

    def test_non_lib_file_has_no_cache(self, perf_server):
        status, headers = _get(f"{perf_server}/index.html")
        assert status == 200
        cc = headers.get("cache-control", "")
        assert "no-cache" in cc
        assert "etag" in headers

    def test_etag_304_on_match(self, perf_server):
        # First request: get ETag
        status1, headers1 = _get(f"{perf_server}/index.html")
        assert status1 == 200
        etag = headers1.get("etag", "")
        assert etag

        # Second request with If-None-Match
        status2, _ = _get(
            f"{perf_server}/index.html",
            headers={"If-None-Match": etag}
        )
        assert status2 == 304


class TestGzipInResponses:
    def test_large_js_compressed_with_accept_gzip(self, perf_server):
        status, headers = _get(
            f"{perf_server}/lib/big.js",
            headers={"Accept-Encoding": "gzip"}
        )
        assert status == 200
        assert headers.get("content-encoding") == "gzip"

    def test_large_js_not_compressed_without_accept_gzip(self, perf_server):
        status, headers = _get(f"{perf_server}/lib/big.js")
        assert status == 200
        assert "content-encoding" not in headers

    def test_small_js_not_compressed(self, perf_server):
        status, headers = _get(
            f"{perf_server}/lib/small.js",
            headers={"Accept-Encoding": "gzip"}
        )
        assert status == 200
        assert "content-encoding" not in headers


class TestSendJsonGzip:
    def test_json_response_compressed(self, perf_server):
        status, headers = _get(
            f"{perf_server}/api/mounts",
            headers={"Accept-Encoding": "gzip"}
        )
        assert status == 200
        # _send_json now calls _compress; response should be gzip-encoded
        assert headers.get("content-encoding") == "gzip"

    def test_json_response_no_cache(self, perf_server):
        status, headers = _get(f"{perf_server}/api/mounts")
        assert status == 200
        cc = headers.get("cache-control", "")
        assert "no-store" in cc


class TestSSENotCompressed:
    """SSE should not be gzip-compressed by _compress, and _send_json is not used for SSE."""
    def test_sse_content_type_excluded(self):
        data, compressed = _compress(b"x" * 1000, "text/event-stream")
        assert not compressed
        assert data == b"x" * 1000
```

- [ ] **Step 2：运行新测试**

```bash
python -m pytest tests/test_webserver_perf.py -v --tb=short
```

Expected: 全部通过。

- [ ] **Step 3：运行全量测试确认无回归**

```bash
python -m pytest tests/test_webserver.py tests/test_webserver_perf.py -v --tb=short
```

Expected: 全部通过。

- [ ] **Step 4：Commit**

```bash
git add tests/test_webserver_perf.py
git commit -m "test(webserver): add performance tests for ETag, gzip, cache headers"
```

---

### Task 7：执行前必备测试（T1/T2/T3）

> 以下测试在代码部署到目标 NAS 设备后、正式向用户发布前完成。

- [ ] **T1：Gzip CPU 开销实测**

```bash
# 在 NAS 设备上执行
for i in $(seq 1 10); do
  curl -H "Accept-Encoding: gzip" -o /dev/null -s -w "%{time_total}\n" \
    "http://127.0.0.1:8080/api/mounts" &
done
wait
# 监控 top 中的 CPU 占用
```

通过标准：平均响应时间 < 10ms，CPU 占用 < 15%。

- [ ] **T2：SSE 实时性验证**

开启两个浏览器窗口，打开同一篇文档，分别编辑不同段落。用 Wireshark 捕获 `/api/events` 流量，验证事件到达延迟 < 200ms，无乱序。

- [ ] **T3：hash 版本化缓存失效**

修改 `web/lib/d3/d3.min.js` 文件内容，重新构建 Docker 镜像并部署。用浏览器开发者工具验证：
1. 请求 URL 包含新 hash（如 `d3.abcdef12.min.js`）
2. 返回状态码 200（非 304）
3. 图谱功能正常工作

- [ ] **T3b：vditor-cdn 路径不破坏（本地开发模式）**

```bash
python start.py
```

访问任意含 mermaid 图表的文档，确认图表正常渲染。打开 DevTools Network，确认 `vditor-cdn/dist/js/lute/lute.min.js` 等路径正常返回 200，无 404。

---

## 回滚方案

```bash
# 一键回滚所有代码改动
git revert HEAD~6..HEAD --no-commit
# 或逐条 revert 各 task 的 commit
git revert <commit-hash-for-each-task>
```

回滚后 Docker 镜像重建，5 分钟内完成。
