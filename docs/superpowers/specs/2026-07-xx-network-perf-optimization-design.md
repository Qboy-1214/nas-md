# nas-md 外网反代访问性能优化 — 设计规格

> 基于 `docs/network-performance-optimization-plan.md` 的 Grill Session 拷问后产出。

## 1. 目标与背景

**痛点**：NAS 部署经 FRP 内网穿透暴露公网后，首屏加载约 6.7 MB 明文资源，带宽 2.36 Mbps 下耗时 ~23 秒，用户感知"侧边栏迟缓、切换文件白屏"。

**基线数据**（FRP 穿透环境实测）：

| 资源 | 大小 | 耗时 |
|------|------|------|
| lute.min.js | 3.1 MB | 10.59 s |
| mermaid.min.js | 3.8 MB | 8.51 s |
| d3.min.js | 280 KB | 207 ms |
| tree-recursive (×5次) | 1.8~13.7 KB | 401~676 ms |

**优化目标**：通过分层缓存 + Gzip 压缩 + d3 懒加载，将首屏加载时间从 ~23 s 降至 ~5 s 以内（估算值，待 T1/T2/T3 实测确认）。

---

## 2. 架构分层

```
浏览器 ──→ NAS Python HTTP 服务 ──→ 文件系统
              │
              ├─ /lib/**          → Tier 1：强缓存 30 天（hash 版本化文件名）
              ├─ 业务 .js/.css     → Tier 2：ETag 协商缓存（no-cache + SHA1 ETag）
              ├─ /api/**          → Tier 3：no-store + Gzip（≥512B）
              └─ /api/events      → Tier 4：chunked 流式，反代层 proxy_buffering off
```

**约束红线**：

| 机制 | 约束 |
|------|------|
| 多端协同（SSE） | 后端代码允许 Gzip；反代层强制 `proxy_buffering off` |
| 文件读写 API | 保持 `Cache-Control: no-cache, no-store` |
| 编辑器生命周期 | `destroy()` + `initEditor()` 架构不变 |
| 外部修改检测 | `/api/mounts/{id}/file` 保持 no-store |

---

## 3. 变更模块

### 3.1 新增：统一压缩函数 `_compress()`

**位置**：`nas_md/webserver/__init__.py`

**职责**：接收原始 bytes + content_type + handler，返回 `(compressed_bytes, was_compressed)`。

**逻辑**：
1. `handler` 不为 None 且客户端 `Accept-Encoding` 不含 `gzip` → 原样返回
2. content_type 含 `image/`、`font/`、`video/`、`audio/`、`event-stream` → 原样返回
3. 数据长度 < 512 字节 → 原样返回
4. 其他情况 → `gzip.GzipFile(fileobj, mode='wb', mtime=0, compresslevel=1)` 压缩

**选择理由**：对比复用现有 `_wrap_gzip`（分散调用点易遗漏 flush），统一函数在调用处一次性处理，逻辑透明、无内存泄漏风险。

### 3.2 新增：ETag 计算函数 `_compute_etag()`

**位置**：`nas_md/webserver/__init__.py`

**公式**：`W/"<sha1_head_512b_前12位>-<full_size>"`

**选择理由**：空文件不会碰撞（内容为空但 size 不同），NAS ARM 设备上读取前 512 字节开销可忽略（远小于全文 SHA1）。

### 3.3 修改：`_serve_static(path)`

**改动**：
1. 计算 ETag，检查 `If-None-Match`，匹配则返回 304
2. `/lib/**` 路径 → `Cache-Control: public, max-age=2592000, immutable`（无 ETag）
3. 其他路径 → `Cache-Control: no-cache` + `ETag` 头
4. 读文件后调用 `_compress(data, ct)`，按需写入压缩数据

### 3.4 修改：`_send_json(data, status)`

**改动**：
1. 生成 body 后调用 `_compress(body, 'application/json')`
2. 按需写入 `Content-Encoding: gzip` 和更新后的 `Content-Length`

**注意**：SSE 事件通过 `sse_handler.py` 直接写 `self.wfile`，不经此函数，不受影响。

### 3.5 新增：d3.min.js 懒加载

**文件**：`web/index.html`、`web/app.js`

**改动**：
1. 从 `<head>` 移除 `<script src="lib/d3/d3.min.js">`
2. `showGraph()` 中动态插入 `<script>` 标签，`d3` 加载完成后再执行 `renderGraph()`
3. 使用 `window.d3` 全局变量检测避免重复加载

**收益**：首屏减少 280 KB，预计节省 1~2 秒加载时间。

### 3.6 新增：构建时 hash 版本化脚本

**文件**：`scripts/hash-lib-assets.sh`（或等效 Dockerfile RUN 步骤）

**逻辑**：
```bash
find web/lib -type f \( -name "*.js" -o -name "*.css" \) | while read f; do
    hash=$(sha1sum "$f" | cut -c1-8)
    base=$(basename "$f")
    ext="${base##*.}"
    name="${base%.*}"
    newname="${name}.${hash}.${ext}"
    mv "$f" "$(dirname "$f")/$newname"
    sed -i "s|${base}|${newname}|g" web/index.html
done
```

**注意**：`sed` 命令仅替换 `web/index.html` 中的顶层引用（不触及 `vditor-cdn` 内部路径）。

**选择理由**：Docker 部署环境下构建时处理最合适，镜像内文件自洽，零运行时开销。

**⚠️ hash 版本化范围限制（已确认）**：

`vditor/index.min.js` 在运行时通过路径拼接动态加载 `lib/vditor-cdn/dist/js/lute/lute.min.js`、`lib/vditor-cdn/dist/js/mermaid/mermaid.min.js` 等子资源。**这些内部路径是 Vditor 硬编码的，不能重命名**。因此 hash 版本化仅覆盖以下直接引用的顶层文件：

```
web/lib/d3/d3.min.js              → d3.<hash>.min.js
web/lib/vditor/index.min.js        → index.<hash>.min.js
web/lib/vditor/index.css           → index.<hash>.css
web/lib/fonts/inter.css            → inter.<hash>.css
web/lib/alpine.min.js              → alpine.<hash>.min.js
web/lib/htmx.min.js                → htmx.<hash>.min.js
web/lib/html2pdf/html2pdf.bundle.min.js → html2pdf.<hash>.bundle.min.js
```

**vditor-cdn 内部文件的缓存处理**：`lib/vditor-cdn/dist/js/` 不参与 hash 重命名（避免 Vditor 运行时 404），改用 Tier 1 的 `Cache-Control: public, max-age=2592000, immutable` 强缓存即可——文件名不变不影响缓存生效，且 30 天内内容不变时浏览器直接从磁盘命中。

**本地开发模式兼容性**：Dockerfile 中的 hash 重命名脚本仅在构建镜像时执行，`web/` 目录的原始文件不受影响。开发者通过 `python start.py` 本地运行时代码时，看到的是原文件名，ETag 协商缓存正常工作，与生产 Docker 镜像行为无缝互补。

---

## 4. 反向代理配置

### Nginx（强制要求）

```nginx
# SSE 通道：禁用缓冲，保障实时性
location /api/events {
    proxy_pass http://127.0.0.1:8080;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_buffering off;       # 关键：关闭缓冲
    proxy_cache off;
    proxy_read_timeout 86400s;
}

# 普通请求
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

### Caddy

```caddy
reverse_proxy localhost:8080

gzip
gzip_min 512
```

> Caddy 默认关闭反代缓冲，但仍需确认 `gzip` 不影响 SSE 实时性（T2 验证）。

---

## 5. 验证计划

### 5.1 发布前强制测试（T1/T2/T3）

| 编号 | 测试项 | 方法 | 通过标准 | 降级方案 |
|------|--------|------|---------|---------|
| T1 | Gzip CPU 开销 | cURL 10 并发压测 | 13.7KB JSON 压缩 <10ms，CPU <15% | 提高体积阈值至 1KB 或跳过 Gzip |
| T2 | SSE 实时性 | 双端协同 + Wireshark | 事件延迟 <200ms，无乱序 | 降级为压缩级别 1 |
| T3 | hash 版本化 | 修改 lib 文件后重新部署 | 浏览器获取新 hash URL，返回 200 | 回滚 Docker 镜像 |
| T3b | vditor-cdn 路径不破坏 | 本地运行 `python start.py` 访问图谱页 | lute.min.js、mermaid.min.js 正常加载，无 404 | — |

### 5.2 功能回归矩阵

| 场景 | 验证方法 | 通过标准 |
|------|---------|---------|
| 多端协同编辑 | 双窗口同文档编辑不同段落 | 段落合并正常，无数据丢失 |
| SSE 长连接 | 监控 `/api/events` 连接状态 | 无断开，事件实时到达 |
| 外部修改检测 | VSCode 修改笔记后观察前端 | 及时弹出外部修改提示 |
| 光标恢复 | 长文档中部定位后刷新 | 自动定位回原标题与视口 |
| 撤销隔离 | 文件A输入→切文件B→Ctrl+Z | 不撤销文件A的内容 |
| d3 懒加载 | 不进入图谱页，检查 Network | d3.min.js 不在首屏请求列表 |
| ETag 边界 | 新建空 Markdown，刷新页面 | 不返回 304，内容正常显示 |

---

## 6. 回滚方案

```bash
# 一键回滚（5 分钟内完成，零数据风险）
git stash push -m "perf-opt" nas_md/webserver/__init__.py
git checkout HEAD~1 -- web/index.html
docker-compose build && docker-compose up -d
```

---

## 7. 决策记录

| 决策 | 选项 | 选择 | 理由 |
|------|------|------|------|
| lib hash 时机 | A.构建时 / B.运行时重定向 | **A** | Docker 部署，构建时最干净 |
| gzip 接入方式 | A.复用_wrap_gzip / B.统一_compress | **B** | 避免分散调用点遗漏 flush |
| ETag hash 范围 | A.前512B / B.全文SHA1 / C.三段采样 | **A** | JS/CSS 头部含版本信息，足够区分；NAS 设备友好 |
| SSE Gzip 策略 | A.完全禁止 / B.允许压缩+反代关缓冲 | **B** | RFC 9110 兼容；反代缓冲才是实时性真凶 |
| 压缩级别 | 未指定 / 建议1~3 | **1（Fastest）** | NAS ARM 设备 CPU 受限 |

---

*Design approved by Grill Session on 2026-07-17.*
