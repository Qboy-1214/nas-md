"""Web server for files.md - mount local directories and serve PWA frontend."""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import stat
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger("webserver")


# --- Mount Manager ---

class MountEntry:
    """A single mounted directory."""
    def __init__(self, id: str, name: str, path: str):
        self.id = id
        self.name = name
        self.path = path  # absolute path on host

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "path": self.path}


class DirEntry:
    """A file or directory entry in a mount point tree."""
    def __init__(self, name: str, path: str, is_dir: bool, size: int = 0, mod_time: int = 0):
        self.name = name
        self.path = path
        self.is_dir = is_dir
        self.size = size
        self.mod_time = mod_time
        self.children: list[DirEntry] = []

    def to_dict(self) -> dict:
        d = {"name": self.name, "path": self.path, "isDir": self.is_dir,
             "size": self.size, "modTime": self.mod_time}
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
        return d


class MountManager:
    """Manages configured mount points and serves directory listings."""

    def __init__(self, mount_dirs: list[str]):
        self.mounts: list[MountEntry] = []
        for i, d in enumerate(mount_dirs):
            d = os.path.abspath(d.strip())
            if not d:
                continue
            name = os.path.basename(d) or f"root-{i}"
            self.mounts.append(MountEntry(f"mount-{i}", name, d))

    def is_empty(self) -> bool:
        return len(self.mounts) == 0

    def find_mount(self, mount_id: str) -> Optional[MountEntry]:
        for m in self.mounts:
            if m.id == mount_id:
                return m
        return None

    def _safe_path(self, mount: MountEntry, rel_path: str) -> Optional[str]:
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
                entries.append(DirEntry(
                    name=name,
                    path=entry_rel,
                    is_dir=is_dir,
                    size=st.st_size,
                    mod_time=int(st.st_mtime * 1000),
                ))
            return entries
        except OSError:
            return []

    def build_tree(self, mount: MountEntry, rel_path: str, depth: int = 0, max_depth: int = 10) -> Optional[DirEntry]:
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
        if is_dir and depth < max_depth:
            for child in self.list_dir(mount, rel_path):
                child_tree = self.build_tree(mount, child.path, depth + 1, max_depth)
                if child_tree:
                    entry.children.append(child_tree)
        return entry


# --- Request Handler ---

class MountHTTPHandler(SimpleHTTPRequestHandler):
    """HTTP handler that serves mount API + static PWA files."""

    # Class-level mount manager and web root (set by server)
    mount_manager: Optional[MountManager] = None
    web_root: str = ""

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

    def _read_body(self) -> bytes:
        content_length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(content_length)

    # --- CORS preflight ---
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, PUT, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    # --- GET ---
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = parse_qs(parsed.query)

        # Mount API routes
        if path == "/api/mounts":
            if self.mount_manager and not self.mount_manager.is_empty():
                self._send_json([m.to_dict() for m in self.mount_manager.mounts])
            else:
                self._send_json([])
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

        # Static files
        self._serve_static(path)

    # --- PUT ---
    def do_PUT(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or ""
        qs = parse_qs(parsed.query)

        # /api/mounts/{id}/file
        if "/api/mounts/" in path and path.endswith("/file"):
            mount_id = path.split("/api/mounts/")[1].split("/file")[0]
            self._handle_write_file(mount_id, qs)
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

    # --- DELETE ---
    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or ""
        qs = parse_qs(parsed.query)

        if "/api/mounts/" in path and path.endswith("/file"):
            mount_id = path.split("/api/mounts/")[1].split("/file")[0]
            self._handle_delete(mount_id, qs)
            return

        self.send_error(405, "Method not allowed")

    # --- POST ---
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or ""

        # /syncFilenames
        if path == "/syncFilenames":
            self._handle_sync_filenames()
            return

        # /syncFile
        if path == "/syncFile":
            self._handle_sync_file()
            return

        self.send_error(405, "Method not allowed")

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
        # Detect content type
        ct, _ = mimetypes.guess_type(abs_path)
        if ct is None:
            ct = "application/octet-stream"
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
        rel_path = qs.get("path", [None])[0]
        if not rel_path:
            return self._send_error("Missing path parameter", 400)
        abs_path = self.mount_manager._safe_path(mount, rel_path)
        if abs_path is None:
            return self._send_error("Path escapes mount root", 403)
        body = self._read_body()
        # Create parent dirs
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "wb") as f:
            f.write(body)
        st = os.stat(abs_path)
        self._send_json({"status": "ok", "modTime": int(st.st_mtime * 1000), "size": st.st_size})

    def _handle_rename(self, mount_id: str, qs: dict):
        if not self.mount_manager:
            return self._send_error("No mounts configured", 404)
        mount = self.mount_manager.find_mount(mount_id)
        if not mount:
            return self._send_error("Mount not found", 404)
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
        rel_path = qs.get("path", [None])[0]
        if not rel_path:
            return self._send_error("Missing path parameter", 400)
        abs_path = self.mount_manager._safe_path(mount, rel_path)
        if abs_path is None:
            return self._send_error("Path escapes mount root", 403)
        if os.path.isdir(abs_path):
            os.rmdir(abs_path)
        else:
            os.remove(abs_path)
        self._send_json({"status": "ok"})

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
        """Serve static PWA files from web_root."""
        if not self.web_root:
            return self.send_error(404, "No web root configured")

        # Default to index.html
        if path == "/":
            path = "/index.html"

        # Resolve within web root
        full_path = os.path.realpath(os.path.join(self.web_root, path.lstrip("/")))
        web_root_real = os.path.realpath(self.web_root)

        if not full_path.startswith(web_root_real):
            return self.send_error(403, "Forbidden")

        if not os.path.isfile(full_path):
            return self.send_error(404, "Not found")

        ct, _ = mimetypes.guess_type(full_path)
        if ct is None:
            ct = "application/octet-stream"

        try:
            with open(full_path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except OSError as e:
            self.send_error(500, str(e))


# --- Server runner ---

def serve(mount_dirs: list[str], web_root: str = "", port: int = 8080, host: str = "0.0.0.0"):
    """Start the HTTP server with mount points and optional static file serving."""
    mgr = MountManager(mount_dirs)

    MountHTTPHandler.mount_manager = mgr
    MountHTTPHandler.web_root = web_root

    server = HTTPServer((host, port), MountHTTPHandler)

    mounts_str = ", ".join(f"{m.name}={m.path}" for m in mgr.mounts) if not mgr.is_empty() else "(none)"
    web_str = web_root if web_root else "(none)"
    logger.info(f"Starting HTTP server on {host}:{port}")
    logger.info(f"  Mount points: {mounts_str}")
    logger.info(f"  Web root: {web_str}")
    logger.info(f"  API endpoints:")
    logger.info(f"    GET  /api/mounts")
    logger.info(f"    GET  /api/mounts/{{id}}/tree?path=/")
    logger.info(f"    GET  /api/mounts/{{id}}/tree-recursive?path=/")
    logger.info(f"    GET  /api/mounts/{{id}}/file?path=/file.md")
    logger.info(f"    PUT  /api/mounts/{{id}}/file?path=/file.md")
    logger.info(f"    PUT  /api/mounts/{{id}}/rename?oldPath=/a.md&newPath=/b.md")
    logger.info(f"    PUT  /api/mounts/{{id}}/mkdir?path=/newdir")
    logger.info(f"    DELETE /api/mounts/{{id}}/file?path=/file.md")
    logger.info(f"  Static files: http://localhost:{port}/")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server stopped.")
        server.server_close()
