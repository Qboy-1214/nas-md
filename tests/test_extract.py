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
