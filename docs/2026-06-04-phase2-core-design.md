# Phase 2 核心：Frontmatter + 对象索引器 设计

> 日期：2026-06-04
> 范围：Phase 2 的核心部分（双向链接和查询 API 的完整版留待后续迭代）

## 目标

让笔记从"静态文档"变成"知识节点"——通过解析 Markdown 内容中的结构化元素（frontmatter、标签、任务、标题），建立对象索引，支持结构化查询。

## 架构决策

- **扩展现有 search 模块**，而非新建 indexer 模块。一个数据库，事务一致，零同步开销。
- **实时索引**：文件保存时立即提取并更新索引，用户无感知延迟。
- **使用 PyYAML**：用成熟的 yaml 库解析 frontmatter，可靠且功能完整。

## 数据库扩展

在现有 `search.db` 的 `pages` 表基础上新增列和表：

### pages 表新增列

```sql
ALTER TABLE pages ADD COLUMN frontmatter TEXT;  -- JSON 格式
```

### 新增表

```sql
CREATE TABLE tags (
    id INTEGER PRIMARY KEY,
    page_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'body',  -- 'frontmatter' 或 'body'
    FOREIGN KEY (page_id) REFERENCES pages(id) ON DELETE CASCADE
);
CREATE INDEX idx_tags_name ON tags(name);
CREATE INDEX idx_tags_page_id ON tags(page_id);

CREATE TABLE tasks (
    id INTEGER PRIMARY KEY,
    page_id INTEGER NOT NULL,
    line_number INTEGER,
    content TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (page_id) REFERENCES pages(id) ON DELETE CASCADE
);
CREATE INDEX idx_tasks_done ON tasks(done);
CREATE INDEX idx_tasks_page_id ON tasks(page_id);

CREATE TABLE headings (
    id INTEGER PRIMARY KEY,
    page_id INTEGER NOT NULL,
    level INTEGER NOT NULL,    -- 1-6
    text TEXT NOT NULL,
    line_number INTEGER,
    FOREIGN KEY (page_id) REFERENCES pages(id) ON DELETE CASCADE
);
CREATE INDEX idx_headings_page_id ON headings(page_id);
```

### 级联删除

`pages` 表删除记录时，通过 `ON DELETE CASCADE` 自动清除关联的 tags/tasks/headings。

## 提取器（nas_md/search/extract.py）

纯函数模块，从 Markdown 内容提取结构化对象。所有函数接收 `content: str`，返回列表或字典。

### extract_frontmatter(content) -> dict | None

- 识别 `---` 包裹的 YAML 块（文件开头）
- 使用 PyYAML (`yaml.safe_load`) 解析，支持完整 YAML 语法
- 解析失败返回 None，不影响全文索引

### extract_tags(content, frontmatter) -> list[dict]

- 从 body 提取 `#tag` 语法（行首或空格后的 `#` + 非空字符序列）
- 从 frontmatter 提取 `tags` 字段（列表或逗号分隔字符串）
- 返回 `[{"name": "tag", "source": "body"|"frontmatter"}, ...]`
- 去重：同一 tag 名在 frontmatter 和 body 都出现时，保留 frontmatter 来源

### extract_tasks(content) -> list[dict]

- 匹配 `- [ ]` 和 `- [x]`（支持 `- [X]`）
- 返回 `[{"content": "任务文本", "done": 0|1, "line_number": N}, ...]`

### extract_headings(content) -> list[dict]

- 匹配 `# ~ ######` 标题
- 返回 `[{"level": 1-6, "text": "标题文本", "line_number": N}, ...]`
- 跳过 frontmatter 块内的内容

## 索引流程

修改 `index_file(path, content)` 函数：

```
1. extract_frontmatter(content) → fm
2. 提取 title：fm.title > 第一行 # heading > 文件名
3. UPSERT pages（含 frontmatter JSON）
4. 获取 page_id
5. DELETE FROM tags/tasks/headings WHERE page_id = ?
6. extract_headings → INSERT headings
7. extract_tags → INSERT tags
8. extract_tasks → INSERT tasks
9. COMMIT（单事务）
```

`remove_file(path)` 已有 CASCADE，无需额外处理。

`rebuild_index(directories)` 同样扩展，遍历文件时一并提取对象。

## 查询 API

在 webserver 中新增 `/api/query` 端点：

| 参数 | 说明 |
|------|------|
| `type=task` | 查询任务，可选 `status=pending`/`done` |
| `type=tag` | 标签列表（含计数），可选 `name=xxx` 筛选某标签下的页面 |
| `type=heading` | 可选 `page=path` 查某页面的标题列表 |

响应格式：

```json
// type=task
{"tasks": [{"content": "...", "done": false, "page": "notes/todo.md", "line": 5}, ...]}

// type=tag
{"tags": [{"name": "project", "count": 5}, ...]}
// type=tag&name=project
{"pages": [{"path": "notes/a.md", "title": "A"}, ...]}

// type=heading&page=notes/a.md
{"headings": [{"level": 2, "text": "Section", "line": 10}, ...]}
```

## 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `nas_md/search/extract.py` | 新建 | 提取器（frontmatter/tags/tasks/headings） |
| `nas_md/search/__init__.py` | 修改 | 扩展 init_db/index_file/rebuild_index，新增查询函数 |
| `nas_md/webserver/__init__.py` | 修改 | 新增 /api/query 端点 |
| `tests/test_search.py` | 修改 | 扩展测试覆盖新功能 |
| `tests/test_extract.py` | 新建 | 提取器单元测试 |

## 不在本次范围

- `[[wiki-link]]` 双向链接解析和反链（Phase 2 后续迭代）
- 前端 UI 展示（任务面板、标签云等，等 API 稳定后再做）
- 知识图谱可视化（Phase 3）
