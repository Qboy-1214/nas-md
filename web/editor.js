/**
 * editor.js - Vditor 编辑器封装
 */

let _vditor = null;
let _currentMountId = null;
let _currentRelPath = null;
let _originalContent = '';
let _editorMode = 'ir';
let _cursorRestoreOffset = 0;

window._getVditor = () => _vditor;

window._reinitEditor = (mode) => {
  if (!_vditor) return;
  const content = _vditor.getValue();
  let scrollTop = 0;
  const oldMode = _vditor.getCurrentMode();
  if (oldMode === 'sv') scrollTop = _vditor.vditor.sv.element.scrollTop;
  else if (oldMode === 'ir') scrollTop = _vditor.vditor.ir.element.scrollTop;
  else if (oldMode === 'wysiwyg') scrollTop = _vditor.vditor.wysiwyg.element.parentElement.scrollTop;

  let cursorOffset = 0;
  try {
    _vditor.focus();
    const sel = window.getSelection();
    if (sel.rangeCount > 0) {
      const range = sel.getRangeAt(0);
      const preRange = range.cloneRange();
      if (oldMode === 'sv') {
        const ta = _vditor.vditor.sv.element;
        if (ta) cursorOffset = ta.selectionStart;
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

  requestAnimationFrame(() => {
    if (!_vditor) return;
    const nd = _vditor.vditor;
    if (mode === 'sv') nd.sv.element.scrollTop = scrollTop;
    else if (mode === 'ir') nd.ir.element.scrollTop = scrollTop;
    else if (mode === 'wysiwyg') nd.wysiwyg.element.parentElement.scrollTop = scrollTop;
    setTimeout(() => { const el = getActiveEditorEl(); if (el) el.focus(); }, 30);
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
      markdown: { toc: true, autoSpace: true, fixTermTypo: true },
      hljs: { enable: true, style: 'github', lineNumber: false },
      theme: { current: 'light', path: 'https://unpkg.com/vditor@3.10.7/dist/css/content-theme' },
    },
    cache: { enable: false },
    upload: { url: '', linkToImgUrl: '' },
    after: () => {
      if (_editorMode === 'sv') setupSVSync();
      if (_cursorRestoreOffset > 0) {
        setTimeout(() => { restoreCursorPosition(_cursorRestoreOffset); _cursorRestoreOffset = 0; }, 50);
      } else {
        setTimeout(() => { const el = getActiveEditorEl(); if (el) el.focus(); }, 50);
      }
      if (readonly) {
        const tb = vditorEl.querySelector('.vditor-toolbar');
        if (tb) tb.style.display = 'none';
        const ed = vditorEl.querySelector('.vditor-ir .vditor-reset, .vditor-sv .vditor-reset, .vditor-wysiwyg .vditor-reset');
        if (ed) { ed.setAttribute('contenteditable', 'false'); ed.style.userSelect = 'text'; }
      }
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

// ─── SV mode: two-way scroll sync + cursor tracking ─────────────────────
//
// Vditor's SV scroll handler directly sets previewEl.scrollTop when
// svEl scrolls. If our rAF also pushes preview→editor, we get:
//   preview scroll → set svEl.scrollTop → Vditor sets previewEl.scrollTop
//   → our rAF sees preview change → pushes back → loop.
//
// Fix: track which side actually changed between ticks. When both sides
// change, it means Vditor pushed editor→preview, so we re-sync
// editor→preview (not preview→editor). This breaks the feedback loop.

let _svCursorHandler = null;
let _svRafId = null;
let _svLastE = 0;
let _svLastP = 0;

function setupSVSync() {
  teardownSVSync();
  const svEl = _vditor.vditor.sv.element;
  const pv = _vditor.vditor.preview;

  function syncE2P(eTop) {
    const eMax = svEl.scrollHeight - svEl.clientHeight;
    const pMax = pv.element.scrollHeight - pv.element.clientHeight;
    if (eMax > 0 && pMax > 0) pv.element.scrollTop = eTop * pMax / eMax;
    _svLastE = eTop;
    _svLastP = pv.element.scrollTop;
  }

  function syncP2E(pTop) {
    const eMax = svEl.scrollHeight - svEl.clientHeight;
    const pMax = pv.element.scrollHeight - pv.element.clientHeight;
    if (eMax > 0 && pMax > 0) svEl.scrollTop = pTop * eMax / pMax;
    _svLastE = svEl.scrollTop;
    _svLastP = pTop;
  }

  const tick = () => {
    const e = svEl.scrollTop;
    const p = pv.element.scrollTop;
    const eMoved = Math.abs(e - _svLastE) > 0.5;
    const pMoved = Math.abs(p - _svLastP) > 0.5;

    if (eMoved && !pMoved) {
      // User scrolled editor → follow preview
      syncE2P(e);
    } else if (pMoved && !eMoved) {
      // User scrolled preview → follow editor
      syncP2E(p);
    } else if (eMoved && pMoved) {
      // Both moved → Vditor pushed editor→preview; re-assert editor→preview
      syncE2P(e);
    }
    // else: nothing changed

    _svRafId = requestAnimationFrame(tick);
  };
  _svRafId = requestAnimationFrame(tick);

  // Cursor tracking: scroll preview to cursor line
  _svCursorHandler = () => {
    const ta = svEl;
    if (!ta) return;
    const pos = ta.selectionStart;
    const before = ta.value.substring(0, pos);
    const line = before.split('\n').length - 1;
    const total = ta.value.split('\n').length;
    if (total <= 1) return;
    const maxP = pv.element.scrollHeight - pv.element.clientHeight;
    pv.element.scrollTop = (line / (total - 1)) * maxP;
    _svLastP = pv.element.scrollTop;
  };
  document.addEventListener('selectionchange', _svCursorHandler);
  setTimeout(() => _svCursorHandler(), 100);
}

function teardownSVSync() {
  if (_svRafId) { cancelAnimationFrame(_svRafId); _svRafId = null; }
  if (_svCursorHandler) { document.removeEventListener('selectionchange', _svCursorHandler); _svCursorHandler = null; }
  _svLastE = 0;
  _svLastP = 0;
}

// ─── Cursor / content helpers ───────────────────────────────────────────

function restoreCursorPosition(offset) {
  if (!_vditor) return;
  const vd = _vditor.vditor;
  const mode = _vditor.getCurrentMode();
  if (mode === 'sv') {
    const ta = vd.sv.element;
    if (ta) { ta.focus(); ta.setSelectionRange(offset, offset); }
    return;
  }
  const el = mode === 'wysiwyg' ? vd.wysiwyg.element : vd.ir.element;
  if (!el) return;
  el.focus();
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
