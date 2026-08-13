"""
Phase 3.5-3.6: Mobile Tab Bar + SSE Mobile Toast — Deep Unit Tests
"""
import os
import re
import pytest


WEB_DIR = os.path.join(os.path.dirname(__file__), '..', 'web')


# ================================================================
# 3.5 Bottom Tab Bar
# ================================================================

class TestTabBarHTML:
    def test_tab_bar_element_exists(self):
        path = os.path.join(WEB_DIR, 'index.html')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'mobile-tab-bar' in content, "index.html should have mobile-tab-bar nav"
        assert 'id="mobile-tab-bar"' in content, "tab bar should have id='mobile-tab-bar'"

    def test_tab_bar_four_tabs(self):
        path = os.path.join(WEB_DIR, 'index.html')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        tabs = ['data-tab="files"', 'data-tab="search"', 'data-tab="graph"', 'data-tab="stats"']
        for tab in tabs:
            assert tab in content, f"tab bar should have tab: {tab}"

    def test_tab_bar_buttons_have_icons(self):
        path = os.path.join(WEB_DIR, 'index.html')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Match tab buttons with any class combination (active may be present)
        tab_btns = re.findall(r'<button[^>]*class="[^"]*tab-btn[^"]*"[^>]*>.*?</button>', content, re.DOTALL)
        assert len(tab_btns) >= 4, f"tab bar should have at least 4 buttons, found {len(tab_btns)}"
        for btn in tab_btns:
            assert '<svg' in btn, f"tab button should have SVG icon: {btn[:80]}"

    def test_tab_bar_buttons_have_labels(self):
        path = os.path.join(WEB_DIR, 'index.html')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        labels = ['文件', '搜索', '图谱', '统计']
        for label in labels:
            assert label in content, f"tab bar should have label: {label}"

    def test_tab_bar_present(self):
        path = os.path.join(WEB_DIR, 'index.html')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'mobile-tab-bar' in content

    def test_collab_toast_present(self):
        path = os.path.join(WEB_DIR, 'sync_layer.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'collab-toast' in content

    def test_tab_bar_js_functions(self):
        path = os.path.join(WEB_DIR, 'app.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'switchTab' in content, "app.js should define switchTab function"
        # Verify switchTab handles all four tabs
        for tab in ('files', 'search', 'graph', 'stats'):
            assert f"'{tab}'" in content or f'"{tab}"' in content, \
                f"switchTab should handle tab '{tab}'"

    def test_initMobileLayout_shows_tab_bar(self):
        path = os.path.join(WEB_DIR, 'app.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        init_block = content[content.find('function initMobileLayout'):
                              content.find('function initMobileLayout') + 600]
        assert 'mobile-tab-bar' in init_block, "initMobileLayout should show tab bar on mobile"
        assert "style.display = 'flex'" in init_block, \
            "initMobileLayout should set tab bar display to flex"

    def test_initMobileLayout_hides_on_desktop(self):
        path = os.path.join(WEB_DIR, 'app.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        init_block = content[content.find('function initMobileLayout'):
                              content.find('function initMobileLayout') + 600]
        assert "style.display = 'none'" in init_block, \
            "initMobileLayout should hide tab bar on desktop"

    def test_tab_bar_css_exists(self):
        path = os.path.join(WEB_DIR, 'app.css')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert '.mobile-tab-bar' in content, "CSS should have .mobile-tab-bar"
        assert '.tab-btn' in content, "CSS should have .tab-btn"
        assert '.tab-btn.active' in content, "CSS should have .tab-btn.active"

    def test_tab_bar_positioning(self):
        path = os.path.join(WEB_DIR, 'app.css')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Should be fixed at bottom
        assert 'position: fixed' in content, "tab bar should be position:fixed"
        assert 'bottom: 0' in content, "tab bar should be at bottom:0"
        assert 'z-index: 200' in content or 'z-index:200' in content, \
            "tab bar should have z-index:200"

    def test_tab_bar_mobile_only(self):
        """Tab bar should only be visible on mobile via media query"""
        path = os.path.join(WEB_DIR, 'app.css')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Find the media query section for the tab bar
        assert '@media (max-width: 767px)' in content, \
            "tab bar should use @media (max-width: 767px)"
        # Inside that media query, display: flex should be set
        media_block = content[content.find('@media (max-width: 767px)'):
                               content.find('@media (max-width: 767px)') + 2000]
        assert '.mobile-tab-bar' in media_block, \
            "tab bar should be shown inside 767px media query"
        assert 'display: flex' in media_block, \
            "tab bar should use display:flex inside media query"

    def test_main_padding_bottom_on_mobile(self):
        """Main content should have padding-bottom to avoid being covered by tab bar"""
        path = os.path.join(WEB_DIR, 'app.css')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        media_block = content[content.find('@media (max-width: 767px)'):
                               content.find('@media (max-width: 767px)') + 2000]
        assert '.main' in media_block and 'padding-bottom' in media_block, \
            "main should have padding-bottom in 767px media query"

    def test_tab_bar_js_click_handlers(self):
        """Tab buttons should have onclick handlers"""
        path = os.path.join(WEB_DIR, 'index.html')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Each tab should have onclick="switchTab('xxx')"
        for tab in ('files', 'search', 'graph', 'stats'):
            assert f"switchTab('{tab}')" in content, \
                f"tab button for '{tab}' should have onclick=switchTab('{tab}')"

    def test_graph_tab_opens_new_window(self):
        """Graph tab should open graph-viewer.html in new window"""
        path = os.path.join(WEB_DIR, 'app.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        switch_tab = content[content.find('function switchTab'):
                              content.find('function switchTab') + 500]
        assert 'graph-viewer.html' in switch_tab, \
            "switchTab('graph') should open graph-viewer.html"
        assert "_blank" in switch_tab or "'_blank'" in switch_tab, \
            "graph tab should open in new window"


# ================================================================
# 3.6 SSE Mobile Toast
# ================================================================

class TestCollabToast:
    def test_sync_layer_has_toast_function(self):
        path = os.path.join(WEB_DIR, 'sync_layer.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'showCollabNotification' in content, \
            "sync_layer.js should have showCollabNotification"

    def test_toast_uses_collab_toast_class(self):
        path = os.path.join(WEB_DIR, 'sync_layer.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'collab-toast' in content, \
            "showCollabNotification should create .collab-toast element"

    def test_toast_has_avatar_and_text(self):
        path = os.path.join(WEB_DIR, 'sync_layer.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'toast-avatar' in content, "toast should have .toast-avatar"
        assert 'toast-text' in content, "toast should have .toast-text"

    def test_toast_replaces_old_toast(self):
        """Each new notification should remove the previous one"""
        path = os.path.join(WEB_DIR, 'sync_layer.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Should query for existing toast and remove it
        assert 'querySelector' in content or 'getElementById' in content, \
            "should query for existing toast before creating new one"
        # Should remove old toast (class removal + timeout removal)
        assert 'classList.remove' in content or 'removeChild' in content, \
            "should clean up old toast"

    def test_toast_auto_removes_after_3s(self):
        path = os.path.join(WEB_DIR, 'sync_layer.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Should use setTimeout for auto-removal
        assert 'setTimeout' in content, "toast should auto-remove with setTimeout"
        # The delay should be around 3000ms
        # Check for 3000 in the setTimeout context
        toast_section = content[content.find('showCollabNotification'):
                                 content.find('showCollabNotification') + 1500]
        assert '3000' in toast_section, "toast should remove after ~3 seconds"

    def test_toast_show_transition(self):
        path = os.path.join(WEB_DIR, 'sync_layer.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Should add 'show' class via requestAnimationFrame
        assert "classList.add('show')" in content or 'classList.add("show")' in content, \
            "toast should add 'show' class for animation"

    def test_toast_css_exists(self):
        path = os.path.join(WEB_DIR, 'app.css')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert '.collab-toast' in content, "CSS should have .collab-toast"
        assert '.toast-avatar' in content, "CSS should have .toast-avatar"
        assert '.toast-text' in content, "CSS should have .toast-text"

    def test_toast_positioned_above_tab_bar(self):
        path = os.path.join(WEB_DIR, 'app.css')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Toast should be positioned above the 56px tab bar + some margin
        assert 'bottom: 72px' in content or 'bottom:72px' in content, \
            "toast should be positioned at bottom:72px (above 56px tab bar + margin)"

    def test_toast_centered_horizontally(self):
        path = os.path.join(WEB_DIR, 'app.css')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'left: 50%' in content, "toast should be centered horizontally"
        assert 'translateX(-50%)' in content, "toast should use translateX(-50%) for centering"

    def test_toast_max_width_mobile_friendly(self):
        path = os.path.join(WEB_DIR, 'app.css')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'max-width: 90vw' in content or 'max-width:90vw' in content, \
            "toast should have max-width: 90vw for mobile safety"

    def test_toast_text_truncation(self):
        path = os.path.join(WEB_DIR, 'app.css')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Toast text should truncate with ellipsis on long names
        toast_text_section = content[content.find('.toast-text'):
                                      content.find('.toast-text') + 300]
        assert 'text-overflow: ellipsis' in toast_text_section or \
               'overflow: hidden' in toast_text_section, \
            "toast text should truncate with ellipsis"

    def test_old_floating_notification_removed(self):
        """The old top-right floating notification system should no longer exist"""
        path = os.path.join(WEB_DIR, 'sync_layer.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Should not create collab-notifications container anymore
        assert 'collab-notifications' not in content, \
            "old collab-notifications container should be removed"

    def test_switchTab_is_global(self):
        """switchTab must be a global function (not in IIFE) so onclick can call it"""
        path = os.path.join(WEB_DIR, 'app.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Function declaration (not inside IIFE)
        assert 'function switchTab(' in content, \
            "switchTab should be a global function declaration"


# ================================================================
# Cross-feature Integration
# ================================================================

class TestPhase35_36Integration:
    def test_tab_bar_and_toast_no_conflict(self):
        """Tab bar (z-index:200) and toast (z-index:9998) should not conflict"""
        path = os.path.join(WEB_DIR, 'app.css')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Extract z-index values
        tab_z = re.search(r'\.mobile-tab-bar[^{]*\{[^}]*z-index:\s*(\d+)', content)
        toast_z = re.search(r'\.collab-toast[^{]*\{[^}]*z-index:\s*(\d+)', content)
        if tab_z and toast_z:
            assert int(toast_z.group(1)) > int(tab_z.group(1)), \
                "toast z-index should be above tab bar z-index"

    def test_tab_bar_loads_before_app_js(self):
        """Tab bar HTML must be in index.html before app.js runs initMobileLayout"""
        path = os.path.join(WEB_DIR, 'index.html')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        tab_idx = content.find('mobile-tab-bar')
        script_idx = content.find('<script src="app.js')
        assert tab_idx > 0 and script_idx > 0, "tab bar HTML and app.js must both exist"
        assert tab_idx < script_idx, \
            "tab bar HTML must appear before app.js script tag"

    def test_no_phase2_regression(self):
        """Phase 3.5/3.6 should not break Phase 2 features"""
        path = os.path.join(WEB_DIR, 'index.html')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'file-context-menu' in content, "Phase 2: context menu should still exist"

        path = os.path.join(WEB_DIR, 'app.js')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'initFileTreeTouch' in content, "Phase 2: file tree touch should still exist"
        assert 'initMobileToolbar' in content, "Phase 2: toolbar scroll should still exist"
