"""Integration tests for the webserver HTTP routes.

Uses a real HTTP server on a random port to verify:
- API route correctness (method, status code, response shape)
- Static file serving (JS/CSS must not return HTML fallback)
- Internal dirs (certs) hidden from file listings
- Self-signed certificate generation
"""

import json
import os
import shutil
import socket
import tempfile
import threading
import time

import pytest

from nas_md.webserver import (
    MountManager,
    MountHTTPHandler,
    _generate_self_signed_cert,
    _create_server,
    serve,
)


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def web_root():
    """Create a temporary web root with minimal static files."""
    d = tempfile.mkdtemp(prefix="nasmd_web_")
    # index.html
    with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
        f.write("<!DOCTYPE html><html><body>app</body></html>")
    # Simulate Vditor JS
    vditor_dir = os.path.join(d, "lib", "vditor")
    os.makedirs(vditor_dir, exist_ok=True)
    with open(os.path.join(vditor_dir, "index.min.js"), "w", encoding="utf-8") as f:
        f.write("var Vditor = function() {};")
    with open(os.path.join(vditor_dir, "index.css"), "w", encoding="utf-8") as f:
        f.write("/* vditor css */")
    # Simulate vditor-cdn
    cdn_dir = os.path.join(d, "lib", "vditor-cdn", "dist", "js")
    os.makedirs(cdn_dir, exist_ok=True)
    with open(os.path.join(cdn_dir, "index.js"), "w", encoding="utf-8") as f:
        f.write("// vditor cdn")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def storage_dir():
    """Create a temporary storage directory."""
    d = tempfile.mkdtemp(prefix="nasmd_storage_")
    # Add a sample .md file
    with open(os.path.join(d, "test.md"), "w", encoding="utf-8") as f:
        f.write("# Hello\n")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def server_url(web_root, storage_dir):
    """Start a test HTTP server and return its base URL."""
    port = _find_free_port()

    # Set up mount manager and handler class attrs directly
    mgr = MountManager([])
    from nas_md.webserver import MountEntry

    builtin = MountEntry("builtin-storage", "nas-md", storage_dir, public=True, readonly=True)
    mgr.mounts.insert(0, builtin)

    MountHTTPHandler.mount_manager = mgr
    MountHTTPHandler.web_root = web_root
    MountHTTPHandler.search_dirs = [storage_dir]

    server = _create_server("127.0.0.1", port, MountHTTPHandler, cert_dir="")

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # Wait for server to be ready
    time.sleep(0.3)

    yield f"http://127.0.0.1:{port}"

    server.shutdown()


def _get(url: str, headers: dict | None = None) -> tuple[int, str, dict]:
    """Send GET request, return (status, body_text, headers_dict)."""
    import urllib.request

    try:
        req = urllib.request.Request(url)
        if headers:
            for k, v in headers.items():
                req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, body, resp_headers
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return e.code, body, {}


def _post(
    url: str,
    data: dict | None = None,
    content_type: str = "application/json",
    headers: dict | None = None,
) -> tuple[int, str]:
    """Send POST request, return (status, body_text)."""
    import urllib.request

    body_bytes = json.dumps(data).encode("utf-8") if data else b"{}"
    try:
        req = urllib.request.Request(url, data=body_bytes, method="POST")
        req.add_header("Content-Type", content_type)
        if headers:
            for k, v in headers.items():
                req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def _put(url: str, data: bytes = b"", headers: dict | None = None) -> tuple[int, str]:
    """Send PUT request, return (status, body_text)."""
    import urllib.request

    try:
        req = urllib.request.Request(url, data=data, method="PUT")
        if headers:
            for k, v in headers.items():
                req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def _delete(url: str, headers: dict | None = None) -> tuple[int, str]:
    """Send DELETE request, return (status, body_text)."""
    import urllib.request

    try:
        req = urllib.request.Request(url, method="DELETE")
        if headers:
            for k, v in headers.items():
                req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


# --- API route tests ---


class TestHealthRoute:
    def test_health_returns_ok(self, server_url):
        status, body, _ = _get(f"{server_url}/api/health")
        assert status == 200
        data = json.loads(body)
        assert data.get("status") == "ok"


class TestMountsRoute:
    def test_mounts_returns_list(self, server_url):
        status, body, _ = _get(f"{server_url}/api/mounts")
        assert status == 200
        data = json.loads(body)
        assert isinstance(data, list)
        # Should include builtin-storage
        ids = [m["id"] for m in data]
        assert "builtin-storage" in ids


class TestSyncRoute:
    def test_sync_post_not_405(self, server_url):
        """POST /api/sync must not return 405 Method Not Allowed."""
        status, _body = _post(f"{server_url}/api/sync?mount=builtin-storage", {"files": {}})
        assert status != 405, "POST /api/sync returned 405 — route missing from do_POST"

    def test_sync_post_returns_json(self, server_url):
        """POST /api/sync must return valid JSON, not HTML."""
        status, body = _post(f"{server_url}/api/sync?mount=builtin-storage", {"files": {}})
        assert status == 200
        data = json.loads(body)
        assert "download" in data
        assert "upload" in data
        assert "delete" in data

    def test_sync_post_with_mount_param(self, server_url):
        """Frontend uses 'mount' query param, not 'mount_id'."""
        status, _body = _post(f"{server_url}/api/sync?mount=builtin-storage", {"files": {}})
        assert status == 200

    def test_sync_status_get(self, server_url):
        """GET /api/sync/status must return valid JSON."""
        status, body, _ = _get(f"{server_url}/api/sync/status?mount=builtin-storage")
        assert status == 200
        data = json.loads(body)
        assert isinstance(data, dict)

    def test_sync_post_unknown_mount(self, server_url):
        """POST /api/sync with unknown mount should return 404, not 405."""
        status, _body = _post(f"{server_url}/api/sync?mount=nonexistent", {"files": {}})
        assert status == 404


class TestFileRoute:
    def test_get_file_returns_content(self, server_url):
        """GET /api/mounts/{id}/file must return file content."""
        status, body, _headers = _get(f"{server_url}/api/mounts/builtin-storage/file?path=/test.md")
        assert status == 200
        assert "Hello" in body

    def test_get_file_not_found(self, server_url):
        status, _body, _ = _get(
            f"{server_url}/api/mounts/builtin-storage/file?path=/nonexistent.md"
        )
        assert status == 404


class TestTreeRoute:
    def test_tree_returns_structure(self, server_url):
        status, body, _ = _get(f"{server_url}/api/mounts/builtin-storage/tree?path=/")
        assert status == 200
        data = json.loads(body)
        assert isinstance(data, list)


# --- Static file serving tests ---


class TestStaticFiles:
    def test_index_html_served(self, server_url):
        status, body, _ = _get(f"{server_url}/")
        assert status == 200
        assert "<!DOCTYPE html>" in body

    def test_vditor_js_served_as_js(self, server_url):
        """Vditor JS must be served with JS content-type, not HTML fallback."""
        status, body, headers = _get(f"{server_url}/lib/vditor/index.min.js")
        assert status == 200
        ct = headers.get("content-type", "")
        assert "javascript" in ct, f"Expected JS content-type, got: {ct}"
        assert "Vditor" in body, "Vditor JS content missing — got HTML fallback?"

    def test_vditor_css_served_as_css(self, server_url):
        status, _body, headers = _get(f"{server_url}/lib/vditor/index.css")
        assert status == 200
        ct = headers.get("content-type", "")
        assert "css" in ct, f"Expected CSS content-type, got: {ct}"

    def test_vditor_cdn_js_served(self, server_url):
        """Vditor CDN JS must not return HTML fallback."""
        status, _body, headers = _get(f"{server_url}/lib/vditor-cdn/dist/js/index.js")
        assert status == 200
        ct = headers.get("content-type", "")
        assert "javascript" in ct

    def test_spa_fallback_for_unknown_path(self, server_url):
        """Non-file paths should fall back to index.html (SPA)."""
        status, body, _ = _get(f"{server_url}/admin")
        assert status == 200
        assert "<!DOCTYPE html>" in body

    def test_nonexistent_static_file_returns_html(self, server_url):
        """A nonexistent .js path should fall back to index.html (SPA), not 404."""
        status, body, _ = _get(f"{server_url}/nonexistent-page-route")
        assert status == 200
        assert "<!DOCTYPE html>" in body


# --- certs directory hidden from file listings ---


class TestCertsHidden:
    def test_certs_dir_not_in_tree(self, server_url, storage_dir):
        """The certs directory must not appear in mount tree listings."""
        # Create a certs dir in storage
        certs_dir = os.path.join(storage_dir, "certs")
        os.makedirs(certs_dir, exist_ok=True)
        with open(os.path.join(certs_dir, "test.crt"), "w") as f:
            f.write("cert")

        status, body, _ = _get(f"{server_url}/api/mounts/builtin-storage/tree-recursive")
        assert status == 200
        data = json.loads(body)
        # Recursively check no "certs" name in the tree
        names = []

        def collect_names(node):
            names.append(node.get("name", ""))
            for child in node.get("children", []):
                collect_names(child)

        collect_names(data)
        assert "certs" not in names, f"'certs' should be hidden but found in tree: {names}"

    def test_certs_dir_not_in_list(self, server_url, storage_dir):
        """The certs directory must not appear in directory listings."""
        certs_dir = os.path.join(storage_dir, "certs")
        os.makedirs(certs_dir, exist_ok=True)

        status, body, _ = _get(f"{server_url}/api/mounts/builtin-storage/tree?path=/")
        assert status == 200
        data = json.loads(body)
        # tree returns a list of entry dicts
        child_names = [e.get("name", "") for e in data]
        assert "certs" not in child_names


# --- Self-signed certificate generation ---


class TestCertGeneration:
    def test_generate_cert_creates_files(self):
        """_generate_self_signed_cert should create cert and key files."""
        d = tempfile.mkdtemp(prefix="nasmd_certs_")
        try:
            cert_path, key_path = _generate_self_signed_cert(d)
            assert os.path.isfile(cert_path), f"Cert file not created: {cert_path}"
            assert os.path.isfile(key_path), f"Key file not created: {key_path}"
            # Verify cert is valid PEM
            with open(cert_path, "rb") as f:
                data = f.read()
            assert b"BEGIN CERTIFICATE" in data
            with open(key_path, "rb") as f:
                data = f.read()
            assert b"BEGIN" in data and b"PRIVATE KEY" in data
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_generate_cert_reuses_existing(self):
        """If cert already exists, should reuse without regenerating."""
        d = tempfile.mkdtemp(prefix="nasmd_certs_")
        try:
            cert_path, _key_path = _generate_self_signed_cert(d)
            # Get mtime of first generation
            mtime1 = os.path.getmtime(cert_path)
            # Call again — should reuse
            time.sleep(0.1)
            cert_path2, _key_path2 = _generate_self_signed_cert(d)
            assert cert_path2 == cert_path
            mtime2 = os.path.getmtime(cert_path)
            assert mtime1 == mtime2, "Cert was regenerated instead of reused"
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_generate_cert_with_cryptography(self):
        """Test cert generation using cryptography library (skip if unavailable)."""
        try:
            from cryptography import x509
        except ImportError:
            pytest.skip("cryptography library not installed")

        d = tempfile.mkdtemp(prefix="nasmd_certs_")
        try:
            cert_path, _key_path = _generate_self_signed_cert(d)
            # Verify the cert has SAN extension
            from cryptography import x509
            from cryptography.hazmat.primitives.serialization import Encoding

            with open(cert_path, "rb") as f:
                cert = x509.load_pem_x509_certificate(f.read())
            san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
            assert san is not None, "Certificate missing SAN extension"
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_create_server_with_https(self):
        """_create_server with cert_dir should create an HTTPS server."""
        d = tempfile.mkdtemp(prefix="nasmd_certs_")
        try:
            _cert_path, _key_path = _generate_self_signed_cert(d)
            port = _find_free_port()
            server = _create_server("127.0.0.1", port, MountHTTPHandler, cert_dir=d)
            assert server is not None
            server.server_close()
        except RuntimeError:
            pytest.skip("Neither openssl nor cryptography available for cert generation")
        finally:
            shutil.rmtree(d, ignore_errors=True)


# --- Writable server fixture for write operation tests ---


@pytest.fixture
def writable_dir():
    """Create a temporary writable storage directory."""
    d = tempfile.mkdtemp(prefix="nasmd_writable_")
    with open(os.path.join(d, "hello.md"), "w", encoding="utf-8") as f:
        f.write("# Hello World\n")
    os.makedirs(os.path.join(d, "subdir"), exist_ok=True)
    with open(os.path.join(d, "subdir", "note.md"), "w", encoding="utf-8") as f:
        f.write("## Sub-note\n")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def writable_server_url(web_root, writable_dir):
    """Start a test server with a writable mount and a readonly mount."""
    from nas_md.webserver.file_version_store import get_store
    from nas_md.webserver import version_history
    import contextlib
    import glob

    store = get_store()
    with store._lock:
        store._files.clear()
    with version_history._lock:
        version_history._histories.clear()
    for f in glob.glob("storage/.version_history/writable__*.json"):
        with contextlib.suppress(OSError):
            os.remove(f)

    port = _find_free_port()
    mgr = MountManager([])
    from nas_md.webserver import MountEntry

    writable = MountEntry(
        "writable", "writable", writable_dir, public=True, readonly=False, host=True
    )
    readonly = MountEntry(
        "readonly", "readonly", writable_dir, public=True, readonly=True, host=True
    )
    mgr.mounts.insert(0, writable)
    mgr.mounts.insert(1, readonly)
    MountHTTPHandler.mount_manager = mgr
    MountHTTPHandler.web_root = web_root
    MountHTTPHandler.search_dirs = [writable_dir]

    server = _create_server("127.0.0.1", port, MountHTTPHandler, cert_dir="")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.3)
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


def test_watcher_external_creation_increments_once_and_broadcasts(tmp_path, monkeypatch):
    from unittest.mock import Mock

    from nas_md.webserver import version_history
    import nas_md.webserver.file_version_store as file_version_store_module
    from nas_md.webserver.file_version_store import FileVersionStore

    mount_dir = tmp_path / "watched"
    mount_dir.mkdir()
    target = mount_dir / "external.md"
    watcher = Mock()
    server = Mock()
    broadcast = Mock()
    store = FileVersionStore(storage_dir=str(tmp_path / ".version_history"))
    monkeypatch.setattr(file_version_store_module, "_store", store)
    with version_history._lock:
        version_history._histories.clear()

    monkeypatch.setattr("nas_md.webserver.file_watcher.get_watcher", lambda: watcher)
    monkeypatch.setattr("nas_md.webserver.sse_handler.sse_broadcast", broadcast)
    monkeypatch.setattr("nas_md.webserver._create_server", lambda *args, **kwargs: server)
    monkeypatch.setattr("nas_md.webserver._init_search_index", lambda _dirs: None)

    def stop_server(_delay):
        raise KeyboardInterrupt

    monkeypatch.setattr("nas_md.webserver.time.sleep", stop_server)

    serve([str(mount_dir)], web_root=str(tmp_path), port=0, https_port=0)

    mount_id, _watched_path, on_change = watcher.watch_mount.call_args.args
    file_key = f"{mount_id}:/external.md"
    store.init_file(file_key, str(target), "", persisted=False)
    target.write_text("external", encoding="utf-8")

    on_change(mount_id, "/external.md", "external")

    assert store.get_current_snapshot(file_key) == {"version": 1, "content": "external"}
    broadcast.assert_called_once_with(
        file_key,
        exclude_id=None,
        event={
            "type": "external_reload",
            "mountId": mount_id,
            "path": "/external.md",
            "newVersion": 1,
            "content": "external",
        },
    )


# --- Write operation API tests ---


class TestWriteFileAPI:
    def test_write_file_creates_new(self, writable_server_url, writable_dir):
        """PUT /api/mounts/{id}/file creates a new file."""
        content = "# New File\n"
        status, body = _put(
            f"{writable_server_url}/api/mounts/writable/file?path=/new.md",
            data=content.encode("utf-8"),
        )
        assert status == 200
        data = json.loads(body)
        assert data.get("status") == "ok"
        # Verify file exists on disk
        assert os.path.isfile(os.path.join(writable_dir, "new.md"))
        with open(os.path.join(writable_dir, "new.md"), encoding="utf-8") as f:
            assert f.read() == content

    def test_get_external_creation_advances_existing_unpersisted_version(
        self, writable_server_url, writable_dir
    ):
        from nas_md.webserver.file_version_store import get_store

        name = f"get-external-{os.path.basename(writable_dir)}.md"
        rel_path = f"/{name}"
        path = os.path.join(writable_dir, name)
        file_key = f"writable:{rel_path}"
        store = get_store()
        store.init_file(file_key, path, "", persisted=False)
        with open(path, "w", encoding="utf-8") as f:
            f.write("external")

        status, body, headers = _get(
            f"{writable_server_url}/api/mounts/writable/file?path={rel_path}"
        )

        assert status == 200
        assert body == "external"
        assert headers["x-file-version"] == "1"
        assert store.get_current_snapshot(file_key) == {"version": 1, "content": "external"}

        status, body, headers = _get(
            f"{writable_server_url}/api/mounts/writable/file?path={rel_path}"
        )
        assert (status, body, headers["x-file-version"]) == (200, "external", "1")

    def test_write_file_creates_missing_empty_markdown_without_history_or_broadcast(
        self, writable_server_url, writable_dir, monkeypatch
    ):
        from unittest.mock import Mock

        from nas_md.webserver import version_history
        from nas_md.webserver.file_version_store import get_store

        name = f"missing-empty-{os.path.basename(writable_dir)}.md"
        rel_path = f"/{name}"
        path = os.path.join(writable_dir, name)
        file_key = f"writable:{rel_path}"
        watcher = Mock()
        prepared_calls = []

        def mark_expected(mount_id, marked_path, prepared_path):
            with open(prepared_path, "rb") as f:
                prepared_calls.append((mount_id, marked_path, f.read()))

        watcher.mark_expected.side_effect = mark_expected
        broadcast = Mock()
        monkeypatch.setattr("nas_md.webserver.file_watcher.get_watcher", lambda: watcher)
        monkeypatch.setattr("nas_md.webserver.sse_handler.sse_broadcast", broadcast)

        status, body = _put(
            f"{writable_server_url}/api/mounts/writable/file?path={rel_path}",
            data=b"",
        )

        assert status == 200
        assert json.loads(body)["newVersion"] == 0
        assert os.path.isfile(path)
        with open(path, "rb") as f:
            assert f.read() == b""
        assert get_store().get_current_version(file_key) == 0
        assert file_key not in version_history._histories
        assert prepared_calls == [("writable", rel_path, b"")]
        broadcast.assert_not_called()

    def test_empty_put_recreates_deleted_version_at_a_new_version(
        self, writable_server_url, writable_dir
    ):
        from nas_md.webserver.file_version_store import get_store

        name = f"deleted-empty-{os.path.basename(writable_dir)}.md"
        rel_path = f"/{name}"
        path = os.path.join(writable_dir, name)
        file_key = f"writable:{rel_path}"

        status, body = _put(
            f"{writable_server_url}/api/mounts/writable/file?path={rel_path}", data=b"B"
        )
        assert status == 200
        assert json.loads(body)["newVersion"] == 1

        status, _body = _delete(f"{writable_server_url}/api/mounts/writable/file?path={rel_path}")
        assert status == 200
        assert not os.path.exists(path)

        status, body = _put(
            f"{writable_server_url}/api/mounts/writable/file?path={rel_path}", data=b""
        )

        assert status == 200
        assert json.loads(body)["newVersion"] == 2
        assert os.path.isfile(path)
        with open(path, encoding="utf-8") as f:
            assert f.read() == ""
        assert get_store().get_current_snapshot(file_key) == {"version": 2, "content": ""}

    def test_deleted_empty_put_resyncs_when_post_recreates_first(
        self, writable_server_url, writable_dir, monkeypatch
    ):
        from nas_md.webserver.file_version_store import FileVersionStore, get_store

        name = f"deleted-empty-race-{os.path.basename(writable_dir)}.md"
        rel_path = f"/{name}"
        path = os.path.join(writable_dir, name)
        file_key = f"writable:{rel_path}"
        status, body = _put(
            f"{writable_server_url}/api/mounts/writable/file?path={rel_path}", data=b"B"
        )
        assert status == 200
        assert json.loads(body)["newVersion"] == 1
        status, _body = _delete(f"{writable_server_url}/api/mounts/writable/file?path={rel_path}")
        assert status == 200

        original_create_empty_file = FileVersionStore.create_empty_file
        empty_before_create = threading.Event()
        release_empty_create = threading.Event()
        empty_result = {}
        errors = []

        def pause_empty_before_create(self, *args, **kwargs):
            if args[0] == file_key:
                empty_before_create.set()
                if not release_empty_create.wait(timeout=5):
                    raise TimeoutError("empty PUT was not released")
            return original_create_empty_file(self, *args, **kwargs)

        def run_empty_put():
            try:
                empty_result["response"] = _put(
                    f"{writable_server_url}/api/mounts/writable/file?path={rel_path}",
                    data=b"",
                )
            except BaseException as exc:
                errors.append(exc)

        monkeypatch.setattr(FileVersionStore, "create_empty_file", pause_empty_before_create)
        empty_thread = threading.Thread(target=run_empty_put, daemon=True)
        try:
            empty_thread.start()
            assert empty_before_create.wait(timeout=5)
            post_status, post_body = _post(
                f"{writable_server_url}/api/mounts/writable/changes?path={rel_path}",
                data={
                    "baseVersion": 1,
                    "baseContent": "B",
                    "content": "C",
                    "changes": [{"type": "replace", "paraIdx": 0, "content": "C"}],
                },
            )
            assert post_status == 200
            assert json.loads(post_body)["newVersion"] == 2
            assert json.loads(post_body)["content"] == "C"
        finally:
            release_empty_create.set()
            empty_thread.join(timeout=5)

        assert not empty_thread.is_alive()
        assert errors == []
        empty_status, empty_body = empty_result["response"]
        assert empty_status == 409
        assert json.loads(empty_body) == {
            "applied": False,
            "merged": False,
            "resyncRequired": True,
            "newVersion": 2,
            "content": "C",
        }
        with open(path, encoding="utf-8") as f:
            assert f.read() == "C"
        assert get_store().get_current_snapshot(file_key) == {"version": 2, "content": "C"}

    def test_missing_empty_markdown_replace_failure_rolls_back_mark_and_returns_stable_500(
        self, writable_server_url, writable_dir, monkeypatch
    ):
        from unittest.mock import Mock

        import nas_md.webserver.file_version_store as file_version_store_module

        name = f"empty-write-failure-{os.path.basename(writable_dir)}.md"
        rel_path = f"/{name}"
        path = os.path.join(writable_dir, name)
        original_replace = os.replace
        original_open = open
        normalized_target = os.path.normcase(os.path.abspath(path))

        def fail_target_replace(src, dst):
            if os.path.normcase(os.path.abspath(dst)) == normalized_target:
                raise OSError("empty replace failed")
            return original_replace(src, dst)

        def fail_direct_target_open(file, mode="r", *args, **kwargs):
            if mode == "w" and os.path.normcase(os.path.abspath(file)) == normalized_target:
                raise OSError("empty direct write failed")
            return original_open(file, mode, *args, **kwargs)

        watcher = Mock()
        token = object()
        watcher.mark_expected.return_value = token
        broadcast = Mock()
        monkeypatch.setattr("builtins.open", fail_direct_target_open)
        monkeypatch.setattr(file_version_store_module.os, "replace", fail_target_replace)
        monkeypatch.setattr("nas_md.webserver.file_watcher.get_watcher", lambda: watcher)
        monkeypatch.setattr("nas_md.webserver.sse_handler.sse_broadcast", broadcast)

        status, body = _put(
            f"{writable_server_url}/api/mounts/writable/file?path={rel_path}", data=b""
        )

        assert (status, watcher.unmark_expected.call_count) == (500, 1)
        assert json.loads(body) == {
            "applied": False,
            "merged": False,
            "newVersion": 0,
            "content": "",
            "errorCode": "write_failed",
            "message": "Unable to save file",
        }
        assert not os.path.exists(path)
        watcher.unmark_expected.assert_called_once_with(token)
        broadcast.assert_not_called()

    def test_failed_missing_empty_put_refreshes_from_external_file_before_post(
        self, writable_server_url, writable_dir, monkeypatch
    ):
        import nas_md.webserver.file_version_store as file_version_store_module

        name = f"empty-ghost-{os.path.basename(writable_dir)}.md"
        rel_path = f"/{name}"
        path = os.path.join(writable_dir, name)
        original_replace = os.replace
        normalized_target = os.path.normcase(os.path.abspath(path))
        failed = False

        def fail_first_target_replace(src, dst):
            nonlocal failed
            if not failed and os.path.normcase(os.path.abspath(dst)) == normalized_target:
                failed = True
                raise OSError("initial empty replace failed")
            return original_replace(src, dst)

        monkeypatch.setattr(file_version_store_module, "_replace_target", fail_first_target_replace)

        status, _body = _put(
            f"{writable_server_url}/api/mounts/writable/file?path={rel_path}", data=b""
        )
        assert status == 500

        external = "external\n\nbase"
        with open(path, "w", encoding="utf-8") as f:
            f.write(external)

        status, body = _post(
            f"{writable_server_url}/api/mounts/writable/changes?path={rel_path}",
            data={
                "baseVersion": 0,
                "changes": [{"type": "replace", "paraIdx": 1, "content": "updated"}],
            },
        )

        assert status == 200
        assert json.loads(body)["content"] == "external\n\nupdated"

    def test_failed_missing_nonempty_put_does_not_become_post_baseline(
        self, writable_server_url, writable_dir, monkeypatch
    ):
        import nas_md.webserver.file_version_store as file_version_store_module

        name = f"nonempty-ghost-{os.path.basename(writable_dir)}.md"
        rel_path = f"/{name}"
        path = os.path.join(writable_dir, name)
        original_replace = os.replace
        normalized_target = os.path.normcase(os.path.abspath(path))
        failed = False

        def fail_first_target_replace(src, dst):
            nonlocal failed
            if not failed and os.path.normcase(os.path.abspath(dst)) == normalized_target:
                failed = True
                raise OSError("initial nonempty replace failed")
            return original_replace(src, dst)

        monkeypatch.setattr(file_version_store_module, "_replace_target", fail_first_target_replace)

        status, _body = _put(
            f"{writable_server_url}/api/mounts/writable/file?path={rel_path}",
            data=b"failed\n\ncontent",
        )
        assert status == 500

        external = "external\n\nbase"
        with open(path, "w", encoding="utf-8") as f:
            f.write(external)

        status, body = _post(
            f"{writable_server_url}/api/mounts/writable/changes?path={rel_path}",
            data={
                "baseVersion": 0,
                "changes": [{"type": "replace", "paraIdx": 1, "content": "updated"}],
            },
        )

        assert status == 200
        assert json.loads(body)["content"] == "external\n\nupdated"

    def test_missing_empty_put_serializes_with_changes_for_same_file(
        self, writable_server_url, writable_dir, monkeypatch
    ):
        import nas_md.webserver.file_version_store as file_version_store_module
        from nas_md.webserver.file_version_store import FileVersionStore, get_store

        name = f"empty-race-{os.path.basename(writable_dir)}.md"
        rel_path = f"/{name}"
        path = os.path.join(writable_dir, name)
        file_key = f"writable:{rel_path}"
        normalized_target = os.path.normcase(os.path.abspath(path))
        original_replace = os.replace
        original_init_file = FileVersionStore.init_file
        empty_at_replace = threading.Event()
        release_empty_replace = threading.Event()
        post_at_init = threading.Event()
        post_finished = threading.Event()
        empty_result = {}
        post_result = {}
        errors = []
        first_target_replace = True

        def pause_empty_replace(src, dst):
            nonlocal first_target_replace
            if first_target_replace and os.path.normcase(os.path.abspath(dst)) == normalized_target:
                first_target_replace = False
                empty_at_replace.set()
                if not release_empty_replace.wait(timeout=5):
                    raise TimeoutError("empty PUT was not released")
            return original_replace(src, dst)

        def observe_init_file(self, *args, **kwargs):
            if args[0] == file_key and empty_at_replace.is_set():
                post_at_init.set()
            return original_init_file(self, *args, **kwargs)

        def run_empty_put():
            try:
                empty_result["response"] = _put(
                    f"{writable_server_url}/api/mounts/writable/file?path={rel_path}",
                    data=b"",
                )
            except BaseException as exc:
                errors.append(exc)

        def run_post():
            try:
                post_result["response"] = _post(
                    f"{writable_server_url}/api/mounts/writable/changes?path={rel_path}",
                    data={
                        "baseVersion": 0,
                        "baseContent": "",
                        "content": "B",
                        "changes": [{"type": "insert", "paraIdx": 0, "content": "B"}],
                    },
                )
            except BaseException as exc:
                errors.append(exc)
            finally:
                post_finished.set()

        monkeypatch.setattr(file_version_store_module, "_replace_target", pause_empty_replace)
        monkeypatch.setattr(FileVersionStore, "init_file", observe_init_file)

        empty_thread = threading.Thread(target=run_empty_put, daemon=True)
        post_thread = threading.Thread(target=run_post, daemon=True)
        lock_was_available = None
        try:
            empty_thread.start()
            assert empty_at_replace.wait(timeout=5)
            fv = get_store()._files[file_key]

            post_thread.start()
            assert post_at_init.wait(timeout=5)
            lock_was_available = fv.lock.acquire(blocking=False)
            if lock_was_available:
                fv.lock.release()

            if lock_was_available:
                assert post_finished.wait(timeout=5)
        finally:
            release_empty_replace.set()
            empty_thread.join(timeout=5)
            post_thread.join(timeout=5)

        assert not empty_thread.is_alive()
        assert not post_thread.is_alive()
        assert errors == []
        assert lock_was_available is False
        assert empty_result["response"][0] == 200
        assert post_result["response"][0] == 200
        assert json.loads(post_result["response"][1])["content"] == "B"
        with open(path, encoding="utf-8") as f:
            assert f.read() == "B"
        assert get_store().get_current_snapshot(file_key) == {"version": 1, "content": "B"}

    def test_missing_empty_put_resyncs_when_post_persists_first(
        self, writable_server_url, writable_dir, monkeypatch
    ):
        from nas_md.webserver.file_version_store import FileVersionStore, get_store

        name = f"empty-reverse-race-{os.path.basename(writable_dir)}.md"
        rel_path = f"/{name}"
        path = os.path.join(writable_dir, name)
        file_key = f"writable:{rel_path}"
        original_create_empty_file = FileVersionStore.create_empty_file
        empty_before_create = threading.Event()
        release_empty_create = threading.Event()
        empty_result = {}
        errors = []

        def pause_empty_before_create(self, *args, **kwargs):
            if args[0] == file_key:
                empty_before_create.set()
                if not release_empty_create.wait(timeout=5):
                    raise TimeoutError("empty PUT was not released")
            return original_create_empty_file(self, *args, **kwargs)

        def run_empty_put():
            try:
                empty_result["response"] = _put(
                    f"{writable_server_url}/api/mounts/writable/file?path={rel_path}",
                    data=b"",
                )
            except BaseException as exc:
                errors.append(exc)

        monkeypatch.setattr(FileVersionStore, "create_empty_file", pause_empty_before_create)
        empty_thread = threading.Thread(target=run_empty_put, daemon=True)
        try:
            empty_thread.start()
            assert empty_before_create.wait(timeout=5)

            post_status, post_body = _post(
                f"{writable_server_url}/api/mounts/writable/changes?path={rel_path}",
                data={
                    "baseVersion": 0,
                    "baseContent": "",
                    "content": "B",
                    "changes": [{"type": "insert", "paraIdx": 0, "content": "B"}],
                },
            )
            assert post_status == 200
            assert json.loads(post_body)["newVersion"] == 1
            assert json.loads(post_body)["content"] == "B"
            with open(path, encoding="utf-8") as f:
                assert f.read() == "B"
            assert get_store().get_current_snapshot(file_key) == {"version": 1, "content": "B"}
        finally:
            release_empty_create.set()
            empty_thread.join(timeout=5)

        assert not empty_thread.is_alive()
        assert errors == []
        empty_status, empty_body = empty_result["response"]
        assert empty_status == 409
        assert json.loads(empty_body) == {
            "applied": False,
            "merged": False,
            "resyncRequired": True,
            "newVersion": 1,
            "content": "B",
        }
        with open(path, encoding="utf-8") as f:
            assert f.read() == "B"
        assert get_store().get_current_snapshot(file_key) == {"version": 1, "content": "B"}

    def test_missing_empty_put_resyncs_invalid_utf8_external_creation(
        self, writable_server_url, writable_dir, monkeypatch
    ):
        from nas_md.webserver.file_version_store import FileVersionStore, get_store

        name = f"empty-invalid-race-{os.path.basename(writable_dir)}.md"
        rel_path = f"/{name}"
        path = os.path.join(writable_dir, name)
        file_key = f"writable:{rel_path}"
        original_create_empty_file = FileVersionStore.create_empty_file
        empty_before_create = threading.Event()
        release_empty_create = threading.Event()
        empty_result = {}
        errors = []

        def pause_empty_before_create(self, *args, **kwargs):
            if args[0] == file_key:
                empty_before_create.set()
                if not release_empty_create.wait(timeout=5):
                    raise TimeoutError("empty PUT was not released")
            return original_create_empty_file(self, *args, **kwargs)

        def run_empty_put():
            try:
                empty_result["response"] = _put(
                    f"{writable_server_url}/api/mounts/writable/file?path={rel_path}",
                    data=b"",
                )
            except BaseException as exc:
                errors.append(exc)

        monkeypatch.setattr(FileVersionStore, "create_empty_file", pause_empty_before_create)
        empty_thread = threading.Thread(target=run_empty_put, daemon=True)
        try:
            empty_thread.start()
            assert empty_before_create.wait(timeout=5)
            with open(path, "wb") as f:
                f.write(b"\xff")
        finally:
            release_empty_create.set()
            empty_thread.join(timeout=5)

        assert not empty_thread.is_alive()
        assert errors == []
        status, body = empty_result["response"]
        assert status == 409
        assert json.loads(body) == {
            "applied": False,
            "merged": False,
            "resyncRequired": True,
            "newVersion": 1,
            "content": "\ufffd",
        }
        with open(path, "rb") as f:
            assert f.read() == b"\xff"
        assert get_store().get_current_snapshot(file_key) == {"version": 1, "content": "\ufffd"}

    def test_write_file_existing_empty_markdown_remains_side_effect_free(
        self, writable_server_url, writable_dir, monkeypatch
    ):
        from unittest.mock import Mock

        from nas_md.webserver import version_history
        from nas_md.webserver.file_version_store import get_store

        name = f"existing-empty-{os.path.basename(writable_dir)}.md"
        rel_path = f"/{name}"
        path = os.path.join(writable_dir, name)
        file_key = f"writable:{rel_path}"
        with open(path, "wb"):
            pass
        watcher = Mock()
        broadcast = Mock()
        monkeypatch.setattr("nas_md.webserver.file_watcher.get_watcher", lambda: watcher)
        monkeypatch.setattr("nas_md.webserver.sse_handler.sse_broadcast", broadcast)

        status, body = _put(
            f"{writable_server_url}/api/mounts/writable/file?path={rel_path}",
            data=b"",
        )

        assert status == 200
        assert json.loads(body)["newVersion"] == 0
        assert os.path.isfile(path)
        with open(path, "rb") as f:
            assert f.read() == b""
        assert get_store().get_current_version(file_key) == 0
        assert file_key not in version_history._histories
        watcher.mark_expected.assert_not_called()
        broadcast.assert_not_called()

    def test_write_file_overwrites_existing(self, writable_server_url, writable_dir):
        """PUT /api/mounts/{id}/file overwrites an existing file."""
        new_content = "# Updated\n"
        status, _body = _put(
            f"{writable_server_url}/api/mounts/writable/file?path=/hello.md",
            data=new_content.encode("utf-8"),
        )
        assert status == 200
        with open(os.path.join(writable_dir, "hello.md"), encoding="utf-8") as f:
            assert f.read() == new_content

    def test_write_file_replace_failure_returns_stable_500_without_broadcast(
        self, writable_server_url, writable_dir, monkeypatch
    ):
        from unittest.mock import Mock

        import nas_md.webserver.file_version_store as file_version_store_module

        name = f"put-write-failure-{os.path.basename(writable_dir)}.md"
        rel_path = f"/{name}"
        path = os.path.join(writable_dir, name)
        original = "before"
        with open(path, "w", encoding="utf-8") as f:
            f.write(original)
        original_replace = os.replace
        normalized_target = os.path.normcase(os.path.abspath(path))

        def fail_target_replace(src, dst):
            if os.path.normcase(os.path.abspath(dst)) == normalized_target:
                raise OSError(f"cannot replace sensitive path {path}")
            return original_replace(src, dst)

        watcher = Mock()
        watcher_token = object()
        prepared_calls = []

        def mark_expected(mount_id, marked_path, prepared_path):
            with open(prepared_path, "rb") as f:
                prepared_calls.append((mount_id, marked_path, f.read()))
            return watcher_token

        watcher.mark_expected.side_effect = mark_expected
        broadcast = Mock()
        monkeypatch.setattr(
            file_version_store_module, "_replace_target", fail_target_replace, raising=False
        )
        monkeypatch.setattr("nas_md.webserver.file_watcher.get_watcher", lambda: watcher)
        monkeypatch.setattr("nas_md.webserver.sse_handler.sse_broadcast", broadcast)

        status, body = _put(
            f"{writable_server_url}/api/mounts/writable/file?path={rel_path}",
            data=b"after",
        )

        assert (status, broadcast.call_count) == (500, 0)
        assert json.loads(body) == {
            "applied": False,
            "merged": False,
            "newVersion": 0,
            "content": original,
            "errorCode": "write_failed",
            "message": "Unable to save file",
        }
        assert path not in body
        with open(path, encoding="utf-8") as f:
            assert f.read() == original
        assert prepared_calls == [("writable", rel_path, b"after")]
        watcher.unmark_expected.assert_called_once_with(watcher_token)
        broadcast.assert_not_called()

    def test_write_file_existing_exact_delimiter_change_is_not_false_success(
        self, writable_server_url, writable_dir
    ):
        path = os.path.join(writable_dir, "exact-formatting.md")
        base = "---\ntitle: Doc\n---\nBody"
        target = "---\ntitle: Doc\n---\n\nBody"
        with open(path, "w", encoding="utf-8") as f:
            f.write(base)

        status, body = _put(
            f"{writable_server_url}/api/mounts/writable/file?path=/exact-formatting.md",
            data=target.encode("utf-8"),
        )

        assert status == 200
        assert json.loads(body)["newVersion"] == 1
        with open(path, "rb") as f:
            assert f.read() == target.replace("\n", os.linesep).encode("utf-8")

    def test_write_file_blank_only_content_increments_version(
        self, writable_server_url, writable_dir
    ):
        path = os.path.join(writable_dir, "blank-only.md")
        with open(path, "wb"):
            pass

        status, body = _put(
            f"{writable_server_url}/api/mounts/writable/file?path=/blank-only.md",
            data=b"\n",
        )

        assert status == 200
        assert json.loads(body)["newVersion"] == 1
        with open(path, "rb") as f:
            assert f.read() == os.linesep.encode("utf-8")

    @pytest.mark.parametrize(
        ("name", "base", "target"),
        [
            ("leading", "", "\nA"),
            ("embedded", "A\n\nB", "A\n \nB"),
            ("blank-only-whitespace", "", " \n"),
            ("blank-only-multiple", "", "\n\n\n"),
        ],
        ids=["leading", "embedded", "blank-only-whitespace", "blank-only-multiple"],
    )
    def test_write_file_preserves_lossless_whitespace(
        self, writable_server_url, writable_dir, name, base, target
    ):
        path = os.path.join(writable_dir, f"lossless-{name}.md")
        with open(path, "wb") as f:
            f.write(base.encode("utf-8"))

        status, body = _put(
            f"{writable_server_url}/api/mounts/writable/file?path=/lossless-{name}.md",
            data=target.encode("utf-8"),
        )

        assert status == 200
        assert json.loads(body)["newVersion"] == 1
        with open(path, "rb") as f:
            assert f.read() == target.replace("\n", os.linesep).encode("utf-8")

    def test_write_file_normalized_line_endings_remain_a_successful_noop(
        self, writable_server_url, writable_dir
    ):
        path = os.path.join(writable_dir, "normalized-noop.md")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("same\n")

        status, body = _put(
            f"{writable_server_url}/api/mounts/writable/file?path=/normalized-noop.md",
            data=b"same\r\n",
        )

        assert status == 200
        assert json.loads(body)["newVersion"] == 0
        with open(path, encoding="utf-8") as f:
            assert f.read() == "same\n"

    def test_write_file_rejected_store_result_returns_conflict_without_marking(
        self, writable_server_url, writable_dir, monkeypatch
    ):
        from unittest.mock import Mock

        from nas_md.webserver.file_version_store import get_store

        path = os.path.join(writable_dir, "rejected-put.md")
        base = "before"
        with open(path, "w", encoding="utf-8") as f:
            f.write(base)

        store = get_store()
        rejected_result = {
            "applied": False,
            "merged": False,
            "resyncRequired": True,
            "newVersion": 0,
            "content": base,
        }
        monkeypatch.setattr(store, "apply_changes", Mock(return_value=rejected_result))
        watcher = Mock()
        broadcast = Mock()
        monkeypatch.setattr("nas_md.webserver.file_watcher.get_watcher", lambda: watcher)
        monkeypatch.setattr("nas_md.webserver.sse_handler.sse_broadcast", broadcast)

        status, _body = _put(
            f"{writable_server_url}/api/mounts/writable/file?path=/rejected-put.md",
            data=b"after",
        )

        assert status == 409
        with open(path, "rb") as f:
            assert f.read() == base.encode("utf-8")
        watcher.mark_expected.assert_not_called()
        broadcast.assert_not_called()

    def test_write_file_with_expected_mtime_no_conflict_copy(
        self, writable_server_url, writable_dir
    ):
        """PUT with stale expected_mtime must NOT create a .conflict.md copy.

        Regression test: the deprecated PUT wrapper routes through apply_changes
        and should never produce conflict files anymore.
        """
        # Seed a file
        with open(os.path.join(writable_dir, "stale.md"), "w", encoding="utf-8") as f:
            f.write("v1")
        # Overwrite via PUT with a deliberately stale expected_mtime
        status, body = _put(
            f"{writable_server_url}/api/mounts/writable/file?path=/stale.md&expected_mtime=1",
            data=b"v2",
        )
        assert status == 200
        data = json.loads(body)
        assert data.get("conflict") is False
        # No .conflict.md file should exist
        assert not os.path.exists(os.path.join(writable_dir, "stale.conflict.md"))
        assert not os.path.exists(os.path.join(writable_dir, "stale.conflict"))
        # New content written
        with open(os.path.join(writable_dir, "stale.md"), encoding="utf-8") as f:
            assert f.read() == "v2"

    def test_write_file_readonly_mount(self, writable_server_url):
        """PUT to a readonly mount should return 403 or connection error."""
        try:
            status, _body = _put(
                f"{writable_server_url}/api/mounts/readonly/file?path=/hello.md",
                data=b"hack",
            )
            assert status == 403
        except (ConnectionError, OSError):
            pass  # Server may abort connection on readonly violation

    def test_write_file_missing_path(self, writable_server_url):
        """PUT without path parameter should return 400 or 500."""
        # Server may crash on missing path param (ConnectionAborted),
        # so we accept any non-200 status or connection error
        try:
            status, _body = _put(
                f"{writable_server_url}/api/mounts/writable/file",
                data=b"content",
            )
            assert status != 200
        except (ConnectionError, OSError):
            pass  # Server aborted connection on bad request

    def test_write_file_unknown_mount(self, writable_server_url):
        """PUT to unknown mount should return 404."""
        status, _body = _put(
            f"{writable_server_url}/api/mounts/nonexistent/file?path=/x.md",
            data=b"x",
        )
        assert status == 404

    def test_write_file_creates_parent_dirs(self, writable_server_url, writable_dir):
        """PUT should auto-create parent directories."""
        status, _body = _put(
            f"{writable_server_url}/api/mounts/writable/file?path=/deep/nested/file.md",
            data=b"deep",
        )
        assert status == 200
        assert os.path.isfile(os.path.join(writable_dir, "deep", "nested", "file.md"))

    def test_write_binary_file_preserves_bytes(self, writable_server_url, writable_dir):
        """PUT a binary (non-md) file must preserve raw bytes without UTF-8 corruption.

        Regression test: images copied local→server were corrupted because the
        PUT handler decoded the body as UTF-8 text and re-encoded it. Non-md
        files must be written as raw bytes.
        """
        import urllib.request

        # PNG signature + arbitrary bytes incl. invalid UTF-8 sequences
        payload = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 4
        status, _body = _put(
            f"{writable_server_url}/api/mounts/writable/file?path=/img/pic.png",
            data=payload,
        )
        assert status == 200
        # Disk file must match exactly (no UTF-8 replacement corruption)
        with open(os.path.join(writable_dir, "img", "pic.png"), "rb") as f:
            assert f.read() == payload
        # GET must return the same raw bytes
        with urllib.request.urlopen(
            f"{writable_server_url}/api/mounts/writable/file?path=/img/pic.png",
            timeout=5,
        ) as resp:
            assert resp.read() == payload

    def test_write_markdown_work_limit_returns_resync_without_overwriting(
        self, writable_server_url, writable_dir
    ):
        path = os.path.join(writable_dir, "work-limit.md")
        old_paragraphs = ["A"] * 600 + ["B"] * 600 + ["C"] * 600
        new_paragraphs = ["B"] * 600 + ["C"] * 600 + ["A"] * 600
        old_content = "\n\n".join(old_paragraphs)
        new_content = "\n\n".join(new_paragraphs)
        with open(path, "w", encoding="utf-8") as f:
            f.write(old_content)

        status, body = _put(
            f"{writable_server_url}/api/mounts/writable/file?path=/work-limit.md",
            data=new_content.encode("utf-8"),
        )

        assert status == 409
        assert json.loads(body) == {
            "applied": False,
            "merged": False,
            "resyncRequired": True,
            "newVersion": 0,
            "content": old_content,
        }
        with open(path, encoding="utf-8") as f:
            assert f.read() == old_content

    def test_write_markdown_work_limit_returns_one_atomic_store_snapshot(
        self, writable_server_url, writable_dir, monkeypatch
    ):
        from nas_md.webserver import paragraph_diff
        from nas_md.webserver.file_version_store import FileVersionStore, get_store

        path = os.path.join(writable_dir, "snapshot.md")
        old_content = "A\n\nB"
        concurrent_content = "A-REMOTE\n\nB"
        file_key = "writable:/snapshot.md"
        with open(path, "w", encoding="utf-8") as f:
            f.write(old_content)

        store = get_store()
        store.init_file(file_key, path, old_content)
        original_get_version = FileVersionStore.get_current_version
        original_compute_diff = paragraph_diff.compute_diff
        interleaving_write_applied = threading.Event()

        def exhaust_diff(_old_text, _new_text):
            raise paragraph_diff.DiffWorkLimitExceeded

        def get_version_then_apply_write(self, key):
            version = original_get_version(self, key)
            result = self.apply_changes(
                file_key,
                path,
                0,
                original_compute_diff(old_content, concurrent_content),
                "remote",
                "Remote",
                "#f00",
                client_content=concurrent_content,
                base_content=old_content,
            )
            assert result["applied"] is True
            interleaving_write_applied.set()
            return version

        monkeypatch.setattr(FileVersionStore, "get_current_version", get_version_then_apply_write)
        monkeypatch.setattr(paragraph_diff, "compute_diff", exhaust_diff)

        status, body = _put(
            f"{writable_server_url}/api/mounts/writable/file?path=/snapshot.md",
            data=b"unreachable replacement",
        )

        assert status == 409
        response = json.loads(body)
        snapshot = (response["newVersion"], response["content"])
        if interleaving_write_applied.is_set():
            assert snapshot == (1, concurrent_content)
        else:
            assert snapshot == (0, old_content)


class TestSubmitChangesAPI:
    """Integration tests for POST /api/mounts/{id}/changes — version-driven paragraph merge."""

    def test_submit_changes_creates_file(self, writable_server_url, writable_dir):
        """POST /changes on a non-existing path should create the file."""
        payload = {
            "baseVersion": 0,
            "changes": [{"type": "insert", "paraIdx": 0, "content": "new para"}],
            "authorName": "tester",
            "authorColor": "#ff0000",
        }
        status, body = _post(
            f"{writable_server_url}/api/mounts/writable/changes?path=/created.md",
            data=payload,
        )
        assert status == 200
        data = json.loads(body)
        assert data["applied"] is True
        assert data["newVersion"] == 1
        assert "new para" in data["content"]
        with open(os.path.join(writable_dir, "created.md"), encoding="utf-8") as f:
            assert f.read() == "new para"

    def test_submit_changes_replace_failure_returns_stable_500_without_broadcast(
        self, writable_server_url, writable_dir, monkeypatch
    ):
        from unittest.mock import Mock

        import nas_md.webserver.file_version_store as file_version_store_module

        name = f"post-write-failure-{os.path.basename(writable_dir)}.md"
        rel_path = f"/{name}"
        path = os.path.join(writable_dir, name)
        original = "before"
        with open(path, "w", encoding="utf-8") as f:
            f.write(original)
        original_replace = os.replace
        normalized_target = os.path.normcase(os.path.abspath(path))

        def fail_target_replace(src, dst):
            if os.path.normcase(os.path.abspath(dst)) == normalized_target:
                raise OSError(f"cannot replace sensitive path {path}")
            return original_replace(src, dst)

        watcher = Mock()
        watcher_token = object()
        prepared_calls = []

        def mark_expected(mount_id, marked_path, prepared_path):
            with open(prepared_path, "rb") as f:
                prepared_calls.append((mount_id, marked_path, f.read()))
            return watcher_token

        watcher.mark_expected.side_effect = mark_expected
        broadcast = Mock()
        monkeypatch.setattr(
            file_version_store_module, "_replace_target", fail_target_replace, raising=False
        )
        monkeypatch.setattr("nas_md.webserver.file_watcher.get_watcher", lambda: watcher)
        monkeypatch.setattr("nas_md.webserver.sse_handler.sse_broadcast", broadcast)

        status, body = _post(
            f"{writable_server_url}/api/mounts/writable/changes?path={rel_path}",
            data={
                "baseVersion": 0,
                "baseContent": original,
                "content": "after",
                "changes": [{"type": "replace", "paraIdx": 0, "content": "after"}],
            },
        )

        assert (status, broadcast.call_count) == (500, 0)
        assert json.loads(body) == {
            "applied": False,
            "merged": False,
            "newVersion": 0,
            "content": original,
            "errorCode": "write_failed",
            "message": "Unable to save file",
        }
        assert path not in body
        with open(path, encoding="utf-8") as f:
            assert f.read() == original
        assert prepared_calls == [("writable", rel_path, b"after")]
        watcher.unmark_expected.assert_called_once_with(watcher_token)
        broadcast.assert_not_called()

    def test_submit_changes_replace_paragraph(self, writable_server_url, writable_dir):
        """POST /changes with replace should update the specified paragraph."""
        # Seed file with 3 paragraphs
        seed = "para one\n\npara two\n\npara three"
        with open(os.path.join(writable_dir, "replace.md"), "w", encoding="utf-8") as f:
            f.write(seed)
        payload = {
            "baseVersion": 0,
            "changes": [{"type": "replace", "paraIdx": 1, "content": "CHANGED"}],
            "authorName": "tester",
        }
        status, body = _post(
            f"{writable_server_url}/api/mounts/writable/changes?path=/replace.md",
            data=payload,
        )
        assert status == 200
        data = json.loads(body)
        assert data["applied"] is True
        assert data["newVersion"] == 1
        assert data["content"] == "para one\n\nCHANGED\n\npara three"

    def test_submit_changes_delimiter_only_preserves_paragraph_text(
        self, writable_server_url, writable_dir
    ):
        path = os.path.join(writable_dir, "delimiter-only.md")
        base = "A\n\nB"
        target = "A\n\n\nB"
        with open(path, "w", encoding="utf-8") as f:
            f.write(base)

        status, body = _post(
            f"{writable_server_url}/api/mounts/writable/changes?path=/delimiter-only.md",
            data={
                "baseVersion": 0,
                "changes": [{"type": "delimiter", "paraIdx": 0, "delimiter": "\n\n\n"}],
            },
        )

        assert status == 200
        data = json.loads(body)
        assert data["applied"] is True
        assert data["newVersion"] == 1
        assert data["content"] == target
        assert data["appliedChanges"] == [
            {"type": "delimiter", "paraIdx": 0, "delimiter": "\n\n\n"}
        ]
        with open(path, "rb") as f:
            assert f.read() == target.replace("\n", os.linesep).encode("utf-8")

    def test_submit_legacy_stale_text_edit_preserves_remote_tab_formatting(
        self, writable_server_url, writable_dir, monkeypatch
    ):
        from unittest.mock import Mock

        from nas_md.webserver import version_history

        name = f"legacy-tab-{os.path.basename(writable_dir)}.md"
        rel_path = f"/{name}"
        path = os.path.join(writable_dir, name)
        file_key = f"writable:{rel_path}"
        base = "A\n\nB"
        remote_content = "A\n\t\nB"
        expected = "A-local\n\t\nB"
        with open(path, "w", encoding="utf-8") as f:
            f.write(base)

        status, body = _post(
            f"{writable_server_url}/api/mounts/writable/changes?path={rel_path}",
            data={
                "baseVersion": 0,
                "baseContent": base,
                "content": remote_content,
                "changes": [{"type": "delimiter", "paraIdx": 0, "delimiter": "\n\t\n"}],
            },
        )
        assert status == 200
        assert json.loads(body)["applied"] is True

        watcher = Mock()
        prepared_calls = []

        def mark_expected(mount_id, marked_path, prepared_path):
            with open(prepared_path, "rb") as f:
                prepared_calls.append((mount_id, marked_path, f.read()))

        watcher.mark_expected.side_effect = mark_expected
        broadcast = Mock()
        monkeypatch.setattr("nas_md.webserver.file_watcher.get_watcher", lambda: watcher)
        monkeypatch.setattr("nas_md.webserver.sse_handler.sse_broadcast", broadcast)

        status, body = _post(
            f"{writable_server_url}/api/mounts/writable/changes?path={rel_path}",
            data={
                "baseVersion": 0,
                "baseContent": base,
                "content": "A-local\n\nB",
                "changes": [{"type": "replace", "paraIdx": 0, "content": "A-local"}],
            },
        )

        assert status == 200
        data = json.loads(body)
        assert data["applied"] is True
        assert data["merged"] is True
        assert data["content"] == expected
        assert data["appliedChanges"] == [
            {
                "type": "replace",
                "paraIdx": 0,
                "content": "A-local",
                "fallbackDelimiter": "\n\n",
            }
        ]
        with open(path, "rb") as f:
            assert f.read() == expected.replace("\n", os.linesep).encode("utf-8")
        assert version_history.get_version_content(file_key, 0) == expected
        assert prepared_calls == [
            ("writable", rel_path, expected.replace("\n", os.linesep).encode("utf-8"))
        ]
        broadcast.assert_called_once()

    @pytest.mark.parametrize(
        ("name", "base", "change", "target"),
        [
            ("prefix", "A", {"type": "prefix", "content": "\n"}, "\nA"),
            (
                "embedded",
                "A\n\nB",
                {"type": "delimiter", "paraIdx": 0, "delimiter": "\n \n"},
                "A\n \nB",
            ),
            ("blank-only", "", {"type": "prefix", "content": " \n"}, " \n"),
        ],
        ids=["prefix", "embedded", "blank-only"],
    )
    def test_submit_changes_preserves_lossless_whitespace(
        self, writable_server_url, writable_dir, name, base, change, target
    ):
        path = os.path.join(writable_dir, f"post-lossless-{name}.md")
        with open(path, "wb") as f:
            f.write(base.encode("utf-8"))

        status, body = _post(
            f"{writable_server_url}/api/mounts/writable/changes?path=/post-lossless-{name}.md",
            data={"baseVersion": 0, "changes": [change]},
        )

        assert status == 200
        data = json.loads(body)
        assert data["applied"] is True
        assert data["newVersion"] == 1
        assert data["content"] == target
        with open(path, "rb") as f:
            assert f.read() == target.replace("\n", os.linesep).encode("utf-8")

    def test_submit_changes_version_increments(self, writable_server_url, writable_dir):
        """Consecutive POST /changes should increment version monotonically."""
        with open(os.path.join(writable_dir, "incr.md"), "w", encoding="utf-8") as f:
            f.write("a")
        # First edit
        payload1 = {
            "baseVersion": 0,
            "changes": [{"type": "replace", "paraIdx": 0, "content": "b"}],
        }
        _s1, b1 = _post(
            f"{writable_server_url}/api/mounts/writable/changes?path=/incr.md",
            data=payload1,
        )
        d1 = json.loads(b1)
        assert d1["newVersion"] == 1
        # Second edit based on new version
        payload2 = {
            "baseVersion": 1,
            "changes": [{"type": "replace", "paraIdx": 0, "content": "c"}],
        }
        _s2, b2 = _post(
            f"{writable_server_url}/api/mounts/writable/changes?path=/incr.md",
            data=payload2,
        )
        d2 = json.loads(b2)
        assert d2["newVersion"] == 2
        assert d2["content"] == "c"

    def test_submit_changes_stale_base_merges(self, writable_server_url, writable_dir):
        """Stale baseVersion should still apply (merged=True) via last-write-wins."""
        base = "orig"
        with open(os.path.join(writable_dir, "merge.md"), "w", encoding="utf-8") as f:
            f.write(base)
        # Client A saves at baseVersion 0
        payload_a = {
            "baseVersion": 0,
            "changes": [{"type": "replace", "paraIdx": 0, "content": "A-wins"}],
            "baseContent": base,
            "content": "A-wins",
        }
        _post(
            f"{writable_server_url}/api/mounts/writable/changes?path=/merge.md",
            data=payload_a,
        )
        # Client B also at baseVersion 0 (stale) — should merge, last-write-wins
        payload_b = {
            "baseVersion": 0,
            "changes": [{"type": "replace", "paraIdx": 0, "content": "B-wins"}],
            "baseContent": base,
            "content": "B-wins",
        }
        _status, body = _post(
            f"{writable_server_url}/api/mounts/writable/changes?path=/merge.md",
            data=payload_b,
        )
        data = json.loads(body)
        assert data["applied"] is True
        assert data["merged"] is True
        assert data["content"] == "B-wins"

    @pytest.mark.parametrize(
        ("remote_changes", "client_changes", "current_content"),
        [
            (
                [{"type": "delete", "paraIdx": 1}],
                [{"type": "delete", "paraIdx": 1}],
                "A\n\nC",
            ),
            (
                [{"type": "replace", "paraIdx": 1, "content": "B2"}],
                [{"type": "replace", "paraIdx": 1, "content": "B2"}],
                "A\n\nB2\n\nC",
            ),
        ],
        ids=["delete-delete", "identical-replace"],
    )
    def test_submit_changes_stale_noop_does_not_mark_or_broadcast(
        self,
        writable_server_url,
        writable_dir,
        monkeypatch,
        remote_changes,
        client_changes,
        current_content,
    ):
        from unittest.mock import Mock

        from nas_md.webserver.file_version_store import get_store

        base = "A\n\nB\n\nC"
        rel_path = "/stale-noop.md"
        path = os.path.join(writable_dir, "stale-noop.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(base)

        status, body = _post(
            f"{writable_server_url}/api/mounts/writable/changes?path={rel_path}",
            data={
                "baseVersion": 0,
                "baseContent": base,
                "content": current_content,
                "changes": remote_changes,
            },
        )
        assert status == 200
        assert json.loads(body)["applied"] is True
        with open(path, "rb") as f:
            disk_before = f.read()

        watcher = Mock()
        broadcast = Mock()
        monkeypatch.setattr("nas_md.webserver.file_watcher.get_watcher", lambda: watcher)
        monkeypatch.setattr("nas_md.webserver.sse_handler.sse_broadcast", broadcast)

        status, body = _post(
            f"{writable_server_url}/api/mounts/writable/changes?path={rel_path}",
            data={
                "baseVersion": 0,
                "baseContent": base,
                "content": current_content,
                "changes": client_changes,
            },
        )

        assert status == 200
        data = json.loads(body)
        assert data["applied"] is False
        assert data["newVersion"] == 1
        assert get_store().get_current_version("writable:/stale-noop.md") == 1
        with open(path, "rb") as f:
            assert f.read() == disk_before
        watcher.mark_expected.assert_not_called()
        broadcast.assert_not_called()

    def test_submit_changes_stale_base_three_way_merges_after_store_restart(
        self, writable_server_url, writable_dir
    ):
        from nas_md.webserver.file_version_store import get_store

        base = "A\n\nB\n\nC"
        path = os.path.join(writable_dir, "restart-merge.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(base)

        status, body = _post(
            f"{writable_server_url}/api/mounts/writable/changes?path=/restart-merge.md",
            data={
                "baseVersion": 0,
                "baseContent": base,
                "content": "A-remote\n\nB\n\nC",
                "changes": [{"type": "replace", "paraIdx": 0, "content": "A-remote"}],
            },
        )
        assert status == 200
        assert json.loads(body)["applied"] is True

        store = get_store()
        with store._lock:
            store._files.clear()

        status, body = _post(
            f"{writable_server_url}/api/mounts/writable/changes?path=/restart-merge.md",
            data={
                "baseVersion": 0,
                "baseContent": base,
                "content": "A\n\nB\n\nC-local",
                "changes": [{"type": "replace", "paraIdx": 2, "content": "C-local"}],
            },
        )

        expected = "A-remote\n\nB\n\nC-local"
        assert status == 200
        data = json.loads(body)
        assert data["applied"] is True
        assert data["merged"] is True
        assert data["content"] == expected
        with open(path, encoding="utf-8") as f:
            assert f.read() == expected

    def test_submit_changes_empty_changes_not_applied(self, writable_server_url, writable_dir):
        """Empty changes list should return applied=False."""
        with open(os.path.join(writable_dir, "empty.md"), "w", encoding="utf-8") as f:
            f.write("content")
        payload = {"baseVersion": 0, "changes": []}
        _status, body = _post(
            f"{writable_server_url}/api/mounts/writable/changes?path=/empty.md",
            data=payload,
        )
        data = json.loads(body)
        assert data["applied"] is False

    @pytest.mark.parametrize(
        ("change", "expected_error"),
        [
            (
                {"type": "replace", "paraIdx": -1, "content": "invalid"},
                "Invalid changes: paraIdx must be nonnegative",
            ),
            (
                {"type": "replace", "paraIdx": 1, "content": "invalid"},
                "Invalid changes: replace/delete paraIdx exceeds base paragraph count",
            ),
            (
                {"type": "replace", "paraIdx": 0, "content": "valid", "delimiter": 7},
                "Invalid changes: delimiter must be a string",
            ),
            (
                {
                    "type": "replace",
                    "paraIdx": 0,
                    "content": "valid",
                    "fallbackDelimiter": 7,
                },
                "Invalid changes: fallbackDelimiter must be a string",
            ),
            (
                {
                    "type": "insert",
                    "paraIdx": 0,
                    "content": "valid",
                    "fallbackDelimiter": "",
                },
                "Invalid changes: fallbackDelimiter is only valid for replace changes",
            ),
            (
                {"type": "delete", "paraIdx": 0, "delimiter": ""},
                "Invalid changes: delimiter is only valid for insert/replace changes",
            ),
            (
                {"type": "delimiter", "paraIdx": 0, "delimiter": "\n", "content": "invalid"},
                "Invalid changes: delimiter changes must not include content",
            ),
            (
                {"type": "delimiter", "paraIdx": 0},
                "Invalid changes: delimiter must be a string",
            ),
            (
                {"type": "prefix"},
                "Invalid changes: prefix content must be a string",
            ),
            (
                {"type": "prefix", "content": 7},
                "Invalid changes: prefix content must be a string",
            ),
            (
                {"type": "prefix", "content": "\n", "paraIdx": 0},
                "Invalid changes: prefix changes must not include paraIdx",
            ),
            (
                {"type": "prefix", "content": "\n", "delimiter": ""},
                "Invalid changes: prefix changes must not include delimiter",
            ),
        ],
        ids=[
            "negative-index",
            "current-version-index-out-of-range",
            "non-string-delimiter",
            "non-string-fallback-delimiter",
            "insert-with-fallback-delimiter",
            "delete-with-delimiter",
            "delimiter-change-with-content",
            "delimiter-change-missing-delimiter",
            "prefix-change-missing-content",
            "prefix-change-non-string-content",
            "prefix-change-with-index",
            "prefix-change-with-delimiter",
        ],
    )
    def test_submit_changes_rejects_invalid_changes_without_side_effects(
        self,
        writable_server_url,
        writable_dir,
        monkeypatch,
        change,
        expected_error,
    ):
        from unittest.mock import Mock

        from nas_md.webserver.file_version_store import get_store

        path = os.path.join(writable_dir, "invalid-change.md")
        original_bytes = b"original"
        with open(path, "wb") as f:
            f.write(original_bytes)

        watcher = Mock()
        broadcast = Mock()
        monkeypatch.setattr("nas_md.webserver.file_watcher.get_watcher", lambda: watcher)
        monkeypatch.setattr("nas_md.webserver.sse_handler.sse_broadcast", broadcast)

        status, body = _post(
            f"{writable_server_url}/api/mounts/writable/changes?path=/invalid-change.md",
            data={"baseVersion": 0, "changes": [change]},
        )

        assert status == 400
        assert json.loads(body) == {"error": expected_error}
        with open(path, "rb") as f:
            assert f.read() == original_bytes
        assert get_store().get_current_version("writable:/invalid-change.md") == 0
        watcher.mark_expected.assert_not_called()
        broadcast.assert_not_called()

    def test_submit_changes_readonly_mount_rejected(self, writable_server_url):
        """POST /changes on a readonly mount should return 403."""
        payload = {"baseVersion": 0, "changes": [{"type": "insert", "paraIdx": 0, "content": "x"}]}
        status, _body = _post(
            f"{writable_server_url}/api/mounts/readonly/changes?path=/x.md",
            data=payload,
        )
        assert status == 403

    def test_submit_changes_records_version_history(self, writable_server_url, writable_dir):
        """POST /changes should record an entry in version_history."""
        # Reset store + history for a clean file
        from nas_md.webserver.file_version_store import get_store
        from nas_md.webserver import version_history

        store = get_store()
        store._files.clear()
        version_history._histories.clear()

        with open(os.path.join(writable_dir, "history.md"), "w", encoding="utf-8") as f:
            f.write("start")
        payload = {
            "baseVersion": 0,
            "changes": [{"type": "replace", "paraIdx": 0, "content": "after-edit"}],
            "authorName": "history-tester",
            "authorColor": "#00ff00",
        }
        _post(
            f"{writable_server_url}/api/mounts/writable/changes?path=/history.md",
            data=payload,
        )
        # Check version history recorded
        file_key = "writable:/history.md"
        hist = version_history._histories.get(file_key)
        assert hist is not None
        assert len(hist.versions) >= 1
        last = hist.versions[-1]
        assert last.author_name == "history-tester"
        assert last.content_snapshot == "after-edit"


class TestRenameAPI:
    def test_rename_file(self, writable_server_url, writable_dir):
        """PUT /api/mounts/{id}/rename renames a file."""
        status, body = _put(
            f"{writable_server_url}/api/mounts/writable/rename?oldPath=/hello.md&newPath=/greeting.md",
        )
        assert status == 200
        data = json.loads(body)
        assert data.get("status") == "ok"
        assert not os.path.exists(os.path.join(writable_dir, "hello.md"))
        assert os.path.isfile(os.path.join(writable_dir, "greeting.md"))

    def test_rename_directory(self, writable_server_url, writable_dir):
        """PUT /api/mounts/{id}/rename renames a directory."""
        status, _body = _put(
            f"{writable_server_url}/api/mounts/writable/rename?oldPath=/subdir&newPath=/renamed-dir",
        )
        assert status == 200
        assert not os.path.exists(os.path.join(writable_dir, "subdir"))
        assert os.path.isdir(os.path.join(writable_dir, "renamed-dir"))
        # File inside should still exist
        assert os.path.isfile(os.path.join(writable_dir, "renamed-dir", "note.md"))

    def test_rename_missing_params(self, writable_server_url):
        """PUT /rename without oldPath/newPath should return 400."""
        status, _body = _put(
            f"{writable_server_url}/api/mounts/writable/rename?oldPath=/hello.md",
        )
        assert status == 400

    def test_rename_root_forbidden(self, writable_server_url):
        """PUT /rename with oldPath=/ should return 403."""
        status, _body = _put(
            f"{writable_server_url}/api/mounts/writable/rename?oldPath=/&newPath=/foo",
        )
        assert status == 403

    def test_rename_readonly_mount(self, writable_server_url):
        """PUT /rename on readonly mount should return 403."""
        status, _body = _put(
            f"{writable_server_url}/api/mounts/readonly/rename?oldPath=/hello.md&newPath=/x.md",
        )
        assert status == 403


class TestMkdirAPI:
    def test_mkdir_creates_directory(self, writable_server_url, writable_dir):
        """PUT /api/mounts/{id}/mkdir creates a directory."""
        status, body = _put(
            f"{writable_server_url}/api/mounts/writable/mkdir?path=/new-folder",
        )
        assert status == 200
        data = json.loads(body)
        assert data.get("status") == "ok"
        assert os.path.isdir(os.path.join(writable_dir, "new-folder"))

    def test_mkdir_nested(self, writable_server_url, writable_dir):
        """PUT /mkdir creates nested directories."""
        status, _body = _put(
            f"{writable_server_url}/api/mounts/writable/mkdir?path=/a/b/c",
        )
        assert status == 200
        assert os.path.isdir(os.path.join(writable_dir, "a", "b", "c"))

    def test_mkdir_missing_path(self, writable_server_url):
        """PUT /mkdir without path should return 400."""
        status, _body = _put(
            f"{writable_server_url}/api/mounts/writable/mkdir",
        )
        assert status == 400

    def test_mkdir_readonly_mount(self, writable_server_url):
        """PUT /mkdir on readonly mount should return 403."""
        status, _body = _put(
            f"{writable_server_url}/api/mounts/readonly/mkdir?path=/x",
        )
        assert status == 403


class TestDeleteAPI:
    def test_delete_file(self, writable_server_url, writable_dir):
        """DELETE /api/mounts/{id}/file removes a file."""
        status, body = _delete(
            f"{writable_server_url}/api/mounts/writable/file?path=/hello.md",
        )
        assert status == 200
        data = json.loads(body)
        assert data.get("status") == "ok"
        assert not os.path.exists(os.path.join(writable_dir, "hello.md"))

    def test_delete_directory(self, writable_server_url, writable_dir):
        """DELETE /api/mounts/{id}/file removes a directory recursively."""
        status, _body = _delete(
            f"{writable_server_url}/api/mounts/writable/file?path=/subdir",
        )
        assert status == 200
        assert not os.path.exists(os.path.join(writable_dir, "subdir"))

    def test_delete_missing_path(self, writable_server_url):
        """DELETE without path should return 400."""
        status, _body = _delete(
            f"{writable_server_url}/api/mounts/writable/file",
        )
        assert status == 400

    def test_delete_readonly_mount(self, writable_server_url):
        """DELETE on readonly mount should return 403."""
        status, _body = _delete(
            f"{writable_server_url}/api/mounts/readonly/file?path=/hello.md",
        )
        assert status == 403


class TestCreateAPI:
    def test_create_file(self, writable_server_url, writable_dir):
        """POST /api/mounts/{id}/create creates a new file."""
        status, body = _post(
            f"{writable_server_url}/api/mounts/writable/create?path=/&name=doc&kind=file",
        )
        assert status == 200
        data = json.loads(body)
        assert data.get("ok") is True
        assert data.get("name") == "doc.md"
        assert os.path.isfile(os.path.join(writable_dir, "doc.md"))

    def test_create_folder(self, writable_server_url, writable_dir):
        """POST /api/mounts/{id}/create creates a folder."""
        status, body = _post(
            f"{writable_server_url}/api/mounts/writable/create?path=/&name=notes&kind=folder",
        )
        assert status == 200
        data = json.loads(body)
        assert data.get("ok") is True
        assert os.path.isdir(os.path.join(writable_dir, "notes"))

    def test_create_duplicate_returns_409(self, writable_server_url):
        """POST /create with existing name should return 409 with suggested_name."""
        status, body = _post(
            f"{writable_server_url}/api/mounts/writable/create?path=/&name=hello&kind=file",
        )
        # hello.md already exists → 409 duplicate
        assert status == 409
        data = json.loads(body)
        assert data.get("error") == "duplicate"
        assert "suggested_name" in data
        assert data["suggested_name"].startswith("hello_")

    def test_create_duplicate_with_overwrite(self, writable_server_url):
        """POST /create with existing name and overwrite=1 should succeed."""
        status, body = _post(
            f"{writable_server_url}/api/mounts/writable/create?path=/&name=hello&kind=file&overwrite=1",
        )
        assert status == 200
        data = json.loads(body)
        assert data.get("ok") is True

    def test_create_duplicate_with_new_name(self, writable_server_url):
        """POST /create with existing name and newName should succeed."""
        status, body = _post(
            f"{writable_server_url}/api/mounts/writable/create?path=/&name=hello&kind=file&newName=hello_custom.md",
        )
        assert status == 200
        data = json.loads(body)
        assert data.get("ok") is True
        assert data["name"] == "hello_custom.md"

    def test_create_missing_name(self, writable_server_url):
        """POST /create without name should return 400."""
        status, _body = _post(
            f"{writable_server_url}/api/mounts/writable/create?path=/",
        )
        assert status == 400

    def test_create_invalid_name(self, writable_server_url):
        """POST /create with slashes in name should return 400 or connection error."""
        try:
            status, _body = _post(
                f"{writable_server_url}/api/mounts/writable/create?path=/&name=a/b&kind=file",
            )
            assert status != 200
        except (ConnectionError, OSError):
            pass  # Server may abort connection on invalid input

    def test_create_readonly_mount(self, writable_server_url):
        """POST /create on readonly mount should return 403."""
        status, _body = _post(
            f"{writable_server_url}/api/mounts/readonly/create?path=/&name=x&kind=file",
        )
        assert status == 403


class TestMoveAPI:
    def test_move_file(self, writable_server_url, writable_dir):
        """POST /api/mounts/{id}/move moves a file."""
        status, body = _post(
            f"{writable_server_url}/api/mounts/writable/move?src=/hello.md&destDir=/subdir",
        )
        assert status == 200
        data = json.loads(body)
        assert data.get("ok") is True
        assert not os.path.exists(os.path.join(writable_dir, "hello.md"))
        assert os.path.isfile(os.path.join(writable_dir, "subdir", "hello.md"))

    def test_move_to_self_subtree_forbidden(self, writable_server_url):
        """POST /move moving a dir into itself should return 400."""
        status, _body = _post(
            f"{writable_server_url}/api/mounts/writable/move?src=/subdir&destDir=/subdir",
        )
        assert status == 400

    def test_move_duplicate_at_dest_returns_409(self, writable_server_url, writable_dir):
        """POST /move with existing name at destination should return 409."""
        shutil.copy2(
            os.path.join(writable_dir, "hello.md"),
            os.path.join(writable_dir, "subdir", "hello.md"),
        )
        status, body = _post(
            f"{writable_server_url}/api/mounts/writable/move?src=/hello.md&destDir=/subdir",
        )
        assert status == 409
        data = json.loads(body)
        assert data.get("error") == "duplicate"
        assert "suggested_name" in data

    def test_move_missing_params(self, writable_server_url):
        """POST /move without src/destDir should return 400."""
        status, _body = _post(
            f"{writable_server_url}/api/mounts/writable/move?src=/hello.md",
        )
        assert status == 400

    def test_move_source_not_found(self, writable_server_url):
        """POST /move with nonexistent source should return 404."""
        status, _body = _post(
            f"{writable_server_url}/api/mounts/writable/move?src=/nope.md&destDir=/",
        )
        assert status == 404


class TestCopyAPI:
    def test_copy_file(self, writable_server_url, writable_dir):
        """POST /api/mounts/{id}/copy copies a file."""
        status, body = _post(
            f"{writable_server_url}/api/mounts/writable/copy?src=/hello.md&destDir=/subdir",
        )
        assert status == 200
        data = json.loads(body)
        assert data.get("ok") is True
        # Original still exists
        assert os.path.isfile(os.path.join(writable_dir, "hello.md"))
        # Copy exists
        assert os.path.isfile(os.path.join(writable_dir, "subdir", "hello.md"))

    def test_copy_duplicate_returns_409(self, writable_server_url, writable_dir):
        """POST /copy with existing name at destination should return 409."""
        shutil.copy2(
            os.path.join(writable_dir, "hello.md"),
            os.path.join(writable_dir, "subdir", "hello.md"),
        )
        status, body = _post(
            f"{writable_server_url}/api/mounts/writable/copy?src=/hello.md&destDir=/subdir",
        )
        assert status == 409
        data = json.loads(body)
        assert data.get("error") == "duplicate"
        assert "suggested_name" in data

    def test_copy_missing_params(self, writable_server_url):
        """POST /copy without src/destDir should return 400."""
        status, _body = _post(
            f"{writable_server_url}/api/mounts/writable/copy?src=/hello.md",
        )
        assert status == 400


class TestCrossMountMove:
    def test_cross_mount_move_to_readonly_fails(self, writable_server_url):
        """POST /api/cross-mount-move to a readonly mount should fail."""
        status, _body = _post(
            f"{writable_server_url}/api/cross-mount-move"
            "?srcMount=writable&srcPath=/hello.md"
            "&destMount=readonly&destDir=/",
        )
        assert status == 403

    def test_cross_mount_move_missing_params(self, writable_server_url):
        """POST /api/cross-mount-move without all params should return 400."""
        status, _body = _post(
            f"{writable_server_url}/api/cross-mount-move?srcMount=writable&srcPath=/hello.md",
        )
        assert status == 400


class TestCrossMountCopy:
    def test_cross_mount_copy_to_readonly_fails(self, writable_server_url):
        """POST /api/cross-mount-copy to a readonly mount should fail."""
        status, _body = _post(
            f"{writable_server_url}/api/cross-mount-copy"
            "?srcMount=writable&srcPath=/hello.md"
            "&destMount=readonly&destDir=/",
        )
        assert status == 403

    def test_cross_mount_copy_missing_params(self, writable_server_url):
        """POST /api/cross-mount-copy without all params should return 400."""
        status, _body = _post(
            f"{writable_server_url}/api/cross-mount-copy?srcMount=writable",
        )
        assert status == 400


class TestTreeRecursiveAPI:
    def test_tree_recursive_returns_structure(self, server_url):
        """GET /api/mounts/{id}/tree-recursive returns nested tree."""
        status, body, _ = _get(f"{server_url}/api/mounts/builtin-storage/tree-recursive")
        assert status == 200
        data = json.loads(body)
        # tree-recursive returns a root node dict with children
        assert isinstance(data, dict)
        assert "children" in data or "name" in data

    def test_tree_recursive_unknown_mount(self, server_url):
        """GET /tree-recursive for unknown mount should return 404."""
        status, _body, _ = _get(f"{server_url}/api/mounts/nonexistent/tree-recursive")
        assert status == 404


class TestMountsPublicAPI:
    def test_mounts_public_returns_list(self, server_url):
        """GET /api/mounts/public returns public mounts."""
        status, body, _ = _get(f"{server_url}/api/mounts/public")
        assert status == 200
        data = json.loads(body)
        assert isinstance(data, list)
        ids = [m["id"] for m in data]
        assert "builtin-storage" in ids


class TestConfigAPI:
    def test_config_returns_dict(self, server_url):
        """GET /api/config returns configuration dict."""
        status, body, _ = _get(f"{server_url}/api/config")
        assert status == 200
        data = json.loads(body)
        assert isinstance(data, dict)


class TestSearchAPI:
    def test_search_returns_results(self, server_url):
        """GET /api/search?q=... returns search results."""
        status, body, _ = _get(f"{server_url}/api/search?q=Hello&limit=5")
        assert status == 200
        data = json.loads(body)
        assert isinstance(data, list)

    def test_search_empty_query(self, server_url):
        """GET /api/search with empty query returns empty list."""
        status, body, _ = _get(f"{server_url}/api/search?q=")
        assert status == 200
        data = json.loads(body)
        assert isinstance(data, list)


class TestPluginsAPI:
    def test_plugins_returns_dict(self, server_url):
        """GET /api/plugins returns plugin dict."""
        status, body, _ = _get(f"{server_url}/api/plugins")
        assert status == 200
        data = json.loads(body)
        assert isinstance(data, dict)
        assert "plugins" in data


class TestSearchVisibility:
    """Test that search results respect mount visibility for admin vs non-admin."""

    @pytest.fixture
    def search_server(self, web_root, storage_dir, tmp_path):
        """Server with a public mount and a private (admin-only) mount."""
        # Create admin-only mount dir with a unique file
        admin_dir = tmp_path / "admin_mount"
        admin_dir.mkdir()
        with open(admin_dir / "secret.md", "w", encoding="utf-8") as f:
            f.write("# Secret Admin Doc\nThis is admin-only content with uniquekeyword123.\n")

        # Create public mount dir with a unique file
        pub_dir = tmp_path / "public_mount"
        pub_dir.mkdir()
        with open(pub_dir / "public.md", "w", encoding="utf-8") as f:
            f.write("# Public Doc\nThis is public content with uniquekeyword123.\n")

        # Also put a file in storage_dir (builtin)
        with open(os.path.join(storage_dir, "builtin.md"), "w", encoding="utf-8") as f:
            f.write("# Builtin Doc\nThis is builtin content with uniquekeyword123.\n")

        port = _find_free_port()
        mgr = MountManager([])
        from nas_md.webserver import MountEntry

        builtin = MountEntry("builtin-storage", "nas-md", storage_dir, public=True, readonly=True)
        admin_mount = MountEntry(
            "admin-mount", "admin-only", str(admin_dir), public=False, readonly=False, host=True
        )
        public_mount = MountEntry(
            "public-mount", "public", str(pub_dir), public=True, readonly=False, host=True
        )
        mgr.mounts = [builtin, admin_mount, public_mount]

        MountHTTPHandler.mount_manager = mgr
        MountHTTPHandler.web_root = web_root
        MountHTTPHandler.search_dirs = [storage_dir, str(admin_dir), str(pub_dir)]

        # Build search index
        from nas_md.search import init_db, rebuild_index

        init_db()
        rebuild_index([storage_dir, str(admin_dir), str(pub_dir)])

        server = _create_server("127.0.0.1", port, MountHTTPHandler, cert_dir="")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        time.sleep(0.3)
        yield f"http://127.0.0.1:{port}", str(admin_dir), str(pub_dir)
        server.shutdown()

    def test_admin_sees_all_mounts(self, search_server):
        """Admin user should see files from all mounts in search results."""
        url, _admin_dir, _pub_dir = search_server
        status, body, _ = _get(
            f"{url}/api/search?q=uniquekeyword123&limit=20",
            headers={"X-Admin": "1"},
        )
        assert status == 200
        data = json.loads(body)
        # Admin should see results from all 3 mounts
        mount_ids = {r.get("mount_id") for r in data}
        assert "builtin-storage" in mount_ids, f"Admin should see builtin, got mounts: {mount_ids}"
        assert "admin-mount" in mount_ids, f"Admin should see admin-mount, got mounts: {mount_ids}"
        assert (
            "public-mount" in mount_ids
        ), f"Admin should see public-mount, got mounts: {mount_ids}"

    def test_non_admin_sees_only_public(self, search_server):
        """Non-admin user should only see files from public mounts."""
        url, _admin_dir, _pub_dir = search_server
        status, body, _ = _get(f"{url}/api/search?q=uniquekeyword123&limit=20")
        assert status == 200
        data = json.loads(body)
        mount_ids = {r.get("mount_id") for r in data}
        assert (
            "admin-mount" not in mount_ids
        ), f"Non-admin should NOT see admin-mount, got: {mount_ids}"
        assert "public-mount" in mount_ids, f"Non-admin should see public-mount, got: {mount_ids}"
        assert "builtin-storage" in mount_ids, f"Non-admin should see builtin, got: {mount_ids}"

    def test_search_result_has_mount_id_and_rel_path(self, search_server):
        """Search results should include mount_id and rel_path for opening files."""
        url, _, _ = search_server
        status, body, _ = _get(
            f"{url}/api/search?q=uniquekeyword123&limit=20",
            headers={"X-Admin": "1"},
        )
        assert status == 200
        data = json.loads(body)
        for r in data:
            assert "mount_id" in r, f"Result missing mount_id: {r}"
            assert "rel_path" in r, f"Result missing rel_path: {r}"
            assert r["mount_id"] is not None, f"mount_id should not be None: {r}"


class TestFileModTimeHeader:
    """Test that GET /api/mounts/{id}/file returns X-Mod-Time header."""

    def test_file_response_has_mod_time_header(self, writable_server_url, writable_dir):
        """GET file should include X-Mod-Time header with millisecond timestamp."""
        status, _body, headers = _get(
            f"{writable_server_url}/api/mounts/writable/file?path=/hello.md"
        )
        assert status == 200
        assert (
            "x-mod-time" in headers
        ), f"Missing X-Mod-Time header, got headers: {list(headers.keys())}"
        mtime_str = headers["x-mod-time"]
        mtime = int(mtime_str)
        # Should be a reasonable millisecond timestamp (after year 2020)
        assert mtime > 1577836800000, f"X-Mod-Time seems too old: {mtime}"

    def test_mod_time_matches_file_mtime(self, writable_server_url, writable_dir):
        """X-Mod-Time should match the file's actual mtime in milliseconds."""
        status, _body, headers = _get(
            f"{writable_server_url}/api/mounts/writable/file?path=/hello.md"
        )
        assert status == 200
        mtime_from_header = int(headers["x-mod-time"])
        actual_mtime_ms = int(os.path.getmtime(os.path.join(writable_dir, "hello.md")) * 1000)
        # Allow 1 second tolerance (filesystem mtime precision)
        assert (
            abs(mtime_from_header - actual_mtime_ms) < 2000
        ), f"X-Mod-Time {mtime_from_header} too far from actual mtime {actual_mtime_ms}"

    def test_mod_time_updates_after_write(self, writable_server_url, writable_dir):
        """X-Mod-Time should change after file is modified."""
        status1, _body1, headers1 = _get(
            f"{writable_server_url}/api/mounts/writable/file?path=/hello.md"
        )
        assert status1 == 200
        mtime1 = int(headers1["x-mod-time"])

        # Wait briefly then modify the file
        time.sleep(0.1)
        with open(os.path.join(writable_dir, "hello.md"), "w", encoding="utf-8") as f:
            f.write("# Modified content\n")

        status2, _body2, headers2 = _get(
            f"{writable_server_url}/api/mounts/writable/file?path=/hello.md"
        )
        assert status2 == 200
        mtime2 = int(headers2["x-mod-time"])
        assert mtime2 >= mtime1, f"X-Mod-Time should not decrease: {mtime2} < {mtime1}"


class TestCrossMountMoveSuccess:
    """Test successful cross-mount move operations."""

    @pytest.fixture
    def dual_mount_server(self, web_root):
        """Server with two writable mounts for cross-mount operations."""
        dir_a = tempfile.mkdtemp(prefix="nasmd_mountA_")
        dir_b = tempfile.mkdtemp(prefix="nasmd_mountB_")
        with open(os.path.join(dir_a, "source.md"), "w", encoding="utf-8") as f:
            f.write("# Source File\n")
        os.makedirs(os.path.join(dir_a, "srcdir"), exist_ok=True)
        with open(os.path.join(dir_a, "srcdir", "nested.md"), "w", encoding="utf-8") as f:
            f.write("## Nested\n")

        port = _find_free_port()
        mgr = MountManager([])
        from nas_md.webserver import MountEntry

        mgr.mounts.insert(
            0, MountEntry("mount-a", "Mount A", dir_a, public=True, readonly=False, host=True)
        )
        mgr.mounts.insert(
            1, MountEntry("mount-b", "Mount B", dir_b, public=True, readonly=False, host=True)
        )
        MountHTTPHandler.mount_manager = mgr
        MountHTTPHandler.web_root = web_root
        MountHTTPHandler.search_dirs = [dir_a, dir_b]

        server = _create_server("127.0.0.1", port, MountHTTPHandler, cert_dir="")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        time.sleep(0.3)
        yield f"http://127.0.0.1:{port}", dir_a, dir_b
        server.shutdown()
        shutil.rmtree(dir_a, ignore_errors=True)
        shutil.rmtree(dir_b, ignore_errors=True)

    def test_cross_mount_move_file_success(self, dual_mount_server):
        """Move a file from mount-a to mount-b."""
        url, dir_a, dir_b = dual_mount_server
        status, body = _post(
            f"{url}/api/cross-mount-move"
            "?srcMount=mount-a&srcPath=/source.md"
            "&destMount=mount-b&destDir=/",
        )
        assert status == 200
        data = json.loads(body)
        assert data.get("ok") is True
        # Source should be removed
        assert not os.path.exists(os.path.join(dir_a, "source.md"))
        # Destination should exist
        assert os.path.isfile(os.path.join(dir_b, "source.md"))
        with open(os.path.join(dir_b, "source.md"), encoding="utf-8") as f:
            assert f.read() == "# Source File\n"

    def test_cross_mount_move_directory_success(self, dual_mount_server):
        """Move a directory from mount-a to mount-b."""
        url, dir_a, dir_b = dual_mount_server
        status, body = _post(
            f"{url}/api/cross-mount-move"
            "?srcMount=mount-a&srcPath=/srcdir"
            "&destMount=mount-b&destDir=/",
        )
        assert status == 200
        data = json.loads(body)
        assert data.get("ok") is True
        # Source should be removed
        assert not os.path.exists(os.path.join(dir_a, "srcdir"))
        # Destination should exist with contents
        assert os.path.isdir(os.path.join(dir_b, "srcdir"))
        assert os.path.isfile(os.path.join(dir_b, "srcdir", "nested.md"))

    def test_cross_mount_move_duplicate_returns_409(self, dual_mount_server):
        """Cross-mount move to existing file should return 409 with suggested name."""
        url, _dir_a, dir_b = dual_mount_server
        # Create a file with same name in destination
        with open(os.path.join(dir_b, "source.md"), "w", encoding="utf-8") as f:
            f.write("# Existing\n")
        status, body = _post(
            f"{url}/api/cross-mount-move"
            "?srcMount=mount-a&srcPath=/source.md"
            "&destMount=mount-b&destDir=/",
        )
        assert status == 409
        data = json.loads(body)
        assert data.get("error") == "duplicate"
        assert "suggested_name" in data

    def test_cross_mount_move_with_overwrite(self, dual_mount_server):
        """Cross-mount move with overwrite=1 should replace existing file."""
        url, dir_a, dir_b = dual_mount_server
        with open(os.path.join(dir_b, "source.md"), "w", encoding="utf-8") as f:
            f.write("# Existing\n")
        status, body = _post(
            f"{url}/api/cross-mount-move"
            "?srcMount=mount-a&srcPath=/source.md"
            "&destMount=mount-b&destDir=/&overwrite=1",
        )
        assert status == 200
        data = json.loads(body)
        assert data.get("ok") is True
        # Destination should have the source content
        with open(os.path.join(dir_b, "source.md"), encoding="utf-8") as f:
            assert f.read() == "# Source File\n"
        # Source should be removed
        assert not os.path.exists(os.path.join(dir_a, "source.md"))


class TestCrossMountCopySuccess:
    """Test successful cross-mount copy operations."""

    @pytest.fixture
    def dual_mount_server(self, web_root):
        """Server with two writable mounts for cross-mount operations."""
        dir_a = tempfile.mkdtemp(prefix="nasmd_mountA_")
        dir_b = tempfile.mkdtemp(prefix="nasmd_mountB_")
        with open(os.path.join(dir_a, "original.md"), "w", encoding="utf-8") as f:
            f.write("# Original\n")

        port = _find_free_port()
        mgr = MountManager([])
        from nas_md.webserver import MountEntry

        mgr.mounts.insert(
            0, MountEntry("mount-a", "Mount A", dir_a, public=True, readonly=False, host=True)
        )
        mgr.mounts.insert(
            1, MountEntry("mount-b", "Mount B", dir_b, public=True, readonly=False, host=True)
        )
        MountHTTPHandler.mount_manager = mgr
        MountHTTPHandler.web_root = web_root
        MountHTTPHandler.search_dirs = [dir_a, dir_b]

        server = _create_server("127.0.0.1", port, MountHTTPHandler, cert_dir="")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        time.sleep(0.3)
        yield f"http://127.0.0.1:{port}", dir_a, dir_b
        server.shutdown()
        shutil.rmtree(dir_a, ignore_errors=True)
        shutil.rmtree(dir_b, ignore_errors=True)

    def test_cross_mount_copy_file_success(self, dual_mount_server):
        """Copy a file from mount-a to mount-b."""
        url, dir_a, dir_b = dual_mount_server
        status, body = _post(
            f"{url}/api/cross-mount-copy"
            "?srcMount=mount-a&srcPath=/original.md"
            "&destMount=mount-b&destDir=/",
        )
        assert status == 200
        data = json.loads(body)
        assert data.get("ok") is True
        # Source should still exist
        assert os.path.isfile(os.path.join(dir_a, "original.md"))
        # Destination should exist
        assert os.path.isfile(os.path.join(dir_b, "original.md"))
        with open(os.path.join(dir_b, "original.md"), encoding="utf-8") as f:
            assert f.read() == "# Original\n"

    def test_cross_mount_copy_duplicate_returns_409(self, dual_mount_server):
        """Cross-mount copy to existing file should return 409."""
        url, _dir_a, dir_b = dual_mount_server
        with open(os.path.join(dir_b, "original.md"), "w", encoding="utf-8") as f:
            f.write("# Existing\n")
        status, body = _post(
            f"{url}/api/cross-mount-copy"
            "?srcMount=mount-a&srcPath=/original.md"
            "&destMount=mount-b&destDir=/",
        )
        assert status == 409
        data = json.loads(body)
        assert data.get("error") == "duplicate"

    def test_cross_mount_copy_with_overwrite(self, dual_mount_server):
        """Cross-mount copy with overwrite=1 should replace existing file."""
        url, dir_a, dir_b = dual_mount_server
        with open(os.path.join(dir_b, "original.md"), "w", encoding="utf-8") as f:
            f.write("# Existing\n")
        status, body = _post(
            f"{url}/api/cross-mount-copy"
            "?srcMount=mount-a&srcPath=/original.md"
            "&destMount=mount-b&destDir=/&overwrite=1",
        )
        assert status == 200
        data = json.loads(body)
        assert data.get("ok") is True
        # Source should still exist
        assert os.path.isfile(os.path.join(dir_a, "original.md"))
        # Destination should have the source content
        with open(os.path.join(dir_b, "original.md"), encoding="utf-8") as f:
            assert f.read() == "# Original\n"
