# tests/test_paragraph_diff.py
import pytest
from nas_md.webserver.paragraph_diff import (
    split_paragraphs,
    compute_diff,
    apply_changes,
    merge_changes,
)


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


def test_merge_changes_no_overlap():
    """无段落重叠的changes应直接合并，全部保留。"""
    existing = [{"type": "replace", "paraIdx": 0, "content": "A2"}]
    incoming = [{"type": "replace", "paraIdx": 2, "content": "C2"}]
    merged = merge_changes(existing, incoming)
    assert len(merged) == 2
    idxs = {c["paraIdx"] for c in merged}
    assert idxs == {0, 2}


def test_merge_changes_overlap_replace():
    """同段落 replace 冲突，incoming 覆盖 existing（后写覆盖）。"""
    existing = [{"type": "replace", "paraIdx": 1, "content": "from_existing"}]
    incoming = [{"type": "replace", "paraIdx": 1, "content": "from_incoming"}]
    merged = merge_changes(existing, incoming)
    replaces = [c for c in merged if c["type"] == "replace" and c["paraIdx"] == 1]
    assert len(replaces) == 1
    assert replaces[0]["content"] == "from_incoming"


def test_merge_changes_insert_non_conflict():
    """insert 到不同位置应全部保留。"""
    existing = [{"type": "insert", "paraIdx": 0, "content": "X"}]
    incoming = [{"type": "insert", "paraIdx": 2, "content": "Y"}]
    merged = merge_changes(existing, incoming)
    assert len(merged) == 2


def test_merge_changes_empty_existing():
    """existing 为空时，merged = incoming。"""
    merged = merge_changes([], [{"type": "replace", "paraIdx": 0, "content": "A"}])
    assert len(merged) == 1
    assert merged[0]["content"] == "A"


def test_merge_changes_empty_incoming():
    """incoming 为空时，merged = existing。"""
    merged = merge_changes([{"type": "replace", "paraIdx": 0, "content": "A"}], [])
    assert len(merged) == 1
    assert merged[0]["content"] == "A"


def test_split_paragraphs_fenced_code_block_with_blank_lines():
    """Fenced code blocks with blank lines inside should NOT be split into multiple paragraphs."""
    text = (
        "Introduction paragraph.\n\n"
        "```python\n"
        "def foo():\n"
        "    x = 1\n"
        "\n"
        "    y = 2\n"
        "    return x + y\n"
        "```\n\n"
        "Conclusion paragraph."
    )
    paras = split_paragraphs(text)
    assert len(paras) == 3
    assert paras[0] == "Introduction paragraph."
    assert paras[1] == (
        "```python\n" "def foo():\n" "    x = 1\n" "\n" "    y = 2\n" "    return x + y\n" "```"
    )
    assert paras[2] == "Conclusion paragraph."


def test_split_paragraphs_tilde_code_block():
    """Tilde ~~~ code blocks should also be protected as atomic blocks."""
    text = (
        "Header\n\n" "~~~javascript\n" "const a = 1;\n" "\n" "console.log(a);\n" "~~~\n\n" "Footer"
    )
    paras = split_paragraphs(text)
    assert len(paras) == 3
    assert paras[1] == "~~~javascript\nconst a = 1;\n\nconsole.log(a);\n~~~"


def test_split_paragraphs_yaml_frontmatter():
    """YAML frontmatter with internal blank lines at document start should remain an atomic block."""
    text = (
        "---\n" "title: Doc Title\n" "\n" "tags:\n" "  - note\n" "---\n\n" "First body paragraph."
    )
    paras = split_paragraphs(text)
    assert len(paras) == 2
    assert paras[0] == "---\ntitle: Doc Title\n\ntags:\n  - note\n---"
    assert paras[1] == "First body paragraph."


def test_split_paragraphs_math_blocks():
    """Math blocks $$ with internal blank lines should remain atomic."""
    text = (
        "Math formula:\n\n"
        "$$\n"
        "\\begin{aligned}\n"
        "a &= b + c \\\\\n"
        "\n"
        "d &= e + f\n"
        "\\end{aligned}\n"
        "$$\n\n"
        "After formula."
    )
    paras = split_paragraphs(text)
    assert len(paras) == 3
    assert paras[1] == "$$\n\\begin{aligned}\na &= b + c \\\\\n\nd &= e + f\n\\end{aligned}\n$$"


def test_split_paragraphs_crlf_normalization():
    """CRLF line endings should be normalized without leaving trailing \\r."""
    text = "para one\r\n\r\npara two\r\n\r\npara three\r\n"
    paras = split_paragraphs(text)
    assert paras == ["para one", "para two", "para three"]
    assert all("\r" not in p for p in paras)


def test_compute_diff_and_apply_with_code_blocks():
    """Diff and apply_changes should work seamlessly with code blocks."""
    old_doc = (
        "Intro\n\n" "```python\n" "def hello():\n" "\n" "    print('world')\n" "```\n\n" "Outro"
    )
    new_doc = (
        "Intro\n\n"
        "```python\n"
        "def hello():\n"
        "\n"
        "    print('hello world')\n"
        "```\n\n"
        "New middle paragraph\n\n"
        "Outro"
    )
    changes = compute_diff(old_doc, new_doc)
    reconstructed = apply_changes(old_doc, changes)
    assert reconstructed == new_doc


def test_transform_changes_with_prior_insert():
    """Incoming changes on base text should shift offsets correctly when prior version inserted paragraphs."""
    from nas_md.webserver.paragraph_diff import transform_changes

    # Base: A (0), B (1), C (2)
    # Server accumulated: insert "X" at 0 -> server now has [X, A, B, C]
    accumulated = [{"type": "insert", "paraIdx": 0, "content": "X"}]
    # Incoming edit: user edited C (index 2 in base)
    incoming = [{"type": "replace", "paraIdx": 2, "content": "C2"}]

    transformed = transform_changes(incoming, accumulated)
    assert len(transformed) == 1
    assert transformed[0]["paraIdx"] == 3  # Shifted from 2 to 3
    assert transformed[0]["content"] == "C2"

    server_content = "X\n\nA\n\nB\n\nC"
    result = apply_changes(server_content, transformed)
    assert result == "X\n\nA\n\nB\n\nC2"


def test_transform_changes_with_prior_delete():
    """Incoming changes should adjust downwards when prior version deleted an earlier paragraph."""
    from nas_md.webserver.paragraph_diff import transform_changes

    # Base: A (0), B (1), C (2)
    # Server accumulated: delete A (0) -> server now has [B, C]
    accumulated = [{"type": "delete", "paraIdx": 0}]
    # Incoming edit: user edited C (index 2 in base)
    incoming = [{"type": "replace", "paraIdx": 2, "content": "C2"}]

    transformed = transform_changes(incoming, accumulated)
    assert len(transformed) == 1
    assert transformed[0]["paraIdx"] == 1  # Shifted from 2 to 1
    assert transformed[0]["content"] == "C2"

    server_content = "B\n\nC"
    result = apply_changes(server_content, transformed)
    assert result == "B\n\nC2"


def test_transform_changes_concurrent_both_insert():
    """Concurrent inserts at different positions should both be correctly preserved."""
    from nas_md.webserver.paragraph_diff import transform_changes

    # Base: A (0), B (1)
    # User 1 inserted X at 0 -> [X, A, B]
    accumulated = [{"type": "insert", "paraIdx": 0, "content": "X"}]
    # User 2 inserted Y at 1 (before B in base)
    incoming = [{"type": "insert", "paraIdx": 1, "content": "Y"}]

    transformed = transform_changes(incoming, accumulated)
    assert len(transformed) == 1
    assert transformed[0]["paraIdx"] == 2  # Shifted to index 2 (before B in server doc)

    server_content = "X\n\nA\n\nB"
    result = apply_changes(server_content, transformed)
    assert result == "X\n\nA\n\nY\n\nB"


def test_apply_changes_preserves_multiline_blank_delimiters():
    """Applying a diff to one paragraph must not collapse multi-line blank delimiters in untouched paragraphs."""
    doc = "# Title\n\n\n\n## Section 1\n\n---\n\n\n\n### Step 1\n\nParagraph to edit\n\n\n\n### Step 2\n\nUntouched\n"
    diff = compute_diff(doc, doc.replace("Paragraph to edit", "Paragraph EDITED"))
    assert len(diff) == 1
    assert diff[0]["type"] == "replace"

    result = apply_changes(doc, diff)
    assert (
        result
        == "# Title\n\n\n\n## Section 1\n\n---\n\n\n\n### Step 1\n\nParagraph EDITED\n\n\n\n### Step 2\n\nUntouched\n"
    )

    # Undo
    undo_diff = compute_diff(result, doc)
    undo_result = apply_changes(result, undo_diff)
    assert undo_result == doc


def test_repeated_subheadings_diff_locality():
    """Repeated subheadings and dividers must not cause distant LCS jumps."""
    doc = (
        "---\n\n"
        "### STEP 1\n\n"
        "Content A\n\n"
        "---\n\n"
        "### STEP 1\n\n"
        "Content B\n\n"
        "---\n\n"
        "### STEP 1\n\n"
        "Content C\n\n"
    )
    # Edit the first Content A
    edited = doc.replace("Content A", "Content A MODIFIED")
    diff = compute_diff(doc, edited)
    assert len(diff) == 1
    assert diff[0]["type"] == "replace"
    assert diff[0]["paraIdx"] == 2
    assert diff[0]["content"] == "Content A MODIFIED"

    applied = apply_changes(doc, diff)
    assert applied == edited
