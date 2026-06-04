/**
 * editor.js - Vditor 编辑器封装
 */

let _vditor = null;
let _currentMountId = null;
let _currentRelPath = null;
let _originalContent = '';
let _editorMode = 'ir';

// State saved before mode switch, restored after reinit
let _pendingRestore = null;
// { headingText, scrollPercent, cursorViewportOffset, svCursorPos }
//   headingText: text of nearest heading above cursor (for cross-mode positioning)
//   scrollPercent: scrollTop / maxScroll (fallback)
//   cursorViewportOffset: cursor's pixel distance from viewport top
//   svCursorPos: character offset for SV mode

window._getVditor = () => _vditor;

// Get the scrollable element for the current editor mode
function _getScrollEl(vd, mode) {
  if (!vd) return null;
  if (mode === 'sv') return vd.sv.element;
  if (mode === 'ir') return vd.ir.element;
  if (mode === 'wysiwyg') return vd.wysiwyg.element;
  return null;
}

// Find the nearest heading element at or above the cursor in the editor
function _findHeadingAboveCursor(editorEl, cursorNode) {
  if (!editorEl || !cursorNode) return null;
  // Get all headings in the editor
  const headings = editorEl.querySelectorAll('h1, h2, h3, h4, h5, h6');
  if (headings.length === 0) return null;

  // Find the last heading that is before or contains the cursor
  let best = null;
  for (const h of headings) {
    const cmp = cursorNode.compareDocumentPosition(h);
    // h is before cursor (DOCUMENT_POSITION_PRECEDING = 2), or cursor is inside h
    if (cmp & Node.DOCUMENT_POSITION_PRECEDING || h.contains(cursorNode)) {
      best = h;
    } else {
      break; // headings are in document order, no need to check further
    }
  }
  return best;
}

window._reinitEditor = (mode) => {
  if (!_vditor) return;
  const content = _vditor.getValue();
  const oldMode = _vditor.getCurrentMode();

  let restore = { headingText: null, scrollPercent: 0, cursorViewportOffset: 0, svCursorPos: 0 };

  // 1. Save scroll percentage as fallback
  const scrollEl = _getScrollEl(_vditor.vditor, oldMode);
  if (scrollEl) {
    const maxScroll = scrollEl.scrollHeight - scrollEl.clientHeight;
    if (maxScroll > 0) restore.scrollPercent = scrollEl.scrollTop / maxScroll;
  }

  try {
    _vditor.focus();
    if (oldMode === 'sv') {
      // SV mode: save character offset
      const ta = _vditor.vditor.sv.element;
      restore.svCursorPos = ta.selectionStart;
      // Find heading text from markdown source
      const text = ta.value;
      const before = text.substring(0, ta.selectionStart);
      const lines = before.split('\n');
      for (let i = lines.length - 1; i >= 0; i--) {
        const m = lines[i].match(/^#{1,6}\s+(.+)/);
        if (m) { restore.headingText = m[1].trim(); break; }
      }
    } else {
      // IR / WYSIWYG mode
      const sel = window.getSelection();
      if (sel.rangeCount > 0) {
        const range = sel.getRangeAt(0);
        const cursorNode = range.startContainer;

        // Save cursor viewport offset
        const cursorRect = range.getBoundingClientRect();
        if (scrollEl) {
          const scrollRect = scrollEl.getBoundingClientRect();
          restore.cursorViewportOffset = Math.max(0, cursorRect.top - scrollRect.top);
        }

        // Find nearest heading above cursor
        const editorEl = scrollEl;
        const heading = _findHeadingAboveCursor(editorEl, cursorNode);
        if (heading) {
          // Get heading text without Vditor markers (use innerText for visible text)
          restore.headingText = (heading.innerText || heading.textContent).trim();
        }
      }
    }
  } catch (_) {}

  teardownSVSync();
  teardownOutlineHighlight();
  _vditor.destroy();
  _pendingRestore = restore;
  initEditor(content, mode);
};

function initEditor(content, mode, readonly) {
  _editorMode = mode || 'ir';
  _originalContent = content || '';
  const vditorEl = document.getElementById('vditor');
  vditorEl.innerHTML = '';

  _vditor = new Vditor('vditor', {
    mode: _editorMode,
    value: _originalContent,
    height: '100%',
    width: '100%',
    placeholder: '开始写作...',
    theme: 'classic',
    icon: 'ant',
    cdn: '/lib/vditor-cdn',
    lang: 'zh_CN',
    toolbar: [
      'outline', 'emoji', 'headings', 'bold', 'italic', 'strike', 'link',
      '|', 'list', 'ordered-list', 'check',
      '|', 'quote', 'line', 'code', 'inline-code',
      '|', 'table',
      '|', 'undo', 'redo',
      '|', 'fullscreen', 'record',
      '|', { name: 'more', toolbar: ['edit-mode', 'preview', 'info', 'help'] },
    ],
    preview: {
      mode: 'both',
      markdown: { toc: true, autoSpace: true, fixTermTypo: true },
      hljs: { enable: true, style: 'github', lineNumber: false },
      theme: { current: 'light', path: '/lib/vditor-cdn/dist/css/content-theme' },
    },
    hint: {
      extend: [
        {
          key: '[',
          hint(_value) {
            // Triggered after typing [[ — search for pages
            return new Promise((resolve) => {
              // Get current line text to find the [[ prefix
              const mode = _vditor.getCurrentMode();
              let searchQuery = '';
              if (mode === 'sv') {
                const ta = _vditor.vditor.sv.element;
                const pos = ta.selectionStart;
                const text = ta.value.substring(0, pos);
                const match = text.match(/\[\[([^\]]*?)$/);
                if (match) searchQuery = match[1];
              } else {
                const sel = window.getSelection();
                if (sel.rangeCount > 0) {
                  const range = sel.getRangeAt(0);
                  const node = range.startContainer;
                  if (node.nodeType === Node.TEXT_NODE) {
                    const text = node.textContent.substring(0, range.startOffset);
                    const match = text.match(/\[\[([^\]]*?)$/);
                    if (match) searchQuery = match[1];
                  }
                }
              }
              if (!searchQuery && searchQuery !== '') {
                resolve([]);
                return;
              }
              API.searchPages(searchQuery).then(results => {
                if (!results || results.length === 0) {
                  resolve([]);
                  return;
                }
                resolve(results.map(r => ({
                  value: `[[${r.title || r.path}]]`,
                  html: `<span style="color:var(--text-primary)">${r.title || r.path}</span> <span style="color:var(--text-secondary);font-size:0.85em">${r.path || ''}</span>`,
                })));
              }).catch(() => resolve([]));
            });
          },
        },
      ],
    },
    cache: { enable: false },
    upload: { url: '', linkToImgUrl: '' },
    after: () => {
      // Hide Vditor's preview toolbar (Desktop/Tablet/Mobile buttons)
      const style = document.createElement('style');
      style.textContent = '.vditor-preview__action { display: none !important; }';
      vditorEl.appendChild(style);
      if (_editorMode === 'sv') setupSVSync();
      setupOutlineHighlight();

      const needsRestore = _pendingRestore !== null;
      if (needsRestore) {
        const doRestore = () => {
          if (!_vditor) return;
          const mode = _vditor.getCurrentMode();
          const r = _pendingRestore;
          const scrollEl = _getScrollEl(_vditor.vditor, mode);

          if (mode === 'sv' && r.svCursorPos > 0) {
            // SV mode: restore by character offset
            const ta = _vditor.vditor.sv.element;
            if (ta) {
              ta.focus({ preventScroll: true });
              ta.setSelectionRange(r.svCursorPos, r.svCursorPos);
            }
            // Restore scroll by percentage
            if (scrollEl && r.scrollPercent > 0) {
              const maxScroll = scrollEl.scrollHeight - scrollEl.clientHeight;
              if (maxScroll > 0) scrollEl.scrollTop = r.scrollPercent * maxScroll;
            }
          } else if (r.headingText) {
            // IR / WYSIWYG: find heading by text, position near it
            const editorEl = scrollEl;
            if (editorEl) {
              const headings = editorEl.querySelectorAll('h1, h2, h3, h4, h5, h6');
              let targetHeading = null;
              for (const h of headings) {
                const hText = (h.innerText || h.textContent).trim();
                if (hText === r.headingText) {
                  targetHeading = h;
                  break;
                }
              }
              if (targetHeading) {
                // Place cursor at start of heading
                editorEl.focus({ preventScroll: true });
                const sel = window.getSelection();
                const range = document.createRange();
                range.setStart(targetHeading, 0);
                range.collapse(true);
                sel.removeAllRanges();
                sel.addRange(range);

                // Scroll so heading appears at the same viewport offset as before
                if (scrollEl) {
                  const headingRect = targetHeading.getBoundingClientRect();
                  const scrollRect = scrollEl.getBoundingClientRect();
                  const currentOffset = headingRect.top - scrollRect.top;
                  const diff = currentOffset - r.cursorViewportOffset;
                  if (Math.abs(diff) > 1) {
                    scrollEl.scrollTop += diff;
                  }
                }
              } else {
                // Heading not found, fall back to scroll percentage
                if (scrollEl && r.scrollPercent > 0) {
                  const maxScroll = scrollEl.scrollHeight - scrollEl.clientHeight;
                  if (maxScroll > 0) scrollEl.scrollTop = r.scrollPercent * maxScroll;
                }
              }
            }
          } else if (scrollEl && r.scrollPercent > 0) {
            // No heading, fall back to scroll percentage
            const maxScroll = scrollEl.scrollHeight - scrollEl.clientHeight;
            if (maxScroll > 0) scrollEl.scrollTop = r.scrollPercent * maxScroll;
          }
        };

        // Multiple attempts with increasing delays for Vditor's async rendering
        setTimeout(doRestore, 100);
        setTimeout(doRestore, 400);

        // Cleanup
        setTimeout(() => { _pendingRestore = null; }, 500);
      } else {
        setTimeout(() => { const el = getActiveEditorEl(); if (el) el.focus(); }, 50);
      }
      if (readonly) {
        const tb = vditorEl.querySelector('.vditor-toolbar');
        if (tb) tb.style.display = 'none';
        const ed = vditorEl.querySelector('.vditor-ir .vditor-reset, .vditor-sv .vditor-reset, .vditor-wysiwyg .vditor-reset');
        if (ed) { ed.setAttribute('contenteditable', 'false'); ed.style.userSelect = 'text'; }
      }
      window._vditor = _vditor;
    },
  });
}

function getActiveEditorEl() {
  if (!_vditor) return null;
  const m = _vditor.getCurrentMode();
  if (m === 'sv') return _vditor.vditor.sv.element;
  if (m === 'ir') return _vditor.vditor.ir.element;
  if (m === 'wysiwyg') return _vditor.vditor.wysiwyg.element;
  return null;
}

// ─── SV mode: scroll sync ────────────────────────────────────────────────
//
// Vditor has built-in editor→preview scroll sync for SV mode.
// We only need to add preview→editor sync when the user scrolls the preview.
// Using wheel event (not rAF polling) avoids feedback loops with Vditor's
// internal scroll handler.

let _svWheelHandler = null;
let _svCursorHandler = null;

function setupSVSync() {
  teardownSVSync();
  const svEl = _vditor.vditor.sv.element;
  const pvEl = _vditor.vditor.preview.element;

  // Sync preview→editor on wheel scroll
  _svWheelHandler = (e) => {
    // Let the browser handle the wheel event first, then sync
    requestAnimationFrame(() => {
      const pTop = pvEl.scrollTop;
      const eMax = svEl.scrollHeight - svEl.clientHeight;
      const pMax = pvEl.scrollHeight - pvEl.clientHeight;
      if (eMax > 0 && pMax > 0) svEl.scrollTop = pTop * eMax / pMax;
    });
  };
  pvEl.addEventListener('wheel', _svWheelHandler, { passive: true });

  // Cursor tracking: scroll preview to cursor line
  _svCursorHandler = () => {
    const ta = svEl;
    if (!ta) return;
    const pos = ta.selectionStart;
    const before = ta.value.substring(0, pos);
    const line = before.split('\n').length - 1;
    const total = ta.value.split('\n').length;
    if (total <= 1) return;
    const maxP = pvEl.scrollHeight - pvEl.clientHeight;
    pvEl.scrollTop = (line / (total - 1)) * maxP;
  };
  document.addEventListener('selectionchange', _svCursorHandler);
  setTimeout(() => _svCursorHandler(), 100);
}

function teardownSVSync() {
  if (_vditor) {
    const pvEl = _vditor.vditor?.preview?.element;
    if (pvEl && _svWheelHandler) pvEl.removeEventListener('wheel', _svWheelHandler);
  }
  _svWheelHandler = null;
  if (_svCursorHandler) { document.removeEventListener('selectionchange', _svCursorHandler); _svCursorHandler = null; }
}

// ─── Outline highlight ──────────────────────────────────────────────────

let _outlineHighlightHandler = null;
let _outlineScrollHandler = null;
let _outlineObserver = null;
let _outlineClickHandler = null;
let _outlineUpdateRAF = null; // throttle rapid updates

function _updateOutlineHighlight() {
  if (!_vditor) return;

  // Throttle: coalesce rapid calls into single rAF frame
  if (_outlineUpdateRAF) return;
  _outlineUpdateRAF = requestAnimationFrame(() => {
    _outlineUpdateRAF = null;
    _doUpdateOutlineHighlight();
  });
}

function _doUpdateOutlineHighlight() {
  if (!_vditor) return;
  const vditorEl = document.getElementById('vditor');
  const outlineEl = vditorEl?.querySelector('.vditor-outline');
  if (!outlineEl) return;
  try {
    const outlineStyle = getComputedStyle(outlineEl);
    if (outlineStyle.display === 'none') return;
  } catch (_) { return; }

  const mode = _vditor.getCurrentMode();
  const scrollEl = _getScrollEl(_vditor.vditor, mode);
  if (!scrollEl) return;

  let cursorHeadingIndex = -1;
  try {
    if (mode === 'sv') {
      const ta = _vditor.vditor.sv.element;
      const textBefore = ta.value.substring(0, ta.selectionStart);
      cursorHeadingIndex = (textBefore.match(/^#{1,6}\s+/gm) || []).length - 1;
    } else {
      const sel = window.getSelection();
      if (sel.rangeCount > 0) {
        const cursorNode = sel.getRangeAt(0).startContainer;
        const headings = scrollEl.querySelectorAll('h1, h2, h3, h4, h5, h6');
        for (let i = 0; i < headings.length; i++) {
          if (headings[i].contains(cursorNode)) { cursorHeadingIndex = i; break; }
          const cmp = cursorNode.compareDocumentPosition(headings[i]);
          if (cmp & Node.DOCUMENT_POSITION_PRECEDING) {
            cursorHeadingIndex = i;
          } else {
            break;
          }
        }
      }
    }
  } catch (_) {}

  try {
    const items = outlineEl.querySelectorAll('li > span');
    items.forEach((item, idx) => {
      if (idx === cursorHeadingIndex) {
        item.classList.add('outline-active');
      } else {
        item.classList.remove('outline-active');
      }
    });
  } catch (_) {}
}

function setupOutlineHighlight() {
  teardownOutlineHighlight();
  _outlineHighlightHandler = () => _updateOutlineHighlight();
  document.addEventListener('selectionchange', _outlineHighlightHandler);
  const scrollEl = _getScrollEl(_vditor?.vditor, _vditor?.getCurrentMode());
  if (scrollEl) {
    _outlineScrollHandler = () => _updateOutlineHighlight();
    scrollEl.addEventListener('scroll', _outlineScrollHandler, { passive: true });
  }
  const vditorEl = document.getElementById('vditor');
  if (vditorEl) {
    _outlineObserver = new MutationObserver((mutations) => {
      for (const m of mutations) {
        if (m.target.classList && m.target.classList.contains('vditor-outline')) {
          _updateOutlineHighlight();
          break;
        }
      }
    });
    _outlineObserver.observe(vditorEl, { childList: true, attributes: true, attributeFilter: ['style', 'class'] });
    _outlineClickHandler = (e) => {
      if (!e.target.closest('.vditor-outline')) return;
      setTimeout(() => _updateOutlineHighlight(), 200);
    };
    vditorEl.addEventListener('click', _outlineClickHandler);
  }
}

function teardownOutlineHighlight() {
  if (_outlineUpdateRAF) { cancelAnimationFrame(_outlineUpdateRAF); _outlineUpdateRAF = null; }
  if (_outlineHighlightHandler) {
    document.removeEventListener('selectionchange', _outlineHighlightHandler);
    _outlineHighlightHandler = null;
  }
  if (_outlineScrollHandler) {
    if (_vditor) {
      const scrollEl = _getScrollEl(_vditor.vditor, _vditor.getCurrentMode());
      if (scrollEl) scrollEl.removeEventListener('scroll', _outlineScrollHandler);
    }
    _outlineScrollHandler = null;
  }
  if (_outlineObserver) {
    _outlineObserver.disconnect();
    _outlineObserver = null;
  }
  if (_outlineClickHandler) {
    const vditorEl = document.getElementById('vditor');
    if (vditorEl) vditorEl.removeEventListener('click', _outlineClickHandler);
    _outlineClickHandler = null;
  }
}

// ─── Cursor / content helpers ───────────────────────────────────────────

function restoreCursorPosition(offset, scrollToFocus = true) {
  if (!_vditor) return;
  const vd = _vditor.vditor;
  const mode = _vditor.getCurrentMode();
  if (mode === 'sv') {
    const ta = vd.sv.element;
    if (ta) { ta.focus({ preventScroll: !scrollToFocus }); ta.setSelectionRange(offset, offset); }
    return;
  }
  const el = mode === 'wysiwyg' ? vd.wysiwyg.element : vd.ir.element;
  if (!el) return;
  el.focus({ preventScroll: !scrollToFocus });
  let cc = 0;
  const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null, false);
  let n;
  while ((n = w.nextNode())) {
    const nl = n.textContent.length;
    if (cc + nl >= offset) {
      const r = document.createRange();
      const s = window.getSelection();
      r.setStart(n, Math.min(offset - cc, nl));
      r.collapse(true);
      s.removeAllRanges(); s.addRange(r);
      return;
    }
    cc += nl;
  }
  const r = document.createRange();
  const s = window.getSelection();
  r.selectNodeContents(el); r.collapse(false);
  s.removeAllRanges(); s.addRange(r);
}

function getEditorContent() { return _vditor ? _vditor.getValue() : ''; }
function isDirty() { return _vditor ? _vditor.getValue() !== _originalContent : false; }
function markSaved() { _originalContent = getEditorContent(); }
function getCurrentFileInfo() { return { mountId: _currentMountId, relPath: _currentRelPath }; }
function setFileInfo(mountId, relPath) { _currentMountId = mountId; _currentRelPath = relPath; }
