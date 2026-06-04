# Phase 2 核心：Frontmatter + 对象索引器 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 search 模块上扩展，实现 Frontmatter 解析、对象索引（Tag/Task/Heading）和结构化查询 API。

**Architecture:** 扩展 `nas_md/search/` 模块，新增 `extract.py` 提取器，修改 `__init__.py` 扩展数据库和索引流程，修改 `webserver/__init__.py` 新增查询 API。使用 PyYAML 解析 frontmatter。

**Tech Stack:** Python stdlib + PyYAML + SQLite3 + 现有 webserver

---

### Task 1: 添加 PyYAML 依赖

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: 在 pyproject.toml 中添加 PyYAML 依赖**

在 `[project]` 部分添加 `dependencies` 字段：

```toml
[project]
name = "nas-md"
version = "0.1.0"
description = "files.md - personal knowledge management system"
requires-python = ">=3.11"
dependencies = ["pyyaml>=6.0"]
```

- [ ] **Step 2: 安装依赖**

Run: `pip install pyyaml>=6.0`
Expected: Successfully installed PyYAML

- [ ] **Step 3: 验证安装**

Run: `python -c "import yaml; print(yaml.__version__)"`
Expected: 打印版本号

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "feat: add pyyaml dependency for frontmatter parsing"
```

---

### Task 2: 创建提取器模块 extract.py

**Files:**
- Create: `nas_md/search/extract.py`
- Create: `tests/test_extract.py`

- [ ] **Step 1: 创建 extract.py — frontmatter 提取**

```python
"""Content extractors for structured objects from Markdown files."""

from __future__ import annotations

import re
from typing import Any

import yaml


def extract_frontmatter(content: str) -> dict[str, Any] | None:
    """Extract YAML frontmatter from Markdown content.

    Returns parsed dict if frontmatter exists, None otherwise.
    Silently returns None on parse errors.
    """
    if not content.startswith("---"):
        return None
    # Find the closing ---
    end = content.find("---", 3)
    if end == -1:
        return None
    yaml_str = content[3:end].strip()
    if not yaml_str:
        return None
    try:
        result = yaml.safe_load(yaml_str)
        if isinstance(result, dict):
            return result
        return None
    except yaml.YAMLError:
        return None


def _strip_frontmatter(content: str) -> str:
    """Return content with frontmatter block removed."""
    if not content.startswith("---"):
        return content
    end = content.find("---", 3)
    if end == -1:
        return content
    return content[end + 3 :].lstrip("\n")
```

- [ ] **Step 2: 创建 extract.py — headings 提取**

追加到 `extract.py`：

```python
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def extract_headings(content: str) -> list[dict]:
    """Extract headings from Markdown content.

    Returns list of {"level": 1-6, "text": str, "line_number": int}.
    Skips headings inside frontmatter block.
    """
    body = _strip_frontmatter(content)
    # Calculate frontmatter line offset
    fm_lines = 0
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            fm_lines = content[: end + 3].count("\n")

    results = []
    for match in _HEADING_RE.finditer(body):
        level = len(match.group(1))
        text = match.group(2).strip()
        # Calculate line number in original content
        line_number = body[: match.start()].count("\n") + fm_lines + 1
        results.append({"level": level, "text": text, "line_number": line_number})
    return results
```

- [ ] **Step 3: 创建 extract.py — tags 提取**

追加到 `extract.py`：

```python
# Match #tag: word chars (including CJK unicode), hyphens, underscores
# Must be at start of line or after whitespace/punctuation
# Not inside a heading (## heading) or code block
_TAG_RE = re.compile(r"(?:^|[\s(\[{,;])(#([\w\u4e00-\u9fff][\w\u4e00-\u9fff\-_]*))", re.UNICODE)

# Common false positives to skip
_TAG_SKIP = frozenset({"#", "#!", "##", "###", "####", "#####", "######"})


def extract_tags(content: str, frontmatter: dict[str, Any] | None = None) -> list[dict]:
    """Extract tags from Markdown content and frontmatter.

    Returns list of {"name": str, "source": "body"|"frontmatter"}.
    Deduplicates: if same tag appears in both, keeps frontmatter source.
    """
    body = _strip_frontmatter(content)
    # Remove code blocks to avoid false positives
    body_no_code = re.sub(r"```[\s\S]*?```", "", body)
    body_no_code = re.sub(r"`[^`]+`", "", body_no_code)
    # Remove headings to avoid matching ## etc
    body_no_code = re.sub(r"^#{1,6}\s+.*$", "", body_no_code, flags=re.MULTILINE)

    tags: dict[str, str] = {}  # name -> source

    # Extract from body
    for match in _TAG_RE.finditer(body_no_code):
        full = match.group(1)
        name = match.group(2)
        if full in _TAG_SKIP:
            continue
        if name not in tags:
            tags[name] = "body"

    # Extract from frontmatter (overrides body source)
    if frontmatter:
        fm_tags = frontmatter.get("tags", [])
        if isinstance(fm_tags, str):
            fm_tags = [t.strip() for t in fm_tags.split(",")]
        if isinstance(fm_tags, list):
            for t in fm_tags:
                t = str(t).strip().lstrip("#")
                if t:
                    tags[t] = "frontmatter"

    return [{"name": name, "source": source} for name, source in sorted(tags.items())]
```

- [ ] **Step 4: 创建 extract.py — tasks 提取**

追加到 `extract.py`：

```python
_TASK_RE = re.compile(r"^[\s]*[-*]\s+\[([ xX])\]\s+(.+)$", re.MULTILINE)


def extract_tasks(content: str) -> list[dict]:
    """Extract task items from Markdown content.

    Returns list of {"content": str, "done": 0|1, "line_number": int}.
    """
    body = _strip_frontmatter(content)
    fm_lines = 0
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            fm_lines = content[: end + 3].count("\n")

    results = []
    for match in _TASK_RE.finditer(body):
        checkbox = match.group(1).lower()
        text = match.group(2).strip()
        done = 1 if checkbox == "x" else 0
        line_number = body[: match.start()].count("\n") + fm_lines + 1
        results.append({"content": text, "done": done, "line_number": line_number})
    return results
```

- [ ] **Step 5: 创建测试文件 tests/test_extract.py**

```python
"""Tests for search extractors."""

import pytest

from nas_md.search.extract import (
    extract_frontmatter,
    extract_headings,
    extract_tags,
    extract_tasks,
)


class TestExtractFrontmatter:
    def test_basic_frontmatter(self):
        content = "---\ntitle: My Note\ntags: [a, b]\n---\n# Content"
        result = extract_frontmatter(content)
        assert result == {"title": "My Note", "tags": ["a", "b"]}

    def test_no_frontmatter(self):
        content = "# Just a heading\nSome text."
        assert extract_frontmatter(content) is None

    def test_empty_frontmatter(self):
        content = "---\n---\n# Content"
        assert extract_frontmatter(content) is None

    def test_invalid_yaml(self):
        content = "---\n: invalid: yaml: [:\n---\n# Content"
        assert extract_frontmatter(content) is None

    def test_multiline_list(self):
        content = "---\ntags:\n  - project\n  - active\n---\n# Content"
        result = extract_frontmatter(content)
        assert result["tags"] == ["project", "active"]

    def test_frontmatter_with_created_date(self):
        content = "---\ntitle: Test\ncreated: 2026-06-04\n---\n# Content"
        result = extract_frontmatter(content)
        assert result["title"] == "Test"

    def test_frontmatter_not_at_start(self):
        content = "Some text\n---\ntitle: Late\n---\n# Content"
        assert extract_frontmatter(content) is None


class TestExtractHeadings:
    def test_single_heading(self):
        content = "# Title\nSome text."
        result = extract_headings(content)
        assert len(result) == 1
        assert result[0]["level"] == 1
        assert result[0]["text"] == "Title"

    def test_multiple_headings(self):
        content = "# H1\n## H2\n### H3\nText\n#### H4"
        result = extract_headings(content)
        assert len(result) == 4
        assert [h["level"] for h in result] == [1, 2, 3, 4]

    def test_headings_skip_frontmatter(self):
        content = "---\ntitle: Test\n---\n# Real Title\n## Section"
        result = extract_headings(content)
        assert len(result) == 2
        assert result[0]["text"] == "Real Title"

    def test_headings_line_numbers(self):
        content = "# Title\n\nParagraph\n\n## Section"
        result = extract_headings(content)
        assert result[0]["line_number"] == 1
        assert result[1]["line_number"] == 5

    def test_no_headings(self):
        content = "Just plain text\nNo headings here."
        assert extract_headings(content) == []


class TestExtractTags:
    def test_body_tags(self):
        content = "Working on #project and #python today."
        result = extract_tags(content)
        names = [t["name"] for t in result]
        assert "project" in names
        assert "python" in names

    def test_frontmatter_tags(self):
        content = "---\ntags: [project, active]\n---\n# Note"
        fm = extract_frontmatter(content)
        result = extract_tags(content, fm)
        fm_tags = [t for t in result if t["source"] == "frontmatter"]
        assert len(fm_tags) == 2

    def test_dedup_keeps_frontmatter(self):
        content = "---\ntags: [project]\n---\n# Note about #project"
        fm = extract_frontmatter(content)
        result = extract_tags(content, fm)
        project_tags = [t for t in result if t["name"] == "project"]
        assert len(project_tags) == 1
        assert project_tags[0]["source"] == "frontmatter"

    def test_skip_heading_hashes(self):
        content = "## Heading\n#tag here"
        result = extract_tags(content)
        names = [t["name"] for t in result]
        assert "tag" in names
        # Should not include "Heading" as a tag

    def test_skip_code_blocks(self):
        content = "```python\n# This is a comment\n```\n#real-tag"
        result = extract_tags(content)
        names = [t["name"] for t in result]
        assert "real-tag" in names
        assert "This" not in names

    def test_no_tags(self):
        content = "Just plain text without any tags."
        assert extract_tags(content) == []

    def test_chinese_tags(self):
        content = "这是 #项目 笔记"
        result = extract_tags(content)
        names = [t["name"] for t in result]
        assert "项目" in names


class TestExtractTasks:
    def test_pending_task(self):
        content = "- [ ] Buy groceries"
        result = extract_tasks(content)
        assert len(result) == 1
        assert result[0]["content"] == "Buy groceries"
        assert result[0]["done"] == 0

    def test_completed_task(self):
        content = "- [x] Done task"
        result = extract_tasks(content)
        assert len(result) == 1
        assert result[0]["done"] == 1

    def test_mixed_tasks(self):
        content = "- [ ] Todo\n- [x] Done\n- [ ] Another"
        result = extract_tasks(content)
        assert len(result) == 3
        assert [t["done"] for t in result] == [0, 1, 0]

    def test_task_line_numbers(self):
        content = "# Title\n\n- [ ] Task one\n\n- [ ] Task two"
        result = extract_tasks(content)
        assert result[0]["line_number"] == 3
        assert result[1]["line_number"] == 5

    def test_tasks_skip_frontmatter(self):
        content = "---\ntitle: Test\n---\n- [ ] Real task"
        result = extract_tasks(content)
        assert len(result) == 1
        assert result[0]["content"] == "Real task"

    def test_no_tasks(self):
        content = "No tasks here, just text."
        assert extract_tasks(content) == []

    def test_asterisk_task(self):
        content = "* [ ] Task with asterisk"
        result = extract_tasks(content)
        assert len(result) == 1
        assert result[0]["content"] == "Task with asterisk"

    def test_uppercase_x(self):
        content = "- [X] Task with uppercase X"
        result = extract_tasks(content)
        assert len(result) == 1
        assert result[0]["done"] == 1
```

- [ ] **Step 6: 运行测试验证**

Run: `python -m pytest tests/test_extract.py -v`
Expected: 所有测试通过

- [ ] **Step 7: Commit**

```bash
git add nas_md/search/extract.py tests/test_extract.py
git commit -m "feat: add content extractors for frontmatter, headings, tags, tasks"
```

---

### Task 3: 扩展 search 模块数据库和索引流程

**Files:**
- Modify: `nas_md/search/__init__.py`
- Modify: `tests/test_search.py`

- [ ] **Step 1: 扩展 init_db() — 新增 tags/tasks/headings 表和 frontmatter 列**

在 `init_db()` 的 `conn.executescript()` 中，在现有建表语句之后追加：

```python
# After existing CREATE TABLE pages and triggers, add:

# Add frontmatter column to pages (idempotent)
conn.execute("ALTER TABLE pages ADD COLUMN frontmatter TEXT")

# Tags table
conn.execute("""
    CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY,
        page_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'body',
        FOREIGN KEY (page_id) REFERENCES pages(id) ON DELETE CASCADE
    )
""")
conn.execute("CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name)")
conn.execute("CREATE INDEX IF NOT EXISTS idx_tags_page_id ON tags(page_id)")

# Tasks table
conn.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY,
        page_id INTEGER NOT NULL,
        line_number INTEGER,
        content TEXT NOT NULL,
        done INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (page_id) REFERENCES pages(id) ON DELETE CASCADE
    )
""")
conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_done ON tasks(done)")
conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_page_id ON tasks(page_id)")

# Headings table
conn.execute("""
    CREATE TABLE IF NOT EXISTS headings (
        id INTEGER PRIMARY KEY,
        page_id INTEGER NOT NULL,
        level INTEGER NOT NULL,
        text TEXT NOT NULL,
        line_number INTEGER,
        FOREIGN KEY (page_id) REFERENCES pages(id) ON DELETE CASCADE
    )
""")
conn.execute("CREATE INDEX IF NOT EXISTS idx_headings_page_id ON headings(page_id)")
```

注意：`ALTER TABLE ADD COLUMN` 在列已存在时会抛异常，需要用 try/except 包裹：

```python
try:
    conn.execute("ALTER TABLE pages ADD COLUMN frontmatter TEXT")
except Exception:
    pass  # Column already exists
```

- [ ] **Step 2: 修改 index_file() — 提取并存储对象**

替换现有 `index_file()` 函数：

```python
def index_file(path: str, content: str) -> None:
    """Index or re-index a single file with structured objects."""
    from nas_md.search.extract import extract_frontmatter, extract_headings, extract_tags, extract_tasks

    conn = get_connection()
    try:
        # Extract structured objects
        fm = extract_frontmatter(content)
        fm_json = json.dumps(fm, ensure_ascii=False) if fm else None

        # Extract title: frontmatter > first heading > filename
        title = None
        if fm and "title" in fm:
            title = str(fm["title"])
        if not title:
            title = _extract_title(content, path)

        filename = os.path.basename(path)
        content_hash = str(hash(content))
        now = int(os.path.getmtime(path) * 1000) if os.path.exists(path) else 0

        # UPSERT page
        conn.execute(
            """
            INSERT INTO pages (path, filename, title, content, content_hash, updated_at, frontmatter)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                title=excluded.title,
                content=excluded.content,
                content_hash=excluded.content_hash,
                updated_at=excluded.updated_at,
                frontmatter=excluded.frontmatter
        """,
            (path, filename, title, content, content_hash, now, fm_json),
        )

        # Get page_id
        row = conn.execute("SELECT id FROM pages WHERE path = ?", (path,)).fetchone()
        page_id = row[0]

        # Clear old objects for this page
        conn.execute("DELETE FROM tags WHERE page_id = ?", (page_id,))
        conn.execute("DELETE FROM tasks WHERE page_id = ?", (page_id,))
        conn.execute("DELETE FROM headings WHERE page_id = ?", (page_id,))

        # Insert headings
        for h in extract_headings(content):
            conn.execute(
                "INSERT INTO headings (page_id, level, text, line_number) VALUES (?, ?, ?, ?)",
                (page_id, h["level"], h["text"], h["line_number"]),
            )

        # Insert tags
        for t in extract_tags(content, fm):
            conn.execute(
                "INSERT INTO tags (page_id, name, source) VALUES (?, ?, ?)",
                (page_id, t["name"], t["source"]),
            )

        # Insert tasks
        for t in extract_tasks(content):
            conn.execute(
                "INSERT INTO tasks (page_id, line_number, content, done) VALUES (?, ?, ?, ?)",
                (page_id, t["line_number"], t["content"], t["done"]),
            )

        conn.commit()
    finally:
        conn.close()
```

需要在文件顶部添加 `import json`。

- [ ] **Step 3: 修改 rebuild_index() — 遍历时一并提取对象**

在 `rebuild_index()` 的 INSERT INTO pages 语句中添加 `frontmatter` 列，并在插入 page 后提取对象：

```python
def rebuild_index(directories: list[str]) -> int:
    """Rebuild the entire search index from scratch."""
    from nas_md.search.extract import extract_frontmatter, extract_headings, extract_tags, extract_tasks

    conn = get_connection()
    try:
        # Clear existing index
        conn.execute("DELETE FROM pages")
        conn.execute("DELETE FROM pages_fts")
        conn.commit()

        count = 0
        for directory in directories:
            dir_path = Path(directory)
            if not dir_path.exists():
                logger.warning("Directory not found: %s", directory)
                continue

            for md_file in dir_path.rglob("*.md"):
                try:
                    content = md_file.read_text(encoding="utf-8", errors="replace")
                    rel_path = str(md_file.relative_to(dir_path))
                    filename = md_file.name
                    content_hash = str(hash(content))
                    updated_at = int(md_file.stat().st_mtime * 1000)

                    # Extract frontmatter
                    fm = extract_frontmatter(content)
                    fm_json = json.dumps(fm, ensure_ascii=False) if fm else None

                    # Extract title
                    title = None
                    if fm and "title" in fm:
                        title = str(fm["title"])
                    if not title:
                        title = _extract_title(content, rel_path)

                    conn.execute(
                        """
                        INSERT INTO pages (path, filename, title, content, content_hash, updated_at, frontmatter)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                        (rel_path, filename, title, content, content_hash, updated_at, fm_json),
                    )

                    # Get page_id
                    row = conn.execute("SELECT id FROM pages WHERE path = ?", (rel_path,)).fetchone()
                    page_id = row[0]

                    # Insert objects
                    for h in extract_headings(content):
                        conn.execute(
                            "INSERT INTO headings (page_id, level, text, line_number) VALUES (?, ?, ?, ?)",
                            (page_id, h["level"], h["text"], h["line_number"]),
                        )
                    for t in extract_tags(content, fm):
                        conn.execute(
                            "INSERT INTO tags (page_id, name, source) VALUES (?, ?, ?)",
                            (page_id, t["name"], t["source"]),
                        )
                    for t in extract_tasks(content):
                        conn.execute(
                            "INSERT INTO tasks (page_id, line_number, content, done) VALUES (?, ?, ?, ?)",
                            (page_id, t["line_number"], t["content"], t["done"]),
                        )

                    count += 1
                except Exception as e:
                    logger.warning("Failed to index %s: %s", md_file, e)

        conn.commit()
        # ... rest of metadata storage unchanged
```

- [ ] **Step 4: 新增查询函数**

在 `search/__init__.py` 末尾添加：

```python
def query_tasks(status: str | None = None, limit: int = 100) -> list[dict]:
    """Query task items. status: 'pending', 'done', or None for all."""
    conn = get_connection()
    try:
        sql = """
            SELECT t.content, t.done, t.line_number, p.path, p.title
            FROM tasks t JOIN pages p ON t.page_id = p.id
        """
        params: list = []
        if status == "pending":
            sql += " WHERE t.done = 0"
        elif status == "done":
            sql += " WHERE t.done = 1"
        sql += " ORDER BY p.path, t.line_number LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        return [
            {
                "content": r[0],
                "done": bool(r[1]),
                "line": r[2],
                "page": r[3],
                "title": r[4] or r[3],
            }
            for r in rows
        ]
    finally:
        conn.close()


def query_tags(name: str | None = None) -> list[dict]:
    """Query tags. If name given, return pages with that tag. Otherwise return all tags with counts."""
    conn = get_connection()
    try:
        if name:
            rows = conn.execute(
                """
                SELECT DISTINCT p.path, p.title
                FROM tags t JOIN pages p ON t.page_id = p.id
                WHERE t.name = ?
                ORDER BY p.path
            """,
                (name,),
            ).fetchall()
            return [{"path": r[0], "title": r[1] or r[0]} for r in rows]
        else:
            rows = conn.execute(
                """
                SELECT name, COUNT(DISTINCT page_id) as cnt
                FROM tags
                GROUP BY name
                ORDER BY cnt DESC, name
            """
            ).fetchall()
            return [{"name": r[0], "count": r[1]} for r in rows]
    finally:
        conn.close()


def query_headings(page_path: str | None = None) -> list[dict]:
    """Query headings. If page_path given, return headings for that page."""
    conn = get_connection()
    try:
        if page_path:
            rows = conn.execute(
                """
                SELECT h.level, h.text, h.line_number
                FROM headings h JOIN pages p ON h.page_id = p.id
                WHERE p.path = ?
                ORDER BY h.line_number
            """,
                (page_path,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT h.level, h.text, h.line_number, p.path
                FROM headings h JOIN pages p ON h.page_id = p.id
                ORDER BY p.path, h.line_number
                LIMIT 500
            """
            ).fetchall()
            return [
                {"level": r[0], "text": r[1], "line": r[2], "page": r[3]}
                for r in rows
            ]
        return [{"level": r[0], "text": r[1], "line": r[2]} for r in rows]
    finally:
        conn.close()
```

- [ ] **Step 5: 扩展测试 tests/test_search.py**

在测试文件中添加新的测试类：

```python
from nas_md.search import (
    init_db,
    index_file,
    remove_file,
    search,
    rebuild_index,
    get_stats,
    get_connection,
    query_tasks,
    query_tags,
    query_headings,
)


class TestObjectIndexing:
    def test_index_file_with_frontmatter(self, search_db):
        content = "---\ntitle: My Note\ntags: [project, active]\n---\n# My Note\nSome text."
        index_file("/note.md", content)
        conn = get_connection(search_db)
        row = conn.execute("SELECT frontmatter FROM pages WHERE path = '/note.md'").fetchone()
        conn.close()
        assert row[0] is not None
        import json
        fm = json.loads(row[0])
        assert fm["title"] == "My Note"

    def test_index_file_extracts_headings(self, search_db):
        content = "# Title\n## Section 1\n### Sub\n## Section 2"
        index_file("/doc.md", content)
        headings = query_headings("/doc.md")
        assert len(headings) == 4
        assert headings[0]["level"] == 1
        assert headings[0]["text"] == "Title"

    def test_index_file_extracts_tags(self, search_db):
        content = "---\ntags: [python]\n---\n# Note\nWorking on #project"
        index_file("/tagged.md", content)
        tags = query_tags()
        names = [t["name"] for t in tags]
        assert "python" in names
        assert "project" in names

    def test_index_file_extracts_tasks(self, search_db):
        content = "# Todo\n- [ ] Buy milk\n- [x] Write code\n- [ ] Review PR"
        index_file("/todo.md", content)
        tasks = query_tasks()
        assert len(tasks) == 3
        pending = query_tasks(status="pending")
        assert len(pending) == 2
        done = query_tasks(status="done")
        assert len(done) == 1

    def test_remove_file_cascades(self, search_db):
        content = "# Title\n- [ ] Task\n#tag"
        index_file("/cascade.md", content)
        remove_file("/cascade.md")
        assert query_headings("/cascade.md") == []
        assert query_tasks() == []

    def test_reindex_updates_objects(self, search_db):
        index_file("/update.md", "# Old Title\n- [ ] Old task")
        index_file("/update.md", "# New Title\n- [x] New task")
        headings = query_headings("/update.md")
        assert len(headings) == 1
        assert headings[0]["text"] == "New Title"
        tasks = query_tasks()
        assert len(tasks) == 1
        assert tasks[0]["done"] is True

    def test_query_tags_with_name(self, search_db):
        index_file("/a.md", "# A\n#project content")
        index_file("/b.md", "# B\n#project other\n#personal")
        result = query_tags(name="project")
        assert len(result) == 2

    def test_title_from_frontmatter(self, search_db):
        content = "---\ntitle: Custom Title\n---\n# Different Heading"
        index_file("/fmtitle.md", content)
        results = search("Custom", limit=5)
        assert len(results) >= 1
        assert results[0]["title"] == "Custom Title"
```

- [ ] **Step 6: 运行全部搜索测试**

Run: `python -m pytest tests/test_search.py tests/test_extract.py -v`
Expected: 所有测试通过

- [ ] **Step 7: Commit**

```bash
git add nas_md/search/__init__.py tests/test_search.py
git commit -m "feat: extend search module with object indexing (tags, tasks, headings, frontmatter)"
```

---

### Task 4: 新增查询 API 端点

**Files:**
- Modify: `nas_md/webserver/__init__.py`

- [ ] **Step 1: 在 webserver do_GET 中添加 /api/query 路由**

在 `do_GET` 方法的路由分发中，在 search API 路由之后添加：

```python
# Query API (structured object queries)
if path == "/api/query":
    self._handle_query(qs)
    return
```

- [ ] **Step 2: 实现 _handle_query 方法**

在 `MountHTTPHandler` 类中添加：

```python
def _handle_query(self, qs: dict):
    """Handle GET /api/query?type=task|tag|heading"""
    from nas_md.search import query_tasks, query_tags, query_headings

    query_type = qs.get("type", [""])[0]

    if query_type == "task":
        status = qs.get("status", [None])[0]
        tasks = query_tasks(status=status)
        self._send_json({"tasks": tasks})
    elif query_type == "tag":
        name = qs.get("name", [None])[0]
        if name:
            pages = query_tags(name=name)
            self._send_json({"pages": pages})
        else:
            tags = query_tags()
            self._send_json({"tags": tags})
    elif query_type == "heading":
        page = qs.get("page", [None])[0]
        headings = query_headings(page_path=page)
        self._send_json({"headings": headings})
    else:
        self._send_error("Invalid query type. Use: task, tag, heading", 400)
```

- [ ] **Step 3: 在 serve() 的 API 端点日志中添加 /api/query**

在 `serve()` 函数的 `logger.info("    GET  /api/search?q=keyword")` 之后添加：

```python
logger.info("    GET  /api/query?type=task|tag|heading")
```

- [ ] **Step 4: 手动测试 API**

启动服务后测试：

Run: `python -m nas_md.cli web` (在另一个终端)

测试命令：
```bash
curl "http://localhost:8080/api/query?type=task"
curl "http://localhost:8080/api/query?type=tag"
curl "http://localhost:8080/api/query?type=heading&page=/欢迎.md"
```

Expected: 返回 JSON 格式的查询结果

- [ ] **Step 5: Commit**

```bash
git add nas_md/webserver/__init__.py
git commit -m "feat: add /api/query endpoint for structured object queries"
```

---

### Task 5: 代码质量检查和 CI 验证

**Files:**
- Possibly modify: `nas_md/search/__init__.py`, `nas_md/search/extract.py`, `tests/test_extract.py`, `tests/test_search.py`

- [ ] **Step 1: 运行 ruff 检查**

Run: `python -m ruff check nas_md/search/ nas_md/webserver/ tests/`
Expected: 无错误，或修复后无错误

- [ ] **Step 2: 运行 black 格式化**

Run: `python -m black nas_md/search/ nas_md/webserver/ tests/`
Expected: 所有文件已格式化

- [ ] **Step 3: 运行全部测试**

Run: `python -m pytest tests/ -v`
Expected: 所有测试通过

- [ ] **Step 4: 推送并监控 CI**

```bash
git push
```

监控 GitHub Actions CI 结果，如有失败则修复。

- [ ] **Step 5: 最终 Commit（如有修复）**

```bash
git add -A
git commit -m "fix: address CI issues from Phase 2 core implementation"
git push
```
