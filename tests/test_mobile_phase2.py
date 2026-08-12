"""
Integration tests for Phase 2 mobile interaction features.
Covers: file tree touch, context menu, search sticky, version history.
"""

import pytest
from pathlib import Path


class TestPhase2CSS:
    """Test Phase 2 CSS changes."""

    def test_app_css_contains_phase2_styles(self):
        """app.css should contain Phase 2 mobile styles."""
        root = Path(__file__).resolve().parent.parent
        css = (root / "web" / "app.css").read_text(encoding="utf-8")

        # File tree touch targets
        assert ".tree-chevron" in css
        assert "min-width: 44px" in css
        assert ".dir-label" in css
        assert ".dir-actions" in css

        # Context menu styles
        assert ".file-context-menu" in css
        assert "bottom: 0" in css
        assert "border-radius: var(--r-lg) var(--r-lg) 0 0" in css

        # Search styles
        assert ".search-sticky" in css
        assert ".search-result-item" in css

        # Version history mobile
        assert "#version-history-panel" in css
        assert ".diff-mobile" in css

    def test_app_css_has_mq480_context_menu(self):
        """Context menu styles should be in 480px breakpoint."""
        root = Path(__file__).resolve().parent.parent
        css = (root / "web" / "app.css").read_text(encoding="utf-8")
        # Find the 480px media query block
        assert "@media (max-width: 480px)" in css


class TestPhase2HTML:
    """Test Phase 2 HTML changes."""

    def test_context_menu_html_exists(self):
        """index.html should contain file context menu."""
        root = Path(__file__).resolve().parent.parent
        html = (root / "web" / "index.html").read_text(encoding="utf-8")

        assert 'id="file-context-menu"' in html
        assert "openFileContextAction" in html
        # Should have 4 action buttons
        assert html.count("openFileContextAction('") == 4

    def test_context_menu_buttons(self):
        """Context menu should have all 4 action buttons."""
        root = Path(__file__).resolve().parent.parent
        html = (root / "web" / "index.html").read_text(encoding="utf-8")

        assert "重命名" in html or "rename" in html.lower()
        assert "删除" in html or "delete" in html.lower()
        assert "分享" in html or "share" in html.lower()
        assert "下载" in html or "download" in html.lower()


class TestPhase2JavaScript:
    """Test Phase 2 JavaScript changes."""

    def test_file_tree_touch_functions(self):
        """app.js should contain file tree touch functions."""
        root = Path(__file__).resolve().parent.parent
        js = (root / "web" / "app.js").read_text(encoding="utf-8")

        assert "function initFileTreeTouch()" in js
        assert "showFileContextMenu" in js
        assert "hideFileContextMenu" in js
        assert "openFileContextAction" in js

    def test_swipe_gesture_logic(self):
        """Should have swipe detection logic."""
        root = Path(__file__).resolve().parent.parent
        js = (root / "web" / "app.js").read_text(encoding="utf-8")

        assert "swipeStartX" in js
        assert "swipeStartY" in js
        assert "swipeItem" in js
        assert "deltaX" in js
        assert "toggleDir" in js

    def test_long_press_logic(self):
        """Should have long press detection."""
        root = Path(__file__).resolve().parent.parent
        js = (root / "web" / "app.js").read_text(encoding="utf-8")

        assert "pressTimer" in js
        assert "longPressTriggered" in js
        assert "setTimeout" in js

    def test_search_sticky_logic(self):
        """Should have search sticky scroll logic."""
        root = Path(__file__).resolve().parent.parent
        js = (root / "web" / "app.js").read_text(encoding="utf-8")

        assert "initSearchSticky" in js
        assert "search-sticky" in js
        assert "scrollY > 100" in js

    def test_version_history_mobile(self):
        """version_history.js should have mobile adaptations."""
        root = Path(__file__).resolve().parent.parent
        js = (root / "web" / "version_history.js").read_text(encoding="utf-8")

        assert "renderDiffMobile" in js
        assert "isMobile" in js
        assert "window.innerWidth" in js


class TestPhase2VersionHistory:
    """Test version history mobile changes."""

    def test_render_diff_mobile_function(self):
        """Should have renderDiffMobile function."""
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        js = (root / "web" / "version_history.js").read_text(encoding="utf-8")

        assert "renderDiffMobile" in js
        assert "diff-mobile" in js


class TestPhase2Integration:
    """Integration tests for Phase 2 features."""

    def test_all_phase2_elements_in_dom(self):
        """All Phase 2 DOM elements should be referenced in HTML."""
        root = Path(__file__).resolve().parent.parent
        html = (root / "web" / "index.html").read_text(encoding="utf-8")
        js = (root / "web" / "app.js").read_text(encoding="utf-8")

        # Context menu HTML element
        assert 'id="file-context-menu"' in html
        # Context menu JS functions
        assert "showFileContextMenu" in js
        assert "hideFileContextMenu" in js
        assert "openFileContextAction" in js

    def test_no_conflicts_with_phase1(self):
        """Phase 2 should not break Phase 1 functionality."""
        root = Path(__file__).resolve().parent.parent
        js = (root / "web" / "app.js").read_text(encoding="utf-8")

        # Phase 1 functions should still exist
        assert "function closeSidebar()" in js
        assert "function toggleMoreMenu()" in js
        assert "function isMobile()" in js
        assert "function isSmallMobile()" in js

        # Phase 2 functions should also exist
        assert "function initFileTreeTouch()" in js
        assert "function showFileContextMenu" in js
        assert "function initSearchSticky" in js
