"""Server-Sent Events handler for real-time collaborative editing."""

import json
import logging
import threading
from collections import defaultdict, deque

logger = logging.getLogger("webserver.sse")

# Global SSE state (thread-safe via _lock)
_lock = threading.Lock()
# "mountId:path" -> list of SSEConnectionHandler instances
_sse_clients: dict[str, list] = defaultdict(list)
_client_counter = 0

# Per-file publication state. Producers enqueue while holding the matching
# FileVersion lock; a single lock-free broadcaster then drains each file FIFO.
_publication_lock = threading.Lock()
_event_queues: dict[str, deque[tuple[str | None, dict]]] = defaultdict(deque)
_flushing_files: dict[str, object] = {}


class SSEConnectionHandler:
    """Manages a single SSE connection lifecycle.

    Each instance represents one client connected via SSE.
    Stored in the global _sse_clients dict, keyed by "mountId:path".
    """

    def __init__(self, handler, session_id: str):
        """handler: the MountHTTPHandler instance managing this SSE connection.
        session_id: the session ID of the client, used for broadcast exclusion."""
        global _client_counter
        self.handler = handler
        self.session_id = session_id
        with _lock:
            _client_counter += 1
            self.client_id = f"client-{_client_counter}"
        self._file_key = None
        self._closed = False

    def attach(self, file_key: str, author_name: str, author_color: str):
        """Register this client as watching a specific file."""
        with _lock:
            if self._file_key and self._file_key in _sse_clients:
                # Remove from previous file
                _sse_clients[self._file_key] = [
                    c for c in _sse_clients[self._file_key] if c is not self
                ]
            self._file_key = file_key
            self.author_name = author_name
            self.author_color = author_color
            _sse_clients[file_key].append(self)

    def detach(self):
        """Remove this client from all file watchers."""
        with _lock:
            if self._file_key and self._file_key in _sse_clients:
                _sse_clients[self._file_key] = [
                    c for c in _sse_clients[self._file_key] if c is not self
                ]
            self._file_key = None
        self._closed = True

    def send_event(self, data: dict) -> bool:
        """Send an SSE event to this client. Returns False if connection closed."""
        if self._closed:
            return False
        try:
            payload = f"data: {json.dumps(data)}\n\n"
            self.handler.wfile.write(payload.encode("utf-8"))
            self.handler.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionResetError, OSError):
            self._closed = True
            return False

    @property
    def is_closed(self):
        return self._closed


def register_sse_client(
    handler, file_key: str, author_name: str, author_color: str, session_id: str
) -> SSEConnectionHandler:
    """Create and register a new SSE connection."""
    conn = SSEConnectionHandler(handler, session_id)
    conn.attach(file_key, author_name, author_color)
    return conn


def sse_broadcast(file_key: str, exclude_id: str | None, event: dict):
    """Broadcast an event to all clients watching a file, except the sender.

    file_key: "mountId:path"
    exclude_id: session_id of the sender (not broadcast to self)
    event: dict to send as JSON
    """
    with _lock:
        clients = list(_sse_clients.get(file_key, []))

    dead = []
    for client in clients:
        if client.session_id == exclude_id:
            continue
        if not client.send_event(event):
            dead.append(client)

    # Clean up dead connections
    for client in dead:
        client.detach()


def queue_sse_event(file_key: str, exclude_id: str | None, event: dict) -> None:
    """Append an event to a file's ordered publication queue."""
    with _publication_lock:
        _event_queues[file_key].append((exclude_id, event))


def _claim_flusher(file_key: str) -> object | None:
    with _publication_lock:
        if file_key in _flushing_files:
            return None
        owner = object()
        _flushing_files[file_key] = owner
        return owner


def _release_flusher(file_key: str, owner: object) -> None:
    with _publication_lock:
        if _flushing_files.get(file_key) is owner:
            _flushing_files.pop(file_key, None)


def flush_sse_events(file_key: str) -> None:
    """Drain one file's queued events in insertion order."""
    with _publication_lock:
        if not _event_queues.get(file_key):
            return
    owner = _claim_flusher(file_key)
    if owner is None:
        return

    try:
        while True:
            with _publication_lock:
                queue = _event_queues.get(file_key)
                if not queue:
                    _event_queues.pop(file_key, None)
                    if _flushing_files.get(file_key) is owner:
                        _flushing_files.pop(file_key, None)
                        owner = None
                    return
                exclude_id, event = queue.popleft()
            try:
                sse_broadcast(file_key, exclude_id=exclude_id, event=event)
            except Exception:
                logger.warning("SSE queued broadcast failed for %s", file_key, exc_info=True)
    finally:
        if owner is not None:
            _release_flusher(file_key, owner)


def get_sse_client_count(file_key: str | None = None) -> int:
    """Get count of active SSE clients. For testing."""
    with _lock:
        if file_key:
            return len(_sse_clients.get(file_key, []))
        return sum(len(v) for v in _sse_clients.values())
