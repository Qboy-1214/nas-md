"""Tests for pkg/txt/md module."""

from nas_md.pkg.txt.md import (
    strip_chat_timestamp,
    add_header_and_text,
    incomplete_checklist_items,
    checklist_items,
    add_checklist_item,
    complete_checklist_item,
    remove_checklist_item,
    remove_completed_checklist_items,
    checklist_item,
    markdown_to_html,
    _hash,
)


class TestStripChatTimestamp:
    def test_with_timestamp(self):
        assert strip_chat_timestamp("`12:34` Hello") == "Hello"

    def test_without_timestamp(self):
        assert strip_chat_timestamp("Hello") == "Hello"

    def test_empty(self):
        assert strip_chat_timestamp("") == ""


class TestAddHeaderAndText:
    def test_new_header(self):
        result = add_header_and_text("", "## Header", "Content")
        assert "## Header" in result
        assert "Content" in result

    def test_existing_header(self):
        existing = "## Header\nOld content"
        result = add_header_and_text(existing, "## Header", "New content")
        assert "New content" in result
        assert "Old content" in result

    def test_empty_existing(self):
        result = add_header_and_text("", "## Header", "Content")
        assert result == "## Header\nContent"


class TestChecklistItems:
    def test_empty(self):
        items, completed = checklist_items("")
        assert items == []
        assert completed == {}

    def test_unchecked(self):
        md = "- [ ] Task 1\n- [ ] Task 2"
        items, completed = checklist_items(md)
        assert len(items) == 2
        assert completed["Task 1"] is False
        assert completed["Task 2"] is False

    def test_checked(self):
        md = "- [x] Done"
        items, completed = checklist_items(md)
        assert len(items) == 1
        assert completed["Done"] is True

    def test_mixed(self):
        md = "- [ ] Todo\n- [x] Done"
        items, completed = checklist_items(md)
        assert len(items) == 2
        assert completed["Todo"] is False
        assert completed["Done"] is True


class TestIncompleteChecklistItems:
    def test_all_incomplete(self):
        md = "- [ ] A\n- [ ] B"
        result = incomplete_checklist_items(md)
        assert result == ["A", "B"]

    def test_some_complete(self):
        md = "- [ ] A\n- [x] B\n- [ ] C"
        result = incomplete_checklist_items(md)
        assert "A" in result
        assert "C" in result
        assert "B" not in result


class TestAddChecklistItem:
    def test_add_unchecked(self):
        result = add_checklist_item("", "New task", False)
        assert "- [ ] New task" in result

    def test_add_checked(self):
        result = add_checklist_item("", "Done task", True)
        assert "- [x] Done task" in result

    def test_duplicate_removed(self):
        md = "- [ ] Task"
        result = add_checklist_item(md, "Task", False)
        assert result.count("- [ ] Task") == 1


class TestCompleteChecklistItem:
    def test_complete(self):
        md = "- [ ] Task"
        item_hash = _hash("Task")
        result, item = complete_checklist_item(md, item_hash)
        assert "- [x] Task" in result
        assert item == "Task"

    def test_not_found(self):
        md = "- [ ] Task"
        _result, item = complete_checklist_item(md, "nonexistent")
        assert item == ""


class TestRemoveChecklistItem:
    def test_remove_by_name(self):
        md = "- [ ] Keep\n- [ ] Remove"
        result, removed = remove_checklist_item(md, "Remove")
        assert "Remove" not in result
        assert "Keep" in result
        assert removed == "Remove"

    def test_remove_by_hash(self):
        md = "- [ ] Task"
        item_hash = _hash("Task")
        _result, removed = remove_checklist_item(md, item_hash)
        assert removed == "Task"


class TestRemoveCompletedChecklistItems:
    def test_remove_completed(self):
        md = "- [ ] Keep\n- [x] Remove"
        result, removed = remove_completed_checklist_items(md)
        assert "Keep" in result
        assert "Remove" not in result
        assert "- [x] Remove" in removed


class TestChecklistItem:
    def test_find_by_name(self):
        md = "- [ ] My Task"
        assert checklist_item(md, "My Task") == "My Task"

    def test_find_by_hash(self):
        md = "- [ ] My Task"
        item_hash = _hash("My Task")
        assert checklist_item(md, item_hash) == "My Task"

    def test_not_found(self):
        assert checklist_item("- [ ] A", "B") == ""


class TestMarkdownToHtml:
    def test_bold(self):
        result = markdown_to_html("**bold**")
        assert "<b>bold</b>" in result

    def test_italic(self):
        result = markdown_to_html("*italic*")
        assert "<i>italic</i>" in result

    def test_code_block(self):
        result = markdown_to_html("```\ncode\n```")
        assert "<pre>" in result

    def test_inline_code(self):
        result = markdown_to_html("`code`")
        assert "<code>code</code>" in result

    def test_header(self):
        result = markdown_to_html("# Title")
        assert "<b>Title</b>" in result

    def test_plain_text(self):
        result = markdown_to_html("Hello World")
        assert "Hello World" in result

    def test_empty(self):
        assert markdown_to_html("") == ""
