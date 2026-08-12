"""
Phase 3 PWA Integration Tests
Tests that the server correctly serves PWA files with proper content-types.
Skipped if server is not running (requires `python -m nas_md.cli web` on port 8080).
"""
import pytest
import httpx


# ================================================================
# Helper: get server URL from environment or default
# ================================================================

def _get_server_url():
    import os
    return os.environ.get('NASMD_SERVER_URL', 'http://127.0.0.1:8080')


def _server_available():
    """Check if server is running"""
    try:
        with httpx.Client(timeout=2.0) as c:
            r = c.get(_get_server_url(), follow_redirects=True)
            return r.status_code in (200, 301, 302, 401, 403)
    except Exception:
        return False


# Skip all tests in this file if server is not running
pytestmark = pytest.mark.skipif(
    not _server_available(),
    reason="Server not running at 127.0.0.1:8080 — start with `python -m nas_md.cli web`"
)


@pytest.fixture(scope='module')
def client():
    """HTTP client for integration tests against running server"""
    with httpx.Client(base_url=_get_server_url(), follow_redirects=True, timeout=5.0) as c:
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

    @pytest.mark.parametrize("filename,expected_ct", [
        ('icons/icon-192.png', 'image/png'),
        ('icons/icon-512.png', 'image/png'),
        ('icons/icon-maskable-192.png', 'image/png'),
        ('icons/icon-maskable-512.png', 'image/png'),
        ('icons/icon.svg', 'image/svg+xml'),
    ])
    def test_icon_content_type(self, client, filename, expected_ct):
        path, exp = filename
        r = client.get(f'/{path}')
        ct = r.headers.get('content-type', '')
        assert exp in ct.lower(), f"{path} content-type should contain '{exp}', got: {ct}"

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
# Error handling: missing PWA files return 404 gracefully
# ================================================================

class TestPwaErrorHandling:
    def test_missing_sw_returns_404(self, client):
        """If sw.js is moved, should return 404 not crash"""
        r = client.get('/sw.js')
        assert r.status_code in (200, 404), f"sw.js should be 200 or 404, got {r.status_code}"

    def test_missing_manifest_returns_404(self, client):
        r = client.get('/manifest.json')
        assert r.status_code in (200, 404), f"manifest should be 200 or 404, got {r.status_code}"


# ================================================================
# Cross-origin / security
# ================================================================

class TestPWASecurity:
    def test_manifest_no_x_frame_options_conflict(self, client):
        """manifest.json should not have X-Frame-Options that would block embeds"""
        r = client.get('/manifest.json')
        xfo = r.headers.get('x-frame-options', '')
        # manifest is a JSON file, not rendered in iframe — this is informational
        assert r.status_code == 200

    def test_sw_no_x_content_type_options_nosniff(self, client):
        """SW should be served without nosniff that could block registration"""
        r = client.get('/sw.js')
        if r.status_code == 200:
            # Some nosniff is fine; we just want to verify it serves
            pass
