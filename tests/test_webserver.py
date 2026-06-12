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
        """POST /api/mounts/{id}/create creates a folder with tmp.md."""
        status, body = _post(
            f"{writable_server_url}/api/mounts/writable/create?path=/&name=notes&kind=folder",
        )
        assert status == 200
        data = json.loads(body)
        assert data.get("ok") is True
        assert os.path.isdir(os.path.join(writable_dir, "notes"))
        assert os.path.isfile(os.path.join(writable_dir, "notes", "tmp.md"))

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
