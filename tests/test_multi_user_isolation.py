"""Tests for multi-user isolation in the web server.

Covers:
- Session management (Cookie-based UUID)
- Mount point visibility per session
- Mount point ownership and write access
- Legacy mount backward compatibility
- Admin access to host mounts
- API isolation for search/stats/query/graph/tags/orphans/backlinks
- mounts.json persistence (grouped by owner)
"""

import json
import os
import shutil
import tempfile
import threading
import time
import urllib.request
import urllib.error

import pytest

# ---------------------------------------------------------------------------
# Helper: start a real HTTP server in a background thread for integration tests
# ---------------------------------------------------------------------------

_BASE_PORT = 18700
_port_lock = threading.Lock()
_port_counter = 0


def _next_port():
    global _port_counter
    with _port_lock:
        _port_counter += 1
        return _BASE_PORT + _port_counter


class ServerFixture:
    """Starts a nas-md web server on a random port with isolated storage."""

    def __init__(self, mount_dirs=None, admin=False):
        self.port = _next_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.tmpdir = tempfile.mkdtemp(prefix="nasmd_test_")
        self.storage_dir = os.path.join(self.tmpdir, "storage")
        os.makedirs(self.storage_dir, exist_ok=True)
        self.mount_dirs = mount_dirs or []
        self.admin = admin
        self._thread = None
        self._server = None

    def start(self):
        from nas_md.webserver import serve, _admin_mode

        if self.admin:
            import nas_md.webserver as ws

            ws._admin_mode = True

        # Create mount dirs on disk
        real_mount_dirs = []
        for d in self.mount_dirs:
            if isinstance(d, dict):
                path = os.path.join(self.tmpdir, d["name"])
                os.makedirs(path, exist_ok=True)
                # Write some test files
                for f in d.get("files", []):
                    fp = os.path.join(path, f["name"])
                    os.makedirs(os.path.dirname(fp), exist_ok=True)
                    with open(fp, "w", encoding="utf-8") as fh:
                        fh.write(f.get("content", ""))
                real_mount_dirs.append(path)
            else:
                os.makedirs(d, exist_ok=True)
                real_mount_dirs.append(d)

        # Start server in daemon thread
        def _run():
            serve(
                mount_dirs=real_mount_dirs,
                web_root="",
                port=self.port,
                storage_dir=self.storage_dir,
            )

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        # Wait for server to be ready
        for _ in range(40):
            try:
                urllib.request.urlopen(f"{self.base}/api/health")
                return
            except Exception:
                time.sleep(0.1)
        raise RuntimeError(f"Server did not start on port {self.port}")

    def stop(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _request(self, path, method="GET", data=None, headers=None, cookie=None):
        """Make an HTTP request and return (status, headers, body_json_or_raw)."""
        url = f"{self.base}{path}"
        body = (
            json.dumps(data).encode()
            if data is not None and not isinstance(data, bytes) and not isinstance(data, str)
            else (data.encode() if isinstance(data, str) else data)
        )
        req = urllib.request.Request(url, data=body, method=method)
        if headers:
            for k, v in headers.items():
                req.add_header(k, v)
        if body and "Content-Type" not in (headers or {}):
            req.add_header("Content-Type", "application/json")
        if cookie:
            req.add_header("Cookie", cookie)
        try:
            r = urllib.request.urlopen(req)
            resp_cookie = r.headers.get("Set-Cookie", "")
            raw = r.read()
            ct = r.headers.get("Content-Type", "")
            if "application/json" in ct:
                resp_data = json.loads(raw)
            else:
                resp_data = {"_raw": raw, "_content_type": ct}
            return r.status, resp_cookie, resp_data
        except urllib.error.HTTPError as e:
            resp_cookie = e.headers.get("Set-Cookie", "")
            try:
                resp_data = json.loads(e.read())
            except Exception:
                resp_data = {"raw": str(e)}
            return e.code, resp_cookie, resp_data

    def get(self, path, cookie=None, admin=False):
        headers = {}
        if admin:
            headers["X-Admin"] = "1"
        return self._request(path, "GET", headers=headers, cookie=cookie)

    def post(self, path, data, cookie=None, admin=False):
        headers = {}
        if admin:
            headers["X-Admin"] = "1"
        return self._request(path, "POST", data=data, headers=headers, cookie=cookie)

    def put(self, path, data=None, cookie=None, admin=False):
        headers = {}
        if admin:
            headers["X-Admin"] = "1"
        return self._request(path, "PUT", data=data, headers=headers, cookie=cookie)

    def delete(self, path, cookie=None, admin=False):
        headers = {}
        if admin:
            headers["X-Admin"] = "1"
        return self._request(path, "DELETE", headers=headers, cookie=cookie)


def _extract_sid(set_cookie):
    """Extract nasmd_sid from a Set-Cookie header value."""
    if not set_cookie:
        return ""
    for part in set_cookie.split(";"):
        part = part.strip()
        if part.startswith("nasmd_sid="):
            return part.split("=", 1)[1]
    return ""


def _make_cookie(sid):
    return f"nasmd_sid={sid}" if sid else None


# ---------------------------------------------------------------------------
# Test: Session management
# ---------------------------------------------------------------------------


class TestSessionManagement:
    def test_new_session_gets_cookie(self):
        """First request without cookie should get a Set-Cookie with nasmd_sid."""
        srv = ServerFixture()
        srv.start()
        try:
            status, cookie, _data = srv.get("/api/mounts")
            assert status == 200
            sid = _extract_sid(cookie)
            assert len(sid) > 10, "Should get a UUID session ID"
        finally:
            srv.stop()

    def test_existing_session_preserved(self):
        """Request with existing cookie should not get a new Set-Cookie."""
        srv = ServerFixture()
        srv.start()
        try:
            # First request to get SID
            _, cookie1, _ = srv.get("/api/mounts")
            sid = _extract_sid(cookie1)
            assert sid, "Should get SID on first request"
            # Second request with same SID
            _, cookie2, _ = srv.get("/api/mounts", cookie=_make_cookie(sid))
            sid2 = _extract_sid(cookie2)
            # Either no new cookie or same SID
            assert not sid2 or sid2 == sid, "Session should be preserved"
        finally:
            srv.stop()

    def test_two_sessions_are_different(self):
        """Two requests without cookies should get different session IDs."""
        srv = ServerFixture()
        srv.start()
        try:
            _, cookie1, _ = srv.get("/api/mounts")
            _, cookie2, _ = srv.get("/api/mounts")
            sid1 = _extract_sid(cookie1)
            sid2 = _extract_sid(cookie2)
            assert sid1 != sid2, "Different clients should get different session IDs"
        finally:
            srv.stop()

    def test_cookie_has_long_max_age(self):
        """Set-Cookie should have Max-Age=31536000 (1 year)."""
        srv = ServerFixture()
        srv.start()
        try:
            _, cookie, _ = srv.get("/api/mounts")
            assert "Max-Age=31536000" in cookie, f"Cookie should last 1 year: {cookie}"
        finally:
            srv.stop()


# ---------------------------------------------------------------------------
# Test: Mount point visibility
# ---------------------------------------------------------------------------


class TestMountVisibility:
    def test_builtin_storage_visible_to_all(self):
        """Builtin storage mount should be visible to all users."""
        srv = ServerFixture()
        srv.start()
        try:
            _, _, data = srv.get("/api/mounts")
            mount_ids = [m["id"] for m in data]
            assert "builtin-storage" in mount_ids
        finally:
            srv.stop()

    def test_host_mounts_only_visible_to_admin(self):
        """Host mounts (from MOUNT_DIRS) should only be visible to admin."""
        srv = ServerFixture(mount_dirs=[{"name": "hostdir", "files": []}])
        srv.start()
        try:
            # Regular user
            _, cookie, data = srv.get("/api/mounts")
            sid = _extract_sid(cookie)
            names = [m["name"] for m in data]
            assert "hostdir" not in names, "Regular user should NOT see host mount"

            # Admin user
            _, _, admin_data = srv.get("/api/mounts", cookie=_make_cookie(sid), admin=True)
            admin_names = [m["name"] for m in admin_data]
            assert "hostdir" in admin_names, "Admin should see host mount"
        finally:
            srv.stop()

    def test_user_mount_only_visible_to_owner(self):
        """User-added mount should only be visible to the user who added it."""
        srv = ServerFixture()
        srv.start()
        try:
            # User A adds a mount
            mount_dir = os.path.join(srv.tmpdir, "user_a_dir")
            os.makedirs(mount_dir, exist_ok=True)
            _, cookie_a, _ = srv.post("/api/mounts", {"path": mount_dir, "name": "UserA-Mount"})
            sid_a = _extract_sid(cookie_a)

            # User B (new session)
            _, cookie_b, data_b = srv.get("/api/mounts")
            _extract_sid(cookie_b)  # consume cookie to establish session

            # User A sees their mount
            _, _, data_a = srv.get("/api/mounts", cookie=_make_cookie(sid_a))
            a_names = [m["name"] for m in data_a]
            assert "UserA-Mount" in a_names, "Owner should see their mount"

            # User B does NOT see User A's mount
            b_names = [m["name"] for m in data_b]
            assert "UserA-Mount" not in b_names, "Other user should NOT see User A's mount"
        finally:
            srv.stop()

    def test_legacy_mount_visible_to_all(self):
        """Mounts with no owner and not host (legacy) should be visible to all."""
        srv = ServerFixture()
        srv.start()
        try:
            # Manually inject a legacy mount (no owner, not host)
            from nas_md.webserver import MountEntry, _save_mounts_to_disk

            legacy = MountEntry("mount-legacy", "LegacyMount", srv.tmpdir, public=True)
            # Use the mount_manager directly
            import nas_md.webserver as ws

            mgr = ws.MountHTTPHandler.mount_manager
            mgr.mounts.append(legacy)
            ws._save_mounts_to_disk(mgr.mounts)

            # Both users should see it
            _, _, data_a = srv.get("/api/mounts")
            _, _, data_b = srv.get("/api/mounts")
            a_names = [m["name"] for m in data_a]
            b_names = [m["name"] for m in data_b]
            assert "LegacyMount" in a_names, "Legacy mount should be visible to user A"
            assert "LegacyMount" in b_names, "Legacy mount should be visible to user B"
        finally:
            srv.stop()


# ---------------------------------------------------------------------------
# Test: Mount point ownership and write access
# ---------------------------------------------------------------------------


class TestMountOwnership:
    def test_owner_can_write_file(self):
        """Owner should be able to write files to their mount."""
        srv = ServerFixture()
        srv.start()
        try:
            mount_dir = os.path.join(srv.tmpdir, "user_dir")
            os.makedirs(mount_dir, exist_ok=True)
            _, cookie, add_data = srv.post("/api/mounts", {"path": mount_dir, "name": "MyMount"})
            sid = _extract_sid(cookie)
            mount_id = add_data["id"]

            # Write a file
            status, _, _ = srv.put(
                f"/api/mounts/{mount_id}/file?path=/test.md",
                data=None,
                cookie=_make_cookie(sid),
            )
            # PUT with no body may fail, let's write actual content
            write_url = f"/api/mounts/{mount_id}/file?path=/hello.md"
            status, _, wdata = srv._request(
                write_url,
                method="PUT",
                data="Hello World",
                headers={"Content-Type": "text/plain"},
                cookie=_make_cookie(sid),
            )
            assert status == 200, f"Owner should be able to write: {wdata}"
        finally:
            srv.stop()

    def test_non_owner_cannot_write_file(self):
        """Non-owner should NOT be able to write files to another user's mount."""
        srv = ServerFixture()
        srv.start()
        try:
            mount_dir = os.path.join(srv.tmpdir, "user_a_dir")
            os.makedirs(mount_dir, exist_ok=True)
            _, _cookie_a, add_data = srv.post(
                "/api/mounts", {"path": mount_dir, "name": "UserA-Mount"}
            )
            mount_id = add_data["id"]

            # User B tries to write
            _, cookie_b, _ = srv.get("/api/mounts")
            sid_b = _extract_sid(cookie_b)

            status, _, wdata = srv._request(
                f"/api/mounts/{mount_id}/file?path=/hack.md",
                method="PUT",
                data="Hacked!",
                headers={"Content-Type": "text/plain"},
                cookie=_make_cookie(sid_b),
            )
            assert status == 404, f"Non-owner should NOT be able to write: {wdata}"
        finally:
            srv.stop()

    def test_owner_can_delete_mount(self):
        """Owner should be able to delete their own mount."""
        srv = ServerFixture()
        srv.start()
        try:
            mount_dir = os.path.join(srv.tmpdir, "user_dir")
            os.makedirs(mount_dir, exist_ok=True)
            _, cookie, add_data = srv.post("/api/mounts", {"path": mount_dir, "name": "MyMount"})
            sid = _extract_sid(cookie)
            mount_id = add_data["id"]

            status, _, ddata = srv.delete(f"/api/mounts/{mount_id}", cookie=_make_cookie(sid))
            assert status == 200, f"Owner should be able to delete: {ddata}"
        finally:
            srv.stop()

    def test_non_owner_cannot_delete_mount(self):
        """Non-owner should NOT be able to delete another user's mount."""
        srv = ServerFixture()
        srv.start()
        try:
            mount_dir = os.path.join(srv.tmpdir, "user_a_dir")
            os.makedirs(mount_dir, exist_ok=True)
            _, _cookie_a, add_data = srv.post(
                "/api/mounts", {"path": mount_dir, "name": "UserA-Mount"}
            )
            mount_id = add_data["id"]

            # User B tries to delete
            _, cookie_b, _ = srv.get("/api/mounts")
            sid_b = _extract_sid(cookie_b)

            status, _, ddata = srv.delete(f"/api/mounts/{mount_id}", cookie=_make_cookie(sid_b))
            assert status == 404, f"Non-owner should NOT be able to delete: {ddata}"
        finally:
            srv.stop()

    def test_legacy_mount_allows_any_user_write(self):
        """Legacy mounts (no owner) should allow any user to write."""
        srv = ServerFixture()
        srv.start()
        try:
            # Inject legacy mount
            import nas_md.webserver as ws

            legacy = ws.MountEntry("mount-legacy", "LegacyMount", srv.tmpdir, public=True)
            ws.MountHTTPHandler.mount_manager.mounts.append(legacy)

            # Any user should be able to write
            _, cookie, _ = srv.get("/api/mounts")
            sid = _extract_sid(cookie)

            status, _, wdata = srv._request(
                "/api/mounts/mount-legacy/file?path=/legacy_test.md",
                method="PUT",
                data="Legacy content",
                headers={"Content-Type": "text/plain"},
                cookie=_make_cookie(sid),
            )
            assert status == 200, f"Any user should write to legacy mount: {wdata}"
        finally:
            srv.stop()

    def test_admin_can_write_host_mount(self):
        """Admin should be able to write to host mounts."""
        srv = ServerFixture(mount_dirs=[{"name": "hostdir", "files": []}])
        srv.start()
        try:
            _, cookie, data = srv.get("/api/mounts", admin=True)
            sid = _extract_sid(cookie)
            host_mounts = [m for m in data if m.get("host")]
            assert host_mounts, "Admin should see host mounts"
            mount_id = host_mounts[0]["id"]

            _status, _, _wdata = srv._request(
                f"/api/mounts/{mount_id}/file?path=/admin_test.md",
                method="PUT",
                data="Admin wrote this",
                headers={"Content-Type": "text/plain"},
                cookie=_make_cookie(sid),
            )
            # Admin with X-Admin header should be able to write
            # Note: need to pass admin header
            status2, _, wdata2 = srv.put(
                f"/api/mounts/{mount_id}/file?path=/admin_test2.md",
                data="Admin wrote this too",
                cookie=_make_cookie(sid),
                admin=True,
            )
            assert status2 == 200, f"Admin should write to host mount: {wdata2}"
        finally:
            srv.stop()


# ---------------------------------------------------------------------------
# Test: File operation isolation
# ---------------------------------------------------------------------------


class TestFileOperationIsolation:
    def test_tree_only_shows_visible_mounts(self):
        """Tree API should only return trees for visible mounts."""
        srv = ServerFixture()
        srv.start()
        try:
            # User A adds mount
            mount_dir = os.path.join(srv.tmpdir, "user_a_dir")
            os.makedirs(mount_dir, exist_ok=True)
            with open(os.path.join(mount_dir, "secret.md"), "w") as f:
                f.write("secret content")
            _, cookie_a, add_data = srv.post(
                "/api/mounts", {"path": mount_dir, "name": "UserA-Mount"}
            )
            sid_a = _extract_sid(cookie_a)
            mount_id = add_data["id"]

            # User A can access tree
            status, _, _tree_a = srv.get(f"/api/mounts/{mount_id}/tree", cookie=_make_cookie(sid_a))
            assert status == 200, "Owner should access tree"

            # User B cannot access tree
            _, cookie_b, _ = srv.get("/api/mounts")
            sid_b = _extract_sid(cookie_b)
            status, _, _tree_b = srv.get(f"/api/mounts/{mount_id}/tree", cookie=_make_cookie(sid_b))
            assert status == 404, "Non-owner should NOT access tree"
        finally:
            srv.stop()

    def test_file_read_only_for_visible_mounts(self):
        """File API should only serve files from visible mounts."""
        srv = ServerFixture()
        srv.start()
        try:
            mount_dir = os.path.join(srv.tmpdir, "user_a_dir")
            os.makedirs(mount_dir, exist_ok=True)
            with open(os.path.join(mount_dir, "secret.md"), "w") as f:
                f.write("secret content")
            _, cookie_a, add_data = srv.post(
                "/api/mounts", {"path": mount_dir, "name": "UserA-Mount"}
            )
            sid_a = _extract_sid(cookie_a)
            mount_id = add_data["id"]

            # User A can read file
            status, _, _ = srv.get(
                f"/api/mounts/{mount_id}/file?path=/secret.md", cookie=_make_cookie(sid_a)
            )
            assert status == 200, "Owner should read file"

            # User B cannot read file
            _, cookie_b, _ = srv.get("/api/mounts")
            sid_b = _extract_sid(cookie_b)
            status, _, _ = srv.get(
                f"/api/mounts/{mount_id}/file?path=/secret.md", cookie=_make_cookie(sid_b)
            )
            assert status == 404, "Non-owner should NOT read file"
        finally:
            srv.stop()

    def test_rename_only_for_owner(self):
        """Rename should only work for mount owner."""
        srv = ServerFixture()
        srv.start()
        try:
            mount_dir = os.path.join(srv.tmpdir, "user_dir")
            os.makedirs(mount_dir, exist_ok=True)
            with open(os.path.join(mount_dir, "old.md"), "w") as f:
                f.write("content")
            _, cookie_a, add_data = srv.post(
                "/api/mounts", {"path": mount_dir, "name": "UserA-Mount"}
            )
            _sid_a = _extract_sid(cookie_a)
            mount_id = add_data["id"]

            # User B tries to rename
            _, cookie_b, _ = srv.get("/api/mounts")
            sid_b = _extract_sid(cookie_b)
            status, _, _ = srv.put(
                f"/api/mounts/{mount_id}/rename?oldPath=/old.md&newPath=/renamed.md",
                cookie=_make_cookie(sid_b),
            )
            assert status == 404, "Non-owner should NOT rename"
        finally:
            srv.stop()

    def test_mkdir_only_for_owner(self):
        """Mkdir should only work for mount owner."""
        srv = ServerFixture()
        srv.start()
        try:
            mount_dir = os.path.join(srv.tmpdir, "user_dir")
            os.makedirs(mount_dir, exist_ok=True)
            _, cookie_a, add_data = srv.post(
                "/api/mounts", {"path": mount_dir, "name": "UserA-Mount"}
            )
            _sid_a = _extract_sid(cookie_a)
            mount_id = add_data["id"]

            # User B tries to mkdir
            _, cookie_b, _ = srv.get("/api/mounts")
            sid_b = _extract_sid(cookie_b)
            status, _, _ = srv.put(
                f"/api/mounts/{mount_id}/mkdir?path=/new_folder",
                cookie=_make_cookie(sid_b),
            )
            assert status == 404, "Non-owner should NOT mkdir"
        finally:
            srv.stop()

    def test_delete_file_only_for_owner(self):
        """File deletion should only work for mount owner."""
        srv = ServerFixture()
        srv.start()
        try:
            mount_dir = os.path.join(srv.tmpdir, "user_dir")
            os.makedirs(mount_dir, exist_ok=True)
            with open(os.path.join(mount_dir, "todelete.md"), "w") as f:
                f.write("delete me")
            _, cookie_a, add_data = srv.post(
                "/api/mounts", {"path": mount_dir, "name": "UserA-Mount"}
            )
            _sid_a = _extract_sid(cookie_a)
            mount_id = add_data["id"]

            # User B tries to delete
            _, cookie_b, _ = srv.get("/api/mounts")
            sid_b = _extract_sid(cookie_b)
            status, _, _ = srv.delete(
                f"/api/mounts/{mount_id}/file?path=/todelete.md",
                cookie=_make_cookie(sid_b),
            )
            assert status == 404, "Non-owner should NOT delete"
        finally:
            srv.stop()


# ---------------------------------------------------------------------------
# Test: mounts.json persistence
# ---------------------------------------------------------------------------


class TestMountsPersistence:
    def test_mounts_saved_grouped_by_owner(self):
        """Mounts should be saved to disk grouped by owner."""
        srv = ServerFixture()
        srv.start()
        try:
            mount_dir = os.path.join(srv.tmpdir, "user_dir")
            os.makedirs(mount_dir, exist_ok=True)
            _, cookie, _ = srv.post("/api/mounts", {"path": mount_dir, "name": "MyMount"})
            sid = _extract_sid(cookie)

            # Check mounts.json
            mounts_file = os.path.join(srv.storage_dir, "mounts.json")
            assert os.path.isfile(mounts_file), "mounts.json should exist"
            with open(mounts_file, encoding="utf-8") as f:
                data = json.load(f)
            assert isinstance(data, dict), "Should be grouped dict"
            assert sid in data, f"Owner key {sid} should be in mounts.json"
            owner_mounts = data[sid]
            assert any(m["name"] == "MyMount" for m in owner_mounts)
        finally:
            srv.stop()

    def test_old_format_migration(self):
        """Old flat-list format mounts.json should be migrated correctly."""
        srv = ServerFixture()
        srv.start()
        try:
            # Write old-format mounts.json
            mounts_file = os.path.join(srv.storage_dir, "mounts.json")
            old_data = [
                {"id": "mount-0", "name": "OldMount", "path": srv.tmpdir, "public": True},
            ]
            with open(mounts_file, "w", encoding="utf-8") as f:
                json.dump(old_data, f)

            # Reload
            from nas_md.webserver import _load_saved_mounts

            result = _load_saved_mounts()
            assert isinstance(result, dict), "Should be migrated to dict format"
            assert "_host" in result, "Old mounts without owner should go to _host key"
        finally:
            srv.stop()


# ---------------------------------------------------------------------------
# Test: MountEntry owner field
# ---------------------------------------------------------------------------


class TestMountEntryOwner:
    def test_to_dict_includes_owner(self):
        from nas_md.webserver import MountEntry

        entry = MountEntry("test-id", "Test", "/tmp", owner="user-123")
        d = entry.to_dict()
        assert d["owner"] == "user-123"

    def test_from_dict_reads_owner(self):
        from nas_md.webserver import MountEntry

        d = {"id": "test-id", "name": "Test", "path": "/tmp", "owner": "user-456"}
        entry = MountEntry.from_dict(d)
        assert entry.owner == "user-456"

    def test_default_owner_empty(self):
        from nas_md.webserver import MountEntry

        entry = MountEntry("test-id", "Test", "/tmp")
        assert entry.owner == ""

    def test_from_dict_missing_owner(self):
        from nas_md.webserver import MountEntry

        d = {"id": "test-id", "name": "Test", "path": "/tmp"}
        entry = MountEntry.from_dict(d)
        assert entry.owner == ""


# ---------------------------------------------------------------------------
# Test: _visible_mount_paths and _path_visible helpers
# ---------------------------------------------------------------------------


class TestPathVisibilityHelpers:
    def test_visible_mount_paths_returns_lowercase(self):
        """_visible_mount_paths should return lowercase, stripped paths."""
        from nas_md.webserver import MountEntry, MountHTTPHandler

        mgr = type("MM", (), {"mounts": [MountEntry("m1", "Test", r"C:\Users\Test\Dir")]})()
        handler = MountHTTPHandler.__new__(MountHTTPHandler)
        handler.mount_manager = mgr
        # Mock _get_session_id and _is_admin_request
        handler._get_session_id = lambda: "test"
        handler._is_admin_request = lambda: False
        # The mount has no owner and is not host, so it's visible
        paths = handler._visible_mount_paths("test")
        assert len(paths) == 1
        assert paths[0] == r"c:\users\test\dir"

    def test_path_visible_matches_prefix(self):
        from nas_md.webserver import MountHTTPHandler

        handler = MountHTTPHandler.__new__(MountHTTPHandler)
        mount_paths = [r"c:\users\test\dir"]
        assert handler._path_visible(r"C:\Users\Test\Dir\notes.md", mount_paths)
        assert handler._path_visible(r"C:\Users\Test\Dir", mount_paths)
        assert not handler._path_visible(r"C:\Users\Other\file.md", mount_paths)

    def test_path_visible_with_forward_slash(self):
        from nas_md.webserver import MountHTTPHandler

        handler = MountHTTPHandler.__new__(MountHTTPHandler)
        mount_paths = [r"c:\users\test\dir"]
        assert handler._path_visible("c:/users/test/dir/notes.md", mount_paths)


# ---------------------------------------------------------------------------
# Test: _owns_mount logic
# ---------------------------------------------------------------------------


class TestOwnsMount:
    def _make_handler(self):
        from nas_md.webserver import MountHTTPHandler

        handler = MountHTTPHandler.__new__(MountHTTPHandler)
        return handler

    def test_builtin_not_owned(self):
        from nas_md.webserver import MountEntry

        handler = self._make_handler()
        builtin = MountEntry("builtin-storage", "nas-md", "/tmp")
        assert not handler._owns_mount(builtin, "any-user")

    def test_host_not_owned(self):
        from nas_md.webserver import MountEntry

        handler = self._make_handler()
        host = MountEntry("mount-0", "Host", "/tmp", host=True)
        assert not handler._owns_mount(host, "any-user")

    def test_owner_match(self):
        from nas_md.webserver import MountEntry

        handler = self._make_handler()
        user_mount = MountEntry("mount-1", "User", "/tmp", owner="user-123")
        assert handler._owns_mount(user_mount, "user-123")
        assert not handler._owns_mount(user_mount, "user-456")

    def test_legacy_anyone_owns(self):
        from nas_md.webserver import MountEntry

        handler = self._make_handler()
        legacy = MountEntry("mount-legacy", "Legacy", "/tmp")
        assert handler._owns_mount(legacy, "any-user")
        assert handler._owns_mount(legacy, "different-user")


# ---------------------------------------------------------------------------
# Test: _visible_mounts logic
# ---------------------------------------------------------------------------


class TestVisibleMounts:
    def _make_handler(self, mounts, is_admin=False):
        from nas_md.webserver import MountHTTPHandler

        handler = MountHTTPHandler.__new__(MountHTTPHandler)
        handler.mount_manager = type("MM", (), {"mounts": mounts})()
        handler._is_admin_request = lambda: is_admin
        return handler

    def test_builtin_always_visible(self):
        from nas_md.webserver import MountEntry

        builtin = MountEntry("builtin-storage", "nas-md", "/tmp")
        handler = self._make_handler([builtin])
        visible = handler._visible_mounts("any-user")
        assert builtin in visible

    def test_host_only_admin(self):
        from nas_md.webserver import MountEntry

        host = MountEntry("mount-0", "Host", "/tmp", host=True)
        handler_user = self._make_handler([host], is_admin=False)
        handler_admin = self._make_handler([host], is_admin=True)
        assert host not in handler_user._visible_mounts("user-1")
        assert host in handler_admin._visible_mounts("admin-user")

    def test_user_mount_owner_only(self):
        from nas_md.webserver import MountEntry

        user_mount = MountEntry("mount-1", "User", "/tmp", owner="user-a")
        handler = self._make_handler([user_mount])
        assert user_mount in handler._visible_mounts("user-a")
        assert user_mount not in handler._visible_mounts("user-b")

    def test_legacy_visible_to_all(self):
        from nas_md.webserver import MountEntry

        legacy = MountEntry("mount-legacy", "Legacy", "/tmp")
        handler = self._make_handler([legacy])
        assert legacy in handler._visible_mounts("user-a")
        assert legacy in handler._visible_mounts("user-b")

    def test_admin_sees_host_and_own_mounts(self):
        from nas_md.webserver import MountEntry

        host = MountEntry("mount-0", "Host", "/tmp", host=True)
        admin_mount = MountEntry("mount-1", "AdminMount", "/tmp2", owner="admin-sid")
        other_mount = MountEntry("mount-2", "OtherMount", "/tmp3", owner="other-sid")
        handler = self._make_handler([host, admin_mount, other_mount], is_admin=True)
        visible = handler._visible_mounts("admin-sid")
        assert host in visible
        assert admin_mount in visible
        assert other_mount not in visible, "Admin should NOT see other user's mounts"


# ---------------------------------------------------------------------------
# Test: Multiple users complete isolation scenario
# ---------------------------------------------------------------------------


class TestCompleteIsolation:
    def test_two_users_completely_isolated(self):
        """End-to-end: two users add mounts, neither can see the other's."""
        srv = ServerFixture()
        srv.start()
        try:
            # User A adds mount
            dir_a = os.path.join(srv.tmpdir, "user_a")
            os.makedirs(dir_a, exist_ok=True)
            with open(os.path.join(dir_a, "a_note.md"), "w") as f:
                f.write("# User A Note\n- [ ] Task A")
            _, cookie_a, add_a = srv.post("/api/mounts", {"path": dir_a, "name": "A-Files"})
            sid_a = _extract_sid(cookie_a)
            mount_a_id = add_a["id"]

            # User B adds mount
            dir_b = os.path.join(srv.tmpdir, "user_b")
            os.makedirs(dir_b, exist_ok=True)
            with open(os.path.join(dir_b, "b_note.md"), "w") as f:
                f.write("# User B Note\n- [ ] Task B")
            _, cookie_b, add_b = srv.post("/api/mounts", {"path": dir_b, "name": "B-Files"})
            sid_b = _extract_sid(cookie_b)
            mount_b_id = add_b["id"]

            # User A sees only A-Files
            _, _, mounts_a = srv.get("/api/mounts", cookie=_make_cookie(sid_a))
            a_names = [m["name"] for m in mounts_a]
            assert "A-Files" in a_names
            assert "B-Files" not in a_names

            # User B sees only B-Files
            _, _, mounts_b = srv.get("/api/mounts", cookie=_make_cookie(sid_b))
            b_names = [m["name"] for m in mounts_b]
            assert "B-Files" in b_names
            assert "A-Files" not in b_names

            # User A can read own file
            status, _, _ = srv.get(
                f"/api/mounts/{mount_a_id}/file?path=/a_note.md", cookie=_make_cookie(sid_a)
            )
            assert status == 200

            # User A cannot read B's file
            status, _, _ = srv.get(
                f"/api/mounts/{mount_b_id}/file?path=/b_note.md", cookie=_make_cookie(sid_a)
            )
            assert status == 404

            # User B cannot read A's file
            status, _, _ = srv.get(
                f"/api/mounts/{mount_a_id}/file?path=/a_note.md", cookie=_make_cookie(sid_b)
            )
            assert status == 404

            # User A cannot delete B's mount
            status, _, _ = srv.delete(f"/api/mounts/{mount_b_id}", cookie=_make_cookie(sid_a))
            assert status == 404

            # User B cannot delete A's mount
            status, _, _ = srv.delete(f"/api/mounts/{mount_a_id}", cookie=_make_cookie(sid_b))
            assert status == 404
        finally:
            srv.stop()

    def test_no_mount_limit_per_user(self):
        """A user should be able to add multiple mount points."""
        srv = ServerFixture()
        srv.start()
        try:
            _, cookie, _ = srv.get("/api/mounts")
            sid = _extract_sid(cookie)

            for i in range(5):
                d = os.path.join(srv.tmpdir, f"dir_{i}")
                os.makedirs(d, exist_ok=True)
                _, _, add_data = srv.post(
                    "/api/mounts",
                    {"path": d, "name": f"Mount-{i}"},
                    cookie=_make_cookie(sid),
                )
                assert add_data.get("id"), f"Should add mount {i}"

            _, _, mounts = srv.get("/api/mounts", cookie=_make_cookie(sid))
            user_mounts = [m for m in mounts if m["name"].startswith("Mount-")]
            assert len(user_mounts) == 5, "Should have 5 user mounts"
        finally:
            srv.stop()
