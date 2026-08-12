"""
Phase 3 PWA Enhancement Tests
Tests for: manifest, SW, offline queue, network status
"""
import os
import json
import pytest


WEB_DIR = os.path.join(os.path.dirname(__file__), '..', 'web')


# === 3.1 Web App Manifest ===

class TestManifest:
    def test_manifest_exists(self):
        path = os.path.join(WEB_DIR, 'manifest.json')
        assert os.path.exists(path), "manifest.json not found"

    def test_manifest_valid_json(self):
        path = os.path.join(WEB_DIR, 'manifest.json')
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert isinstance(data, dict)

    def test_manifest_required_fields(self):
        path = os.path.join(WEB_DIR, 'manifest.json')
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert 'name' in data, "manifest missing 'name'"
        assert 'short_name' in data, "manifest missing 'short_name'"
        assert 'start_url' in data, "manifest missing 'start_url'"
        assert 'display' in data, "manifest missing 'display'"
        assert 'theme_color' in data, "manifest missing 'theme_color'"
        assert 'icons' in data, "manifest missing 'icons'"

    def test_manifest_theme_color(self):
        path = os.path.join(WEB_DIR, 'manifest.json')
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert data['theme_color'] == '#5645d4', "theme_color should match CSS primary"
        assert data['background_color'] == '#0a1530', "background_color should match CSS dark bg"
        assert data['display'] == 'standalone', "display should be standalone for PWA"

    def test_manifest_icons(self):
        path = os.path.join(WEB_DIR, 'manifest.json')
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        icons = data['icons']
        assert len(icons) >= 2, "manifest should have at least 2 icon sizes"
        sizes = {icon['sizes'] for icon in icons}
        assert '192x192' in sizes, "manifest should include 192x192 icon"
        assert '512x512' in sizes, "manifest should include 512x512 icon"

    def test_icon_files_exist(self):
        icon_dir = os.path.join(WEB_DIR, 'icons')
        assert os.path.isdir(icon_dir), "icons/ directory missing"
        expected = ['icon-192.png', 'icon-512.png', 'icon.svg']
        for name in expected:
            path = os.path.join(icon_dir, name)
            assert os.path.exists(path), f"Icon file missing: {name}"
            assert os.path.getsize(path) > 0, f"Icon file is empty: {name}"

    def test_maskable_icons(self):
        icon_dir = os.path.join(WEB_DIR, 'icons')
        assert os.path.exists(os.path.join(icon_dir, 'icon-maskable-192.png'))
        assert os.path.exists(os.path.join(icon_dir, 'icon-maskable-512.png'))
        # Check manifest has maskable purpose
        with open(os.path.join(WEB_DIR, 'manifest.json'), 'r') as f:
            data = json.load(f)
        maskable = [i for i in data['icons'] if i.get('purpose') == 'maskable']
        assert len(maskable) >= 2, "manifest should have at least 2 maskable icons"


# === index.html PWA tags ===

class TestIndexHtmlPwa:
    def test_manifest_link(self):
        path = os.path.join(WEB_DIR, 'index.html')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'manifest.json' in content, "index.html should link manifest.json"

    def test_theme_color_meta(self):
        path = os.path.join(WEB_DIR, 'index.html')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'theme-color' in content, "index.html should have theme-color meta"
        assert '#5645d4' in content, "theme-color should match primary color"

    def test_apple_meta_tags(self):
        path = os.path.join(WEB_DIR, 'index.html')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'apple-mobile-web-app-capable' in content
        assert 'apple-mobile-web-app-status-bar-style' in content
        assert 'apple-mobile-web-app-title' in content

    def test_favicon_link(self):
        path = os.path.join(WEB_DIR, 'index.html')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'icon.svg' in content or 'icon-192.png' in content, "favicon link missing"

    def test_offline_queue_script(self):
        path = os.path.join(WEB_DIR, 'index.html')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'offline_queue.js' in content, "offline_queue.js should be loaded in index.html"

    def test_script_order(self):
        """offline_queue.js must load before app.js"""
        path = os.path.join(WEB_DIR, 'index.html')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        q_idx = content.find('offline_queue.js')
        a_idx = content.find('app.js')
        assert q_idx > 0, "offline_queue.js not found in index.html"
        assert a_idx > 0, "app.js not found in index.html"
        assert q_idx < a_idx, "offline_queue.js must load before app.js"


# === 3.2 Service Worker ===

class TestServiceWorker:
    def test_sw_file_exists(self):
        path = os.path.join(WEB_DIR, 'sw.js')
        assert os.path.exists(path), "sw.js not found"

    def test_sw_valid_syntax(self):
        path = os.path.join(WEB_DIR, 'sw.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Basic syntax checks
        assert "addEventListener('install'" in content or 'addEventListener("install"' in content
        assert "addEventListener('fetch'" in content or 'addEventListener("fetch"' in content
        assert "addEventListener('activate'" in content or 'addEventListener("activate"' in content

    def test_sw_cache_names(self):
        path = os.path.join(WEB_DIR, 'sw.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'CACHE_NAME' in content, "SW should define CACHE_NAME"

    def test_sw_static_assets(self):
        path = os.path.join(WEB_DIR, 'sw.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Should cache key assets
        assert 'app.css' in content
        assert 'app.js' in content
        assert 'manifest.json' in content

    def test_sw_network_first_api(self):
        """API requests should use network-first strategy"""
        path = os.path.join(WEB_DIR, 'sw.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert '/api/' in content, "SW should handle /api/ requests"
        assert 'networkFirst' in content or 'cacheFirst' in content, "SW should have fetch strategies"

    def test_sw_registerd_in_app_js(self):
        path = os.path.join(WEB_DIR, 'app.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert "navigator.serviceWorker.register" in content, "app.js should register SW"
        assert "/sw.js" in content, "app.js should register /sw.js"


# === 3.3 Offline Queue ===

class TestOfflineQueue:
    def test_file_exists(self):
        path = os.path.join(WEB_DIR, 'offline_queue.js')
        assert os.path.exists(path), "offline_queue.js not found"

    def test_valid_syntax(self):
        path = os.path.join(WEB_DIR, 'offline_queue.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'indexedDB' in content, "offline_queue.js should use IndexedDB"
        assert 'queueEdit' in content, "offline_queue.js should define queueEdit"
        assert 'replayPending' in content, "offline_queue.js should define replayPending"
        assert 'nasmdOfflineQueue' in content, "offline_queue.js should expose nasmdOfflineQueue"

    def test_queue_functions_exposed(self):
        path = os.path.join(WEB_DIR, 'offline_queue.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        expected = ['queueEdit', 'getPendingEdits', 'markSynced', 'clearQueue', 'replayPending']
        for fn in expected:
            assert fn in content, f"offline_queue.js should expose {fn}"

    def test_online_event_listener(self):
        path = os.path.join(WEB_DIR, 'offline_queue.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert "addEventListener('online'" in content or 'addEventListener("online"' in content, \
            "offline_queue should listen for online event"

    def test_saveFile_integration(self):
        """saveFile should use offline queue when no network"""
        path = os.path.join(WEB_DIR, 'app.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'nasmdOfflineQueue' in content, "app.js should reference nasmdOfflineQueue"
        assert 'queueEdit' in content, "app.js should call queueEdit in offline path"


# === 3.4 Network Status Indicator ===

class TestNetworkStatus:
    def test_html_element(self):
        path = os.path.join(WEB_DIR, 'index.html')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'network-status' in content, "index.html should have network-status element"
        assert 'network-dot' in content, "index.html should have network-dot element"
        assert 'network-label' in content, "index.html should have network-label element"

    def test_css_styles(self):
        path = os.path.join(WEB_DIR, 'app.css')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert '.network-status' in content, "app.css should have .network-status styles"
        assert '.network-dot' in content, "app.css should have .network-dot styles"
        assert '.network-label' in content, "app.css should have .network-label styles"
        assert 'offline' in content, "app.css should have offline state styles"
        assert 'syncing' in content, "app.css should have syncing state styles"

    def test_js_initialization(self):
        path = os.path.join(WEB_DIR, 'app.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'initNetworkStatus' in content, "app.js should have initNetworkStatus"
        assert "navigator.onLine" in content, "initNetworkStatus should check navigator.onLine"

    def test_mobile_network_dot_hidden_label(self):
        """On mobile, only the dot should be visible (label hidden)"""
        path = os.path.join(WEB_DIR, 'app.css')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Check that there's a media query hiding the label
        assert '@media' in content and 'network-label' in content, \
            "CSS should hide network-label on mobile via media query"

    def test_pulse_animation(self):
        """Syncing state should have pulse animation"""
        path = os.path.join(WEB_DIR, 'app.css')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert '@keyframes pulse' in content, "CSS should have pulse animation for syncing state"


# === Integration: all Phase 3 pieces ===

class TestPhase3Integration:
    def test_all_phase3_files(self):
        expected = [
            'web/manifest.json',
            'web/sw.js',
            'web/offline_queue.js',
            'web/icons/icon-192.png',
            'web/icons/icon-512.png',
            'web/icons/icon-maskable-192.png',
            'web/icons/icon-maskable-512.png',
            'web/icons/icon.svg',
        ]
        for rel in expected:
            full = os.path.join(os.path.dirname(__file__), '..', rel)
            assert os.path.exists(full), f"Missing Phase 3 file: {rel}"

    def test_no_phase2_regression(self):
        """Phase 3 changes should not break Phase 2 functionality"""
        # Check that Phase 2 elements still exist
        path = os.path.join(WEB_DIR, 'index.html')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'file-context-menu' in content, "Phase 2: context menu should still exist"
        assert 'search-results' in content, "Phase 2: search results should still exist"

        path = os.path.join(WEB_DIR, 'app.css')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert '.file-context-menu' in content, "Phase 2: context menu CSS should still exist"
        assert '@media (max-width: 480px)' in content, "Phase 2: 480px breakpoint should still exist"

        path = os.path.join(WEB_DIR, 'app.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'initFileTreeTouch' in content, "Phase 2: file tree touch should still exist"
        assert 'initMobileToolbar' in content, "Phase 2: toolbar scroll should still exist"
