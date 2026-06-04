"""Tests for search module - SQLite FTS5 full-text search."""

import os
import tempfile
import pytest

from nas_md.search import (
    init_db,
    index_file,
    remove_file,
    search,
    rebuild_index,
    get_stats,
    get_connection,
)


@pytest.fixture
def search_db(tmp_path):
    """Create a temporary search database."""
    db_path = str(tmp_path / "test_search.db")
    os.environ["SEARCH_DB"] = db_path
    init_db(db_path)
    yield db_path
    # Cleanup
    os.environ.pop("SEARCH_DB", None)
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def sample_dir(tmp_path):
    """Create a directory with sample markdown files."""
    d = tmp_path / "notes"
    d.mkdir()

    (d / "python_basics.md").write_text(
        "# Python Basics\n\nPython is a great programming language.\n"
        "It supports object oriented programming and functional programming.\n"
    )
    (d / "godot_game.md").write_text(
        "# Godot Game Development\n\nGodot is a free game engine.\n"
        "It uses GDScript which is similar to Python.\n"
    )
    (d / "daily_journal.md").write_text(
        "## 23 May, Friday\n\nToday I worked on the nas-md project.\n"
        "Added search functionality using SQLite FTS5.\n"
    )
    (d / "empty.md").write_text("")

    return str(d)


class TestSearchInit:
    def test_init_db(self, search_db):
        conn = get_connection(search_db)
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = [t[0] for t in tables]
        assert "pages" in table_names
        assert "pages_fts" in table_names
        assert "index_meta" in table_names
        conn.close()

    def test_init_db_idempotent(self, search_db):
        # Should not fail on second call
        init_db(search_db)
        stats = get_stats()
        assert stats["file_count"] == 0


class TestSearchIndex:
    def test_index_file(self, search_db, sample_dir):
        index_file("/test.md", "# Hello World\nThis is a test.")
        stats = get_stats()
        assert stats["file_count"] == 1

    def test_index_multiple_files(self, search_db, sample_dir):
        for name in ["a.md", "b.md", "c.md"]:
            index_file(f"/{name}", f"# File {name}\nContent for {name}.")
        stats = get_stats()
        assert stats["file_count"] == 3

    def test_reindex_updates(self, search_db):
        index_file("/test.md", "# Original\nOld content.")
        index_file("/test.md", "# Updated\nNew content.")
        stats = get_stats()
        assert stats["file_count"] == 1  # Still 1, not 2

    def test_remove_file(self, search_db):
        index_file("/test.md", "# Hello\nContent.")
        remove_file("/test.md")
        stats = get_stats()
        assert stats["file_count"] == 0

    def test_extract_title_from_heading(self, search_db):
        index_file("/myfile.md", "# My Title\nSome content.")
        results = search("Title", limit=5)
        assert len(results) == 1
        assert results[0]["title"] == "My Title"

    def test_extract_title_fallback_to_filename(self, search_db):
        index_file("/myfile.md", "No heading here, just content.")
        results = search("content", limit=5)
        assert len(results) == 1
        assert results[0]["title"] == "myfile"


class TestSearchQuery:
    def test_basic_search(self, search_db, sample_dir):
        for name in ["a.md", "b.md", "c.md"]:
            index_file(f"/{name}", f"# File {name}\nContent about {name}.")
        results = search("Content", limit=10)
        assert len(results) == 3

    def test_search_by_heading(self, search_db, sample_dir):
        index_file("/python.md", "# Python Guide\nLearn Python.")
        index_file("/godot.md", "# Godot Guide\nLearn Godot.")
        results = search("Python", limit=10)
        assert len(results) == 1
        assert results[0]["path"] == "/python.md"

    def test_search_limit(self, search_db):
        for i in range(10):
            index_file(f"/file{i}.md", f"# File {i}\nContent number {i}.")
        results = search("Content", limit=3)
        assert len(results) == 3

    def test_search_no_results(self, search_db):
        index_file("/test.md", "# Hello\nWorld.")
        results = search("nonexistent", limit=10)
        assert len(results) == 0

    def test_search_empty_query(self, search_db):
        index_file("/test.md", "# Hello\nWorld.")
        results = search("", limit=10)
        assert len(results) == 0

    def test_search_result_structure(self, search_db):
        index_file("/test.md", "# Test\nHello World.")
        results = search("Hello", limit=5)
        assert len(results) == 1
        r = results[0]
        assert "path" in r
        assert "title" in r
        assert "snippet" in r
        assert "rank" in r


class TestRebuildIndex:
    def test_rebuild_from_directory(self, search_db, sample_dir):
        count = rebuild_index([sample_dir])
        assert count >= 3  # At least the 3 non-empty files
        stats = get_stats()
        assert stats["file_count"] >= 3

    def test_rebuild_clears_old(self, search_db, sample_dir):
        index_file("/old.md", "# Old\nThis should be removed.")
        rebuild_index([sample_dir])
        results = search("removed", limit=10)
        assert len(results) == 0

    def test_rebuild_nonexistent_dir(self, search_db):
        count = rebuild_index(["/nonexistent/path/that/does/not/exist"])
        assert count == 0


class TestSearchWithChinese:
    def test_chinese_content(self, search_db):
        index_file("/中文.md", "# 中文笔记\n这是一个测试。\nPython 编程很好玩。")
        results = search("中文", limit=5)
        assert len(results) >= 1

    def test_chinese_mixed_search(self, search_db):
        index_file("/mixed.md", "# 混合内容\nPython 和 Godot 都是好工具。")
        results = search("Python", limit=5)
        assert len(results) >= 1
