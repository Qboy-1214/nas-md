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
      // SV mode: wire up reverse scroll sync (preview → editor)
      // and cursor tracking (editor cursor → preview scroll)
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
        // Even without cursor offset, restore focus to the editor
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

// SV mode: reverse scroll sync + cursor tracking
let _svCursorSyncHandler = null;
let _svRafId = null;
let _svLastEditorTop = 0;
let _svLastPreviewTop = 0;

function setupSVSync() {
  teardownSVSync();

  const svEl = _vditor.vditor.sv.element;
  const previewEl = _vditor.vditor.preview.element;

  // Use a single rAF loop instead of scroll events to avoid feedback.
  // Scroll events from Vditor's built-in sync and our own adjustments
  // create an infinite loop when both sides listen. A polling loop
  // sidesteps this entirely: we only push scroll position when it
  // actually changed from the last known value.
  // One-way sync: editor → preview only.
  // Syncing preview back to editor causes a feedback loop because
  // changing editor scrollTop triggers Vditor to re-render the preview,
  // which resets preview scrollTop, which triggers another sync.
  // The preview panel is read-only rendered output — user scrolling it
  // should not affect the editor.
  const tick = () => {
    const eTop = svEl.scrollTop;
    if (eTop !== _svLastEditorTop) {
      const eMax = svEl.scrollHeight - svEl.clientHeight;
      const pMax = previewEl.scrollHeight - previewEl.clientHeight;
      if (eMax > 0 && pMax > 0) {
        previewEl.scrollTop = eTop * pMax / eMax;
      }
      _svLastEditorTop = eTop;
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
    const previewScrollHeight = previewEl.scrollHeight - previewEl.clientHeight;
    const ratio = lineNumber / (totalLines - 1);
    previewEl.scrollTop = ratio * previewScrollHeight;
    _svLastPreviewTop = previewEl.scrollTop;
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
  _svLastEditorTop = 0;
  _svLastPreviewTop = 0;
}

function restoreCursorPosition(offset) {
  if (!_vditor) return;
  const vditor = _vditor.vditor;
  const mode = _vditor.getCurrentMode();

  if (mode === 'sv') {
    // SV mode: textarea
    const textarea = vditor.sv.element;
    if (textarea) {
      textarea.focus();
      textarea.setSelectionRange(offset, offset);
    }
  } else {
    // IR or WYSIWYG mode: contenteditable div
    const el = mode === 'wysiwyg' ? vditor.wysiwyg.element : vditor.ir.element;
    if (!el) return;
    el.focus();
    // Walk text nodes to find the node and offset at the target position
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
    // If offset is beyond content length, collapse to end
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
