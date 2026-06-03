/**
 * editor.js - Vditor 编辑器封装
 */

let _vditor = null;
let _currentMountId = null;
let _currentRelPath = null;
let _originalContent = '';
let _editorMode = 'ir';  // ir | sv | wysiwyg

// Expose for app.js
window._getVditor = () => _vditor;

// Reinitialize editor with a new mode (Vditor doesn't support runtime mode switch)
window._reinitEditor = (mode) => {
  if (!_vditor) return;
  const content = _vditor.getValue();
  _vditor.destroy();
  initEditor(content, mode, false);
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

function getEditorContent() {
  if (!_vditor) return '';
  return _vditor.getValue();
}

function setEditorMode(mode) {
  _editorMode = mode;
  if (_vditor) {
    _vditor.setMode(mode);
  }
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
