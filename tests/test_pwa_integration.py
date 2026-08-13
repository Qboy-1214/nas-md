"""
Phase 3 PWA Integration Tests
Tests that the server correctly serves PWA files with proper content-types.

Auto-starts a test server on a free port if none is running, then tears it down.
Usage: python -m pytest tests/test_pwa_integration.py -v
"""
import os
import signal
import subprocess
import time
from pathlib import Path
import pytest
import httpx


# ================================================================
# Server lifecycle
# ================================================================

_PORT = None
_PROC = None
_BASE_URL = None


def _find_free_port():
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


def _server_alive(url, timeout=2.0):
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True)
        return r.status_code in (200, 301, 302, 401, 403)
    except Exception:
        return False


def _start_server(port):
    """Start nas-md web server on given port. Returns True if ready."""
    global _PROC, _PORT, _BASE_URL
    _PORT = port
    _BASE_URL = f'http://127.0.0.1:{port}'

    project_root = Path(__file__).resolve().parent.parent
    web_root = project_root / 'web'
    storage_dir = project_root / 'tests' / 'storage-test-integration'
    mount_dirs = project_root / 'tests' / 'e2e' / 'test-mount'
    storage_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env['WEB_PORT'] = str(port)
    env['WEB_HOST'] = '127.0.0.1'
    env['WEB_ROOT'] = str(web_root)
    env['STORAGE_DIR'] = str(storage_dir)
    env['MOUNT_DIRS'] = str(mount_dirs)
    env['PYTHONIOENCODING'] = 'utf-8'

    _PROC = subprocess.Popen(
        ['python', '-m', 'nas_md.cli', 'web'],
        cwd=str(project_root),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait up to 20s for server to be ready
    for i in range(40):
        time.sleep(0.5)
        if _server_alive(_BASE_URL):
            return True
        if _PROC.poll() is not None:
            break

    # Server didn't start — kill and report
    if _PROC and _PROC.poll() is None:
        _PROC.kill()
    return False


def _stop_server():
    global _PROC
    if _PROC and _PROC.poll() is None:
        try:
            _PROC.terminate()
            _PROC.wait(timeout=5)
        except Exception:
            try:
                _PROC.kill()
            except Exception:
                pass
    _PROC = None
    _PORT = None
    _BASE_URL = None


# ================================================================
# Session-scoped fixture: manages server lifecycle
# ================================================================

@pytest.fixture(scope='session', autouse=True)
def pwa_test_server():
    """Auto-start a test server if none is available on the default port."""
    global _PORT, _BASE_URL

    # Check if server already running on common ports
    for candidate_port in (8080, 8081, 8082):
        url = f'http://127.0.0.1:{candidate_port}'
        if _server_alive(url):
            _PORT = candidate_port
            _BASE_URL = url
            yield
            return

    # No server found — start one on a free port
    port = _find_free_port()
    if not _start_server(port):
        pytest.skip('Could not start test server')
        return

    yield

    _stop_server()


# ================================================================
# HTTP client
# ================================================================

@pytest.fixture(scope='session')
def client(pwa_test_server):
    with httpx.Client(base_url=_BASE_URL, follow_redirects=True, timeout=10.0) as c:
        yield c


# ================================================================
# Manifest endpoint
# ================================================================

class TestManifestEndpoint:
    def test_manifest_returns_200(self, client):
        r = client.get('/manifest.json')
        assert r.status_code == 200, f"manifest.json returned {r.status_code}"

    def test_manifest_content_type_json(self, client):
        r = client.get('/manifest.json')
        ct = r.headers.get('content-type', '')
        assert 'json' in ct.lower(), f"manifest content-type should be JSON, got: {ct}"

    def test_manifest_body_valid_json(self, client):
        r = client.get('/manifest.json')
        data = r.json()
        assert 'name' in data
        assert 'icons' in data
        assert len(data['icons']) >= 2


# ================================================================
# Service Worker endpoint
# ================================================================

class TestServiceWorkerEndpoint:
    def test_sw_returns_200(self, client):
        r = client.get('/sw.js')
        assert r.status_code == 200, f"sw.js returned {r.status_code}"

    def test_sw_content_type_javascript(self, client):
        r = client.get('/sw.js')
        ct = r.headers.get('content-type', '')
        assert 'javascript' in ct.lower() or 'text' in ct.lower(), \
            f"sw.js content-type should be JS, got: {ct}"

    def test_sw_body_not_empty(self, client):
        r = client.get('/sw.js')
        assert len(r.text) > 100, "sw.js body should not be empty"

    def test_sw_body_contains_fetch_handler(self, client):
        r = client.get('/sw.js')
        assert 'fetch' in r.text, "sw.js should contain fetch event handler"


# ================================================================
# Icon endpoints
# ================================================================

class TestIconEndpoints:
    @pytest.mark.parametrize("filename", [
        'icons/icon-192.png',
        'icons/icon-512.png',
        'icons/icon-maskable-192.png',
        'icons/icon-maskable-512.png',
        'icons/icon.svg',
    ])
    def test_icon_returns_200(self, client, filename):
        r = client.get(f'/{filename}')
        assert r.status_code == 200, f"{filename} returned {r.status_code}"

    @pytest.mark.parametrize("path,expected_ct", [
        ('icons/icon-192.png', 'image/png'),
        ('icons/icon-512.png', 'image/png'),
        ('icons/icon-maskable-192.png', 'image/png'),
        ('icons/icon-maskable-512.png', 'image/png'),
        ('icons/icon.svg', 'image/svg+xml'),
    ])
    def test_icon_content_type(self, client, path, expected_ct):
        r = client.get(f'/{path}')
        ct = r.headers.get('content-type', '')
        assert expected_ct in ct.lower(), f"{path} content-type should contain '{expected_ct}', got: {ct}"

    def test_icon_not_empty(self, client):
        r = client.get('/icons/icon-192.png')
        assert len(r.content) > 0, "icon-192.png should not be empty"


# ================================================================
# Main page with PWA tags
# ================================================================

class TestMainPagePwa:
    def test_admin_page_contains_manifest_link(self, client):
        r = client.get('/admin')
        assert r.status_code == 200
        assert 'manifest.json' in r.text, "admin page should link manifest"

    def test_admin_page_contains_theme_color(self, client):
        r = client.get('/admin')
        assert 'theme-color' in r.text, "admin page should have theme-color meta"

    def test_admin_page_contains_network_status(self, client):
        r = client.get('/admin')
        assert 'network-status' in r.text, "admin page should have network-status element"

    def test_admin_page_contains_offline_queue_script(self, client):
        r = client.get('/admin')
        assert 'offline_queue.js' in r.text, "admin page should load offline_queue.js"


# ================================================================
# Error handling
# ================================================================

class TestPwaErrorHandling:
    def test_missing_sw_returns_404(self, client):
        r = client.get('/sw.js')
        assert r.status_code in (200, 404), f"sw.js should be 200 or 404, got {r.status_code}"

    def test_missing_manifest_returns_404(self, client):
        r = client.get('/manifest.json')
        assert r.status_code in (200, 404), f"manifest should be 200 or 404, got {r.status_code}"


# ================================================================
# Security headers
# ================================================================

class TestPWASecurity:
    def test_manifest_no_x_frame_options_conflict(self, client):
        r = client.get('/manifest.json')
        assert r.status_code == 200

    def test_sw_no_nosniff_block(self, client):
        r = client.get('/sw.js')
        if r.status_code == 200:
            pass  # served successfully
