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


def _get(url: str) -> tuple[int, str, dict]:
    """Send GET request, return (status, body_text, headers_dict)."""
    import urllib.request

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, body, headers
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return e.code, body, {}


def _post(url: str, data: dict | None = None, content_type: str = "application/json") -> tuple[int, str]:
    """Send POST request, return (status, body_text)."""
    import urllib.request

    body_bytes = json.dumps(data).encode("utf-8") if data else b"{}"
    try:
        req = urllib.request.Request(url, data=body_bytes, method="POST")
        req.add_header("Content-Type", content_type)
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
        status, body, _headers = _get(
            f"{server_url}/api/mounts/builtin-storage/file?path=/test.md"
        )
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
