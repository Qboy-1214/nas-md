import json
from pathlib import Path

import pytest
from nas_md.webserver import paragraph_diff
from nas_md.webserver.paragraph_diff import (
    split_paragraphs,
    split_paragraphs_with_delims,
    compute_diff,
    apply_changes,
    merge_changes,
)

PARAGRAPH_SPLIT_CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "paragraph_split_cases.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize(
    "case",
    PARAGRAPH_SPLIT_CASES,
    ids=[case["name"] for case in PARAGRAPH_SPLIT_CASES],
)
def test_split_paragraphs_shared_contract(case):
    assert split_paragraphs(case["text"]) == case["paragraphs"]


@pytest.mark.parametrize(
    "case",
    [case for case in PARAGRAPH_SPLIT_CASES if "delimiters" in case],
    ids=[case["name"] for case in PARAGRAPH_SPLIT_CASES if "delimiters" in case],
)
def test_lossless_parser_reconstructs_normalized_input(case):
    parse_document = getattr(paragraph_diff, "_parse_document", None)
    assert callable(parse_document), "lossless document parser is missing"

    parsed = parse_document(case["text"])
    paragraphs, delimiters = split_paragraphs_with_delims(case["text"])

    assert parsed.prefix == case.get("prefix", "")
    assert parsed.paragraphs == case["paragraphs"]
    assert parsed.delimiters == case["delimiters"]
    assert paragraphs == case["paragraphs"]
    assert delimiters == case["delimiters"]
    assert (
        parsed.prefix
        + "".join(
            paragraph + parsed.delimiters[idx] for idx, paragraph in enumerate(parsed.paragraphs)
        )
        == case["text"]
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


@pytest.mark.parametrize(
    ("base", "target"),
    [
        ("A\n\nB\n\nC", "A\n\nB"),
        ("A\n\nB", "A\n\nB\n"),
        ("A\n\nB", "A\n\n\n\nB"),
        ("---\ntitle: Doc\n---\nBody", "---\ntitle: Doc\n---\n\nBody"),
        ("A", ""),
        ("", "\nA"),
        ("\nA", ""),
        ("", " \nA"),
        ("A", "A\nB"),
        ("A", "A\n \nB"),
        ("A\n \nB", "A"),
        ("", "\n"),
        ("\n", ""),
        ("", " \n"),
        (" \n", ""),
        ("", "\n\n\n"),
        ("\n", "---\nx: y\n---\nA"),
    ],
    ids=[
        "delete-final-paragraph",
        "add-trailing-newline",
        "change-blank-line-delimiter",
        "change-frontmatter-boundary",
        "empty-content",
        "leading-blank-content",
        "delete-leading-blank-content",
        "leading-whitespace-content",
        "single-newline-separator",
        "whitespace-separator",
        "delete-whitespace-separated-paragraph",
        "blank-only-content",
        "delete-blank-only-content",
        "blank-only-whitespace-content",
        "delete-blank-only-whitespace-content",
        "multiple-blank-lines",
        "blank-prefix-to-frontmatter",
    ],
)
def test_compute_diff_apply_round_trips_exact_content(base, target):
    changes = compute_diff(base, target)

    assert apply_changes(base, changes) == target


@pytest.mark.parametrize(
    ("name", "character"),
    [
        ("next-line", "\u0085"),
        ("no-break-space", "\u00a0"),
        ("vertical-tab", "\u000b"),
        ("byte-order-mark", "\ufeff"),
    ],
)
def test_non_markdown_line_whitespace_has_stable_diff_coordinates(name, character):
    base = f"{character}\nA"
    target = f"{character}\nB"
    expected = [
        {
            "type": "replace",
            "paraIdx": 0,
            "content": target,
            "delimiter": "",
        }
    ]

    changes = compute_diff(base, target)

    assert changes == expected, name
    assert apply_changes(base, changes) == target


def test_compute_diff_replace():
    old = "para one\n\npara two\n\npara three"
    new = "para one\n\nCHANGED\n\npara three"
    changes = compute_diff(old, new)
    assert len(changes) == 1
    assert changes[0]["type"] == "replace"
    assert changes[0]["paraIdx"] == 1
    assert changes[0]["content"] == "CHANGED"


def test_compute_diff_uses_dedicated_delimiter_change_without_stale_text():
    from nas_md.webserver.paragraph_diff import transform_changes

    changes = compute_diff("A\n\nB", "A\n\n\nB")

    assert changes == [{"type": "delimiter", "paraIdx": 0, "delimiter": "\n\n\n"}]
    transformed = transform_changes(
        changes,
        [{"type": "replace", "paraIdx": 0, "content": "A-remote", "delimiter": "\n\n"}],
        base_para_count=2,
    )
    assert transformed == changes
    assert apply_changes("A-remote\n\nB", transformed) == "A-remote\n\n\nB"
    assert (
        transform_changes(
            [{"type": "delimiter", "paraIdx": 1, "delimiter": ""}],
            [{"type": "delete", "paraIdx": 1}],
            base_para_count=2,
        )
        == []
    )


def test_transform_delimiter_change_maps_position_and_preserves_metadata():
    from nas_md.webserver.paragraph_diff import transform_changes

    transformed = transform_changes(
        [
            {
                "type": "delimiter",
                "paraIdx": 1,
                "delimiter": "\n",
                "operationId": "local-format-1",
            }
        ],
        [{"type": "insert", "paraIdx": 0, "content": "HEADER"}],
        base_para_count=2,
    )

    assert transformed == [
        {
            "type": "delimiter",
            "paraIdx": 2,
            "delimiter": "\n",
            "operationId": "local-format-1",
        }
    ]


def test_transform_prefix_change_is_coordinate_independent_and_preserves_metadata():
    from nas_md.webserver.paragraph_diff import transform_changes

    incoming = [
        {
            "type": "prefix",
            "content": "\n",
            "operationId": "local-prefix-1",
        }
    ]
    transformed = transform_changes(
        incoming,
        [
            {"type": "prefix", "content": " \n"},
            {"type": "insert", "paraIdx": 0, "content": "HEADER"},
        ],
        base_para_count=2,
    )

    assert transformed == incoming


def test_compute_diff_multi_paragraph_replacement_has_deterministic_operations():
    assert compute_diff("A\n\nB", "X\n\nY") == [
        {"type": "replace", "paraIdx": 0, "content": "X", "delimiter": "\n\n"},
        {"type": "replace", "paraIdx": 1, "content": "Y", "delimiter": ""},
    ]


def test_compute_diff_prefix_and_multi_paragraph_operations_are_deterministic():
    assert compute_diff("\nA\n\nB", " \nX\n \nY") == [
        {"type": "prefix", "content": " \n"},
        {"type": "replace", "paraIdx": 0, "content": "X", "delimiter": "\n \n"},
        {"type": "replace", "paraIdx": 1, "content": "Y", "delimiter": ""},
    ]


def test_apply_changes_does_not_rewrite_explicit_delimiter_before_trailing_insert():
    changes = [
        {"type": "delimiter", "paraIdx": 0, "delimiter": "\n"},
        {"type": "insert", "paraIdx": 1, "content": "B", "delimiter": ""},
    ]

    assert apply_changes("A", changes) == "A\nB"


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


def test_transform_changes_batch_uses_base_coordinates_for_multiple_inserts():
    from nas_md.webserver.paragraph_diff import transform_changes

    incoming = [{"type": "replace", "paraIdx": 1, "content": "B-local"}]
    accumulated = [
        {"type": "insert", "paraIdx": 0, "content": "X"},
        {"type": "insert", "paraIdx": 2, "content": "Y"},
    ]

    transformed = transform_changes(incoming, accumulated, base_para_count=3)

    assert transformed == [{"type": "replace", "paraIdx": 2, "content": "B-local"}]
    assert apply_changes("X\n\nA\n\nB\n\nY\n\nC", transformed) == ("X\n\nA\n\nB-local\n\nY\n\nC")


def test_transform_changes_batch_handles_adjacent_remote_deletes():
    from nas_md.webserver.paragraph_diff import transform_changes

    incoming = [{"type": "replace", "paraIdx": 2, "content": "C-local"}]
    accumulated = [
        {"type": "delete", "paraIdx": 1},
        {"type": "delete", "paraIdx": 2},
    ]

    transformed = transform_changes(incoming, accumulated, base_para_count=4)

    assert transformed == [{"type": "insert", "paraIdx": 1, "content": "C-local"}]
    assert apply_changes("A\n\nD", transformed) == "A\n\nC-local\n\nD"


def test_transform_changes_batch_handles_mixed_remote_insert_and_delete():
    from nas_md.webserver.paragraph_diff import transform_changes

    incoming = [{"type": "replace", "paraIdx": 0, "content": "A-local"}]
    accumulated = [
        {"type": "insert", "paraIdx": 0, "content": "X"},
        {"type": "delete", "paraIdx": 1},
    ]

    transformed = transform_changes(incoming, accumulated, base_para_count=4)

    assert transformed == [{"type": "replace", "paraIdx": 1, "content": "A-local"}]
    assert apply_changes("X\n\nA\n\nC\n\nD", transformed) == ("X\n\nA-local\n\nC\n\nD")


def test_transform_changes_batch_orders_local_inserts_after_remote_inserts():
    from nas_md.webserver.paragraph_diff import transform_changes

    incoming = [
        {"type": "insert", "paraIdx": 1, "content": "L1"},
        {"type": "insert", "paraIdx": 1, "content": "L2"},
    ]
    accumulated = [
        {"type": "insert", "paraIdx": 1, "content": "R1"},
        {"type": "insert", "paraIdx": 1, "content": "R2"},
    ]

    transformed = transform_changes(incoming, accumulated, base_para_count=2)

    assert transformed == [
        {"type": "insert", "paraIdx": 3, "content": "L1"},
        {"type": "insert", "paraIdx": 3, "content": "L2"},
    ]
    assert apply_changes("A\n\nR1\n\nR2\n\nB", transformed) == ("A\n\nR1\n\nR2\n\nL1\n\nL2\n\nB")


@pytest.mark.parametrize(
    "incoming,accumulated,base_count,error",
    [
        ([], [], "3", TypeError),
        ([], [], -1, ValueError),
        ([], [], 2**53, ValueError),
        ([{"type": "replace", "paraIdx": -1, "content": "X"}], [], 1, ValueError),
        ([{"type": "insert", "paraIdx": 2, "content": "X"}], [], 1, ValueError),
        ([{"type": "replace", "paraIdx": 1, "content": "X"}], [], 1, ValueError),
        ([{"type": "unknown", "paraIdx": 0}], [], 1, ValueError),
        ([{"type": "insert", "paraIdx": 0, "content": 7}], [], 1, TypeError),
        (
            [{"type": "replace", "paraIdx": 0, "content": "X", "delimiter": 7}],
            [],
            1,
            TypeError,
        ),
        ([{"type": "delete", "paraIdx": 0, "delimiter": ""}], [], 1, ValueError),
        ([{"type": "delimiter", "paraIdx": 0}], [], 1, TypeError),
        ([{"type": "delimiter", "paraIdx": 0, "delimiter": 7}], [], 1, TypeError),
        (
            [{"type": "delimiter", "paraIdx": 0, "delimiter": "\n", "content": "X"}],
            [],
            1,
            ValueError,
        ),
        ([{"type": "delimiter", "paraIdx": 1, "delimiter": "\n"}], [], 1, ValueError),
        ([{"type": "prefix"}], [], 1, TypeError),
        ([{"type": "prefix", "content": 7}], [], 1, TypeError),
        ([{"type": "prefix", "content": "\n", "paraIdx": 0}], [], 1, ValueError),
        ([{"type": "prefix", "content": "\n", "delimiter": ""}], [], 1, ValueError),
        ([], [{"type": "delete", "paraIdx": -1}], 1, ValueError),
        (
            [{"type": "insert", "paraIdx": 2**53, "content": "X"}],
            [],
            2**53 - 1,
            ValueError,
        ),
    ],
    ids=[
        "base-count-type",
        "negative-base-count",
        "unsafe-base-count",
        "negative-index",
        "insert-past-end",
        "replace-at-end",
        "unknown-type",
        "non-string-content",
        "non-string-delimiter",
        "delete-with-delimiter",
        "delimiter-change-missing-delimiter",
        "delimiter-change-non-string-delimiter",
        "delimiter-change-with-content",
        "delimiter-change-at-end",
        "prefix-change-missing-content",
        "prefix-change-non-string-content",
        "prefix-change-with-index",
        "prefix-change-with-delimiter",
        "invalid-accumulated-change",
        "unsafe-change-index",
    ],
)
def test_transform_changes_rejects_invalid_input(incoming, accumulated, base_count, error):
    from nas_md.webserver.paragraph_diff import transform_changes

    with pytest.raises(error):
        transform_changes(incoming, accumulated, base_para_count=base_count)


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
