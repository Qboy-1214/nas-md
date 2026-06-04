"""Tests for search module - SQLite FTS5 full-text search."""

import json
import os
import tempfile

import pytest

from nas_md.search import (
    get_connection,
    get_graph_data,
    get_stats,
    index_file,
    init_db,
    query_backlinks,
    query_headings,
    query_links,
    query_tags,
    query_tasks,
    rebuild_index,
    remove_file,
    search,
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
        assert "tags" in table_names
        assert "tasks" in table_names
        assert "headings" in table_names
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


class TestObjectIndexing:
    def test_index_file_with_frontmatter(self, search_db):
        content = "---\ntitle: My Note\ntags: [project, active]\n---\n# My Note\nSome text."
        index_file("/note.md", content)
        conn = get_connection(search_db)
        row = conn.execute("SELECT frontmatter FROM pages WHERE path = '/note.md'").fetchone()
        conn.close()
        assert row[0] is not None
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

    def test_query_headings_all(self, search_db):
        index_file("/a.md", "# Page A\n## Section")
        index_file("/b.md", "# Page B")
        headings = query_headings()
        assert len(headings) == 3

    def test_query_tags_count(self, search_db):
        index_file("/a.md", "# A\n#project\n#python")
        index_file("/b.md", "# B\n#project")
        tags = query_tags()
        project_tag = next(t for t in tags if t["name"] == "project")
        assert project_tag["count"] == 2


class TestLinksIndexing:
    def test_index_file_extracts_links(self, search_db):
        index_file("/a.md", "# A\nSee [[B]] for details.")
        links = query_links("/a.md")
        assert len(links) == 1
        assert links[0]["target"] == "B"
        assert links[0]["display_text"] is None

    def test_index_file_extracts_links_with_display(self, search_db):
        index_file("/a.md", "# A\nSee [[B|beta]] for details.")
        links = query_links("/a.md")
        assert len(links) == 1
        assert links[0]["target"] == "B"
        assert links[0]["display_text"] == "beta"

    def test_query_backlinks(self, search_db):
        index_file("/a.md", "# Page A\nSee [[B]] here.")
        index_file("/b.md", "# Page B\nContent")
        backlinks = query_backlinks("/b.md")
        assert len(backlinks) == 1
        assert backlinks[0]["path"] == "/a.md"
        assert backlinks[0]["target"] == "B"

    def test_query_backlinks_by_title(self, search_db):
        index_file("/a.md", "# A\nSee [[Page B]] here.")
        index_file("/b.md", "# Page B\nContent")
        backlinks = query_backlinks("/b.md")
        assert len(backlinks) == 1
        assert backlinks[0]["path"] == "/a.md"

    def test_query_backlinks_no_results(self, search_db):
        index_file("/a.md", "# A\nNo links here.")
        index_file("/b.md", "# B\nContent")
        backlinks = query_backlinks("/b.md")
        assert len(backlinks) == 0

    def test_remove_file_cascades_links(self, search_db):
        index_file("/a.md", "# A\nSee [[B]].")
        conn = get_connection()
        try:
            count_before = conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]
            assert count_before == 1
        finally:
            conn.close()
        remove_file("/a.md")
        conn = get_connection()
        try:
            count_after = conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]
            assert count_after == 0
        finally:
            conn.close()

    def test_reindex_updates_links(self, search_db):
        index_file("/a.md", "# A\nSee [[B]].")
        assert len(query_links("/a.md")) == 1
        index_file("/a.md", "# A\nSee [[C]] and [[D]].")
        links = query_links("/a.md")
        assert len(links) == 2
        targets = {l["target"] for l in links}
        assert targets == {"C", "D"}

    def test_query_links_all(self, search_db):
        index_file("/a.md", "# A\n[[B]]")
        index_file("/c.md", "# C\n[[D]]")
        links = query_links()
        assert len(links) == 2


class TestStatsAndGraph:
    def test_get_stats_basic(self, search_db):
        index_file("/a.md", "# A\n- [x] Task1\n- [ ] Task2\n#tag1")
        stats = get_stats()
        assert stats["file_count"] == 1
        assert stats["task_total"] == 2
        assert stats["task_done"] == 1
        assert stats["tag_count"] == 1

    def test_get_stats_recent_pages(self, search_db):
        index_file("/a.md", "# Page A")
        index_file("/b.md", "# Page B")
        stats = get_stats()
        assert len(stats["recent_pages"]) == 2

    def test_get_stats_empty(self, search_db):
        stats = get_stats()
        assert stats["file_count"] == 0
        assert stats["task_total"] == 0
        assert stats["tag_count"] == 0
        assert stats["link_count"] == 0

    def test_get_graph_data_basic(self, search_db):
        index_file("/a.md", "# A\nSee [[B]]")
        index_file("/b.md", "# B\nContent")
        data = get_graph_data()
        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 1
        assert data["edges"][0]["source"] != data["edges"][0]["target"]

    def test_get_graph_data_no_links(self, search_db):
        index_file("/a.md", "# A\nNo links")
        data = get_graph_data()
        assert len(data["nodes"]) == 1
        assert len(data["edges"]) == 0

    def test_get_graph_data_empty(self, search_db):
        data = get_graph_data()
        assert data["nodes"] == []
        assert data["edges"] == []

    def test_get_graph_data_multiple_links(self, search_db):
        index_file("/a.md", "# A\n[[B]] and [[C]]")
        index_file("/b.md", "# B\n[[C]]")
        index_file("/c.md", "# C\nContent")
        data = get_graph_data()
        assert len(data["nodes"]) == 3
        assert len(data["edges"]) == 3  # A->B, A->C, B->C
