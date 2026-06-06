"""Full-text search module for nas-md using SQLite FTS5."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger("search")

# Default database path — can be overridden via SEARCH_DB env
DEFAULT_DB_PATH = os.path.join(os.getcwd(), "search.db")

# FTS tokenizer version — increment to force rebuild when tokenizer changes
_FTS_TOKENIZER_VERSION = 2  # v1=unicode61, v2=trigram


def _migrate_fts_tokenizer(conn: sqlite3.Connection) -> None:
    """Check if FTS table uses the correct tokenizer; rebuild if not."""
    try:
        # Check current tokenizer version
        row = conn.execute(
            "SELECT value FROM index_meta WHERE key = 'fts_tokenizer_version'"
        ).fetchone()
        current_version = int(row[0]) if row else 1

        if current_version >= _FTS_TOKENIZER_VERSION:
            return  # Already up to date

        # Need to rebuild — drop and recreate FTS table
        logger.info(
            "Migrating FTS tokenizer from v%d to v%d, rebuilding index...",
            current_version,
            _FTS_TOKENIZER_VERSION,
        )
        conn.execute("DROP TABLE IF EXISTS pages_fts")
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
                path,
                title,
                content,
                content='pages',
                tokenize='trigram'
            )
        """)
        # Recreate triggers
        conn.execute("DROP TRIGGER IF EXISTS pages_ai")
        conn.execute("DROP TRIGGER IF EXISTS pages_ad")
        conn.execute("DROP TRIGGER IF EXISTS pages_au")
        conn.executescript("""
            CREATE TRIGGER IF NOT EXISTS pages_ai AFTER INSERT ON pages BEGIN
                INSERT INTO pages_fts(rowid, path, title, content)
                VALUES (new.id, new.path, new.title, new.content);
            END;

            CREATE TRIGGER IF NOT EXISTS pages_ad AFTER DELETE ON pages BEGIN
                INSERT INTO pages_fts(pages_fts, rowid, path, title, content)
                VALUES ('delete', old.id, old.path, old.title, old.content);
            END;

            CREATE TRIGGER IF NOT EXISTS pages_au AFTER UPDATE ON pages BEGIN
                INSERT INTO pages_fts(pages_fts, rowid, path, title, content)
                VALUES ('delete', old.id, old.path, old.title, old.content);
                INSERT INTO pages_fts(rowid, path, title, content)
                VALUES (new.id, new.path, new.title, new.content);
            END;
        """)
        # Re-populate FTS from pages table
        conn.execute("""
            INSERT INTO pages_fts(rowid, path, title, content)
            SELECT id, path, title, content FROM pages
        """)
        # Record new version
        conn.execute(
            "INSERT OR REPLACE INTO index_meta (key, value) VALUES (?, ?)",
            ("fts_tokenizer_version", str(_FTS_TOKENIZER_VERSION)),
        )
        conn.commit()
        logger.info("FTS tokenizer migration complete.")
    except Exception as e:
        logger.error("FTS migration error: %s", e)


def get_db_path() -> str:
    """Get the search database path."""
    return os.environ.get("SEARCH_DB", DEFAULT_DB_PATH)


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    """Get a SQLite connection with FTS5 support."""
    path = db_path or get_db_path()
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: str | None = None) -> None:
    """Initialize the search database with required tables."""
    conn = get_connection(db_path)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS pages (
                id INTEGER PRIMARY KEY,
                path TEXT UNIQUE NOT NULL,
                filename TEXT NOT NULL,
                title TEXT,
                content TEXT,
                content_hash TEXT,
                created_at INTEGER,
                updated_at INTEGER
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
                path,
                title,
                content,
                content='pages',
                tokenize='trigram'
            );

            CREATE TABLE IF NOT EXISTS index_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            -- Triggers to keep FTS in sync with pages
            CREATE TRIGGER IF NOT EXISTS pages_ai AFTER INSERT ON pages BEGIN
                INSERT INTO pages_fts(rowid, path, title, content)
                VALUES (new.id, new.path, new.title, new.content);
            END;

            CREATE TRIGGER IF NOT EXISTS pages_ad AFTER DELETE ON pages BEGIN
                INSERT INTO pages_fts(pages_fts, rowid, path, title, content)
                VALUES ('delete', old.id, old.path, old.title, old.content);
            END;

            CREATE TRIGGER IF NOT EXISTS pages_au AFTER UPDATE ON pages BEGIN
                INSERT INTO pages_fts(pages_fts, rowid, path, title, content)
                VALUES ('delete', old.id, old.path, old.title, old.content);
                INSERT INTO pages_fts(rowid, path, title, content)
                VALUES (new.id, new.path, new.title, new.content);
            END;
        """)

        # Add frontmatter column (idempotent — skip if already exists)
        with contextlib.suppress(sqlite3.OperationalError):
            conn.execute("ALTER TABLE pages ADD COLUMN frontmatter TEXT")

        # Migrate FTS from unicode61 to trigram if needed
        _migrate_fts_tokenizer(conn)

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

        # Links table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS links (
                id INTEGER PRIMARY KEY,
                page_id INTEGER NOT NULL,
                target TEXT NOT NULL,
                display_text TEXT,
                line_number INTEGER,
                FOREIGN KEY (page_id) REFERENCES pages(id) ON DELETE CASCADE
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_links_target ON links(target)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_links_page_id ON links(page_id)")

        conn.commit()
        logger.info("Search database initialized at %s", db_path or get_db_path())
    finally:
        conn.close()


def index_file(path: str, content: str) -> None:
    """Index or re-index a single file with structured objects."""
    from nas_md.search.extract import (
        extract_frontmatter,
        extract_headings,
        extract_links,
        extract_tags,
        extract_tasks,
    )

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
        conn.execute("DELETE FROM links WHERE page_id = ?", (page_id,))

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

        # Insert links
        for lk in extract_links(content):
            conn.execute(
                "INSERT INTO links (page_id, target, display_text, line_number) VALUES (?, ?, ?, ?)",
                (page_id, lk["target"], lk.get("display_text"), lk["line_number"]),
            )

        conn.commit()
    finally:
        conn.close()


def remove_file(path: str) -> None:
    """Remove a file from the search index."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM pages WHERE path = ?", (path,))
        conn.commit()
    finally:
        conn.close()


def search(query: str, limit: int = 20) -> list[dict]:
    """Search the index for matching files."""
    if not query or not query.strip():
        return []

    conn = get_connection()
    try:
        # trigram tokenizer: use direct match (no prefix * needed)
        # For queries < 3 chars, fall back to LIKE
        if len(query) < 3:
            rows = conn.execute(
                """
                SELECT path, filename, title,
                       '' as snippet,
                       0 as rank
                FROM pages
                WHERE title LIKE ? OR content LIKE ?
                ORDER BY updated_at DESC
                LIMIT ?
            """,
                (f"%{query}%", f"%{query}%", limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT p.path, p.filename, p.title,
                       snippet(pages_fts, 2, '<mark>', '</mark>', '...', 32) as snippet,
                       rank
                FROM pages_fts
                JOIN pages p ON p.id = pages_fts.rowid
                WHERE pages_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """,
                (query, limit),
            ).fetchall()

        results = []
        for row in rows:
            results.append(
                {
                    "path": row[0],
                    "filename": row[1],
                    "title": row[2] or row[1],
                    "snippet": row[3] or "",
                    "rank": row[4],
                }
            )
        return results
    except Exception as e:
        logger.error("Search error: %s", e)
        return []
    finally:
        conn.close()


def rebuild_index(directories: list[str]) -> int:
    """Rebuild the entire search index from scratch."""
    from nas_md.search.extract import (
        extract_frontmatter,
        extract_headings,
        extract_links,
        extract_tags,
        extract_tasks,
    )

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
                    abs_path = str(md_file)
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
                        title = _extract_title(content, filename)

                    conn.execute(
                        """
                        INSERT INTO pages (path, filename, title, content, content_hash, updated_at, frontmatter)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                        (abs_path, filename, title, content, content_hash, updated_at, fm_json),
                    )

                    # Get page_id
                    row = conn.execute(
                        "SELECT id FROM pages WHERE path = ?", (abs_path,)
                    ).fetchone()
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
                    for lk in extract_links(content):
                        conn.execute(
                            "INSERT INTO links (page_id, target, display_text, line_number) VALUES (?, ?, ?, ?)",
                            (page_id, lk["target"], lk.get("display_text"), lk["line_number"]),
                        )

                    count += 1
                except Exception as e:
                    logger.warning("Failed to index %s: %s", md_file, e)

        conn.commit()
        logger.info("Indexed %d files", count)

        # Store index metadata
        conn.execute(
            """
            INSERT OR REPLACE INTO index_meta (key, value)
            VALUES ('last_rebuild', ?)
        """,
            (str(int(time.time() * 1000)),),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO index_meta (key, value)
            VALUES ('file_count', ?)
        """,
            (str(count),),
        )
        conn.commit()

        return count
    finally:
        conn.close()


def _extract_title(content: str, path: str) -> str:
    """Extract a title from the file's first heading or filename."""
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
        if line.startswith("## "):
            continue  # skip second-level, prefer first-level
    # Fallback to filename without extension
    return Path(path).stem


def get_stats() -> dict:
    """Get index statistics."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT COUNT(*) FROM pages").fetchone()
        count = row[0] if row else 0

        meta = {}
        for row in conn.execute("SELECT key, value FROM index_meta"):
            meta[row[0]] = row[1]

        # Task stats
        task_total = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        task_done = conn.execute("SELECT COUNT(*) FROM tasks WHERE done = 1").fetchone()[0]

        # Tag count
        tag_count = conn.execute("SELECT COUNT(DISTINCT name) FROM tags").fetchone()[0]

        # Link count
        link_count = conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]

        # Recent pages (last 10)
        recent_rows = conn.execute(
            "SELECT path, title, updated_at FROM pages ORDER BY updated_at DESC LIMIT 10"
        ).fetchall()
        recent = [{"path": r[0], "title": r[1] or r[0], "updated_at": r[2]} for r in recent_rows]

        return {
            "file_count": count,
            "task_total": task_total,
            "task_done": task_done,
            "tag_count": tag_count,
            "link_count": link_count,
            "last_rebuild": meta.get("last_rebuild", ""),
            "recent_pages": recent,
        }
    finally:
        conn.close()


# --- Structured query functions ---


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
            rows = conn.execute("""
                SELECT name, COUNT(DISTINCT page_id) as cnt
                FROM tags
                GROUP BY name
                ORDER BY cnt DESC, name
            """).fetchall()
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
            return [{"level": r[0], "text": r[1], "line": r[2]} for r in rows]
        else:
            rows = conn.execute("""
                SELECT h.level, h.text, h.line_number, p.path
                FROM headings h JOIN pages p ON h.page_id = p.id
                ORDER BY p.path, h.line_number
                LIMIT 500
            """).fetchall()
            return [{"level": r[0], "text": r[1], "line": r[2], "page": r[3]} for r in rows]
    finally:
        conn.close()


def query_links(page_path: str | None = None) -> list[dict]:
    """Query outgoing links. If page_path given, return links from that page."""
    conn = get_connection()
    try:
        if page_path:
            rows = conn.execute(
                """
                SELECT l.target, l.display_text, l.line_number
                FROM links l JOIN pages p ON l.page_id = p.id
                WHERE p.path = ?
                ORDER BY l.line_number
            """,
                (page_path,),
            ).fetchall()
            return [{"target": r[0], "display_text": r[1], "line": r[2]} for r in rows]
        else:
            rows = conn.execute("""
                SELECT l.target, l.display_text, l.line_number, p.path
                FROM links l JOIN pages p ON l.page_id = p.id
                ORDER BY p.path, l.line_number
                LIMIT 500
            """).fetchall()
            return [
                {"target": r[0], "display_text": r[1], "line": r[2], "page": r[3]} for r in rows
            ]
    finally:
        conn.close()


def query_backlinks(page_path: str) -> list[dict]:
    """Query backlinks — pages that link TO the given page.

    Matches links.target against the page path, filename stem, or title.
    """
    conn = get_connection()
    try:
        # Get the page's filename stem and title for matching
        page_row = conn.execute(
            "SELECT filename, title FROM pages WHERE path = ?", (page_path,)
        ).fetchone()
        if not page_row:
            return []

        filename = page_row[0]
        title = page_row[1] or ""
        stem = Path(filename).stem  # e.g. "a" from "a.md"

        # Match target against: exact path, filename stem, or title
        rows = conn.execute(
            """
            SELECT DISTINCT p.path, p.title, l.line_number, l.target, l.display_text
            FROM links l JOIN pages p ON l.page_id = p.id
            WHERE l.target = ?
               OR l.target = ?
               OR l.target = ?
               OR l.target LIKE '%' || ? || '%'
            ORDER BY p.path, l.line_number
        """,
            (page_path, stem, title, stem),
        ).fetchall()
        return [
            {
                "path": r[0],
                "title": r[1] or r[0],
                "line": r[2],
                "target": r[3],
                "display_text": r[4],
            }
            for r in rows
        ]
    finally:
        conn.close()


def get_graph_data() -> dict:
    """Get graph data for knowledge graph visualization.

    Returns {"nodes": [...], "edges": [...]}.
    Nodes are pages, edges are links between them.
    """
    conn = get_connection()
    try:
        # Nodes: all pages
        page_rows = conn.execute("SELECT id, path, title FROM pages").fetchall()
        nodes = [{"id": r[0], "path": r[1], "title": r[2] or r[1]} for r in page_rows]

        # Build path->id map for resolving link targets
        path_to_id = {r[1]: r[0] for r in page_rows}
        stem_to_id = {}
        for r in page_rows:
            stem = Path(r[1]).stem
            if stem not in stem_to_id:
                stem_to_id[stem] = r[0]
        title_to_id = {}
        for r in page_rows:
            if r[2]:
                title_to_id[r[2]] = r[0]

        # Edges: links with resolved targets
        link_rows = conn.execute("""
            SELECT l.page_id, l.target
            FROM links l
        """).fetchall()

        edges = []
        seen = set()
        for source_id, target in link_rows:
            # Resolve target to page id
            target_id = path_to_id.get(target) or title_to_id.get(target) or stem_to_id.get(target)
            if target_id and target_id != source_id:
                key = (source_id, target_id)
                if key not in seen:
                    seen.add(key)
                    edges.append({"source": source_id, "target": target_id})

        return {"nodes": nodes, "edges": edges}
    finally:
        conn.close()
