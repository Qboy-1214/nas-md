# Phase 2 剩余：双向链接 + 反链 设计 ✅ 已完成

> 日期：2026-06-04
> 范围：Phase 2 的最后部分，补全 wiki-link 解析、反链索引和前端展示

## 目标

让笔记之间建立链接关系——通过解析 `[[Page Name]]` 语法，建立出链和反链索引，支持结构化查询和前端反链面板展示。

## 架构决策

- **延续现有模式**：在 `extract.py` 新增 `extract_links()`，在 `search/__init__.py` 新增 `links` 表，复用已有的索引流程和查询模式。
- **target 存储为页面名**：`[[xxx]]` 中的 `xxx` 直接存储，不做路径解析。反链查询时通过 `LIKE` 匹配页面路径。
- **前端反链面板**：编辑器底部可折叠面板，显示引用当前页面的其他页面列表，点击可跳转。

## 链接提取器（nas_md/search/extract.py）

### extract_links(content) -> list[dict]

- 匹配 `[[Page Name]]` 和 `[[Page Name|Display Text]]` 语法
- 跳过代码块内的链接
- 返回 `[{"target": "Page Name", "display_text": "Display Text"|None, "line_number": N}]`

正则：`\[\[([^\]|]+)(?:\|([^\]]+))?\]\]`

- `[[Project Notes]]` → target="Project Notes", display_text=None
- `[[Project Notes|项目笔记]]` → target="Project Notes", display_text="项目笔记"

## 数据库扩展

### 新增 links 表

```sql
CREATE TABLE IF NOT EXISTS links (
    id INTEGER PRIMARY KEY,
    page_id INTEGER NOT NULL,
    target TEXT NOT NULL,        -- 目标页面名（[[xxx]] 中的 xxx）
    display_text TEXT,           -- 显示文本（[[xxx|yyy]] 中的 yyy）
    line_number INTEGER,
    FOREIGN KEY (page_id) REFERENCES pages(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_links_target ON links(target);
CREATE INDEX IF NOT EXISTS idx_links_page_id ON links(page_id);
```

级联删除：删除页面时自动清除关联链接。

## 索引流程

在 `index_file()` 和 `rebuild_index()` 中，在提取 tags/tasks/headings 之后：

```
6. extract_links(content) → INSERT links
7. DELETE FROM links WHERE page_id = ? (先删后插，同 tags/tasks/headings)
```

## 查询 API

### 出链查询

```
GET /api/query?type=link&page=notes/a.md
```

响应：
```json
{
  "links": [
    {"target": "Project Notes", "display_text": "项目笔记", "line": 5},
    {"target": "TODO", "display_text": null, "line": 12}
  ]
}
```

### 反链查询

```
GET /api/backlinks?page=notes/a.md
```

查询逻辑：在 links 表中查找 target 匹配页面路径或文件名的记录，关联 pages 表获取来源页面信息。

响应：
```json
{
  "backlinks": [
    {"path": "notes/b.md", "title": "Note B", "line": 3, "context": "参考 [[a]] 的内容"},
    {"path": "journal/2026.06 June.md", "title": "2026.06 June", "line": 15, "context": "..."}
  ]
}
```

## 前端反链面板

### 位置

编辑器区域底部，`#editor-container` 下方，新增 `#backlinks-panel`。

### 结构

```html
<div id="backlinks-panel" class="backlinks-panel" style="display:none">
  <div class="backlinks-header" onclick="toggleBacklinks()">
    <span class="backlinks-title">反向链接 (3)</span>
    <span class="backlinks-toggle">▼</span>
  </div>
  <div class="backlinks-content">
    <div class="backlink-item" onclick="openFile('/notes/b.md', mountId)">
      <span class="backlink-page">Note B</span>
      <span class="backlink-line">第 3 行</span>
    </div>
    ...
  </div>
</div>
```

### 行为

1. 打开文件时，调用 `/api/backlinks?page=xxx` 获取反链
2. 有反链时显示面板，无反链时隐藏
3. 面板默认展开，点击 header 可折叠
4. 点击反链项跳转打开对应页面

### 样式

- 面板高度固定 150px，内容溢出滚动
- 半透明背景，与编辑器区分
- 反链项 hover 高亮

## 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `nas_md/search/extract.py` | 修改 | 新增 extract_links() |
| `nas_md/search/__init__.py` | 修改 | 新增 links 表、索引流程、query_links()、query_backlinks() |
| `nas_md/webserver/__init__.py` | 修改 | 新增 /api/backlinks 端点，扩展 /api/query?type=link |
| `web/files.js` | 修改 | 新增 API.getBacklinks() |
| `web/app.js` | 修改 | 新增 loadBacklinks()、toggleBacklinks()、反链面板渲染 |
| `web/index.html` | 修改 | 新增 #backlinks-panel HTML |
| `web/app.css` | 修改 | 新增反链面板样式 |
| `tests/test_extract.py` | 修改 | 新增 extract_links 测试 |
| `tests/test_search.py` | 修改 | 新增 links 索引和查询测试 |

## 不在本次范围

- `[[link]]` 点击跳转（需要 Vditor 自定义渲染，复杂度高）
- `[[link]]` 悬停预览
- `[[link]]` 自动补全
- 孤立页面检测
