# tests/test_sse_handler.py
import threading
from unittest.mock import Mock

import nas_md.webserver.sse_handler as sse_handler
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


def test_ordered_queue_flushes_earlier_version_before_later_flush(monkeypatch):
    queue_event = getattr(sse_handler, "queue_sse_event", None)
    flush_events = getattr(sse_handler, "flush_sse_events", None)
    assert callable(queue_event)
    assert callable(flush_events)

    file_key = "mount1:ordered.md"
    delivered = []
    monkeypatch.setattr(
        sse_handler,
        "sse_broadcast",
        lambda key, exclude_id, event: delivered.append((key, exclude_id, event)),
    )

    queue_event(file_key, None, {"type": "external_reload", "newVersion": 1})
    queue_event(file_key, "writer", {"type": "remote_edit", "newVersion": 2})

    # The v2 request reaches flush first while the v1 producer is delayed.
    flush_events(file_key)
    flush_events(file_key)

    assert [event[2]["newVersion"] for event in delivered] == [1, 2]


def test_stale_flusher_cannot_release_new_owner():
    claim = getattr(sse_handler, "_claim_flusher", None)
    release = getattr(sse_handler, "_release_flusher", None)
    assert callable(claim)
    assert callable(release)

    file_key = "mount1:ownership.md"
    old_owner = claim(file_key)
    assert old_owner is not None
    release(file_key, old_owner)

    new_owner = claim(file_key)
    assert new_owner is not None
    release(file_key, old_owner)

    # A third flusher must not be admitted while the newer owner is active;
    # otherwise its v2 delivery can complete before the newer owner's v1.
    assert claim(file_key) is None
    release(file_key, new_owner)


def test_concurrent_flush_keeps_fifo_and_single_owner_during_stale_release(
    monkeypatch,
):
    file_key = "mount1:concurrent-ownership.md"
    v1_started = threading.Event()
    release_v1 = threading.Event()
    state_lock = threading.Lock()
    delivered = []
    active_broadcasters = 0
    max_active_broadcasters = 0

    def blocking_broadcast(file_key, exclude_id, event):
        del file_key, exclude_id
        nonlocal active_broadcasters, max_active_broadcasters
        with state_lock:
            active_broadcasters += 1
            max_active_broadcasters = max(max_active_broadcasters, active_broadcasters)
        try:
            if event["newVersion"] == 1:
                v1_started.set()
                assert release_v1.wait(timeout=5)
            with state_lock:
                delivered.append(event["newVersion"])
        finally:
            with state_lock:
                active_broadcasters -= 1

    monkeypatch.setattr(sse_handler, "sse_broadcast", blocking_broadcast)

    old_owner = sse_handler._claim_flusher(file_key)
    assert old_owner is not None
    sse_handler._release_flusher(file_key, old_owner)
    sse_handler.queue_sse_event(file_key, None, {"newVersion": 1})

    first_flusher = threading.Thread(target=sse_handler.flush_sse_events, args=(file_key,))
    first_flusher.start()
    try:
        assert v1_started.wait(timeout=5)

        stale_release = threading.Thread(
            target=sse_handler._release_flusher,
            args=(file_key, old_owner),
        )
        stale_release.start()
        stale_release.join(timeout=5)
        assert not stale_release.is_alive()

        def queue_and_flush_v2():
            sse_handler.queue_sse_event(file_key, None, {"newVersion": 2})
            sse_handler.flush_sse_events(file_key)

        second_flusher = threading.Thread(target=queue_and_flush_v2)
        second_flusher.start()
        second_flusher.join(timeout=5)
        assert not second_flusher.is_alive()
    finally:
        release_v1.set()
        first_flusher.join(timeout=5)
        with sse_handler._publication_lock:
            sse_handler._event_queues.pop(file_key, None)
            sse_handler._flushing_files.pop(file_key, None)

    assert not first_flusher.is_alive()
    assert delivered == [1, 2]
    assert max_active_broadcasters == 1


def test_dead_client_cleanup_does_not_reenter_global_sse_lock():
    file_key = "mount1:dead.md"
    client = Mock()
    client.session_id = "dead-client"
    client.send_event.return_value = False

    def detach_without_reentry():
        assert not sse_handler._lock.locked()
        with sse_handler._lock:
            sse_handler._sse_clients[file_key] = [
                item for item in sse_handler._sse_clients[file_key] if item is not client
            ]

    client.detach.side_effect = detach_without_reentry
    with sse_handler._lock:
        sse_handler._sse_clients[file_key] = [client]

    try:
        sse_broadcast(file_key, None, {"type": "test"})
        client.detach.assert_called_once_with()
        assert get_sse_client_count(file_key) == 0
    finally:
        with sse_handler._lock:
            sse_handler._sse_clients.pop(file_key, None)
