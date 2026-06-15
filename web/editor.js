/**
 * editor.js - Vditor 编辑器封装
 */

let _vditor = null;
let _currentMountId = null;
let _currentRelPath = null;
let _originalContent = '';
let _editorMode = 'ir';

/**
 * Generate a heading ID from text, matching common markdown anchor conventions.
 * e.g. "1.1 表格" → "11-表格", "Hello World" → "hello-world"
 * Rules: lowercase, spaces→hyphens, remove punctuation (keep CJK, letters, digits, hyphens)
 */
function _headingId(text) {
  return text
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '-')
    .replace(/[^\p{L}\p{N}-]/gu, '')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');
}

/**
 * Add id attributes to heading tags in HTML string (for preview pane).
 */
function _addHeadingIds(html) {
  return html.replace(/<(h[1-6])(\s[^>]*)?>([\s\S]*?)<\/\1>/gi, (match, tag, attrs, content) => {
    attrs = attrs || '';
    if (/id=/.test(attrs)) return match; // already has id
    const text = content.replace(/<[^>]*>/g, '').trim();
    if (!text) return match;
    const id = _headingId(text);
    return `<${tag}${attrs} id="${id}">${content}</${tag}>`;
  });
}

/**
 * Add id attributes to heading elements in all Vditor panes (IR, WYSIWYG, preview).
 */
function _addHeadingIdsToEditor(vditorEl) {
  const areas = vditorEl.querySelectorAll('.vditor-ir, .vditor-wysiwyg, .vditor-preview');
  areas.forEach((area) => {
    area.querySelectorAll('h1, h2, h3, h4, h5, h6').forEach((h) => {
      if (h.id) return;
      // In IR mode, heading markers (##) are in .vditor-ir__marker spans — exclude them
      let text = h.textContent || '';
      const markers = h.querySelectorAll('.vditor-ir__marker--heading, .vditor-ir__marker');
      if (markers.length > 0) {
        // Clone and remove markers to get clean text
        const clone = h.cloneNode(true);
        clone.querySelectorAll('.vditor-ir__marker--heading, .vditor-ir__marker').forEach((m) => {
          m.remove();
        });
        text = clone.textContent || '';
      }
      text = text.trim();
      if (text) h.id = _headingId(text);
    });
  });
}

/**
 * Handle a link click from any Vditor mode (IR, WYSIWYG, preview).
 * Extracts href from the element using multiple strategies.
 */
function _handleLinkClick(el) {
  let href = '';
  // Strategy 1: <a> element with href attribute (WYSIWYG / preview)
  if (el.tagName === 'A' || el.getAttribute('href')) {
    href = el.getAttribute('href') || '';
  }
  // Strategy 2: IR mode link marker — textContent is the URL
  if (!href && el.classList && el.classList.contains('vditor-ir__marker--link')) {
    href = (el.textContent || '').trim();
  }
  // Strategy 3: data-href attribute
  if (!href) {
    href = el.getAttribute('data-href') || '';
  }
  // Strategy 4: Walk up to find <a> or data-type="a" parent
  if (!href) {
    let parent = el.parentElement;
    while (parent) {
      if (parent.tagName === 'A') {
        href = parent.getAttribute('href') || '';
        break;
      }
      if (parent.getAttribute('data-type') === 'a') {
        // IR mode link container — find the link marker inside
        const linkMarker = parent.querySelector('.vditor-ir__marker--link');
        if (linkMarker) {
          href = (linkMarker.textContent || '').trim();
          break;
        }
      }
      const pHref = parent.getAttribute('href') || parent.getAttribute('data-href') || '';
      if (pHref) {
        href = pHref;
        break;
      }
      parent = parent.parentElement;
    }
  }

  if (href.startsWith('#')) {
    const targetId = href.slice(1);
    const vditorEl = document.getElementById('vditor');
    if (vditorEl) _scrollToAnchor(targetId, vditorEl);
  } else if (href) {
    window.open(href);
  }
}

/**
 * Scroll to an anchor target within the Vditor editor.
 * Tries multiple matching strategies: exact ID, normalized ID, heading text.
 */
function _scrollToAnchor(targetId, vditorEl) {
  const decodedId = decodeURIComponent(targetId);
  // Ensure heading IDs are up-to-date before searching
  _addHeadingIdsToEditor(vditorEl);
  // Normalize ID for comparison: lowercase, trim spaces/dashes
  const normalize = (s) =>
    s
      .toLowerCase()
      .replace(/^\s+|\s+$/g, '')
      .replace(/-+/g, '-')
      .replace(/^-|-$/g, '');
  const normTarget = normalize(decodedId);

  // Search by id attribute in editor areas (IR, WYSIWYG, preview)
  /* eslint-disable no-undef */
  let target =
    vditorEl.querySelector(`[id="${CSS.escape(decodedId)}"]`) ||
    vditorEl.querySelector(`[id="${CSS.escape(targetId)}"]`);
  /* eslint-enable no-undef */
  if (!target) {
    // Try matching by normalized id
    const allIds = vditorEl.querySelectorAll('[id]');
    for (const el of allIds) {
      if (normalize(el.id) === normTarget) {
        target = el;
        break;
      }
    }
  }
  if (!target) {
    // Fallback: try matching heading text content
    const headings = vditorEl.querySelectorAll('h1, h2, h3, h4, h5, h6');
    for (const h of headings) {
      const text = (h.innerText || h.textContent).trim();
      if (normalize(text) === normTarget || text === decodedId || text === targetId) {
        target = h;
        break;
      }
    }
  }
  if (target) {
    // Determine which scrollable container the target is in
    const scrollParent = target.closest('.vditor-ir, .vditor-wysiwyg, .vditor-preview, .vditor-sv');
    if (scrollParent) {
      const parentRect = scrollParent.getBoundingClientRect();
      const targetRect = target.getBoundingClientRect();
      scrollParent.scrollTop += targetRect.top - parentRect.top - parentRect.height / 3;
    } else {
      target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }
}

/**
 * Rewrite relative image src to API path so images in mounted dirs display correctly.
 * e.g. ![](photo.png) in /notes/readme.md → /api/mounts/{id}/file?path=/notes/photo.png
 */
function rewriteImageSrc(html) {
  if (!_currentMountId) return html;
  // Get the directory of the current file
  const dir = _currentRelPath
    ? _currentRelPath.substring(0, _currentRelPath.lastIndexOf('/') + 1)
    : '/';
  return html.replace(/(<img\s+[^>]*src=")([^"]+)("[^>]*>)/g, (match, prefix, src, suffix) => {
    // Skip absolute URLs, data URIs, and already-rewritten API paths
    if (
      src.startsWith('http://') ||
      src.startsWith('https://') ||
      src.startsWith('data:') ||
      src.startsWith('/api/')
    ) {
      return match;
    }
    // Resolve relative path against current file's directory
    let resolved;
    if (src.startsWith('/')) {
      resolved = src;
    } else {
      resolved = dir + src;
    }
    // Normalize: remove ./ and ../
    const parts = resolved.split('/');
    const normalized = [];
    for (const p of parts) {
      if (p === '..') {
        normalized.pop();
      } else if (p !== '.' && p !== '') {
        normalized.push(p);
      }
    }
    const apiPath = '/api/mounts/' + _currentMountId + '/file?path=/' + normalized.join('/');
    return prefix + apiPath + suffix;
  });
}

// Also rewrite images in the editor area (IR/WYSIWYG) after rendering
function rewriteEditorImages() {
  if (!_currentMountId || !_vditor) return;
  const dir = _currentRelPath
    ? _currentRelPath.substring(0, _currentRelPath.lastIndexOf('/') + 1)
    : '/';
  const vditorEl = document.getElementById('vditor');
  if (!vditorEl) return;
  // Target IR, WYSIWYG, and preview areas
  const areas = vditorEl.querySelectorAll('.vditor-ir, .vditor-wysiwyg, .vditor-preview');
  areas.forEach((area) => {
    area.querySelectorAll('img').forEach((img) => {
      const src = img.getAttribute('src') || '';
      if (
        src.startsWith('http://') ||
        src.startsWith('https://') ||
        src.startsWith('data:') ||
        src.startsWith('/api/')
      )
        return;
      let resolved;
      if (src.startsWith('/')) {
        resolved = src;
      } else {
        resolved = dir + src;
      }
      const parts = resolved.split('/');
      const normalized = [];
      for (const p of parts) {
        if (p === '..') normalized.pop();
        else if (p !== '.' && p !== '') normalized.push(p);
      }
      img.src = '/api/mounts/' + _currentMountId + '/file?path=/' + normalized.join('/');
    });
  });
}

// State saved before mode switch, restored after reinit
let _pendingRestore = null;
// { headingText, scrollPercent, cursorViewportOffset, svCursorPos }
//   headingText: text of nearest heading above cursor (for cross-mode positioning)
//   scrollPercent: scrollTop / maxScroll (fallback)
//   cursorViewportOffset: cursor's pixel distance from viewport top
//   svCursorPos: character offset for SV mode

window._getVditor = () => _vditor;

// Toggle outline panel visibility, persist to localStorage
window._toggleOutline = () => {
  if (!_vditor) return;
  // Find and click Vditor's built-in outline toolbar button
  const vditorEl = document.getElementById('vditor');
  const outlineBtn = vditorEl?.querySelector('.vditor-toolbar [data-type="outline"]');
  if (outlineBtn) {
    outlineBtn.click();
    return;
  }
  // Fallback: toggle outline element directly
  const outlineEl = vditorEl?.querySelector('.vditor-outline');
  if (!outlineEl) return;
  const isCurrentlyVisible = outlineEl.style.display !== 'none';
  const shouldShow = !isCurrentlyVisible;
  outlineEl.style.display = shouldShow ? '' : 'none';
  localStorage.setItem('nasmd_outline_visible', shouldShow ? '1' : '0');
};

// Restore outline visibility from localStorage after editor init
function _restoreOutlineVisibility() {
  const saved = localStorage.getItem('nasmd_outline_visible');
  if (saved === null) return; // no saved state, use Vditor default
  const vditorEl = document.getElementById('vditor');
  const outlineEl = vditorEl?.querySelector('.vditor-outline');
  if (!outlineEl) return;
  const shouldShow = saved === '1';
  outlineEl.style.display = shouldShow ? '' : 'none';
  // If showing outline, force Vditor to render it
  if (shouldShow && _vditor) {
    // Vditor only renders outline content on certain events;
    // trigger a render by dispatching a resize
    window.dispatchEvent(new Event('resize'));
  }
}

// Watch for outline panel toggle (via Vditor toolbar button) and persist state
let _outlineToggleObserver = null;
function _watchOutlineToggle() {
  if (_outlineToggleObserver) _outlineToggleObserver.disconnect();
  const vditorEl = document.getElementById('vditor');
  const outlineEl = vditorEl?.querySelector('.vditor-outline');
  if (!outlineEl) return;
  _outlineToggleObserver = new MutationObserver(() => {
    const isVisible = outlineEl.style.display !== 'none';
    localStorage.setItem('nasmd_outline_visible', isVisible ? '1' : '0');
  });
  _outlineToggleObserver.observe(outlineEl, {
    attributes: true,
    attributeFilter: ['style', 'class'],
  });
}

// Get the scrollable element for the current editor mode
// IR/WYSIWYG: .vditor-reset (overflow:auto) is the actual scroll container, not .vditor-ir
function _getScrollEl(vd, mode) {
  if (!vd) return null;
  if (mode === 'sv') return vd.sv.element;
  const base = mode === 'wysiwyg' ? vd.wysiwyg.element : vd.ir.element;
  if (!base) return null;
  // .vditor-reset has overflow:auto and is the real scrollable container
  const reset = base.querySelector('.vditor-reset');
  return reset || base;
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

window._findHeadingAboveCursor = _findHeadingAboveCursor;

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
        if (m) {
          restore.headingText = m[1].trim();
          break;
        }
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
  } catch (_err) {}

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
    theme: document.documentElement.classList.contains('dark') ? 'dark' : 'classic',
    icon: 'ant',
    cdn: '/lib/vditor-cdn',
    lang: 'zh_CN',
    toolbar: [
      'outline',
      'emoji',
      'headings',
      'bold',
      'italic',
      'strike',
      'link',
      '|',
      'list',
      'ordered-list',
      'check',
      '|',
      'quote',
      'line',
      'code',
      'inline-code',
      '|',
      'table',
      '|',
      'undo',
      'redo',
      '|',
      'fullscreen',
      'record',
      '|',
      { name: 'more', toolbar: ['edit-mode', 'preview', 'info', 'help'] },
    ],
    input: () => {
      if (typeof onEditorInput === 'function') onEditorInput();
    },
    link: {
      isOpen: false,
      click: (el) => {
        _handleLinkClick(el);
      },
    },
    preview: {
      mode: 'both',
      markdown: { toc: true, autoSpace: true, fixTermTypo: true },
      hljs: {
        enable: true,
        style: document.documentElement.classList.contains('dark') ? 'dracula' : 'github',
        lineNumber: false,
      },
      theme: {
        current: document.documentElement.classList.contains('dark') ? 'dark' : 'light',
        path: '/lib/vditor-cdn/dist/css/content-theme',
      },
      transform: (html) => _addHeadingIds(rewriteImageSrc(html)),
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
              API.searchPages(searchQuery)
                .then((results) => {
                  if (!results || results.length === 0) {
                    resolve([]);
                    return;
                  }
                  resolve(
                    results.map((r) => ({
                      value: `[[${r.title || r.path}]]`,
                      html: `<span style="color:var(--text-primary)">${r.title || r.path}</span> <span style="color:var(--text-secondary);font-size:0.85em">${r.path || ''}</span>`,
                    })),
                  );
                })
                .catch(() => resolve([]));
            });
          },
        },
      ],
    },
    cache: { enable: false },
    upload: { url: '', linkToImgUrl: '' },
    after: () => {
      // Sync window._originalContent with Vditor's normalized content
      // (Vditor may add trailing newline or normalize content)
      window._originalContent = _vditor.getValue();
      _originalContent = _vditor.getValue();
      // Hide Vditor's preview toolbar (Desktop/Tablet/Mobile buttons)
      const style = document.createElement('style');
      style.textContent = '.vditor-preview__action { display: none !important; }';
      vditorEl.appendChild(style);
      // Add heading IDs to editor panes for anchor navigation
      _addHeadingIdsToEditor(vditorEl);
      if (_editorMode === 'sv') setupSVSync();
      setupOutlineHighlight();
      _restoreOutlineVisibility();
      _watchOutlineToggle();

      // Add native title tooltips to all Vditor toolbar buttons
      // Vditor sets aria-label on buttons with vditor-tooltipped class
      // Use MutationObserver to handle buttons added/updated after init (e.g. dark mode switch)
      function addTitleTooltips(root) {
        root
          .querySelectorAll('.vditor-toolbar__item button, .vditor-toolbar__item [role="button"]')
          .forEach((btn) => {
            if (btn.getAttribute('title')) return;
            const ariaLabel = btn.getAttribute('aria-label');
            if (ariaLabel) {
              btn.setAttribute('title', ariaLabel);
            }
          });
      }
      addTitleTooltips(vditorEl);
      const toolbarEl = vditorEl.querySelector('.vditor-toolbar');
      if (toolbarEl) {
        new MutationObserver(() => addTitleTooltips(vditorEl)).observe(toolbarEl, {
          childList: true,
          subtree: true,
          attributes: true,
          attributeFilter: ['aria-label', 'class'],
        });
      }

      // Rewrite relative image paths in editor content
      rewriteEditorImages();
      _addHeadingIdsToEditor(vditorEl);
      const contentEl =
        vditorEl.querySelector('.vditor-ir') || vditorEl.querySelector('.vditor-wysiwyg');
      if (contentEl) {
        new MutationObserver(() => {
          rewriteEditorImages();
          _addHeadingIdsToEditor(vditorEl);
        }).observe(contentEl, {
          childList: true,
          subtree: true,
        });
      }
      const previewEl = vditorEl.querySelector('.vditor-preview');
      if (previewEl) {
        new MutationObserver(() => {
          rewriteEditorImages();
          _addHeadingIdsToEditor(vditorEl);
        }).observe(previewEl, {
          childList: true,
          subtree: true,
        });
        // Handle link clicks in preview pane (Vditor doesn't use link.click for preview)
        previewEl.addEventListener('click', (e) => {
          const a = e.target.closest('a');
          if (!a) return;
          e.preventDefault();
          e.stopPropagation();
          const href = a.getAttribute('href') || '';
          if (href.startsWith('#')) {
            _scrollToAnchor(href.slice(1), vditorEl);
          } else if (href) {
            window.open(href);
          }
        });
      }

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
        // Longer documents need more time for Vditor to finish rendering
        setTimeout(doRestore, 200);
        setTimeout(doRestore, 600);
        setTimeout(doRestore, 1200);
        setTimeout(doRestore, 2000);

        // Cleanup
        setTimeout(() => {
          _pendingRestore = null;
        }, 2500);
      } else {
        setTimeout(() => {
          const el = getActiveEditorEl();
          if (el) el.focus();
        }, 50);
      }
      if (readonly) {
        const tb = vditorEl.querySelector('.vditor-toolbar');
        if (tb) tb.style.display = 'none';
        const ed = vditorEl.querySelector(
          '.vditor-ir .vditor-reset, .vditor-sv .vditor-reset, .vditor-wysiwyg .vditor-reset',
        );
        if (ed) {
          ed.setAttribute('contenteditable', 'false');
          ed.style.userSelect = 'text';
        }
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
  _svWheelHandler = (_e) => {
    // Let the browser handle the wheel event first, then sync
    requestAnimationFrame(() => {
      const pTop = pvEl.scrollTop;
      const eMax = svEl.scrollHeight - svEl.clientHeight;
      const pMax = pvEl.scrollHeight - pvEl.clientHeight;
      if (eMax > 0 && pMax > 0) svEl.scrollTop = (pTop * eMax) / pMax;
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
  if (_svCursorHandler) {
    document.removeEventListener('selectionchange', _svCursorHandler);
    _svCursorHandler = null;
  }
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
  } catch (_err) {
    return;
  }

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
          if (headings[i].contains(cursorNode)) {
            cursorHeadingIndex = i;
            break;
          }
          const cmp = cursorNode.compareDocumentPosition(headings[i]);
          if (cmp & Node.DOCUMENT_POSITION_PRECEDING) {
            cursorHeadingIndex = i;
          } else {
            break;
          }
        }
      }
    }
  } catch (_err) {}

  try {
    const items = outlineEl.querySelectorAll('li > span');
    items.forEach((item, idx) => {
      if (idx === cursorHeadingIndex) {
        item.classList.add('outline-active');
      } else {
        item.classList.remove('outline-active');
      }
    });
  } catch (_err) {}
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
    _outlineObserver.observe(vditorEl, {
      childList: true,
      attributes: true,
      attributeFilter: ['style', 'class'],
    });
    _outlineClickHandler = (e) => {
      if (!e.target.closest('.vditor-outline')) return;
      setTimeout(() => _updateOutlineHighlight(), 200);
    };
    vditorEl.addEventListener('click', _outlineClickHandler);
  }
}

function teardownOutlineHighlight() {
  if (_outlineUpdateRAF) {
    cancelAnimationFrame(_outlineUpdateRAF);
    _outlineUpdateRAF = null;
  }
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
    if (ta) {
      ta.focus({ preventScroll: !scrollToFocus });
      ta.setSelectionRange(offset, offset);
    }
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
      s.removeAllRanges();
      s.addRange(r);
      return;
    }
    cc += nl;
  }
  const r = document.createRange();
  const s = window.getSelection();
  r.selectNodeContents(el);
  r.collapse(false);
  s.removeAllRanges();
  s.addRange(r);
}

function getEditorContent() {
  return _vditor ? _vditor.getValue() : '';
}
function isDirty() {
  if (!_vditor) return false;
  const cur = _vditor.getValue();
  const orig = _originalContent;
  // Normalize both to avoid false positives from Vditor's trailing newline
  const norm = (s) => (typeof s === 'string' ? s.replace(/\r\n/g, '\n').replace(/\n+$/, '') : '');
  return norm(cur) !== norm(orig);
}
function markSaved() {
  _originalContent = getEditorContent();
}
function getCurrentFileInfo() {
  return { mountId: _currentMountId, relPath: _currentRelPath };
}
function setFileInfo(mountId, relPath) {
  _currentMountId = mountId;
  _currentRelPath = relPath;
}
