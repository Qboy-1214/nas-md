# tests/test_paragraph_diff.py
import pytest
from nas_md.webserver.paragraph_diff import split_paragraphs, compute_diff


def test_split_paragraphs_basic():
    text = "para one\n\npara two\n\npara three"
    assert split_paragraphs(text) == ["para one", "para two", "para three"]


def test_split_paragraphs_trailing_newline():
    text = "para one\n\npara two\n\n"
    assert split_paragraphs(text) == ["para one", "para two"]


def test_split_paragraphs_empty():
    assert split_paragraphs("") == []


def test_compute_diff_no_change():
    text = "para one\n\npara two"
    assert compute_diff(text, text) == []


def test_compute_diff_replace():
    old = "para one\n\npara two\n\npara three"
    new = "para one\n\nCHANGED\n\npara three"
    changes = compute_diff(old, new)
    assert len(changes) == 1
    assert changes[0]["type"] == "replace"
    assert changes[0]["paraIdx"] == 1
    assert changes[0]["content"] == "CHANGED"


def test_compute_diff_insert():
    old = "para one\n\npara three"
    new = "para one\n\npara two\n\npara three"
    changes = compute_diff(old, new)
    assert any(c["type"] == "insert" for c in changes)


def test_compute_diff_delete():
    old = "para one\n\npara two\n\npara three"
    new = "para one\n\npara three"
    changes = compute_diff(old, new)
    assert any(c["type"] == "delete" for c in changes)


def test_compute_diff_multiple_changes():
    old = "A\n\nB\n\nC\n\nD"
    new = "A\n\nB2\n\nC\n\nE"
    changes = compute_diff(old, new)
    types = {c["type"] for c in changes}
    assert "replace" in types
    # B->B2 and D->E are both 1-to-1 replacements (equal length)
    assert len(changes) >= 2


from nas_md.webserver.paragraph_diff import apply_changes


def test_apply_changes_replace():
    """apply_changes 应将 replace change 应用到文本。"""
    text = "para one\n\npara two\n\npara three"
    changes = [{"type": "replace", "paraIdx": 1, "content": "CHANGED"}]
    result = apply_changes(text, changes)
    assert result == "para one\n\nCHANGED\n\npara three"


def test_apply_changes_insert():
    """apply_changes 应在指定位置插入段落。"""
    text = "para one\n\npara three"
    changes = [{"type": "insert", "paraIdx": 1, "content": "para two"}]
    result = apply_changes(text, changes)
    assert result == "para one\n\npara two\n\npara three"


def test_apply_changes_delete():
    """apply_changes 应删除指定段落。"""
    text = "para one\n\npara two\n\npara three"
    changes = [{"type": "delete", "paraIdx": 1}]
    result = apply_changes(text, changes)
    assert result == "para one\n\npara three"


def test_apply_changes_empty_changes():
    """空 changes 列表应返回原文本。"""
    text = "para one\n\npara two"
    result = apply_changes(text, [])
    assert result == text


def test_apply_changes_multiple():
    """多个 changes 应按顺序应用（paraIdx基于原文本位置）。"""
    text = "A\n\nB\n\nC"
    changes = [
        {"type": "replace", "paraIdx": 0, "content": "A2"},
        {"type": "insert", "paraIdx": 2, "content": "B2"},
    ]
    result = apply_changes(text, changes)
    assert result == "A2\n\nB\n\nB2\n\nC"


def test_apply_changes_para_idx_out_of_range():
    """paraIdx 越界时 replace 应忽略，insert 应追加到末尾。"""
    text = "para one"
    changes = [
        {"type": "replace", "paraIdx": 5, "content": "X"},
        {"type": "insert", "paraIdx": 10, "content": "appended"},
    ]
    result = apply_changes(text, changes)
    assert result == "para one\n\nappended"
