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
  var _queuedVersions = {};
  // Active collaborators (authorId -> {name, color, lastActive})
  var _collaborators = {};

  // === Edit state tracking ===

  function isActivelyEditing() {
    return Date.now() - _lastInputTime < 2000;
  }

  function getCursorParagraphIndex() {
    if (!window._vditor) return -1;
    try {
      var content = window._vditor.getValue();
      if (!content) return 0;
      var split =
        window.nasmdDiff && window.nasmdDiff.splitParagraphs
          ? window.nasmdDiff.splitParagraphs(content)
          : content.split('\n\n');
      if (split.length <= 1) return 0;

      var sel = window.getSelection();
      if (!sel || !sel.rangeCount) return -1;
      var range = sel.getRangeAt(0);
      var node = range.startContainer;
      var el = node.nodeType === 3 ? node.parentElement : node;

      var vditorEl = document.getElementById('vditor');
      if (!vditorEl) return -1;

      var contentArea =
        vditorEl.querySelector('.vditor-wysiwyg') ||
        vditorEl.querySelector('.vditor-sv') ||
        vditorEl.querySelector('.vditor-ir') ||
        vditorEl;

      var current = el;
      while (current && current.parentElement !== contentArea && current !== contentArea) {
        current = current.parentElement;
      }
      if (current && current.parentElement === contentArea) {
        var topBlocks = Array.prototype.slice.call(contentArea.children);
        var blockIdx = topBlocks.indexOf(current);
        if (blockIdx !== -1) {
          return Math.min(blockIdx, split.length - 1);
        }
      }
    } catch (_e) {
      /* fallback */
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

  function applyChangesToContent(text, changes) {
    if (!changes || changes.length === 0) return text;
    if (window.nasmdDiff && window.nasmdDiff.applyChangesLocally) {
      return window.nasmdDiff.applyChangesLocally(text, changes);
    }
    var paragraphs =
      window.nasmdDiff && window.nasmdDiff.splitParagraphs
        ? window.nasmdDiff.splitParagraphs(text)
        : text.split('\n\n');

    var replaces = {};
    var deletes = {};
    var insertsByIdx = {};

    for (var i = 0; i < changes.length; i++) {
      var ch = changes[i];
      var t = ch.type;
      var idx = ch.paraIdx !== undefined ? ch.paraIdx : 0;
      if (t === 'replace') {
        replaces[idx] = ch.content !== undefined ? ch.content : '';
      } else if (t === 'delete') {
        deletes[idx] = true;
      } else if (t === 'insert') {
        if (!insertsByIdx[idx]) insertsByIdx[idx] = [];
        insertsByIdx[idx].push(ch.content !== undefined ? ch.content : '');
      }
    }

    var resultParas = [];
    var n = paragraphs.length;

    for (var p = 0; p < n; p++) {
      if (insertsByIdx[p]) {
        for (var k = 0; k < insertsByIdx[p].length; k++) {
          resultParas.push(insertsByIdx[p][k]);
        }
      }
      if (deletes[p]) {
        continue;
      }
      if (replaces[p] !== undefined) {
        resultParas.push(replaces[p]);
      } else {
        resultParas.push(paragraphs[p]);
      }
    }

    // Trailing inserts (paraIdx >= n)
    var extraKeys = Object.keys(insertsByIdx)
      .map(Number)
      .filter(function (keyIdx) {
        return keyIdx >= n;
      })
      .sort(function (a, b) {
        return a - b;
      });

    for (var ek = 0; ek < extraKeys.length; ek++) {
      var eIdx = extraKeys[ek];
      for (var ekk = 0; ekk < insertsByIdx[eIdx].length; ekk++) {
        resultParas.push(insertsByIdx[eIdx][ekk]);
      }
    }

    return resultParas.join('\n\n');
  }

  function applyBatchRemoteChanges(batch) {
    if (!window._vditor || !batch || batch.length === 0) return;

    if (window.state) {
      var currentKey = state.currentMountId + ':' + state.currentPath;
      var currentBatch = [];
      for (var itemIdx = 0; itemIdx < batch.length; itemIdx++) {
        var item = batch[itemIdx];
        if (!item.versionKey || item.versionKey === currentKey) {
          currentBatch.push(item);
        } else if (state.fileVersions) {
          state.fileVersions[item.versionKey] = Math.max(
            Number(state.fileVersions[item.versionKey]) || 0,
            Number(item.version) || 0,
          );
        }
      }
      batch = currentBatch;
      if (batch.length === 0) return;
    }

    if (window.state && state.dirty) {
      state.pendingRemoteUpdate = true;
      var dirtyKey = batch[batch.length - 1].versionKey;
      if (dirtyKey) _queuedVersions[dirtyKey] = Number(state.baseVersion) || 0;
      if (window.showToast) {
        window.showToast('检测到远端有更新，本地有未保存内容，将在下次保存时合并', 'info');
      }
      return;
    }

    var currentContent = window._vditor.getValue();
    var newContent = currentContent;
    var batchIdx = 0;
    while (batchIdx < batch.length) {
      var version = batch[batchIdx].version;
      var versionChanges = [];
      while (batchIdx < batch.length && batch[batchIdx].version === version) {
        versionChanges.push(batch[batchIdx].change);
        batchIdx++;
      }
      newContent = applyChangesToContent(newContent, versionChanges);
    }
    var latest = batch[batch.length - 1];

    function commitBaseline(content) {
      window._originalContent = content;
      window._lastSavedContent = content;
      if (window.state) {
        state.baseContent = content;
        state.baseVersion = latest.version;
        state.pendingRemoteUpdate = false;
        if (state.fileVersions && latest.versionKey) {
          state.fileVersions[latest.versionKey] = latest.version;
        }
      }
    }

    // Skip if content didn't actually change
    if (newContent === currentContent) {
      commitBaseline(currentContent);
      for (var b = 0; b < batch.length; b++) {
        showCollabNotification(batch[b].author, batch[b].change.type, batch[b].change.paraIdx);
      }
      return;
    }

    // Set flag to prevent onEditorInput from triggering auto-save (breaks the loop)
    _applyingRemote = true;

    // Save cursor/scroll position
    if (window.saveCursorScrollToStorage) {
      window.saveCursorScrollToStorage();
    }

    // Apply to editor in ONE single setValue call
    window._vditor.setValue(newContent);
    commitBaseline(window._vditor.getValue());

    // Clear the flag after Vditor finishes rendering
    setTimeout(function () {
      _applyingRemote = false;
      if (window.restoreCursorScrollFromStorage) {
        window.restoreCursorScrollFromStorage();
      }
    }, 150);

    // Show floating notifications
    for (var b2 = 0; b2 < batch.length; b2++) {
      showCollabNotification(batch[b2].author, batch[b2].change.type, batch[b2].change.paraIdx);
    }
  }

  function applyRemoteChange(change, author) {
    applyBatchRemoteChanges([{ change: change, author: author }]);
  }

  // === Pending update queue ===

  function applyPendingUpdates() {
    if (_pendingUpdates.length === 0) return;
    if (isActivelyEditing()) return;

    var pending = _pendingUpdates.slice();
    _pendingUpdates = [];
    applyBatchRemoteChanges(pending);
  }

  // === Remote edit handler (with batching) ===

  function handleRemoteEdit(data) {
    if (!data.changes || !Array.isArray(data.changes)) return;

    var serverVersion = Number(data.newVersion) || 0;
    var isCurrentFile = state.currentMountId === data.mountId && state.currentPath === data.path;
    var versionKey = data.mountId + ':' + data.path;

    if (isCurrentFile) {
      var myVersion = Math.max(
        Number(state.baseVersion) || 0,
        Number(_queuedVersions[versionKey]) || 0,
      );
      if (serverVersion <= myVersion) return;
      if (state.dirty) {
        state.pendingRemoteUpdate = true;
        if (window.showToast) {
          window.showToast('检测到远端有更新，本地有未保存内容，将在下次保存时合并', 'info');
        }
        return;
      }
      if (serverVersion > myVersion + 1) {
        fetchFullContent(data.mountId, data.path, serverVersion);
        return;
      }
    } else {
      var knownVersion = state.fileVersions ? Number(state.fileVersions[versionKey]) || 0 : 0;
      if (state.fileVersions && serverVersion > knownVersion) {
        state.fileVersions[versionKey] = serverVersion;
      }
      return;
    }

    var author = {
      id: data.authorId,
      name: data.authorName,
      color: data.authorColor,
    };

    // Update collaborator presence
    updateCollaborator(author);

    _queuedVersions[versionKey] = serverVersion;

    var deferVersion = false;
    for (var pendingIdx = 0; pendingIdx < _pendingUpdates.length; pendingIdx++) {
      if (_pendingUpdates[pendingIdx].versionKey === versionKey) {
        deferVersion = true;
        break;
      }
    }
    if (!deferVersion && isActivelyEditing()) {
      for (var protectedIdx = 0; protectedIdx < data.changes.length; protectedIdx++) {
        if (data.changes[protectedIdx].paraIdx === _cursorParaIdx) {
          deferVersion = true;
          break;
        }
      }
    }

    if (deferVersion && _pendingBatch.length > 0) {
      if (_applyTimer) clearTimeout(_applyTimer);
      _applyTimer = null;
      _pendingUpdates = _pendingUpdates.concat(_pendingBatch);
      _pendingBatch = [];
    }

    var destination = deferVersion ? _pendingUpdates : _pendingBatch;
    for (var i = 0; i < data.changes.length; i++) {
      destination.push({
        change: data.changes[i],
        author: author,
        version: serverVersion,
        versionKey: versionKey,
      });
    }

    if (!deferVersion) {
      // Debounce: wait 300ms for more changes before applying batch
      if (_applyTimer) clearTimeout(_applyTimer);
      _applyTimer = setTimeout(function () {
        var batch = _pendingBatch.slice();
        _pendingBatch = [];
        _applyTimer = null;
        applyBatchRemoteChanges(batch);
      }, 300);
    }
  }

  function fetchFullContent(mountId, path, expectedVersion) {
    if (!API || !window._vditor) return;
    API.getFile(mountId, path)
      .then(function (result) {
        if (!result || result.content === undefined) return;

        var resultVersion = Number(result.version);
        var currentVersion = window.state ? Number(state.baseVersion) || 0 : 0;
        if (
          !Number.isFinite(resultVersion) ||
          resultVersion < (Number(expectedVersion) || 0) ||
          resultVersion < currentVersion
        ) {
          return;
        }
        if (state.currentMountId !== mountId || state.currentPath !== path) return;

        if (window.state && window.state.dirty) {
          state.pendingRemoteUpdate = true;
          if (window.showToast) {
            window.showToast('检测到远端有更新，本地有未保存内容，将在下次保存时合并', 'info');
          }
          return;
        }

        var key = mountId + ':' + path;
        if (_applyTimer) clearTimeout(_applyTimer);
        _applyTimer = null;
        _pendingBatch = [];
        _pendingUpdates = [];
        _queuedVersions[key] = resultVersion;

        // Update version metadata
        if (window.state) {
          if (result.version !== undefined) {
            state.baseVersion = result.version;
            if (state.fileVersions) {
              state.fileVersions[key] = result.version;
            }
          }
        }

        _applyingRemote = true;
        window._vditor.setValue(result.content);
        window._originalContent = result.content;
        if (window.state) {
          state.baseContent = result.content;
          state.pendingRemoteUpdate = false;
          window._lastSavedContent = result.content;
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

    var key = data.mountId + ':' + data.path;
    var currentVersion = Math.max(
      Number(state.baseVersion) || 0,
      Number(_queuedVersions[key]) || 0,
    );
    var serverVersion = Number(data.newVersion) || 0;
    if (serverVersion <= currentVersion) return;
    if (state.dirty) {
      state.pendingRemoteUpdate = true;
      window.showToast('文件已被外部修改，你的未保存编辑将在下次保存时合并', 'info');
      return;
    }
    if (serverVersion > currentVersion + 1) {
      fetchFullContent(data.mountId, data.path, serverVersion);
      return;
    }

    // Update version state regardless of whether we reload
    if (serverVersion) {
      state.baseVersion = serverVersion;
      if (state.fileVersions) {
        state.fileVersions[key] = serverVersion;
      }
    }

    // No unsaved edits — reload the editor with the new content
    if (data.content !== undefined && window._vditor) {
      if (_applyTimer) clearTimeout(_applyTimer);
      _applyTimer = null;
      _pendingBatch = [];
      _pendingUpdates = [];
      _queuedVersions[key] = serverVersion;
      _applyingRemote = true;
      window._vditor.setValue(data.content);
      window._originalContent = data.content;
      state.baseContent = data.content;
      state.pendingRemoteUpdate = false;
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
    applyRemoteChange: applyRemoteChange,
    applyChangesToContent: applyChangesToContent,
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
