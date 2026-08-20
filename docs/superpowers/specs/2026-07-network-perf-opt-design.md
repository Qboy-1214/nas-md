# nas-md 外网反代访问性能优化设计

**日期**：2026-07-xx
**背景**：nas-md 通过 FRP 内网穿透暴露到公网后，静态资源每次全量明文传输（6.7 MB），首屏加载约 23 秒。方案经 Grill Session 逐条拷问后确认，详见 `docs/network-performance-optimization-plan.md`。

---

## 一、变更范围

| 模块 | 变更类型 | 影响面 |
|------|---------|--------|
| `nas_md/webserver/__init__.py` | 修改 + 新增函数 | HTTP 响应头、压缩、ETag |
| `web/index.html` | 移除 d3 script 标签 | 首屏资源减少 280 KB |
| `web/app.js` | 修改 `showGraph()` | d3 按需加载 |
| `web/lib/` 下的 .js/.css 文件 | 构建时重命名为 hash 版本 | 文件名变化 |
| `Dockerfile` | 新增 hash 重命名步骤 | 镜像构建流程 |

**不变更**：所有协同逻辑、SSE 推送、编辑器生命周期、文件读写、版本控制、外部修改检测。

---

## 二、架构分层

```
浏览器 → Python HTTP 处理器 → 四层分流
         ├── Tier 1: /lib/** → ETag(前512B SHA1+size) + Cache-Control: public, max-age=30d, immutable
         ├── Tier 2: 业务文件 → ETag(前512B SHA1+size) + Cache-Control: no-cache
         ├── Tier 3: /api/** JSON → Cache-Control: no-store + Gzip压缩(≥512B, level=1)
         └── Tier 4: /api/events → SSE流, 后端不压缩(event-stream类型跳过), 反代proxy_buffering off
```

---

## 三、具体变更设计

### 3.1 统一压缩函数 `_compress(data, content_type, handler)`

替换现有死代码 `_GzipWriter` 调用模式，改为集中式函数。

**参数**：
- `data: bytes` — 原始响应体
- `content_type: str` — MIME 类型
- `handler: MountHTTPHandler` — 请求处理器实例（用于获取 Accept-Encoding）

**返回值**：`(compressed_data: bytes, did_compress: bool)`

**排除逻辑**（任一满足则不压缩）：
1. `Accept-Encoding` 不含 `gzip`
2. `content_type` 包含 `image/`、`font/`、`video/`、`audio/`（已压缩媒体类型）
3. `content_type` 包含 `event-stream`（SSE 路径由 SSE handler 直接写 wfile，不经此函数；此处作为安全兜底）
4. `len(data) < 512`（小响应体压缩开销 > 收益）

**压缩配置**：
- 算法：`gzip`（Python 标准库）
- 压缩级别：`1`（Fastest，NAS ARM 设备 CPU 友好）
- `mtime=0`（避免将文件时间泄露到 Content-Encoding 元数据）

**调用方式**：
```python
compressed, did_compress = _compress(data, ct, self)
if did_compress:
    self.send_header('Content-Encoding', 'gzip')
    self.send_header('Content-Length', str(len(compressed)))
    self.wfile.write(compressed)
else:
    self.send_header('Content-Length', str(len(data)))
    self.wfile.write(data)
```

---

### 3.2 ETag 计算函数 `_compute_etag(filepath)`

**实现**：
```python
import hashlib

def _compute_etag(filepath: str) -> str | None:
    """用文件内容前512字节的SHA1摘要 + 完整文件大小生成 weak ETag。
    格式: W/"<12位hex>-<size>"
    例: W/"a1b2c3d4e5f6-3276800"
    """
    try:
        size = os.path.getsize(filepath)
        with open(filepath, 'rb') as f:
            head = f.read(512)
        h = hashlib.sha1(head).hexdigest()[:12]
        return f'W/"{h}-{size}"'
    except OSError:
        return None
```

**为什么不使用全文 SHA1**：NAS ARM 设备在每次请求时都读完整文件（最坏情况 3.8 MB）做 SHA1，高并发下累积 CPU 开销不可接受。前 512 字节对于 JavaScript/CSS 等文本文件已足够区分不同版本（包含版权头、版本号、构建时间戳等元信息）。空文件场景（size=0）也通过 size 字段完全区分。

**为什么不用 mtime**：ext4 默认 mtime 精度为 1 秒，同一秒内多次修改会共享相同 ETag，导致客户端拿到过期缓存。内容 hash 彻底消除此风险。

---

### 3.3 `_serve_static` 重写

**入口不变**，以下行为变更：

1. **路径分流**：
   - `path.startswith('/lib/')` → `Cache-Control: public, max-age=2592000, immutable`（30 天强缓存）
   - 其他业务文件 → `Cache-Control: no-cache` + `ETag` header

2. **304 短路**：
   - 计算 ETag
   - 若请求头 `If-None-Match` 匹配 → 返回 304 + `end_headers()` → 立即 return

3. **统一压缩**：
   - 读取文件内容后调用 `_compress(data, ct, self)`
   - 根据 `did_compress` 结果设置 `Content-Encoding` 和更新后的 `Content-Length`

**不变更**：SPA fallback（非文件路径回退 index.html）、路径安全检查、Content-Type 推断。

---

### 3.4 `_send_json` 修改

**变化**：在原有发送逻辑后接入 `_compress()`，替换原来的 `self.wfile.write(body)`。

**不变更**：
- `Cache-Control: no-cache, no-store, must-revalidate` 保持不变
- `Access-Control-Allow-Origin: *` 保持不变
- 所有 JSON 接口语义不变

**注意**：SSE 长连接（`/api/events`）由 `sse_handler.py` 直接操作 `self.wfile.write()`，不经 `_send_json`，不受本次修改影响。

---

### 3.5 d3.min.js 懒加载

**当前状态**：`index.html` 第 381 行 `<script src="lib/d3/d3.min.js">` 首屏加载。`d3` 仅在 `app.js:showGraph()` 中使用时调用。

**变更**：
1. `index.html`：移除 `<script src="lib/d3/d3.min.js">` 这一行
2. `app.js` `showGraph()` 函数开头插入懒加载逻辑：

```javascript
async function showGraph() {
  $('breadcrumb').textContent = '知识图谱';
  showPage('graph');
  if (!window.d3) {
    await new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = 'lib/d3/d3.min.js';
      s.onload = resolve;
      s.onerror = () => reject(new Error('d3 load failed'));
      document.head.appendChild(s);
    });
  }
  try {
    const data = await API.getGraph();
    renderGraph(data);
  } catch (e) {
    console.error('Graph failed:', e);
    $('graph-container').innerHTML = '<p>加载图谱失败</p>';
  }
}
```

**回退保障**：若 d3 加载失败（网络异常），`Promise.reject` 会中断后续执行，catch 块显示错误提示，不影响其他功能。

---

### 3.6 Dockerfile 构建时 hash 版本化

**目的**：`/lib/**` 文件设置 30 天 `immutable` 缓存，必须配合文件名 hash 才能确保内容更新时浏览器获取新版本。

**实现**：在 Dockerfile 中，`COPY web/ /app/web/` 之后增加一步 shell 脚本：

```dockerfile
# 对 web/lib/ 下所有 .js/.css 文件计算 SHA1 前8位，重命名并更新 index.html 引用
RUN find /app/web/lib -type f \( -name "*.js" -o -name "*.css" \) \
    | sort \
    | while read f; do \
        hash=$(sha1sum "$f" | cut -c1-8); \
        base=$(basename "$f"); \
        ext="${base##*.}"; \
        name="${base%.*}"; \
        newname="${name}.${hash}.${ext}"; \
        if [ "$base" != "$newname" ]; then \
            mv "$f" "$(dirname "$f")/$newname"; \
            sed -i "s|${base}|${newname}|g" /app/web/index.html; \
            echo "Hashed: $base → $newname"; \
        fi; \
    done
```

**注意事项**：
- `sort` 保证文件处理顺序 deterministic，构建可复现
- `if [ "$base" != "$newname" ]` 避免 hash 恰好等于原名时的无效操作（概率极低，但防御性编程）
- `sed` 只更新 `index.html` 中匹配的引用，不影响其他文件
- 构建时 `sha1sum` 运行一次，不增加运行时开销

---

## 四、不变更清单（安全边界）

| 机制 | 理由 |
|------|------|
| `/api/events` SSE 流 | 不经 `_send_json`，由 SSE handler 独立管理，不受 gzip 影响 |
| `/api/mounts/{id}/file` 文件读取 | 保持 `no-store`，仅增加 gzip 压缩，不影响元数据实时性 |
| 编辑器 `destroy()` + `initEditor()` 生命周期 | 完全不变 |
| 多端协同段落 diff 逻辑 | 完全不变 |
| 外部修改热重载轮询逻辑 | 完全不变 |
| 撤销历史栈隔离 | 完全不变 |
| 本地挂载 Blob URL 逻辑 | 完全不变 |

---

## 五、验证计划

### 5.1 执行前必备测试（T1-T3）

| 编号 | 测试项 | 方法 | 通过标准 |
|------|--------|------|---------|
| T1 | Gzip CPU 开销 | cURL 在目标 NAS 上发起并发请求，测压缩耗时和 CPU 占用 | 13.7 KB JSON 压缩 < 10ms；10 并发 CPU < 15% |
| T2 | SSE 实时性 | 开启 gzip 后模拟双端协同编辑，抓包验证事件延迟 | 延迟 < 200ms，无积压或乱序 |
| T3 | hash 缓存失效 | 修改 lib 文件内容重新构建镜像，浏览器开发者工具验证 | URL 含新 hash，返回 200（非 304） |

任一测试不通过，禁止发布。

### 5.2 回归测试矩阵

| 场景 | 验证方法 | 通过标准 |
|------|---------|---------|
| 首屏静态资源缓存 | Network 面板检查 `/lib/**` 刷新后状态 | `(disk cache)` 或 `(memory cache)` |
| 业务代码更新 | 修改 `app.css`，刷新页面 | 返回 200 + 最新内容 |
| tree-recursive 压缩 | 请求 `/api/mounts/{id}/tree-recursive` | 响应头含 `Content-Encoding: gzip`，体积下降 > 70% |
| 多端协同 | 两窗口同编辑一篇文档 | 段落合并正常，无冲突 |
| SSE 事件到达 | 监控 `/api/events` 连接 | 事件实时到达，无卡顿 |
| 外部修改检测 | VSCode 修改笔记后观察前端 | 弹出外部修改通知 |
| 光标恢复 | 长文档中部滚动后刷新 | 自动定位回原标题与光标 |
| 撤销隔离 | 文件 A 输入后切换到 B 按 Ctrl+Z | 不撤销 A 的内容 |
| 本地图片 | 挂载本地文件夹插入相对路径图片 | 图片显示正常，Markdown 导出完整 |

---

## 六、预期收益

| 指标 | 优化前 | 优化后（预估） |
|------|--------|---------------|
| 首屏下载量 | ~6.7 MB（明文） | ~4.5 MB（d3 懒加载）→ 压缩后 ~1.5 MB |
| 冷启动加载时间 | ~23 秒（2.36 Mbps） | ~5~8 秒（首次）/ ~2 秒（30 天内重复访问） |
| 业务代码刷新 | 全量下载 ~161 KB | 304 响应（0 字节下载）|
| 目录树传输 | ~13.7 KB 明文 | ~3 KB gzip（约 78% 压缩率）|

---

## 七、待实现

- [ ] 实现 `_compress()` 统一压缩函数
- [ ] 实现 `_compute_etag()` 函数
- [ ] 重写 `_serve_static()` 接入 ETag 分流和压缩
- [ ] 修改 `_send_json()` 接入压缩
- [ ] `index.html` 移除 d3 script 标签
- [ ] `app.js` `showGraph()` 接入懒加载
- [ ] `Dockerfile` 添加 hash 版本化构建步骤
- [ ] 执行 T1/T2/T3 验证
- [ ] 执行回归测试矩阵
