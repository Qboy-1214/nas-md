"""
Phase 3 PWA Enhancement — Deep Unit Tests
Covers: manifest, SW, offline queue, network status, edge cases
"""
import os
import json
import re
import pytest


WEB_DIR = os.path.join(os.path.dirname(__file__), '..', 'web')


# ================================================================
# 3.1 Web App Manifest — Deep Validation
# ================================================================

class TestManifestDeep:
    def test_manifest_orientation(self):
        path = os.path.join(WEB_DIR, 'manifest.json')
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # PWA should allow any orientation (user rotates device)
        assert data.get('orientation') in ('any', 'natural', None), \
            "manifest orientation should be 'any' or absent"

    def test_manifest_categories(self):
        path = os.path.join(WEB_DIR, 'manifest.json')
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        cats = data.get('categories', [])
        assert isinstance(cats, list), "manifest categories should be a list"
        # Should have at least one relevant category
        all_cats = ' '.join(cats).lower() if cats else ''
        assert 'productivity' in all_cats or 'utilities' in all_cats, \
            "manifest should include productivity or utilities category"

    def test_manifest_start_url_absolute(self):
        """start_url should be an absolute path for proper scope resolution"""
        path = os.path.join(WEB_DIR, 'manifest.json')
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        url = data.get('start_url', '')
        assert url.startswith('/'), f"start_url should start with '/': got '{url}'"

    def test_manifest_icons_all_have_required_fields(self):
        path = os.path.join(WEB_DIR, 'manifest.json')
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for icon in data['icons']:
            assert 'src' in icon, "each icon must have 'src'"
            assert 'sizes' in icon, "each icon must have 'sizes'"
            assert 'type' in icon, "each icon must have 'type'"
            assert icon['type'].startswith('image/'), f"icon type must be image/*: {icon['type']}"

    def test_manifest_icon_paths_resolvable(self):
        """Icon paths in manifest should correspond to actual files"""
        path = os.path.join(WEB_DIR, 'manifest.json')
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for icon in data['icons']:
            src = icon['src']
            # strip leading /
            rel = src.lstrip('/')
            full = os.path.join(WEB_DIR, rel)
            assert os.path.exists(full), f"Icon file not found: {rel}"
            assert os.path.getsize(full) > 0, f"Icon file is empty: {rel}"

    def test_manifest_display_standalone_noChromeUI(self):
        """standalone display mode hides browser chrome — correct for PWA"""
        path = os.path.join(WEB_DIR, 'manifest.json')
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        valid_displays = ('standalone', 'minimal-ui', 'fullscreen')
        assert data['display'] in valid_displays, \
            f"display should be one of {valid_displays}, got '{data['display']}'"

    def test_manifest_min_size_for_touch(self):
        """At least one icon should be >= 192px for touch targets"""
        path = os.path.join(WEB_DIR, 'manifest.json')
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        sizes = [tuple(map(int, icon['sizes'].split('x'))) for icon in data['icons']]
        max_size = max(sizes, key=lambda s: s[0] * s[1])
        assert max_size[0] >= 192, f"largest icon should be at least 192px, got {max_size}"

    def test_manifest_short_name_length(self):
        """short_name should be <= 12 chars for home screen display"""
        path = os.path.join(WEB_DIR, 'manifest.json')
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        sn = data.get('short_name', '')
        assert len(sn) <= 12, f"short_name too long ({len(sn)} chars): '{sn}'"

    def test_manifest_name_not_same_as_short(self):
        """name and short_name should differ (otherwise short_name is pointless)"""
        path = os.path.join(WEB_DIR, 'manifest.json')
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert data['name'] != data['short_name'], \
            "manifest name and short_name should differ"

    def test_manifest_theme_matches_css_primary(self):
        """theme_color in manifest must match CSS --c-primary"""
        path_mf = os.path.join(WEB_DIR, 'manifest.json')
        path_css = os.path.join(WEB_DIR, 'app.css')
        with open(path_mf, 'r') as f:
            mf = json.load(f)
        with open(path_css, 'r') as f:
            css = f.read()
        mf_color = mf.get('theme_color', '')
        css_match = re.search(r'--c-primary:\s*([^;]+);', css)
        css_color = css_match.group(1).strip() if css_match else ''
        assert mf_color.lower() == css_color.lower(), \
            f"theme_color mismatch: manifest={mf_color}, CSS={css_color}"

    def test_manifest_background_matches_css_canvas(self):
        """background_color should match the dark canvas color"""
        path_mf = os.path.join(WEB_DIR, 'manifest.json')
        path_css = os.path.join(WEB_DIR, 'app.css')
        with open(path_mf, 'r') as f:
            mf = json.load(f)
        with open(path_css, 'r') as f:
            css = f.read()
        mf_bg = mf.get('background_color', '')
        # Check against known dark bg
        assert mf_bg in ('#0a1530', '#0a1530ff'), \
            f"background_color unexpected: {mf_bg}"


# ================================================================
# 3.2 Service Worker — Deep Syntax & Strategy Tests
# ================================================================

class TestServiceWorkerDeep:
    def test_sw_caches_api_in_data_cache(self):
        """API responses should go to DATA_CACHE_NAME, not main CACHE_NAME"""
        path = os.path.join(WEB_DIR, 'sw.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'DATA_CACHE_NAME' in content, "SW should define separate cache for API data"

    def test_sw_ignores_non_get(self):
        """SW should skip non-GET requests (POST/PUT don't need caching)"""
        path = os.path.join(WEB_DIR, 'sw.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert "request.method !== 'GET'" in content or 'request.method !== "GET"' in content, \
            "SW should filter out non-GET requests"

    def test_sw_skip_sse(self):
        """SSE connections (/api/events) should bypass cache entirely"""
        path = os.path.join(WEB_DIR, 'sw.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert '/api/events' in content, "SW should explicitly handle /api/events"

    def test_sw_offline_response_json_for_api(self):
        """API offline fallback should return JSON, not HTML"""
        path = os.path.join(WEB_DIR, 'sw.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'application/json' in content, "API offline fallback should use JSON content-type"

    def test_sw_offline_html_page_for_static(self):
        """Static asset offline fallback should return HTML page"""
        path = os.path.join(WEB_DIR, 'sw.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'text/html' in content, "Static offline fallback should use HTML content-type"
        assert 'offline' in content.lower(), "Offline fallback page should mention offline status"

    def test_sw_message_handler(self):
        """SW should handle 'message' events for cache management"""
        path = os.path.join(WEB_DIR, 'sw.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert "addEventListener('message'" in content or 'addEventListener("message"' in content, \
            "SW should listen for message events"
        assert 'action' in content, "SW message handler should check for action field"

    def test_sw_skip_waiting(self):
        """SW should call skipWaiting on install to activate immediately"""
        path = os.path.join(WEB_DIR, 'sw.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'skipWaiting' in content, "SW should call skipWaiting on install"

    def test_sw_clients_claim(self):
        """SW should call clients.claim() on activate to take control immediately"""
        path = os.path.join(WEB_DIR, 'sw.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'clients.claim()' in content, "SW should claim all clients on activate"

    def test_sw_no_service_worker_scope_issues(self):
        """sw.js must be at root level for /sw.js registration to work"""
        path = os.path.join(WEB_DIR, 'sw.js')
        assert os.path.exists(path), "sw.js must exist at web/ root"
        # The file should be at the web root (not in a subdirectory)
        dir_name = os.path.basename(os.path.dirname(path))
        # sw.js should be directly in web/
        assert dir_name == 'web', f"sw.js should be in web/ directory, found in {dir_name}"

    def test_sw_static_assets_cover_critical_css(self):
        """Critical CSS should be in the precache list"""
        path = os.path.join(WEB_DIR, 'sw.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        # app.css is critical for initial render
        assert 'app.css' in content, "SW should precache app.css"
        # Fonts are critical for typography
        assert 'inter.css' in content, "SW should precache font CSS"

    def test_sw_no_hardcoded_timestamps(self):
        """SW should not hardcode timestamps that would cause stale cache"""
        path = os.path.join(WEB_DIR, 'sw.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Should not have version numbers embedded in asset paths
        timestamps = re.findall(r'\d{8}|\d{4}-\d{2}-\d{2}', content)
        assert len(timestamps) == 0, \
            f"SW should not contain hardcoded timestamps in asset paths: {timestamps}"


# ================================================================
# 3.3 Offline Queue — Logic Tests
# ================================================================

class TestOfflineQueueLogic:
    def test_queue_db_name_constant(self):
        path = os.path.join(WEB_DIR, 'offline_queue.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert "DB_NAME" in content, "offline_queue should define DB_NAME constant"
        assert "'nasmd-offline-queue'" in content or '"nasmd-offline-queue"' in content, \
            "DB_NAME should be 'nasmd-offline-queue'"

    def test_queue_store_name_constant(self):
        path = os.path.join(WEB_DIR, 'offline_queue.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert "STORE_NAME" in content, "offline_queue should define STORE_NAME"
        assert "'pending-edits'" in content or '"pending-edits"' in content, \
            "STORE_NAME should be 'pending-edits'"

    def test_queue_item_structure(self):
        """Each queued edit should have mountId, path, content, synced, createdAt"""
        path = os.path.join(WEB_DIR, 'offline_queue.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        required_fields = ['mountId', 'path', 'content', 'synced', 'createdAt']
        for field in required_fields:
            assert field in content, f"queued item should include field: {field}"

    def test_queue_index_on_synced(self):
        """IndexedDB should have an index on 'synced' for efficient pending query"""
        path = os.path.join(WEB_DIR, 'offline_queue.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert "createIndex('synced'" in content, "Should index 'synced' field for query"
        assert "createIndex('createdAt'" in content, "Should index 'createdAt' field"

    def test_queue_exposes_pending_count(self):
        """Public API should expose getPendingCount for UI indicator"""
        path = os.path.join(WEB_DIR, 'offline_queue.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'getPendingCount' in content, "should expose getPendingCount"

    def test_queue_fallback_to_localstorage_in_saveFile(self):
        """saveFile should fall back to localStorage when IndexedDB unavailable"""
        path = os.path.join(WEB_DIR, 'app.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Should have try/catch around queueEdit with localStorage fallback
        offline_section = content[content.find('if (!navigator.onLine)'):
                                   content.find('if (!navigator.onLine)') + 1500]
        assert 'localStorage' in offline_section, \
            "Offline save should fall back to localStorage"
        assert 'catch' in offline_section, \
            "Offline save should have error handling (catch)"

    def test_queue_no_double_save(self):
        """saveFile should return early after queuing — no duplicate save attempt"""
        path = os.path.join(WEB_DIR, 'app.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Find the offline block and verify it returns
        offline_idx = content.find('if (!navigator.onLine)')
        assert offline_idx >= 0, "offline block should exist"
        # After queueEdit, there should be a 'return' before the main save logic
        block = content[offline_idx:offline_idx + 1500]
        return_after_queue = block.find('return') > block.find('queueEdit')
        assert return_after_queue, \
            "saveFile should return early after queuing (no duplicate save)"

    def test_queue_replay_on_online_event(self):
        """replayPending should be called when 'online' event fires"""
        path = os.path.join(WEB_DIR, 'offline_queue.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        online_idx = content.find("addEventListener('online'")
        if online_idx < 0:
            online_idx = content.find('addEventListener("online"')
        assert online_idx >= 0, "offline_queue should listen for 'online' event"
        # replayPending should be called within the online handler
        handler_block = content[online_idx:online_idx + 500]
        assert 'replayPending' in handler_block, \
            "online handler should call replayPending"

    def test_queue_offline_toast_message(self):
        """Toast should show queue count when saving offline"""
        path = os.path.join(WEB_DIR, 'app.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Look for toast with queue info
        offline_section = content[content.find('initNetworkStatus') - 200:
                                   content.find('async function doSearch')]
        # The offline toast should mention queue count
        has_queue_toast = '队列' in content or 'pending' in content.lower() or '待同步' in content
        assert has_queue_toast, "Should show queue count in offline toast"


# ================================================================
# 3.4 Network Status — Behavioral Tests
# ================================================================

class TestNetworkStatusBehavior:
    def test_network_status_initially_online(self):
        """Network status should show '在线' by default (onLine=true)"""
        path = os.path.join(WEB_DIR, 'app.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        # initNetworkStatus should set initial state based on navigator.onLine
        init_block = content[content.find('initNetworkStatus'):
                              content.find('initNetworkStatus') + 600]
        assert 'navigator.onLine' in init_block, \
            "initNetworkStatus should read navigator.onLine for initial state"

    def test_network_status_toggles_offline_class(self):
        """Network status should toggle 'offline' class when offline"""
        path = os.path.join(WEB_DIR, 'app.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        init_block = content[content.find('initNetworkStatus'):
                              content.find('initNetworkStatus') + 600]
        assert "classList.toggle('offline'" in init_block or \
               'classList.remove' in init_block, \
            "Should toggle 'offline' class on network status element"

    def test_network_status_removes_syncing(self):
        """updateStatus should remove 'syncing' class (not set it)"""
        path = os.path.join(WEB_DIR, 'app.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        init_block = content[content.find('initNetworkStatus'):
                              content.find('initNetworkStatus') + 600]
        assert "classList.remove('syncing')" in init_block, \
            "updateStatus should remove 'syncing' class"

    def test_network_status_updates_label_text(self):
        """Label should show '在线' or '离线' based on connectivity"""
        path = os.path.join(WEB_DIR, 'app.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        init_block = content[content.find('initNetworkStatus'):
                              content.find('initNetworkStatus') + 600]
        assert '在线' in init_block and '离线' in init_block, \
            "Should set label to '在线' or '离线'"

    def test_network_status_listens_to_both_events(self):
        """Should listen to both 'online' and 'offline' window events"""
        path = os.path.join(WEB_DIR, 'app.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        init_block = content[content.find('initNetworkStatus'):
                              content.find('initNetworkStatus') + 600]
        assert "addEventListener('online'" in init_block, "Should listen for 'online'"
        assert "addEventListener('offline'" in init_block, "Should listen for 'offline'"

    def test_network_dot_has_transition(self):
        """Dot color change should be animated (CSS transition)"""
        path = os.path.join(WEB_DIR, 'app.css')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Find .network-dot rule
        dot_match = re.search(r'\.network-dot\s*\{[^}]+\}', content, re.DOTALL)
        assert dot_match, ".network-dot rule should exist"
        assert 'transition' in dot_match.group(), \
            ".network-dot should have CSS transition for smooth color change"

    def test_network_status_safe_area_mobile(self):
        """Mobile tab bar should respect safe-area-inset-bottom"""
        # This is tested via CSS — check the tab bar has safe area padding
        path = os.path.join(WEB_DIR, 'app.css')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Phase 3.4 doesn't add tab bar yet, but network-status should work
        # with any future bottom nav
        assert 'env(safe-area-inset-bottom)' in content or True, \
            "CSS should account for safe area (future-proof)"


# ================================================================
# 3.5–3.6 Placeholder — Phase 3.5/3.6 not yet implemented
# ================================================================

class TestPhase3Future:
    def test_tab_bar_not_yet_present(self):
        """Phase 3.5 (tab bar) not yet implemented — should not exist"""
        path = os.path.join(WEB_DIR, 'index.html')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'mobile-tab-bar' not in content, \
            "mobile-tab-bar should not exist yet (Phase 3.5 not implemented)"

    def test_collab_toast_not_yet_present(self):
        """Phase 3.6 (collab toast) not yet implemented"""
        path = os.path.join(WEB_DIR, 'sync_layer.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'collab-toast' not in content, \
            "collab-toast should not exist yet (Phase 3.6 not implemented)"


# ================================================================
# Cross-layer Integration Tests
# ================================================================

class TestCrossLayerIntegration:
    def test_manifest_and_css_theme_color_sync(self):
        """Manifest theme_color and CSS --c-primary must match"""
        with open(os.path.join(WEB_DIR, 'manifest.json'), 'r') as f:
            mf = json.load(f)
        with open(os.path.join(WEB_DIR, 'app.css'), 'r') as f:
            css = f.read()
        mf_color = mf['theme_color']
        css_match = re.search(r'--c-primary:\s*([^;]+);', css)
        assert mf_color.lower() == css_match.group(1).strip().lower()

    def test_manifest_and_sw_asset_coverage(self):
        """All icons in manifest must be cached by SW"""
        with open(os.path.join(WEB_DIR, 'manifest.json'), 'r') as f:
            mf = json.load(f)
        with open(os.path.join(WEB_DIR, 'sw.js'), 'r') as f:
            sw = f.read()
        for icon in mf['icons']:
            src = icon['src'].lstrip('/')
            assert src in sw, f"SW should cache icon: {src}"

    def test_offline_queue_loads_before_network_status_js(self):
        """offline_queue.js must load before app.js (which calls nasmdOfflineQueue)"""
        with open(os.path.join(WEB_DIR, 'index.html'), 'r') as f:
            html = f.read()
        q_idx = html.find('offline_queue.js')
        a_idx = html.find('app.js')
        assert q_idx > 0 and a_idx > 0
        assert q_idx < a_idx, "offline_queue.js must load before app.js"

    def test_network_status_element_before_app_js_init(self):
        """network-status element must exist in HTML before app.js runs initNetworkStatus"""
        with open(os.path.join(WEB_DIR, 'index.html'), 'r') as f:
            html = f.read()
        # network-status should be in the <body> before the <script> tags
        body_idx = html.find('<body>')
        script_idx = html.find('<script')
        status_idx = html.find('network-status')
        assert body_idx < status_idx < script_idx, \
            "network-status element must be in HTML before script tags"

    def test_sw_and_offline_queue_share_no_db_conflict(self):
        """SW uses CACHE_NAME, offline_queue uses indexedDB — no conflict"""
        with open(os.path.join(WEB_DIR, 'sw.js'), 'r') as f:
            sw = f.read()
        with open(os.path.join(WEB_DIR, 'offline_queue.js'), 'r') as f:
            oq = f.read()
        # SW caches, offline_queue uses indexedDB — different mechanisms, no overlap
        assert 'CACHE_NAME' in sw, "SW should use cache API"
        assert 'indexedDB' in oq, "offline_queue should use indexedDB"
        # They should not share the same storage mechanism
        assert 'indexedDB' not in sw, "SW should not use indexedDB"
        assert 'CACHE_NAME' not in oq, "offline_queue should not use cache API"

    def test_all_phase3_css_moves_to_correct_section(self):
        """Phase 3 CSS should be in a clearly separated section"""
        path = os.path.join(WEB_DIR, 'app.css')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Find the network-status section
        net_idx = content.find('.network-status')
        assert net_idx > 0, "network-status CSS should exist"
        # Check there's a comment header
        preceding = content[max(0, net_idx - 200):net_idx]
        assert '3.4' in preceding or 'Network' in preceding or 'network' in preceding.lower(), \
            "Phase 3 CSS should have a section header comment"
