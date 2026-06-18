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
