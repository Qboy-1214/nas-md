"""Full-text search module for nas-md using SQLite FTS5."""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger("search")

# Default database path — can be overridden via SEARCH_DB env
DEFAULT_DB_PATH = os.path.join(os.getcwd(), "search.db")


def get_db_path() -> str:
    """Get the search database path."""
    return os.environ.get("SEARCH_DB", DEFAULT_DB_PATH)


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    """Get a SQLite connection with FTS5 support."""
    path = db_path or get_db_path()
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
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
                tokenize='unicode61'
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
        conn.commit()
        logger.info("Search database initialized at %s", db_path or get_db_path())
    finally:
        conn.close()


def index_file(path: str, content: str) -> None:
    """Index or re-index a single file."""
    conn = get_connection()
    try:
        # Extract title from first heading or filename
        title = _extract_title(content, path)
        filename = os.path.basename(path)
        content_hash = str(hash(content))
        now = int(os.path.getmtime(path) * 1000) if os.path.exists(path) else 0

        conn.execute("""
            INSERT INTO pages (path, filename, title, content, content_hash, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                title=excluded.title,
                content=excluded.content,
                content_hash=excluded.content_hash,
                updated_at=excluded.updated_at
        """, (path, filename, title, content, content_hash, now))
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
    conn = get_connection()
    try:
        # Use FTS5 query with prefix matching
        fts_query = f"{query}*"
        rows = conn.execute("""
            SELECT p.path, p.filename, p.title,
                   snippet(pages_fts, 2, '<mark>', '</mark>', '...', 32) as snippet,
                   rank
            FROM pages_fts
            JOIN pages p ON p.id = pages_fts.rowid
            WHERE pages_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (fts_query, limit)).fetchall()

        results = []
        for row in rows:
            results.append({
                "path": row[0],
                "filename": row[1],
                "title": row[2] or row[1],
                "snippet": row[3] or "",
                "rank": row[4],
            })
        return results
    except Exception as e:
        logger.error("Search error: %s", e)
        return []
    finally:
        conn.close()


def rebuild_index(directories: list[str]) -> int:
    """Rebuild the entire search index from scratch."""
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
                    title = _extract_title(content, rel_path)
                    filename = md_file.name
                    content_hash = str(hash(content))
                    updated_at = int(md_file.stat().st_mtime * 1000)

                    conn.execute("""
                        INSERT INTO pages (path, filename, title, content, content_hash, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (rel_path, filename, title, content, content_hash, updated_at))
                    count += 1
                except Exception as e:
                    logger.warning("Failed to index %s: %s", md_file, e)

        conn.commit()
        logger.info("Indexed %d files", count)

        # Store index metadata
        conn.execute("""
            INSERT OR REPLACE INTO index_meta (key, value)
            VALUES ('last_rebuild', ?)
        """, (str(int(time.time() * 1000)),))
        conn.execute("""
            INSERT OR REPLACE INTO index_meta (key, value)
            VALUES ('file_count', ?)
        """, (str(count),))
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

        return {
            "file_count": count,
            "last_rebuild": meta.get("last_rebuild", ""),
        }
    finally:
        conn.close()
