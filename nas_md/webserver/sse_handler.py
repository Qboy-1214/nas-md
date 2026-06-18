"""Server-Sent Events handler for real-time collaborative editing."""

import json
import logging
import threading
import time
from collections import defaultdict

logger = logging.getLogger("webserver.sse")

# Global SSE state (thread-safe via _lock)
_lock = threading.Lock()
# "mountId:path" -> list of SSEConnectionHandler instances
_sse_clients: dict[str, list] = defaultdict(list)
_client_counter = 0


class SSEConnectionHandler:
    """Manages a single SSE connection lifecycle.

    Each instance represents one client connected via SSE.
    Stored in the global _sse_clients dict, keyed by "mountId:path".
    """

    def __init__(self, handler):
        """handler: the MountHTTPHandler instance managing this SSE connection."""
        global _client_counter
        self.handler = handler
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
    handler, file_key: str, author_name: str, author_color: str
) -> SSEConnectionHandler:
    """Create and register a new SSE connection."""
    conn = SSEConnectionHandler(handler)
    conn.attach(file_key, author_name, author_color)
    return conn


def sse_broadcast(file_key: str, exclude_id: str, event: dict):
    """Broadcast an event to all clients watching a file, except the sender.

    file_key: "mountId:path"
    exclude_id: client_id of the sender (not broadcast to self)
    event: dict to send as JSON
    """
    with _lock:
        clients = list(_sse_clients.get(file_key, []))

    dead = []
    for client in clients:
        if client.client_id == exclude_id:
            continue
        if not client.send_event(event):
            dead.append(client)

    # Clean up dead connections
    if dead:
        with _lock:
            for client in dead:
                client.detach()


def get_sse_client_count(file_key: str = None) -> int:
    """Get count of active SSE clients. For testing."""
    with _lock:
        if file_key:
            return len(_sse_clients.get(file_key, []))
        return sum(len(v) for v in _sse_clients.values())
