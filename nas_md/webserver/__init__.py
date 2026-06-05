"""Web server for files.md - mount local directories and serve PWA frontend."""

from __future__ import annotations

import contextlib
import gzip
import json
import logging
import mimetypes
import os
import shutil
import socket
import stat
import time
import traceback
from http.server import HTTPServer, SimpleHTTPRequestHandler
from io import BytesIO
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger("webserver")

# --- Admin mode (no token auth; admin access via /admin URL prefix) ---
_admin_mode: bool = False  # Set True if server started with admin enabled

# --- Content-Type overrides for text files (add charset=utf-8) ---

_TEXT_EXTENSIONS = {
    ".md": "text/plain; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".xml": "application/xml; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
    ".yaml": "text/plain; charset=utf-8",
    ".yml": "text/plain; charset=utf-8",
    ".toml": "text/plain; charset=utf-8",
    ".ini": "text/plain; charset=utf-8",
    ".cfg": "text/plain; charset=utf-8",
    ".conf": "text/plain; charset=utf-8",
    ".sh": "text/plain; charset=utf-8",
    ".bash": "text/plain; charset=utf-8",
    ".py": "text/plain; charset=utf-8",
    ".go": "text/plain; charset=utf-8",
    ".rs": "text/plain; charset=utf-8",
    ".java": "text/plain; charset=utf-8",
    ".c": "text/plain; charset=utf-8",
    ".cpp": "text/plain; charset=utf-8",
    ".h": "text/plain; charset=utf-8",
    ".hpp": "text/plain; charset=utf-8",
    ".ts": "text/plain; charset=utf-8",
    ".tsx": "text/plain; charset=utf-8",
    ".jsx": "text/plain; charset=utf-8",
    ".vue": "text/plain; charset=utf-8",
    ".svelte": "text/plain; charset=utf-8",
    ".php": "text/plain; charset=utf-8",
    ".rb": "text/plain; charset=utf-8",
    ".pl": "text/plain; charset=utf-8",
    ".lua": "text/plain; charset=utf-8",
    ".sql": "text/plain; charset=utf-8",
    ".graphql": "text/plain; charset=utf-8",
    ".proto": "text/plain; charset=utf-8",
    ".dockerignore": "text/plain; charset=utf-8",
    ".gitignore": "text/plain; charset=utf-8",
    ".makefile": "text/plain; charset=utf-8",
    ".cmake": "text/plain; charset=utf-8",
    ".env": "text/plain; charset=utf-8",
    ".log": "text/plain; charset=utf-8",
}


def _content_type(path: str) -> str:
    """Detect content type with proper charset for text files."""
    ext = os.path.splitext(path)[1].lower()
    if ext in _TEXT_EXTENSIONS:
        return _TEXT_EXTENSIONS[ext]
    ct, _ = mimetypes.guess_type(path)
    if ct is None:
        return "application/octet-stream"
    # Ensure text/* types have charset
    if ct.startswith("text/") and "charset" not in ct:
        return ct + "; charset=utf-8"
    return ct


# --- Mount Manager ---


class MountEntry:
    """A single mounted directory."""

    def __init__(
        self,
        id: str,
        name: str,
        path: str,
        public: bool = False,
        readonly: bool = False,
        host: bool = False,
    ):
        self.id = id
        self.name = name
        self.path = path  # absolute path on host
        self.public = public  # visible to visitors without auth
        self.readonly = readonly  # files in this mount cannot be modified
        self.host = host  # True = host-mounted (from MOUNT_DIRS), only visible to admin

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "path": self.path,
            "public": self.public,
            "readonly": self.readonly,
            "host": self.host,
        }

    @staticmethod
    def from_dict(d: dict) -> MountEntry:
        return MountEntry(
            d["id"],
            d["name"],
            d["path"],
            d.get("public", False),
            d.get("readonly", False),
            d.get("host", False),
        )


class DirEntry:
    """A file or directory entry in a mount point tree."""

    def __init__(self, name: str, path: str, is_dir: bool, size: int = 0, mod_time: int = 0):
        self.name = name
        self.path = path
        self.is_dir = is_dir
        self.size = size
        self.mod_time = mod_time
        self.children: list[DirEntry] = []
        self.has_md: bool = False  # True if this subtree contains any .md file

    def to_dict(self) -> dict:
        d = {
            "name": self.name,
            "path": self.path,
            "isDir": self.is_dir,
            "size": self.size,
            "modTime": self.mod_time,
            "hasMd": self.has_md,
        }
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
        return d


_MOUNTS_FILE = ""  # Set by serve() to storage_dir/mounts.json


def _load_saved_mounts() -> list[dict]:
    """Load dynamic mount entries from disk."""
    if not _MOUNTS_FILE or not os.path.isfile(_MOUNTS_FILE):
        return []
    try:
        with open(_MOUNTS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_mounts_to_disk(mounts: list[MountEntry]) -> None:
    """Persist dynamic mount entries to disk (excluding builtin)."""
    if not _MOUNTS_FILE:
        return
    data = [m.to_dict() for m in mounts if m.id != "builtin-storage"]
    try:
        tmp = _MOUNTS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _MOUNTS_FILE)
    except OSError as e:
        logger.warning(f"Failed to save mounts: {e}")


class MountManager:
    """Manages configured mount points and serves directory listings."""

    def __init__(self, mount_dirs: list[str]):
        self.mounts: list[MountEntry] = []
        for i, d in enumerate(mount_dirs):
            d = d.strip()
            if not d:
                continue
            # Support "显示名:path" format
            if ":" in d and d[1:2] != ":":  # not a Windows drive letter
                name, path = d.split(":", 1)
                name = name.strip()
                path = os.path.abspath(path.strip())
            else:
                path = os.path.abspath(d)
                name = os.path.basename(path) or f"root-{i}"
            if not os.path.isdir(path):
                continue
            self.mounts.append(MountEntry(f"mount-{i}", name, path, host=True))

    def is_empty(self) -> bool:
        return len(self.mounts) == 0

    def add_mount(self, path: str, name: str | None = None) -> MountEntry:
        """Add a new mount point at runtime."""
        path = os.path.abspath(path.strip())
        if not os.path.isdir(path):
            return None
        # Check for duplicates
        for m in self.mounts:
            if os.path.normpath(m.path) == os.path.normpath(path):
                return m
        display_name = name or (os.path.basename(path) or path)
        entry = MountEntry(f"mount-{len(self.mounts)}", display_name, path)
        self.mounts.append(entry)
        _save_mounts_to_disk(self.mounts)
        return entry

    def find_mount(self, mount_id: str) -> MountEntry | None:
        for m in self.mounts:
            if m.id == mount_id:
                return m
        return None

    def find_mount_by_path(self, path: str) -> MountEntry | None:
        """Find a mount by its path."""
        target = os.path.normpath(path)
        for m in self.mounts:
            if os.path.normpath(m.path) == target:
                return m
        return None

    def update_mount(
        self, mount_id: str, name: str | None = None, public: bool | None = None
    ) -> MountEntry | None:
        """Update mount point properties. Returns updated entry or None."""
        mount = self.find_mount(mount_id)
        if not mount:
            return None
        if name is not None:
            mount.name = name
        if public is not None:
            mount.public = public
        return mount

    def public_mounts(self) -> list[MountEntry]:
        """Return mounts marked as public."""
        return [m for m in self.mounts if m.public]

    def visible_mounts(self, visitor_mounts: list[str] | None = None) -> list[MountEntry]:
        """Return mounts visible to a visitor: public + visitor's own mounts."""
        visible = [m for m in self.mounts if m.public]
        if visitor_mounts:
            for m in self.mounts:
                if m.id in visitor_mounts and m not in visible:
                    visible.append(m)
        return visible

    def _safe_path(self, mount: MountEntry, rel_path: str) -> str | None:
        """Resolve rel_path within mount, or None if it escapes the mount root."""
        clean = os.path.normpath(rel_path).replace("\\", "/")
        if clean in (".", ""):
            return mount.path
        # Strip leading /
        rel = clean.lstrip("/")
        abs_path = os.path.realpath(os.path.join(mount.path, rel))
        # Safety: must be under mount root
        mount_real = os.path.realpath(mount.path)
        if not abs_path.startswith(mount_real + os.sep) and abs_path != mount_real:
            return None
        return abs_path

    def list_dir(self, mount: MountEntry, rel_path: str) -> list[DirEntry]:
        abs_path = self._safe_path(mount, rel_path)
        if abs_path is None:
            return []
        try:
            entries = []
            for name in sorted(os.listdir(abs_path)):
                # Skip hidden
                if name.startswith("."):
                    continue
                full = os.path.join(abs_path, name)
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                entry_rel = f"{rel_path.rstrip('/')}/{name}" if rel_path != "/" else f"/{name}"
                is_dir = stat.S_ISDIR(st.st_mode)
                entries.append(
                    DirEntry(
                        name=name,
                        path=entry_rel,
                        is_dir=is_dir,
                        size=st.st_size,
                        mod_time=int(st.st_mtime * 1000),
                    )
                )
            return entries
        except OSError:
            return []

    def build_tree(
        self, mount: MountEntry, rel_path: str, depth: int = 0, max_depth: int = 10
    ) -> DirEntry | None:
        abs_path = self._safe_path(mount, rel_path)
        if abs_path is None:
            return None
        try:
            st = os.stat(abs_path)
        except OSError:
            return None
        is_dir = stat.S_ISDIR(st.st_mode)
        entry = DirEntry(
            name=os.path.basename(abs_path) or mount.name,
            path=rel_path,
            is_dir=is_dir,
            size=st.st_size,
            mod_time=int(st.st_mtime * 1000),
        )
        # Check if this is a .md file
        if not is_dir and abs_path.lower().endswith(".md"):
            entry.has_md = True
        if is_dir and depth < max_depth:
            for child in self.list_dir(mount, rel_path):
                child_tree = self.build_tree(mount, child.path, depth + 1, max_depth)
                if child_tree:
                    entry.children.append(child_tree)
                    if child_tree.has_md:
                        entry.has_md = True
        return entry


# --- Gzip support ---


class _GzipWriter:
    """Wrapper that gzip-compresses the response."""

    def __init__(self, handler: MountHTTPHandler):
        self.handler = handler
        self.buffer = BytesIO()
        self.gz = gzip.GzipFile(fileobj=self.buffer, mode="wb")

    def write(self, data: bytes):
        self.gz.write(data)

    def close(self):
        self.gz.close()
        self.handler.wfile.write(self.buffer.getvalue())


def _accepts_gzip(handler: MountHTTPHandler) -> bool:
    ae = handler.headers.get("Accept-Encoding", "")
    return "gzip" in ae


# --- Request Handler ---


class MountHTTPHandler(SimpleHTTPRequestHandler):
    """HTTP handler that serves mount API + static PWA files."""

    # Class-level mount manager and web root (set by server)
    mount_manager: MountManager | None = None
    web_root: str = ""
    search_dirs: list[str] = []  # directories to index for search

    def log_message(self, format, *args):
        logger.info(f"{self.client_address[0]} - {format % args}")

    def _send_json(self, data: dict | list, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, msg: str, status: int = 400):
        self._send_json({"error": msg}, status)

    def _is_admin_request(self) -> bool:
        """Check if this request comes from the /admin path."""
        referer = self.headers.get("Referer", "")
        if "/admin" in referer:
            return True
        return self.headers.get("X-Admin", "") == "1"

    def _read_body(self) -> bytes:
        content_length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(content_length)

    def _wrap_gzip(self) -> bool:
        """If client accepts gzip, wrap wfile for transparent compression."""
        if _accepts_gzip(self):
            self._gzip_writer = _GzipWriter(self)
            self.wfile = self._gzip_writer  # type: ignore[assignment]
            self.send_header("Content-Encoding", "gzip")
            return True
        return False

    def _finish_gzip(self):
        """Flush gzip writer if active."""
        if hasattr(self, "_gzip_writer"):
            self._gzip_writer.close()

    # --- Request handling ---
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, PUT, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Admin")
        self.end_headers()

    # --- GET ---
    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            qs = parse_qs(parsed.query)

            # --- API routes ---

            # Public health check
            if path == "/api/health":
                self._send_json({"status": "ok"})
                return

            # Search API (public for all visitors)
            if path == "/api/search":
                self._handle_search(qs)
                return

            # Query API (structured object queries)
            if path == "/api/query":
                self._handle_query(qs)
                return

            # Backlinks API
            if path == "/api/backlinks":
                self._handle_backlinks(qs)
                return

            # Stats API
            if path == "/api/stats":
                self._handle_stats()
                return

            # Graph API
            if path == "/api/graph":
                self._handle_graph()
                return

            # Tags API
            if path == "/api/tags":
                self._handle_tags(qs)
                return

            # Orphans API
            if path == "/api/orphans":
                self._handle_orphans()
                return

            # Sync API
            if path == "/api/sync" and self.command == "POST":
                sync_mount_id = qs.get("mount_id", [None])[0] or ""
                self._handle_sync(sync_mount_id, qs)
                return

            if path == "/api/sync/status":
                sync_mount_id = qs.get("mount_id", [None])[0] or ""
                self._handle_sync_status(sync_mount_id)
                return

            # Plugin API
            if path == "/api/plugins":
                self._handle_plugins()
                return

            # Mounts endpoint (admin sees all, non-admin sees only non-host mounts)
            if path == "/api/mounts":
                if self.mount_manager and not self.mount_manager.is_empty():
                    if self._is_admin_request():
                        mounts = self.mount_manager.mounts
                    else:
                        # Non-admin: only see local (non-host) mounts
                        mounts = [m for m in self.mount_manager.mounts if not m.host]
                    self._send_json([m.to_dict() for m in mounts])
                else:
                    self._send_json([])
                return

            # Public mounts endpoint (returns public + visitor mounts)
            if path == "/api/mounts/public":
                self._handle_public_mounts()
                return

            # Static files (public, no auth needed for frontend)
            # Also serves SPA routes like /admin, /graph etc. via fallback to index.html
            if not path.startswith("/api/"):
                self._serve_static(path)
                return

            # GET /api/find-path?name=xxx
            if path == "/api/find-path":
                qs = parse_qs(parsed.query)
                self._handle_find_path(qs)
                return

            # /api/mounts/{id}/tree
            if "/api/mounts/" in path and path.endswith("/tree"):
                mount_id = path.split("/api/mounts/")[1].split("/tree")[0]
                self._handle_tree(mount_id, qs)
                return

            # /api/mounts/{id}/tree-recursive
            if "/api/mounts/" in path and path.endswith("/tree-recursive"):
                mount_id = path.split("/api/mounts/")[1].split("/tree-recursive")[0]
                self._handle_recursive_tree(mount_id, qs)
                return

            # /api/mounts/{id}/file
            if "/api/mounts/" in path and path.endswith("/file"):
                mount_id = path.split("/api/mounts/")[1].split("/file")[0]
                self._handle_file(mount_id, qs)
                return

            self.send_error(404, "Not found")
        except Exception:
            logger.error("GET handler error: %s", traceback.format_exc())
            with contextlib.suppress(Exception):
                self._send_error("Internal server error", 500)

    # --- PUT ---
    def do_PUT(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or ""
            qs = parse_qs(parsed.query)

            # PUT /api/mounts/{id} — update mount properties
            # Match before /file, /rename, /mkdir which have longer paths
            if path.startswith("/api/mounts/") and "/" not in path[len("/api/mounts/") :].rstrip(
                "/"
            ):
                mount_id = path[len("/api/mounts/") :].rstrip("/")
                self._handle_update_mount(mount_id)
                return

            # /api/mounts/{id}/file
            if "/api/mounts/" in path and path.endswith("/file"):
                mount_id = path.split("/api/mounts/")[1].split("/file")[0]
                if self._handle_write_file(mount_id, qs) and self.search_dirs:
                    self._update_search_index()
                return

            # /api/mounts/{id}/rename
            if "/api/mounts/" in path and path.endswith("/rename"):
                mount_id = path.split("/api/mounts/")[1].split("/rename")[0]
                self._handle_rename(mount_id, qs)
                return

            # /api/mounts/{id}/mkdir
            if "/api/mounts/" in path and path.endswith("/mkdir"):
                mount_id = path.split("/api/mounts/")[1].split("/mkdir")[0]
                self._handle_mkdir(mount_id, qs)
                return

            self.send_error(405, "Method not allowed")
        except Exception:
            logger.error("PUT handler error: %s", traceback.format_exc())
            with contextlib.suppress(Exception):
                self._send_error("Internal server error", 500)

    # --- DELETE ---
    def do_DELETE(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or ""
            qs = parse_qs(parsed.query)

            if "/api/mounts/" in path and path.endswith("/file"):
                mount_id = path.split("/api/mounts/")[1].split("/file")[0]
                self._handle_delete(mount_id, qs)
                return

            # DELETE /api/mounts/{id} — remove mount point
            if path.startswith("/api/mounts/") and "/" not in path[len("/api/mounts/") :]:
                mount_id = path[len("/api/mounts/") :]
                self._handle_delete_mount(mount_id)
                return

            self.send_error(405, "Method not allowed")
        except Exception:
            logger.error("DELETE handler error: %s", traceback.format_exc())
            with contextlib.suppress(Exception):
                self._send_error("Internal server error", 500)

    # --- POST ---
    def do_POST(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or ""

            # POST /api/mounts — add new mount
            if path == "/api/mounts":
                self._handle_add_mount()
                return

            # /syncFilenames
            if path == "/syncFilenames":
                self._handle_sync_filenames()
                return

            # /syncFile
            if path == "/syncFile":
                self._handle_sync_file()
                return

            self.send_error(405, "Method not allowed")
        except Exception:
            logger.error("POST handler error: %s", traceback.format_exc())
            with contextlib.suppress(Exception):
                self._send_error("Internal server error", 500)

    # --- Mount API handlers ---

    def _handle_tree(self, mount_id: str, qs: dict):
        if not self.mount_manager:
            return self._send_error("No mounts configured", 404)
        mount = self.mount_manager.find_mount(mount_id)
        if not mount:
            return self._send_error("Mount not found", 404)
        rel_path = qs.get("path", ["/"])[0]
        entries = self.mount_manager.list_dir(mount, rel_path)
        self._send_json([e.to_dict() for e in entries])

    def _handle_recursive_tree(self, mount_id: str, qs: dict):
        if not self.mount_manager:
            return self._send_error("No mounts configured", 404)
        mount = self.mount_manager.find_mount(mount_id)
        if not mount:
            return self._send_error("Mount not found", 404)
        rel_path = qs.get("path", ["/"])[0]
        tree = self.mount_manager.build_tree(mount, rel_path)
        if tree is None:
            return self._send_error("Cannot build tree", 500)
        self._send_json(tree.to_dict())

    def _handle_file(self, mount_id: str, qs: dict):
        if not self.mount_manager:
            return self._send_error("No mounts configured", 404)
        mount = self.mount_manager.find_mount(mount_id)
        if not mount:
            return self._send_error("Mount not found", 404)
        rel_path = qs.get("path", [None])[0]
        if not rel_path:
            return self._send_error("Missing path parameter", 400)
        abs_path = self.mount_manager._safe_path(mount, rel_path)
        if abs_path is None:
            return self._send_error("Path escapes mount root", 403)
        if not os.path.isfile(abs_path):
            return self._send_error("File not found", 404)
        ct = _content_type(abs_path)
        try:
            with open(abs_path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except OSError as e:
            self._send_error(str(e), 500)

    def _handle_write_file(self, mount_id: str, qs: dict):
        if not self.mount_manager:
            return self._send_error("No mounts configured", 404)
        mount = self.mount_manager.find_mount(mount_id)
        if not mount:
            return self._send_error("Mount not found", 404)
        if mount.readonly:
            return self._send_error("Mount is read-only", 403)
        rel_path = qs.get("path", [None])[0]
        if not rel_path:
            return self._send_error("Missing path parameter", 400)
        abs_path = self.mount_manager._safe_path(mount, rel_path)
        if abs_path is None:
            return self._send_error("Path escapes mount root", 403)

        # Conflict detection: if expected_mtime given and file has been modified
        expected_mtime = qs.get("expected_mtime", [None])[0]
        if expected_mtime and os.path.isfile(abs_path):
            actual_mtime = int(os.path.getmtime(abs_path) * 1000)
            if actual_mtime != int(expected_mtime):
                # Conflict! Create a .conflict.md copy
                conflict_path = abs_path.rsplit(".", 1)
                conflict_path = (
                    conflict_path[0] + ".conflict." + conflict_path[1]
                    if len(conflict_path) > 1
                    else abs_path + ".conflict"
                )
                try:
                    import shutil

                    shutil.copy2(abs_path, conflict_path)
                    logger.warning(
                        "Sync conflict detected for %s, created %s",
                        rel_path,
                        os.path.basename(conflict_path),
                    )
                except OSError:
                    pass

        body = self._read_body()
        # Create parent dirs
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "wb") as f:
            f.write(body)
        st = os.stat(abs_path)
        self._send_json({"status": "ok", "modTime": int(st.st_mtime * 1000), "size": st.st_size})
        return True

    def _handle_rename(self, mount_id: str, qs: dict):
        if not self.mount_manager:
            return self._send_error("No mounts configured", 404)
        mount = self.mount_manager.find_mount(mount_id)
        if not mount:
            return self._send_error("Mount not found", 404)
        if mount.readonly:
            return self._send_error("Mount is read-only", 403)
        old_path = qs.get("oldPath", [None])[0]
        new_path = qs.get("newPath", [None])[0]
        if not old_path or not new_path:
            return self._send_error("Missing oldPath or newPath", 400)
        old_abs = self.mount_manager._safe_path(mount, old_path)
        new_abs = self.mount_manager._safe_path(mount, new_path)
        if old_abs is None or new_abs is None:
            return self._send_error("Path escapes mount root", 403)
        os.makedirs(os.path.dirname(new_abs), exist_ok=True)
        os.rename(old_abs, new_abs)
        self._send_json({"status": "ok"})

    def _handle_mkdir(self, mount_id: str, qs: dict):
        if not self.mount_manager:
            return self._send_error("No mounts configured", 404)
        mount = self.mount_manager.find_mount(mount_id)
        if not mount:
            return self._send_error("Mount not found", 404)
        if mount.readonly:
            return self._send_error("Mount is read-only", 403)
        rel_path = qs.get("path", [None])[0]
        if not rel_path:
            return self._send_error("Missing path parameter", 400)
        abs_path = self.mount_manager._safe_path(mount, rel_path)
        if abs_path is None:
            return self._send_error("Path escapes mount root", 403)
        os.makedirs(abs_path, exist_ok=True)
        self._send_json({"status": "ok"})

    def _handle_delete(self, mount_id: str, qs: dict):
        if not self.mount_manager:
            return self._send_error("No mounts configured", 404)
        mount = self.mount_manager.find_mount(mount_id)
        if not mount:
            return self._send_error("Mount not found", 404)
        if mount.readonly:
            return self._send_error("Mount is read-only", 403)
        rel_path = qs.get("path", [None])[0]
        if not rel_path:
            return self._send_error("Missing path parameter", 400)
        abs_path = self.mount_manager._safe_path(mount, rel_path)
        if abs_path is None:
            return self._send_error("Path escapes mount root", 403)
        if os.path.isdir(abs_path):
            shutil.rmtree(abs_path)
        else:
            os.remove(abs_path)
        self._send_json({"status": "ok"})

    # --- Search handler ---

    def _handle_search(self, qs: dict):
        """Handle full-text search requests."""
        from nas_md.search import search, init_db

        query = qs.get("q", [""])[0]
        limit = int(qs.get("limit", ["20"])[0])

        if not query.strip():
            self._send_json([])
            return

        try:
            init_db()  # Ensure DB exists
            results = search(query.strip(), limit=limit)
            # Enrich results with mount_id and relative path
            for r in results:
                mount_info = self._find_mount_for_path(r["path"])
                if mount_info:
                    r["mount_id"] = mount_info["mount_id"]
                    r["rel_path"] = mount_info["rel_path"]
                else:
                    r["mount_id"] = None
                    r["rel_path"] = r["path"]
            self._send_json(results)
        except Exception as e:
            logger.error("Search error: %s", e)
            self._send_json({"error": str(e)}, 500)

    def _find_mount_for_path(self, file_path: str) -> dict | None:
        """Find the mount that contains this file path and return mount_id + relative path.

        file_path may be an absolute path or a relative path stored in the search index.
        """
        if not self.mount_manager:
            return None
        # Normalize the file path
        file_path_norm = file_path.replace("\\", "/")
        for m in self.mount_manager.mounts:
            # Try as absolute path
            mount_path_norm = os.path.normcase(m.path.replace("\\", "/")).rstrip("/")
            fp_norm = os.path.normcase(file_path_norm)
            if fp_norm.startswith(mount_path_norm + "/") or fp_norm == mount_path_norm:
                rel = file_path_norm[len(mount_path_norm) :].lstrip("/")
                return {"mount_id": m.id, "rel_path": rel}
            # Try as relative path — check if file exists under mount root
            abs_candidate = os.path.join(m.path, file_path)
            if os.path.isfile(abs_candidate):
                return {"mount_id": m.id, "rel_path": file_path_norm}
        return None

    def _handle_query(self, qs: dict):
        """Handle GET /api/query?type=task|tag|heading|link"""
        from nas_md.search import init_db, query_tasks, query_tags, query_headings, query_links

        query_type = qs.get("type", [""])[0]

        try:
            init_db()  # Ensure DB exists

            if query_type == "task":
                status = qs.get("status", [None])[0]
                tasks = query_tasks(status=status)
                self._send_json({"tasks": tasks})
            elif query_type == "tag":
                name = qs.get("name", [None])[0]
                if name:
                    pages = query_tags(name=name)
                    self._send_json({"pages": pages})
                else:
                    tags = query_tags()
                    self._send_json({"tags": tags})
            elif query_type == "heading":
                page = qs.get("page", [None])[0]
                headings = query_headings(page_path=page)
                self._send_json({"headings": headings})
            elif query_type == "link":
                page = qs.get("page", [None])[0]
                links = query_links(page_path=page)
                self._send_json({"links": links})
            else:
                self._send_error("Invalid query type. Use: task, tag, heading, link", 400)
        except Exception as e:
            logger.error("Query error: %s", e)
            self._send_json({"error": str(e)}, 500)

    def _handle_backlinks(self, qs: dict):
        """Handle GET /api/backlinks?page=xxx"""
        from nas_md.search import init_db, query_backlinks

        page = qs.get("page", [""])[0]
        if not page:
            self._send_error("Missing 'page' parameter", 400)
            return

        try:
            init_db()
            backlinks = query_backlinks(page)
            self._send_json({"backlinks": backlinks})
        except Exception as e:
            logger.error("Backlinks error: %s", e)
            self._send_json({"error": str(e)}, 500)

    def _handle_stats(self):
        """Handle GET /api/stats — only count files in user-mounted directories"""
        from nas_md.search import init_db, get_stats

        try:
            init_db()
            stats = get_stats()
            # Filter to only include files in user-mounted directories (exclude built-in storage)
            if self.mount_manager and not self.mount_manager.is_empty():
                mount_paths = [m.path.lower().rstrip("\\/") for m in self.mount_manager.mounts]
                stats["recent_pages"] = [
                    p
                    for p in stats.get("recent_pages", [])
                    if any(
                        p["path"].lower().startswith(mp + os.sep) or p["path"].lower() == mp
                        for mp in mount_paths
                    )
                ]
                # Also filter aggregate stats by mount paths
                from nas_md.search import get_connection

                conn = get_connection()
                try:
                    # Build path prefix conditions for each mount
                    # Each mount produces 3 LIKE patterns: dir\%, dir/%, and exact dir
                    conditions = []
                    params = []
                    for mp in mount_paths:
                        conditions.append(
                            "(LOWER(path) LIKE ? OR LOWER(path) LIKE ? OR LOWER(path) = ?)"
                        )
                        params.append(mp + "\\%")
                        params.append(mp + "/%")
                        params.append(mp)
                    where_clause = " OR ".join(conditions)
                    page_filter = f"SELECT rowid FROM pages WHERE {where_clause}"

                    row = conn.execute(
                        f"SELECT COUNT(*) FROM pages WHERE {where_clause}", params
                    ).fetchone()
                    stats["file_count"] = row[0] if row else 0
                    task_row = conn.execute(
                        f"SELECT COUNT(*) FROM tasks WHERE page_id IN ({page_filter})", params
                    ).fetchone()
                    stats["task_total"] = task_row[0] if task_row else 0
                    task_done_row = conn.execute(
                        f"SELECT COUNT(*) FROM tasks WHERE done = 1 AND page_id IN ({page_filter})",
                        params,
                    ).fetchone()
                    stats["task_done"] = task_done_row[0] if task_done_row else 0
                    tag_row = conn.execute(
                        f"SELECT COUNT(DISTINCT name) FROM tags WHERE page_id IN ({page_filter})",
                        params,
                    ).fetchone()
                    stats["tag_count"] = tag_row[0] if tag_row else 0
                    link_row = conn.execute(
                        f"SELECT COUNT(*) FROM links WHERE page_id IN ({page_filter})", params
                    ).fetchone()
                    stats["link_count"] = link_row[0] if link_row else 0
                finally:
                    conn.close()
            self._send_json(stats)
        except Exception as e:
            logger.error("Stats error: %s", e)
            self._send_json({"error": str(e)}, 500)

    def _handle_graph(self):
        """Handle GET /api/graph"""
        from nas_md.search import init_db, get_graph_data

        try:
            init_db()
            data = get_graph_data()
            self._send_json(data)
        except Exception as e:
            logger.error("Graph error: %s", e)
            self._send_json({"error": str(e)}, 500)

    def _handle_tags(self, qs: dict):
        """Handle GET /api/tags[?name=xxx] — list all tags or pages for a specific tag."""
        from nas_md.search import init_db, query_tags

        try:
            init_db()
            name = qs.get("name", [None])[0] if qs else None
            result = query_tags(name)
            self._send_json(result)
        except Exception as e:
            logger.error("Tags error: %s", e)
            self._send_json({"error": str(e)}, 500)

    def _handle_orphans(self):
        """Handle GET /api/orphans — pages with no incoming or outgoing links."""
        from nas_md.search import init_db, get_connection

        try:
            init_db()
            conn = get_connection()
            try:
                # Pages that have no links pointing to them and link to nothing
                rows = conn.execute("""
                    SELECT p.path, p.title
                    FROM pages p
                    WHERE p.id NOT IN (SELECT target_page_id FROM links WHERE target_page_id IS NOT NULL)
                      AND p.id NOT IN (SELECT source_page_id FROM links)
                    ORDER BY p.path
                """).fetchall()
                result = [{"path": r[0], "title": r[1] or r[0]} for r in rows]
                self._send_json(result)
            finally:
                conn.close()
        except Exception as e:
            logger.error("Orphans error: %s", e)
            self._send_json({"error": str(e)}, 500)

    def _handle_sync(self, mount_id: str, qs: dict):
        """Handle POST /api/sync — incremental file synchronization.

        Client sends: {"files": [{"path": "a.md", "mtime": 1234567890}, ...]}
        Server returns: {"download": [...], "upload": [...], "delete": [...]}
        - download: server has newer versions (client should download)
        - upload: client has newer versions (server confirms, client should upload)
        - delete: files deleted on server (client should delete)
        """
        if not self.mount_manager:
            return self._send_error("No mounts configured", 404)
        mount = self.mount_manager.find_mount(mount_id)
        if not mount:
            return self._send_error("Mount not found", 404)

        try:
            body = self._read_body()
            data = json.loads(body) if body else {}
            client_files = data.get("files", {})

            # Scan server files
            download = []
            upload = []
            server_files = {}

            for root, dirs, files in os.walk(mount.path):
                # Skip hidden dirs
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for fname in files:
                    if fname.startswith("."):
                        continue
                    abs_path = os.path.join(root, fname)
                    rel_path = os.path.relpath(abs_path, mount.path).replace("\\", "/")
                    st = os.stat(abs_path)
                    server_mtime = int(st.st_mtime * 1000)
                    server_files[rel_path] = server_mtime

                    if rel_path in client_files:
                        client_mtime = client_files[rel_path]
                        if server_mtime > client_mtime:
                            download.append({"path": rel_path, "mtime": server_mtime})
                        elif client_mtime > server_mtime:
                            upload.append({"path": rel_path, "mtime": client_mtime})
                    else:
                        # New file on server, client doesn't have it
                        download.append({"path": rel_path, "mtime": server_mtime})

            # Files on client but not on server = deleted on server
            delete = [{"path": p} for p in client_files if p not in server_files]

            self._send_json(
                {
                    "download": download,
                    "upload": upload,
                    "delete": delete,
                    "server_time": int(time.time() * 1000),
                }
            )
        except Exception as e:
            logger.error("Sync error: %s", e)
            self._send_json({"error": str(e)}, 500)

    def _handle_sync_status(self, mount_id: str):
        """Handle GET /api/sync/status — get sync status for a mount."""
        if not self.mount_manager:
            return self._send_error("No mounts configured", 404)
        mount = self.mount_manager.find_mount(mount_id)
        if not mount:
            return self._send_error("Mount not found", 404)

        try:
            # Count files on server
            file_count = 0
            total_size = 0
            latest_mtime = 0
            for root, dirs, files in os.walk(mount.path):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for fname in files:
                    if fname.startswith("."):
                        continue
                    abs_path = os.path.join(root, fname)
                    st = os.stat(abs_path)
                    file_count += 1
                    total_size += st.st_size
                    mtime = int(st.st_mtime * 1000)
                    if mtime > latest_mtime:
                        latest_mtime = mtime

            self._send_json(
                {
                    "mount_id": mount_id,
                    "file_count": file_count,
                    "total_size": total_size,
                    "latest_mtime": latest_mtime,
                }
            )
        except Exception as e:
            logger.error("Sync status error: %s", e)
            self._send_json({"error": str(e)}, 500)

    def _handle_plugins(self):
        """Handle GET /api/plugins — list loaded plugins."""
        from nas_md.plugins import PluginManager

        try:
            pm = getattr(self.__class__, "_plugin_manager", None)
            if pm is None:
                pm = PluginManager()
                pm.load_all()
                self.__class__._plugin_manager = pm
            plugins = [
                {"name": p.name, "version": p.version, "description": p.description}
                for p in pm.plugins
            ]
            self._send_json({"plugins": plugins})
        except Exception as e:
            logger.error("Plugins error: %s", e)
            self._send_json({"error": str(e)}, 500)

    def _handle_find_path(self, qs: dict):
        """Search for a directory by name in common locations."""
        name = qs.get("name", [None])[0]
        if not name:
            return self._send_error("Missing name parameter", 400)

        # Search in common base directories
        search_roots = []
        home = os.path.expanduser("~")
        # User home and subdirs
        for sub in ["", "Documents", "Desktop", "Downloads"]:
            p = os.path.join(home, sub) if sub else home
            if os.path.isdir(p):
                search_roots.append(p)
        # All drive roots and their Documents folders
        for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
            root = f"{letter}:\\"
            if os.path.isdir(root):
                search_roots.append(root)
                docs = os.path.join(root, "Documents")
                if os.path.isdir(docs):
                    search_roots.append(docs)

        for root in search_roots:
            if not os.path.isdir(root):
                continue
            try:
                for entry in os.scandir(root):
                    if entry.is_dir() and entry.name.lower() == name.lower():
                        self._send_json({"path": entry.path, "name": entry.name})
                        return
            except PermissionError:
                continue

        self._send_json({"path": None, "name": name})

    def _handle_public_mounts(self):
        """Return mounts marked as public (no auth required)."""
        if not self.mount_manager:
            self._send_json([])
            return
        public = self.mount_manager.public_mounts()
        self._send_json([m.to_dict() for m in public])

    def _handle_add_mount(self):
        """Handle POST /api/mounts to add a new mount point.

        No auth required — both visitors and admin users can mount.
        Visitors are limited to 1 mount. Admin users limited to 1 dynamic mount.
        """
        body = self._read_body()
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return self._send_error("Invalid JSON", 400)

        dir_path = data.get("path", "").strip()
        if not dir_path:
            return self._send_error("Missing path", 400)
        logger.info(f"ADD MOUNT request: path={dir_path!r}")

        display_name = data.get("name", "").strip() or None

        if not self.mount_manager:
            return self._send_error("Mount manager not configured", 500)

        # Count dynamic (non-pre-configured) mounts
        # Pre-configured mounts have IDs like "mount-0", "mount-1" from startup
        # Dynamic mounts get IDs after those

        # Check if this is a new path (not duplicate)
        is_duplicate = False
        for m in self.mount_manager.mounts:
            if os.path.normpath(m.path) == os.path.normpath(dir_path):
                is_duplicate = True
                break

        if not is_duplicate:
            # Visitor limit: max 1 dynamic mount
            # For now we allow the mount; frontend enforces the limit
            entry = self.mount_manager.add_mount(dir_path, name=display_name)
            if entry:
                entry.public = True
            if entry is None:
                return self._send_error("Not a valid directory: " + dir_path, 400)
        else:
            entry = self.mount_manager.find_mount_by_path(dir_path)
            if entry is None:
                entry = self.mount_manager.add_mount(dir_path, name=display_name)
                if entry is None:
                    return self._send_error("Not a valid directory: " + dir_path, 400)

        # Update search index for new mount
        if self.search_dirs is not None and dir_path not in self.search_dirs:
            self.search_dirs.append(dir_path)
        self._update_search_index()

        self._send_json(entry.to_dict())

    def _handle_update_mount(self, mount_id: str):
        """Handle PUT /api/mounts/{id} to update mount properties."""
        if not self.mount_manager:
            return self._send_error("Mount manager not configured", 500)

        body = self._read_body()
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return self._send_error("Invalid JSON", 400)

        name = data.get("name")
        public = data.get("public")

        entry = self.mount_manager.update_mount(
            mount_id,
            name=name.strip() if name else None,
            public=bool(public) if public is not None else None,
        )
        if entry is None:
            return self._send_error("Mount not found", 404)

        _save_mounts_to_disk(self.mount_manager.mounts)
        self._send_json(entry.to_dict())

    def _handle_delete_mount(self, mount_id: str):
        """Handle DELETE /api/mounts/{id} to remove a mount point."""
        if not self.mount_manager:
            return self._send_error("Mount manager not configured", 500)

        # Check if mount exists
        mount = self.mount_manager.find_mount(mount_id)
        if not mount:
            return self._send_error("Mount not found", 404)

        # Cannot delete builtin mount
        if mount.id == "builtin-storage":
            return self._send_error("Cannot delete built-in mount", 403)

        # Remove from mount manager
        self.mount_manager.mounts = [m for m in self.mount_manager.mounts if m.id != mount_id]
        _save_mounts_to_disk(self.mount_manager.mounts)

        # Remove from search dirs
        if self.search_dirs and mount.path in self.search_dirs:
            self.search_dirs.remove(mount.path)

        self._send_json({"id": mount_id, "removed": True})

    def _update_search_index(self):
        """Rebuild search index after file write."""
        from nas_md.search import rebuild_index

        try:
            count = rebuild_index(self.search_dirs)
            logger.info("Search index updated: %d files", count)
        except Exception as e:
            logger.error("Search index update failed: %s", e)

    # --- Sync handlers (simplified, no auth) ---

    def _handle_sync_filenames(self):
        """Simplified sync - returns files from the first mount point."""
        if not self.mount_manager or self.mount_manager.is_empty():
            return self._send_json({"status": "ok", "files": [], "timestamps": {}})
        # Just return empty for now - full sync requires user FS
        self._send_json({"status": "ok", "files": [], "timestamps": {}})

    def _handle_sync_file(self):
        self._send_json({"status": "ok", "lastModified": 0})

    # --- Static files ---

    def _serve_static(self, path: str):
        """Serve static PWA files from web_root. Falls back to index.html for SPA routes."""
        if not self.web_root:
            return self.send_error(404, "No web root")

        # Default to index.html
        if path == "/":
            path = "/index.html"

        # Resolve within web root
        full_path = os.path.realpath(os.path.join(self.web_root, path.lstrip("/")))
        web_root_real = os.path.realpath(self.web_root)

        if not full_path.startswith(web_root_real):
            return self.send_error(403, "Forbidden")

        if not os.path.isfile(full_path):
            # SPA fallback: serve index.html for any non-file path
            # (e.g. /admin, /graph, /dashboard — all handled by frontend JS)
            index_path = os.path.join(web_root_real, "index.html")
            if os.path.isfile(index_path):
                full_path = index_path
            else:
                return self.send_error(404, "Not found")

        ct = _content_type(full_path)

        try:
            with open(full_path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except OSError:
            self.send_error(500, "Internal server error")


# --- Server runner ---


def serve(
    mount_dirs: list[str],
    web_root: str = "",
    port: int = 8080,
    host: str = "0.0.0.0",
    storage_dir: str = "",
):
    """Start the HTTP server with mount points and optional static file serving."""
    global _MOUNTS_FILE
    _MOUNTS_FILE = os.path.join(storage_dir, "mounts.json") if storage_dir else ""

    mgr = MountManager(mount_dirs)

    # Auto-mount storage dir as built-in readonly mount (always visible, cannot be removed)
    if storage_dir and os.path.isdir(storage_dir):
        builtin = MountEntry("builtin-storage", "nas-md", storage_dir, public=True, readonly=True)
        mgr.mounts.insert(0, builtin)

    # Restore dynamic mounts from disk (survives restart)
    saved = _load_saved_mounts()
    if saved:
        existing_paths = {os.path.normpath(m.path) for m in mgr.mounts}
        for entry_dict in saved:
            try:
                entry = MountEntry.from_dict(entry_dict)
                if os.path.isdir(entry.path) and os.path.normpath(entry.path) not in existing_paths:
                    entry.public = True  # All dynamic mounts are public by default
                    mgr.mounts.append(entry)
                    existing_paths.add(os.path.normpath(entry.path))
                    logger.info(f"Restored mount: {entry.name} ({entry.id})={entry.path}")
                elif not os.path.isdir(entry.path):
                    logger.warning(f"Skipping restored mount, directory missing: {entry.path}")
            except (KeyError, TypeError) as e:
                logger.warning(f"Skipping invalid mount entry: {e}")

    MountHTTPHandler.mount_manager = mgr
    MountHTTPHandler.web_root = web_root

    # Include storage dir in search dirs
    all_dirs = list(mount_dirs)
    if storage_dir and os.path.isdir(storage_dir) and storage_dir not in all_dirs:
        all_dirs.insert(0, storage_dir)
    # Also add restored mount paths to search dirs
    for m in mgr.mounts:
        if m.id != "builtin-storage" and os.path.isdir(m.path) and m.path not in all_dirs:
            all_dirs.append(m.path)
    MountHTTPHandler.search_dirs = all_dirs

    # Initialize search index
    _init_search_index(all_dirs)

    server = _create_server(host, port, MountHTTPHandler)

    mounts_str = (
        ", ".join(f"{m.name} ({m.id})={m.path}" for m in mgr.mounts)
        if not mgr.is_empty()
        else "(none)"
    )
    web_str = web_root if web_root else "(none)"
    logger.info(f"Starting HTTP server on {host}:{port}")
    logger.info(f"  Mount points: {mounts_str}")
    logger.info(f"  Web root: {web_str}")
    logger.info("  Admin: access via /admin URL path")
    logger.info("  API endpoints:")
    logger.info("    GET  /api/health")
    logger.info("    GET  /api/search?q=keyword")
    logger.info("    GET  /api/query?type=task|tag|heading|link")
    logger.info("    GET  /api/backlinks?page=xxx")
    logger.info("    GET  /api/stats")
    logger.info("    GET  /api/graph")
    logger.info("    POST /api/sync")
    logger.info("    GET  /api/sync/status")
    logger.info("    GET  /api/plugins")
    logger.info("    GET  /api/mounts")
    logger.info("    GET  /api/mounts/public")
    logger.info("    PUT  /api/mounts/{id}")
    logger.info("    GET  /api/mounts/{id}/tree?path=/")
    logger.info("    GET  /api/mounts/{id}/tree-recursive?path=/")
    logger.info("    GET  /api/mounts/{id}/file?path=/file.md")
    logger.info("    PUT  /api/mounts/{id}/file?path=/file.md")
    logger.info("    PUT  /api/mounts/{id}/rename?oldPath=/a.md&newPath=/b.md")
    logger.info("    PUT  /api/mounts/{id}/mkdir?path=/newdir")
    logger.info("    DELETE /api/mounts/{id}/file?path=/file.md")
    logger.info(f"  Static files: http://localhost:{port}/")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server stopped.")
        server.server_close()


def _create_server(host: str, port: int, handler: type) -> HTTPServer:
    """Create HTTPServer with SO_REUSEADDR to avoid port-in-use errors on restart."""

    class ReusableHTTPServer(HTTPServer):
        allow_reuse_address = True

        def server_bind(self) -> None:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            super().server_bind()

    try:
        return ReusableHTTPServer((host, port), handler)
    except OSError as e:
        logger.error("Failed to bind %s:%s — %s", host, port, e)
        logger.error("Port may be in use. Try: netstat -ano | findstr %s", port)
        raise SystemExit(1) from e


def _init_search_index(mount_dirs: list[str]) -> None:
    """Initialize the search database and index all mounted directories."""
    from nas_md.search import init_db, rebuild_index, get_stats

    try:
        init_db()
        stats = get_stats()
        if stats["file_count"] == 0:
            logger.info("Building initial search index...")
            count = rebuild_index(mount_dirs)
            logger.info("Search index built: %d files indexed", count)
        else:
            logger.info("Search index ready: %d files", stats["file_count"])
    except Exception as e:
        logger.error("Failed to initialize search index: %s", e)
