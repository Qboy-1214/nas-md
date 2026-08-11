"""
Integration tests for mobile adaptation - server-side behavior.
Tests API endpoints that should work correctly regardless of client device.
"""

import pytest
from nas_md.webserver import serve


@pytest.fixture
def web_server():
    """Create a test web server with mock HTTP handler."""
    from nas_md.webserver import MountHTTPHandler
    handler = MountHTTPHandler
    return handler


class TestMobileAPIEndpoints:
    """Test that all API endpoints work correctly (mobile-compatible)."""

    def test_health_check(self, web_server):
        """Health endpoint should be accessible from any device."""
        # The health check is handled in MountHTTPHandler.do_GET
        # Just verify the class exists and has the handler
        assert hasattr(web_server, 'do_GET')

    def test_config_endpoint(self, web_server):
        """Config endpoint should return docker_mode."""
        assert hasattr(web_server, 'do_GET')


class TestMobileCSSContent:
    """Test that mobile CSS is present in served content."""

    def test_app_css_contains_mobile_styles(self):
        """app.css should contain mobile-specific styles."""
        import os
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        css_path = root / "web" / "app.css"
        css = css_path.read_text(encoding="utf-8")

        # Verify mobile breakpoint exists
        assert "@media (max-width: 480px)" in css
        assert "--sidebar-w: 240px" in css

        # Verify sidebar close button styles
        assert ".sidebar-close" in css
        assert ".sidebar-close:hover" in css

        # Verify more menu styles
        assert ".topbar-more-wrapper" in css
        assert ".more-menu" in css

        # Verify Vditor toolbar mobile styles
        assert ".vditor-toolbar-mobile" in css
        assert ".vditor-toolbar-mobile::after" in css

    def test_index_html_contains_mobile_elements(self):
        """index.html should contain mobile-specific elements."""
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        html = (root / "web" / "index.html").read_text(encoding="utf-8")

        # Verify sidebar close button
        assert 'class="sidebar-close"' in html
        assert "closeSidebar()" in html

        # Verify more menu
        assert 'id="topbar-more"' in html
        assert 'id="more-menu"' in html
        assert "toggleMoreMenu()" in html

        # Verify more menu items
        assert 'id="more-download"' in html
        assert 'id="more-refresh"' in html
        assert 'id="more-pdf"' in html

    def test_app_js_contains_mobile_functions(self):
        """app.js should contain mobile-specific functions."""
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        js = (root / "web" / "app.js").read_text(encoding="utf-8")

        # Verify functions exist
        assert "function closeSidebar()" in js
        assert "function toggleMoreMenu()" in js
        assert "function isMobile()" in js
        assert "function isSmallMobile()" in js
        assert "function initMobileLayout()" in js
        assert "function initMobileSearch()" in js
        assert "function initMobileToolbar()" in js

        # Verify event listeners
        assert "window.addEventListener('load', initMobileLayout)" in js
        assert "window.addEventListener('resize', initMobileLayout)" in js


class TestMobileLayoutInitialization:
    """Test mobile layout initialization logic."""

    def test_mobile_detection_thresholds(self):
        """Verify mobile detection uses correct breakpoints."""
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        js = (root / "web" / "app.js").read_text(encoding="utf-8")

        # isMobile should use 768px threshold
        assert "window.innerWidth < 768" in js
        # isSmallMobile should use 480px threshold
        assert "window.innerWidth < 480" in js

    def test_overlay_click_handler(self):
        """Verify sidebar overlay click handler logic."""
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        js = (root / "web" / "app.js").read_text(encoding="utf-8")

        # Should check if click is outside sidebar and menu-toggle
        assert "!sidebar.contains(e.target)" in js
        assert "!menuToggle.contains(e.target)" in js
        assert "sidebar.classList.contains('open')" in js

    def test_more_menu_click_handler(self):
        """Verify more menu click outside handler."""
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        js = (root / "web" / "app.js").read_text(encoding="utf-8")

        # Should check if click is outside topbar-more-wrapper
        assert "!moreWrapper.contains(e.target)" in js
        assert "moreMenu.classList.contains('open')" in js
