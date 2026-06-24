# tests/test_sse_handler.py
import pytest
from nas_md.webserver.sse_handler import (
    SSEConnectionHandler,
    sse_broadcast,
    register_sse_client,
    get_sse_client_count,
)
from nas_md.webserver.paragraph_diff import compute_diff


def test_compute_diff_basic():
    """Verify diff engine works for SSE use case."""
    old = "# Title\n\nParagraph one.\n\nParagraph two."
    new = "# Title\n\nParagraph one changed.\n\nParagraph two."
    changes = compute_diff(old, new)
    assert len(changes) == 1
    assert changes[0]["type"] == "replace"
    assert changes[0]["paraIdx"] == 1


def test_paragraph_split_preserves_headings():
    from nas_md.webserver.paragraph_diff import split_paragraphs

    text = "# Title\n\n## Section\n\nContent"
    paras = split_paragraphs(text)
    assert paras[0] == "# Title"
    assert paras[1] == "## Section"
    assert paras[2] == "Content"


def test_sse_broadcast_no_clients():
    """Broadcast with no clients should not raise."""
    sse_broadcast("mount1:test.md", "client-0", {"type": "test"})


def test_get_sse_client_count_empty():
    assert get_sse_client_count() == 0
    assert get_sse_client_count("nonexistent") == 0
