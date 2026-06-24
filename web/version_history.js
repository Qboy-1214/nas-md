/**
 * version_history.js - Version history panel for collaborative editing
 *
 * Shows recent edits with timestamp, author, and diff summary.
 * Allows viewing/restoring previous versions.
 */
(function () {
  'use strict';

  var _panel = null;
  var _currentFileKey = null;

  function createPanel() {
    if (_panel) return _panel;

    _panel = document.createElement('div');
    _panel.id = 'version-history-panel';
    _panel.style.cssText =
      'position:fixed;top:0;right:-420px;width:400px;height:100vh;background:#fff;' +
      'box-shadow:-2px 0 12px rgba(0,0,0,0.15);z-index:10000;transition:right 0.3s;' +
      'display:flex;flex-direction:column;font-family:system-ui,sans-serif;';

    _panel.innerHTML =
      '<div style="padding:14px 18px;border-bottom:1px solid #e0e0e0;display:flex;justify-content:space-between;align-items:center;background:#f8f9fa;">' +
      '<h3 style="margin:0;font-size:16px;color:#333;">版本历史</h3>' +
      '<button id="vh-close" style="border:none;background:none;font-size:20px;cursor:pointer;color:#666;padding:4px 8px;">&times;</button>' +
      '</div>' +
      '<div id="vh-list" style="flex:1;overflow-y:auto;padding:8px 0;">' +
      '<div style="padding:40px 20px;text-align:center;color:#999;">点击刷新加载历史记录</div>' +
      '</div>' +
      '<div style="padding:10px 18px;border-top:1px solid #e0e0e0;background:#f8f9fa;">' +
      '<button id="vh-refresh" style="width:100%;padding:8px;background:#3498db;color:white;border:none;border-radius:4px;cursor:pointer;font-size:14px;">刷新历史</button>' +
      '</div>';

    document.body.appendChild(_panel);

    document.getElementById('vh-close').addEventListener('click', hide);
    document.getElementById('vh-refresh').addEventListener('click', function () {
      loadHistory();
    });

    return _panel;
  }

  function show(fileKey) {
    _currentFileKey = fileKey;
    createPanel();
    _panel.style.right = '0';
    loadHistory();
  }

  function hide() {
    if (_panel) {
      _panel.style.right = '-420px';
    }
  }

  function isVisible() {
    return _panel && _panel.style.right === '0';
  }

  function loadHistory() {
    if (!_currentFileKey) return;

    var listEl = document.getElementById('vh-list');
    if (listEl) {
      listEl.innerHTML =
        '<div style="padding:40px 20px;text-align:center;color:#999;">加载中...</div>';
    }

    var url = '/api/history?file=' + encodeURIComponent(_currentFileKey) + '&limit=20';

    fetch(url)
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        renderHistory(data.versions || []);
      })
      .catch(function (err) {
        if (listEl) {
          listEl.innerHTML =
            '<div style="padding:20px;color:#e74c3c;">加载失败: ' +
            escapeHtml(err.message) +
            '</div>';
        }
      });
  }

  function renderHistory(versions) {
    var listEl = document.getElementById('vh-list');
    if (!listEl) return;

    if (versions.length === 0) {
      listEl.innerHTML =
        '<div style="padding:40px 20px;text-align:center;color:#999;">暂无编辑历史</div>';
      return;
    }

    var html = '';
    for (var i = 0; i < versions.length; i++) {
      var v = versions[i];
      var date = new Date(v.timestamp * 1000);
      var timeStr =
        date.getMonth() +
        1 +
        '/' +
        date.getDate() +
        ' ' +
        String(date.getHours()).padStart(2, '0') +
        ':' +
        String(date.getMinutes()).padStart(2, '0') +
        ':' +
        String(date.getSeconds()).padStart(2, '0');

      var changeSummary = '';
      for (var j = 0; j < v.changes.length; j++) {
        var c = v.changes[j];
        var action = '';
        switch (c.type) {
          case 'replace':
            action = '编辑';
            break;
          case 'insert':
            action = '新增';
            break;
          case 'delete':
            action = '删除';
            break;
        }
        changeSummary +=
          '<div style="font-size:12px;color:#666;margin-top:2px;">' +
          action +
          '第' +
          (c.paraIdx + 1) +
          '段' +
          (c.content
            ? '：' + escapeHtml(c.content.substring(0, 40)) + (c.content.length > 40 ? '...' : '')
            : '') +
          '</div>';
      }

      html +=
        '<div class="vh-item" data-version="' +
        i +
        '" style="padding:12px 18px;border-bottom:1px solid #f0f0f0;cursor:pointer;transition:background 0.2s;" onmouseover="this.style.background=\'#f5f6f7\'" onmouseout="this.style.background=\'transparent\'">' +
        '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">' +
        '<div style="width:24px;height:24px;border-radius:50%;background:' +
        v.authorColor +
        ';color:white;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:bold;flex-shrink:0;">' +
        escapeHtml((v.authorName || '?').charAt(0).toUpperCase()) +
        '</div>' +
        '<span style="font-weight:500;color:#333;font-size:13px;">' +
        escapeHtml(v.authorName || 'Anonymous') +
        '</span>' +
        '<span style="font-size:12px;color:#999;margin-left:auto;">' +
        timeStr +
        '</span>' +
        '</div>' +
        changeSummary +
        '<div style="font-size:11px;color:#aaa;margin-top:4px;">' +
        v.contentLength +
        ' 字符</div>' +
        '</div>';
    }

    listEl.innerHTML = html;

    // Add click handlers for version items
    var items = listEl.querySelectorAll('.vh-item');
    for (var k = 0; k < items.length; k++) {
      items[k].addEventListener('click', function () {
        var versionIdx = parseInt(this.getAttribute('data-version'));
        viewVersion(versionIdx);
      });
    }
  }

  function viewVersion(versionIdx) {
    if (!_currentFileKey) return;

    var url = '/api/history?file=' + encodeURIComponent(_currentFileKey) + '&version=' + versionIdx;

    fetch(url)
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        if (data.content) {
          // Use previousContent from API for diff (version vs its previous version)
          // If no previous version, diff against empty string (everything is new)
          var prevContent = data.previousContent || '';
          showVersionPreview(data.content, versionIdx, prevContent, data);
        }
      })
      .catch(function (err) {
        console.error('Version load failed:', err);
      });
  }

  // === Simple line-level diff using LCS ===

  function computeLineDiff(oldText, newText) {
    var oldLines = oldText.split('\n');
    var newLines = newText.split('\n');
    var m = oldLines.length;
    var n = newLines.length;

    // Build LCS table
    var dp = [];
    for (var i = 0; i <= m; i++) {
      dp[i] = new Array(n + 1).fill(0);
    }
    for (var i = m - 1; i >= 0; i--) {
      for (var j = n - 1; j >= 0; j--) {
        if (oldLines[i] === newLines[j]) {
          dp[i][j] = dp[i + 1][j + 1] + 1;
        } else {
          dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1]);
        }
      }
    }

    // Backtrack to build diff
    var result = [];
    var i = 0,
      j = 0;
    while (i < m && j < n) {
      if (oldLines[i] === newLines[j]) {
        result.push({ type: 'equal', oldLine: oldLines[i], newLine: newLines[j] });
        i++;
        j++;
      } else if (dp[i + 1][j] >= dp[i][j + 1]) {
        result.push({ type: 'delete', oldLine: oldLines[i], newLine: null });
        i++;
      } else {
        result.push({ type: 'insert', oldLine: null, newLine: newLines[j] });
        j++;
      }
    }
    while (i < m) {
      result.push({ type: 'delete', oldLine: oldLines[i], newLine: null });
      i++;
    }
    while (j < n) {
      result.push({ type: 'insert', oldLine: null, newLine: newLines[j] });
      j++;
    }
    return result;
  }

  function renderDiffHTML(diff) {
    var html = '';
    var oldLineNum = 0;
    var newLineNum = 0;
    for (var i = 0; i < diff.length; i++) {
      var d = diff[i];
      if (d.type === 'equal') {
        oldLineNum++;
        newLineNum++;
        html +=
          '<div class="vh-diff-equal"><span class="vh-line-num">' +
          newLineNum +
          '</span><span class="vh-diff-content">' +
          escapeHtml(d.newLine) +
          '</span></div>';
      } else if (d.type === 'insert') {
        newLineNum++;
        html +=
          '<div class="vh-diff-insert"><span class="vh-diff-sign">+</span><span class="vh-line-num">' +
          newLineNum +
          '</span><span class="vh-diff-content">' +
          escapeHtml(d.newLine) +
          '</span></div>';
      } else if (d.type === 'delete') {
        oldLineNum++;
        html +=
          '<div class="vh-diff-delete"><span class="vh-diff-sign">-</span><span class="vh-line-num">' +
          oldLineNum +
          '</span><span class="vh-diff-content">' +
          escapeHtml(d.oldLine) +
          '</span></div>';
      }
    }
    return html;
  }

  function renderPlainContent(text) {
    var lines = text.split('\n');
    var html = '';
    for (var i = 0; i < lines.length; i++) {
      html +=
        '<div class="vh-plain-line"><span class="vh-line-num">' +
        (i + 1) +
        '</span><span class="vh-plain-content">' +
        escapeHtml(lines[i]) +
        '</span></div>';
    }
    return html;
  }

  function showVersionPreview(versionContent, versionIdx, previousContent, versionMeta) {
    // Create or update preview modal
    var modal = document.getElementById('vh-preview-modal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'vh-preview-modal';
      modal.style.cssText =
        'position:fixed;top:0;left:0;width:100vw;height:100vh;background:rgba(0,0,0,0.5);z-index:10001;display:flex;align-items:center;justify-content:center;';
      document.body.appendChild(modal);
    }

    // Compute diff: previousContent -> versionContent (what this edit changed)
    var hasPrev = previousContent && previousContent !== '';
    var diff,
      diffHTML,
      insertCount = 0,
      deleteCount = 0;

    if (hasPrev) {
      diff = computeLineDiff(previousContent, versionContent);
      diffHTML = renderDiffHTML(diff);
      for (var i = 0; i < diff.length; i++) {
        if (diff[i].type === 'insert') insertCount++;
        if (diff[i].type === 'delete') deleteCount++;
      }
    } else {
      // No previous version: show content as plain text (not as all-new)
      diff = [];
      diffHTML = renderPlainContent(versionContent);
    }

    // Build author info
    var authorName = (versionMeta && versionMeta.authorName) || 'Unknown';
    var authorColor = (versionMeta && versionMeta.authorColor) || '#3498db';
    var timeStr = '';
    if (versionMeta && versionMeta.timestamp) {
      var date = new Date(versionMeta.timestamp * 1000);
      timeStr =
        date.getMonth() +
        1 +
        '/' +
        date.getDate() +
        ' ' +
        String(date.getHours()).padStart(2, '0') +
        ':' +
        String(date.getMinutes()).padStart(2, '0') +
        ':' +
        String(date.getSeconds()).padStart(2, '0');
    }

    var statsHTML = hasPrev
      ? '<span style="margin-left:12px;font-size:12px;color:#27ae60;">+' +
        insertCount +
        ' 行</span>' +
        '<span style="margin-left:6px;font-size:12px;color:#e74c3c;">-' +
        deleteCount +
        ' 行</span>'
      : '<span style="margin-left:12px;font-size:12px;color:#999;">无前序版本可对比</span>';

    modal.innerHTML =
      '<div style="background:white;width:90%;max-width:1000px;height:85vh;border-radius:8px;display:flex;flex-direction:column;overflow:hidden;">' +
      '<div style="padding:14px 20px;border-bottom:1px solid #e0e0e0;display:flex;justify-content:space-between;align-items:center;background:#f8f9fa;">' +
      '<div>' +
      '<h3 style="margin:0;font-size:16px;display:inline-block;">版本预览 #' +
      (versionIdx + 1) +
      '</h3>' +
      '<span style="margin-left:12px;font-size:13px;color:#666;">' +
      (hasPrev ? '与上一版本对比' : '初始版本') +
      '</span>' +
      '<span style="margin-left:8px;font-size:12px;color:' +
      authorColor +
      ';">' +
      escapeHtml(authorName) +
      '</span>' +
      '<span style="margin-left:8px;font-size:12px;color:#999;">' +
      timeStr +
      '</span>' +
      statsHTML +
      '</div>' +
      '<div style="display:flex;gap:8px;align-items:center;">' +
      (hasPrev
        ? '<label style="font-size:13px;color:#666;cursor:pointer;display:flex;align-items:center;gap:4px;">' +
          '<input type="checkbox" id="vh-toggle-view" onchange="window.__vhToggleView(this.checked)" /> 仅看差异' +
          '</label>'
        : '') +
      '<button id="vh-restore" style="padding:6px 16px;background:#27ae60;color:white;border:none;border-radius:4px;cursor:pointer;font-size:13px;">恢复此版本</button>' +
      '<button id="vh-preview-close" style="padding:6px 16px;background:#95a5a6;color:white;border:none;border-radius:4px;cursor:pointer;font-size:13px;">关闭</button>' +
      '</div>' +
      '</div>' +
      '<div id="vh-diff-container" style="flex:1;overflow:auto;padding:0;font-family:Consolas,Monaco,monospace;font-size:13px;line-height:1.6;">' +
      '<style>' +
      '.vh-diff-equal, .vh-diff-insert, .vh-diff-delete, .vh-plain-line { display:flex; align-items:flex-start; }' +
      '.vh-line-num { display:inline-block; width:40px; min-width:40px; padding:1px 6px; text-align:right; color:#aaa; font-size:11px; user-select:none; border-right:1px solid #e0e0e0; margin-right:8px; flex-shrink:0; }' +
      '.vh-diff-sign { display:inline-block; width:14px; min-width:14px; font-weight:bold; color:inherit; flex-shrink:0; }' +
      '.vh-diff-content, .vh-plain-content { flex:1; white-space:pre-wrap; word-break:break-word; }' +
      '.vh-diff-equal { padding:1px 20px 1px 0; color:#999; }' +
      '.vh-diff-insert { padding:1px 20px 1px 0; background:rgba(39,174,96,0.12); border-left:3px solid #27ae60; color:#1a6b3a; }' +
      '.vh-diff-delete { padding:1px 20px 1px 0; background:rgba(231,76,60,0.12); border-left:3px solid #e74c3c; color:#8b2a1f; text-decoration:line-through; text-decoration-color:rgba(231,76,60,0.5); }' +
      '.vh-plain-line { padding:1px 20px 1px 0; color:#333; }' +
      '</style>' +
      diffHTML +
      '</div>' +
      '</div>';

    // Store diff data for toggle
    window.__vhDiffData = diff;

    document.getElementById('vh-preview-close').addEventListener('click', function () {
      modal.style.display = 'none';
    });
    document.getElementById('vh-restore').addEventListener('click', function () {
      if (window._vditor && confirm('确定要恢复到这个版本吗？当前内容将被覆盖。')) {
        window._vditor.setValue(versionContent);
        window._originalContent = versionContent;
        // Trigger save
        if (window.saveContent) {
          window.saveContent();
        } else if (window.debouncedSave) {
          window.debouncedSave();
        }
        modal.style.display = 'none';
      }
    });

    modal.style.display = 'flex';
  }

  // Toggle: show only differences
  window.__vhToggleView = function (onlyDiff) {
    var container = document.getElementById('vh-diff-container');
    if (!container) return;
    var equals = container.querySelectorAll('.vh-diff-equal');
    for (var i = 0; i < equals.length; i++) {
      equals[i].style.display = onlyDiff ? 'none' : '';
    }
  };

  function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
  }

  // Expose
  window.nasmdHistory = {
    show: show,
    hide: hide,
    isVisible: isVisible,
    loadHistory: loadHistory,
  };
})();
