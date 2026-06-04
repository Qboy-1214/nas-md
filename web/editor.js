/**
 * editor.js - Vditor 编辑器封装
 */

let _vditor = null;
let _currentMountId = null;
let _currentRelPath = null;
let _originalContent = '';
let _editorMode = 'ir';  // ir | sv | wysiwyg
let _cursorRestoreOffset = 0;

// Expose for app.js
window._getVditor = () => _vditor;

// Reinitialize editor with a new mode (Vditor doesn't support runtime mode switch)
window._reinitEditor = (mode) => {
  if (!_vditor) return;
  const content = _vditor.getValue();

  // Save scroll position from the active panel
  let scrollTop = 0;
  const oldMode = _vditor.getCurrentMode();
  if (oldMode === 'sv') {
    scrollTop = _vditor.vditor.sv.element.scrollTop;
  } else if (oldMode === 'ir') {
    scrollTop = _vditor.vditor.ir.element.scrollTop;
  } else if (oldMode === 'wysiwyg') {
    scrollTop = _vditor.vditor.wysiwyg.element.parentElement.scrollTop;
  }

  // Save cursor position as text offset
  let cursorOffset = 0;
  try {
    _vditor.focus();
    const sel = window.getSelection();
    if (sel.rangeCount > 0) {
      const range = sel.getRangeAt(0);
      const preRange = range.cloneRange();
      if (oldMode === 'sv') {
        const textarea = _vditor.vditor.sv.element;
        if (textarea) cursorOffset = textarea.selectionStart;
      } else {
        const el = oldMode === 'wysiwyg' ? _vditor.vditor.wysiwyg.element : _vditor.vditor.ir.element;
        preRange.selectNodeContents(el);
        preRange.setEnd(range.startContainer, range.startOffset);
        cursorOffset = preRange.toString().length;
      }
    }
  } catch (_) {}

  teardownSVSync();
  _vditor.destroy();
  _cursorRestoreOffset = cursorOffset;
  initEditor(content, mode, false, cursorOffset);

  // Restore scroll position after the new editor renders
  requestAnimationFrame(() => {
    if (!_vditor) return;
    const nd = _vditor.vditor;
    if (mode === 'sv') {
      nd.sv.element.scrollTop = scrollTop;
    } else if (mode === 'ir') {
      nd.ir.element.scrollTop = scrollTop;
    } else if (mode === 'wysiwyg') {
      nd.wysiwyg.element.parentElement.scrollTop = scrollTop;
    }
    // Restore focus after scroll is set
    setTimeout(() => {
      const el = getActiveEditorEl();
      if (el) el.focus();
    }, 30);
  });
};

function initEditor(content, mode, readonly, cursorOffset) {
  _editorMode = mode || 'ir';
  _originalContent = content || '';
  _cursorRestoreOffset = cursorOffset || 0;

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
      'emoji', 'headings', 'bold', 'italic', 'strike', 'link',
      '|', 'list', 'ordered-list', 'check',
      '|', 'quote', 'line', 'code', 'inline-code',
      '|', 'table', 'record',
      '|', 'undo', 'redo',
      '|', { name: 'more', toolbar: ['fullscreen', 'edit-mode', 'preview', 'outline', 'info', 'help'] },
    ],
    preview: {
      mode: 'both',
      markdown: {
        toc: true,
        autoSpace: true,
        fixTermTypo: true,
      },
      hljs: {
        enable: true,
        style: 'github',
        lineNumber: false,
      },
      theme: {
        current: 'light',
        path: 'https://unpkg.com/vditor@3.10.7/dist/css/content-theme',
      },
    },
    cache: {
      enable: false,
    },
    upload: {
      url: '',  // 暂不启用上传
      linkToImgUrl: '',
    },
    after: () => {
      // SV mode: wire up scroll sync and cursor tracking
      if (_editorMode === 'sv') {
        setupSVSync();
      }
      // Restore cursor/focus after a delay to ensure DOM is fully ready
      if (_cursorRestoreOffset > 0) {
        setTimeout(() => {
          restoreCursorPosition(_cursorRestoreOffset);
          _cursorRestoreOffset = 0;
        }, 50);
      } else {
        setTimeout(() => {
          const el = getActiveEditorEl();
          if (el) el.focus();
        }, 50);
      }
      // 只读模式：禁用编辑区，隐藏工具栏
      if (readonly) {
        const toolbar = vditorEl.querySelector('.vditor-toolbar');
        if (toolbar) toolbar.style.display = 'none';
        const editor = vditorEl.querySelector('.vditor-ir .vditor-reset, .vditor-sv .vditor-reset, .vditor-wysiwyg .vditor-reset');
        if (editor) {
          editor.setAttribute('contenteditable', 'false');
          editor.style.userSelect = 'text';
        }
      }
    },
  });
}

function getActiveEditorEl() {
  if (!_vditor) return null;
  const mode = _vditor.getCurrentMode();
  if (mode === 'sv') return _vditor.vditor.sv.element;
  if (mode === 'ir') return _vditor.vditor.ir.element;
  if (mode === 'wysiwyg') return _vditor.vditor.wysiwyg.element;
  return null;
}

// ─── SV mode: two-way scroll sync + cursor tracking ─────────────────────
//
// Challenge: Vditor's SV mode has a scroll handler on sv.element that
// calls preview.render(). If we set svEl.scrollTop, that handler fires,
// re-renders the preview, and resets preview.scrollTop → feedback loop.
//
// Solution: wrap preview.render with a suppression flag. When our rAF
// loop is about to set svEl.scrollTop (preview→editor sync), we set
// _svRenderSuppress=true first. Vditor's scroll handler still fires,
// but preview.render() becomes a no-op. After the scroll is set, we
// clear the flag so future user-triggered scrolls render normally.

let _svCursorSyncHandler = null;
let _svRafId = null;
let _svLastEditorTop = 0;
let _svLastPreviewTop = 0;
let _svRenderSuppress = false;

function setupSVSync() {
  teardownSVSync();

  const svEl = _vditor.vditor.sv.element;
  const preview = _vditor.vditor.preview;

  // DEBUG: log render calls to trace the loop
  const origRender = preview.render.bind(preview);
  let _svRenderCount = 0;
  preview.render = function(vditor) {
    _svRenderCount++;
    if (_svRenderSuppress) {
      console.warn('[SV] render SUPPRESSED #' + _svRenderCount + ', pTop:', preview.element.scrollTop, 'eTop:', svEl.scrollTop);
      return;
    }
    console.warn('[SV] render #' + _svRenderCount + ', pTop:', preview.element.scrollTop, 'eTop:', svEl.scrollTop);
    return origRender(vditor);
  };

  let _svTickCount = 0;
  const _svDebugEl = document.createElement('div');
  _svDebugEl.style.cssText = 'position:fixed;bottom:0;left:0;right:0;background:rgba(0,0,0,0.8);color:#0f0;font:12px monospace;padding:4px;z-index:9999;max-height:60px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;';
  document.body.appendChild(_svDebugEl);

  const _svLog = (msg) => {
    _svDebugEl.textContent = msg;
    // Also keep a ring buffer
    _svDebugRing = _svDebugRing.slice(-5);
    _svDebugRing.push(msg);
  };
  let _svDebugRing = [];

  const tick = () => {
    _svTickCount++;
    const eTop = svEl.scrollTop;
    const pTop = preview.element.scrollTop;

    // Editor changed → sync to preview
    if (Math.abs(eTop - _svLastEditorTop) > 0.5) {
      const eMax = svEl.scrollHeight - svEl.clientHeight;
      const pMax = preview.element.scrollHeight - preview.element.clientHeight;
      if (eMax > 0 && pMax > 0) {
        preview.element.scrollTop = eTop * pMax / eMax;
      }
      _svLog('e→p e:' + Math.round(eTop) + ' p:' + Math.round(preview.element.scrollTop) + ' render:' + _svRenderCount);
      _svLastEditorTop = eTop;
      _svLastPreviewTop = preview.element.scrollTop;
    }
    // Preview changed → sync to editor
    else if (Math.abs(pTop - _svLastPreviewTop) > 0.5) {
      const eMax = svEl.scrollHeight - svEl.clientHeight;
      const pMax = preview.element.scrollHeight - preview.element.clientHeight;
      if (eMax > 0 && pMax > 0) {
        const target = pTop * eMax / pMax;
        _svLog('p→e p:' + Math.round(pTop) + ' t:' + Math.round(target) + ' r:' + _svRenderCount);
        _svRenderSuppress = true;
        svEl.scrollTop = target;
        _svRenderSuppress = false;
        _svLastEditorTop = svEl.scrollTop;
      }
      _svLastPreviewTop = pTop;
    }
    else {
      _svLastEditorTop = eTop;
      _svLastPreviewTop = pTop;
    }

    _svRafId = requestAnimationFrame(tick);
  };
  _svRafId = requestAnimationFrame(tick);

  // Cursor/selection change → scroll preview to cursor line
  _svCursorSyncHandler = () => {
    const textarea = svEl;
    if (!textarea) return;
    const pos = textarea.selectionStart;
    const text = textarea.value;
    const textBefore = text.substring(0, pos);
    const lineNumber = textBefore.split('\n').length - 1;
    const totalLines = text.split('\n').length;
    if (totalLines <= 1) return;
    const previewScrollHeight = preview.element.scrollHeight - preview.element.clientHeight;
    const ratio = lineNumber / (totalLines - 1);
    preview.element.scrollTop = ratio * previewScrollHeight;
    _svLastPreviewTop = preview.element.scrollTop;
  };
  document.addEventListener('selectionchange', _svCursorSyncHandler);

  // Scroll preview to match initial cursor position
  setTimeout(() => _svCursorSyncHandler(), 100);
}

function teardownSVSync() {
  if (_svRafId) {
    cancelAnimationFrame(_svRafId);
    _svRafId = null;
  }
  if (_svCursorSyncHandler) {
    document.removeEventListener('selectionchange', _svCursorSyncHandler);
    _svCursorSyncHandler = null;
  }
  // Restore original preview.render if we wrapped it
  if (_vditor) {
    const preview = _vditor.vditor.preview;
    // We can't easily restore since we replaced it, but on reinit
    // Vditor is destroyed and recreated, so the wrap is fresh.
  }
  _svLastEditorTop = 0;
  _svLastPreviewTop = 0;
  _svRenderSuppress = false;
}

// ─── Cursor / content helpers ───────────────────────────────────────────

function restoreCursorPosition(offset) {
  if (!_vditor) return;
  const vditor = _vditor.vditor;
  const mode = _vditor.getCurrentMode();

  if (mode === 'sv') {
    const textarea = vditor.sv.element;
    if (textarea) {
      textarea.focus();
      textarea.setSelectionRange(offset, offset);
    }
  } else {
    const el = mode === 'wysiwyg' ? vditor.wysiwyg.element : vditor.ir.element;
    if (!el) return;
    el.focus();
    let charCount = 0;
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null, false);
    let node;
    while ((node = walker.nextNode())) {
      const nodeLen = node.textContent.length;
      if (charCount + nodeLen >= offset) {
        const range = document.createRange();
        const sel = window.getSelection();
        range.setStart(node, Math.min(offset - charCount, nodeLen));
        range.collapse(true);
        sel.removeAllRanges();
        sel.addRange(range);
        return;
      }
      charCount += nodeLen;
    }
    const range = document.createRange();
    const sel = window.getSelection();
    range.selectNodeContents(el);
    range.collapse(false);
    sel.removeAllRanges();
    sel.addRange(range);
  }
}

function getEditorContent() {
  if (!_vditor) return '';
  return _vditor.getValue();
}

function isDirty() {
  if (!_vditor) return false;
  return _vditor.getValue() !== _originalContent;
}

function markSaved() {
  _originalContent = getEditorContent();
}

function getCurrentFileInfo() {
  return {
    mountId: _currentMountId,
    relPath: _currentRelPath,
  };
}

function setFileInfo(mountId, relPath) {
  _currentMountId = mountId;
  _currentRelPath = relPath;
}
