/**
 * sync_layer.js - Remote edit sync with edit-in-progress protection
 *
 * IMPORTANT: Never modify Vditor's editor DOM directly (no appendChild, no
 * classList on editor elements). Vditor serializes DOM back to markdown, so
 * any injected elements become document content. Use floating notifications
 * outside the editor instead.
 */
(function () {
  'use strict';

  var _lastInputTime = 0;
  var _cursorParaIdx = -1;
  var _pendingUpdates = [];
  // Flag to prevent save-loop: when true, onEditorInput will NOT trigger auto-save
  var _applyingRemote = false;
  // Debounce timer for batching remote updates
  var _applyTimer = null;
  var _pendingBatch = [];
  // Active collaborators (authorId -> {name, color, lastActive})
  var _collaborators = {};

  // === Edit state tracking ===

  function isActivelyEditing() {
    return Date.now() - _lastInputTime < 2000;
  }

  function getCursorParagraphIndex() {
    if (!window._vditor) return -1;
    var sel = window.getSelection();
    if (!sel.rangeCount) return -1;
    var range = sel.getRangeAt(0);
    var node = range.startContainer;
    var el = node.nodeType === 3 ? node.parentElement : node;

    var vditorEl = document.getElementById('vditor');
    if (!vditorEl) return -1;

    var paraSelectors = 'p, h1, h2, h3, h4, h5, h6, pre, blockquote, ul, ol, table, hr';
    var allParas = vditorEl.querySelectorAll(paraSelectors);
    for (var i = 0; i < allParas.length; i++) {
      if (allParas[i].contains(el) || allParas[i] === el) return i;
    }
    return -1;
  }

  // === Floating notification (outside editor DOM) ===

  function showCollabNotification(author, changeType, paraIdx) {
    var container = document.getElementById('collab-notifications');
    if (!container) {
      container = document.createElement('div');
      container.id = 'collab-notifications';
      container.style.cssText =
        'position:fixed;top:60px;right:20px;z-index:9999;pointer-events:none;display:flex;flex-direction:column;gap:6px;';
      document.body.appendChild(container);
    }

    var notif = document.createElement('div');
    notif.style.cssText =
      'background:' +
      (author.color || '#3498db') +
      ';color:white;padding:6px 14px;border-radius:16px;font-size:13px;box-shadow:0 2px 8px rgba(0,0,0,0.2);opacity:0;transition:opacity 0.3s;display:flex;align-items:center;gap:6px;';

    var actionText = '';
    switch (changeType) {
      case 'replace':
        actionText = '编辑了第' + (paraIdx + 1) + '段';
        break;
      case 'insert':
        actionText = '新增了第' + (paraIdx + 1) + '段';
        break;
      case 'delete':
        actionText = '删除了第' + (paraIdx + 1) + '段';
        break;
    }

    notif.innerHTML =
      '<span style="font-weight:bold;">' +
      escapeHtml(author.name || 'Anonymous') +
      '</span><span>' +
      actionText +
      '</span>';

    container.appendChild(notif);

    // Fade in
    requestAnimationFrame(function () {
      notif.style.opacity = '1';
    });

    // Fade out and remove after 3 seconds
    setTimeout(function () {
      notif.style.opacity = '0';
      setTimeout(function () {
        if (notif.parentNode) notif.parentNode.removeChild(notif);
      }, 300);
    }, 3000);
  }

  function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  // === Collaborator presence ===

  function updateCollaborator(author) {
    if (!author || !author.id) return;
    _collaborators[author.id] = {
      name: author.name,
      color: author.color,
      lastActive: Date.now(),
    };
    renderCollaboratorBar();
  }

  function renderCollaboratorBar() {
    var bar = document.getElementById('collab-presence-bar');
    if (!bar) {
      bar = document.createElement('div');
      bar.id = 'collab-presence-bar';
      bar.style.cssText =
        'position:fixed;top:50px;right:20px;z-index:9998;display:flex;gap:6px;pointer-events:none;';
      document.body.appendChild(bar);
    }
    bar.innerHTML = '';
    var now = Date.now();
    for (var id in _collaborators) {
      var c = _collaborators[id];
      // Remove stale collaborators (no activity for 30s)
      if (now - c.lastActive > 30000) {
        delete _collaborators[id];
        continue;
      }
      var avatar = document.createElement('div');
      avatar.style.cssText =
        'width:28px;height:28px;border-radius:50%;background:' +
        c.color +
        ';color:white;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:bold;border:2px solid white;box-shadow:0 1px 4px rgba(0,0,0,0.2);';
      avatar.title = c.name;
      avatar.textContent = (c.name || '?').charAt(0).toUpperCase();
      bar.appendChild(avatar);
    }
  }

  // === Paragraph update application ===

  function applyRemoteChange(change, author) {
    if (!window._vditor) return;

    var currentContent = window._vditor.getValue();
    var paragraphs = currentContent.split('\n\n');

    switch (change.type) {
      case 'replace':
        if (change.paraIdx < paragraphs.length) {
          paragraphs[change.paraIdx] = change.content;
        }
        break;
      case 'delete':
        if (change.paraIdx < paragraphs.length) {
          paragraphs.splice(change.paraIdx, 1);
        }
        break;
      case 'insert':
        paragraphs.splice(change.paraIdx, 0, change.content);
        break;
    }

    var newContent = paragraphs.join('\n\n');

    // Skip if content didn't actually change
    if (newContent === currentContent) {
      // Still show notification even if content is same (edge case)
      showCollabNotification(author, change.type, change.paraIdx);
      return;
    }

    // Set flag to prevent onEditorInput from triggering auto-save (breaks the loop)
    _applyingRemote = true;

    // Save cursor/scroll position
    if (window.saveCursorScrollToStorage) {
      window.saveCursorScrollToStorage();
    }

    // Apply to editor
    window._vditor.setValue(newContent);
    window._originalContent = window._vditor.getValue();

    // Clear the flag after Vditor finishes rendering
    setTimeout(function () {
      _applyingRemote = false;
      if (window.restoreCursorScrollFromStorage) {
        window.restoreCursorScrollFromStorage();
      }
    }, 150);

    // Show floating notification (NOT modifying editor DOM)
    showCollabNotification(author, change.type, change.paraIdx);
  }

  // === Pending update queue ===

  function applyPendingUpdates() {
    if (_pendingUpdates.length === 0) return;
    if (isActivelyEditing()) return;

    var pending = _pendingUpdates.slice();
    _pendingUpdates = [];
    for (var i = 0; i < pending.length; i++) {
      applyRemoteChange(pending[i].change, pending[i].author);
    }
  }

  // === Remote edit handler (with batching) ===

  function handleRemoteEdit(data) {
    if (!data.changes || !Array.isArray(data.changes)) return;

    var author = {
      id: data.authorId,
      name: data.authorName,
      color: data.authorColor,
    };

    // Update collaborator presence
    updateCollaborator(author);

    // Update version state (replaces mtime tracking)
    if (data.newVersion && window.state && data.mountId && data.path) {
      var versionKey = data.mountId + ':' + data.path;
      if (state.fileVersions) {
        state.fileVersions[versionKey] = data.newVersion;
      }
      // If the edit is on the currently open file, bump baseVersion so the
      // client's next save uses the fresh version (no false merge).
      if (state.currentMountId === data.mountId && state.currentPath === data.path) {
        state.baseVersion = data.newVersion;
      }
    }

    // Check if this is the currently open file
    var isCurrentFile = state.currentMountId === data.mountId && state.currentPath === data.path;

    if (isCurrentFile && window._vditor) {
      // Before applying changes, check if client's version matches server's version
      // If versions don't match, fetch the full content instead of applying incremental changes
      var myVersion = state.baseVersion || 0;
      var serverVersion = data.newVersion || 0;
      if (myVersion < serverVersion - 1) {
        // Version gap is too large, fetch full content to ensure consistency
        fetchFullContent(data.mountId, data.path, serverVersion);
        return;
      }
    }

    for (var i = 0; i < data.changes.length; i++) {
      var change = data.changes[i];
      var isProtected = isActivelyEditing() && change.paraIdx === _cursorParaIdx;

      if (isProtected) {
        _pendingUpdates.push({
          change: change,
          author: author,
        });
      } else {
        // Batch non-protected changes and apply with debounce to avoid rapid setValue calls
        _pendingBatch.push({ change: change, author: author });
      }
    }

    // Debounce: wait 300ms for more changes before applying batch
    if (_applyTimer) clearTimeout(_applyTimer);
    _applyTimer = setTimeout(function () {
      var batch = _pendingBatch.slice();
      _pendingBatch = [];
      _applyTimer = null;
      for (var j = 0; j < batch.length; j++) {
        applyRemoteChange(batch[j].change, batch[j].author);
      }
      // After applying remote changes, sync baseContent to the new editor content
      // so the next local save diff is computed against the merged result.
      if (window._vditor && window.state) {
        var merged = window._vditor.getValue();
        state.baseContent = merged;
        window._originalContent = merged;
      }
    }, 300);
  }

  function fetchFullContent(mountId, path, _expectedVersion) {
    if (!API || !window._vditor) return;
    API.getFile(mountId, path)
      .then(function (result) {
        if (!result || !result.content) return;
        _applyingRemote = true;
        window._vditor.setValue(result.content);
        window._originalContent = result.content;
        if (window.state) {
          state.baseContent = result.content;
          if (result.version !== undefined) {
            state.baseVersion = result.version;
            var key = mountId + ':' + path;
            if (state.fileVersions) {
              state.fileVersions[key] = result.version;
            }
          }
        }
        setTimeout(function () {
          _applyingRemote = false;
        }, 150);
        showCollabNotification({ name: 'System', color: '#3498db' }, 'replace', 0);
      })
      .catch(function (_e) {
        console.error('Failed to fetch full content for sync:', _e);
      });
  }

  // Handle external file modification (delivered by file_watcher via SSE)
  function handleExternalReload(data) {
    if (!data.mountId || !data.path) return;
    if (!window.state) return;
    // Only handle the currently open file
    if (state.currentMountId !== data.mountId || state.currentPath !== data.path) {
      return;
    }

    // Update version state regardless of whether we reload
    if (data.newVersion) {
      state.baseVersion = data.newVersion;
      var key = data.mountId + ':' + data.path;
      if (state.fileVersions) {
        state.fileVersions[key] = data.newVersion;
      }
    }

    // If user has unsaved edits, don't blow them away — let next save merge.
    if (state.dirty) {
      window.showToast('文件已被外部修改，你的未保存编辑将在下次保存时合并', 'info');
      return;
    }

    // No unsaved edits — reload the editor with the new content
    if (data.content && window._vditor) {
      _applyingRemote = true;
      window._vditor.setValue(data.content);
      window._originalContent = data.content;
      state.baseContent = data.content;
      window._lastSavedContent = data.content;
      setTimeout(function () {
        _applyingRemote = false;
      }, 150);
      window.showToast('文件已被外部修改，已自动重载');
    }
  }

  // === Initialization ===

  var _hooked = false;

  function hookOnEditorInput() {
    if (_hooked) return;
    if (!window.onEditorInput) return;
    _hooked = true;
    var origOnEditorInput = window.onEditorInput;
    window.onEditorInput = function () {
      // Track edit time for protection logic
      _lastInputTime = Date.now();
      _cursorParaIdx = getCursorParagraphIndex();

      // If this input was triggered by remote sync, skip auto-save to break the loop
      if (_applyingRemote) {
        return;
      }

      if (origOnEditorInput) origOnEditorInput();
    };
  }

  function init() {
    // Try to hook immediately
    hookOnEditorInput();
    // Retry after delays in case onEditorInput is defined later
    setTimeout(hookOnEditorInput, 100);
    setTimeout(hookOnEditorInput, 500);
    setTimeout(hookOnEditorInput, 1500);

    // Check for pending updates when cursor moves
    setInterval(function () {
      var newParaIdx = getCursorParagraphIndex();
      if (newParaIdx !== _cursorParaIdx) {
        _cursorParaIdx = newParaIdx;
        applyPendingUpdates();
      }
      // Also clean up stale collaborators
      renderCollaboratorBar();
    }, 1000);

    // Connect SSE and register handler
    if (window.nasmdSSE) {
      window.nasmdSSE.on('remote_edit', handleRemoteEdit);
      window.nasmdSSE.on('external_reload', handleExternalReload);
    }
  }

  // Expose
  window.nasmdSync = {
    init: init,
    handleRemoteEdit: handleRemoteEdit,
    handleExternalReload: handleExternalReload,
    applyPendingUpdates: applyPendingUpdates,
    isApplyingRemote: function () {
      return _applyingRemote;
    },
  };

  // Auto-init when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
