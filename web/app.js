/**
 * app.js - 应用主逻辑（原生 JS，无框架）
 */

// === 状态 ===
const state = {
  mounts: [],
  expandedMounts: [],
  treeData: {},
  currentPath: null,
  currentMountId: null,
  editorMode: 'ir',
  dirty: false,
  searchResults: [],
  recentFiles: [],
  accessLog: JSON.parse(localStorage.getItem('nasmd_access_log') || '{}'), // path -> timestamp
  toastTimer: null,
  syncStatus: 'offline', // offline | synced | syncing | conflict
  syncTimer: null,
  lastSyncTime: 0,
  isAdmin: window.location.pathname.startsWith('/admin') || window.location.hash === '#admin',
  dockerMode: false,
};

// === DOM 引用 ===
const $ = (id) => document.getElementById(id);

// === 初始化 ===
document.addEventListener('DOMContentLoaded', async () => {
  // Load runtime config (e.g. Docker mode)
  try {
    const cfg = await API.getConfig();
    if (cfg) state.dockerMode = cfg.docker_mode === true;
  } catch (_e) { /* ignore */ }
  await loadMounts();
  await loadRecentFiles();
  // Restore last opened file, or fall back to welcome.md
  const lastPath = localStorage.getItem('nasmd_last_path');
  const lastMountId = localStorage.getItem('nasmd_last_mount');
  if (lastPath && lastMountId) {
    const mount = state.mounts.find((m) => m.id === lastMountId);
    if (mount) {
      try {
        const content = await API.getFile(mount.id, lastPath);
        if (content !== null) {
          state.currentPath = lastPath;
          state.currentMountId = mount.id;
          state.searchResults = [];
          $('breadcrumb').textContent = lastPath + (mount.readonly ? ' 🔒' : '');
          $('editor-modes').style.display = mount.readonly
            ? 'none'
            : lastPath.endsWith('.md')
              ? ''
              : 'none';
          $('save-group').style.display = mount.readonly ? 'none' : '';
          showPage('editor');
          if (window._vditor) window._vditor.destroy();
          initEditor(content, state.editorMode, !!mount.readonly);
          setFileInfo(mount.id, lastPath);
          state.dirty = false;
          startDirtyCheck();
          // Expand sidebar to show the current file
          if (!state.expandedMounts.includes(mount.id)) {
            state.expandedMounts.push(mount.id);
          }
          // Expand all parent directories in the path
          const dirParts = lastPath.split('/').filter(Boolean);
          const dirsToExpand = [];
          for (let i = 1; i < dirParts.length; i++) {
            const dirPath = '/' + dirParts.slice(0, i).join('/');
            dirsToExpand.push(dirPath);
          }
          // Load tree data sequentially for each directory level, then render
          (async () => {
            await loadTree(mount.id, '/');
            // Also load builtin-storage tree so welcome.md shows in sidebar
            const builtin = state.mounts.find((m) => m.id === 'builtin-storage');
            if (builtin && !state.treeData[builtin.id]) {
              await loadTree(builtin.id, '/');
            }
            for (const dp of dirsToExpand) {
              const dirKey = `${mount.id}:${dp}`;
              if (!state.expandedMounts.includes(dirKey)) {
                state.expandedMounts.push(dirKey);
              }
              await loadTree(mount.id, dp);
            }
            renderSidebar();
          })();
          renderSidebar();
          return;
        }
      } catch (e) {
        console.error('Failed to restore last file:', e);
      }
      // File no longer exists, clear stale state
      localStorage.removeItem('nasmd_last_path');
      localStorage.removeItem('nasmd_last_mount');
    }
  }
  // Fallback: open welcome.md from builtin mount
  const builtin = state.mounts.find((m) => m.id === 'builtin-storage');
  if (builtin) {
    if (!state.treeData[builtin.id]) {
      await loadTree(builtin.id, '/');
    }
    const root = state.treeData[builtin.id]?.['/'];
    if (root) {
      const welcome = (root.children || []).find((e) => e.name === '欢迎.md');
      if (welcome) openFile(welcome.path, builtin.id);
    }
  }
});

// === UI 更新 ===
function showPage(page) {
  $('welcome-page').style.display = page === 'welcome' ? '' : 'none';
  $('editor-container').style.display = page === 'editor' ? '' : 'none';
  $('graph-page').style.display = page === 'graph' ? '' : 'none';
  $('dashboard-page').style.display = page === 'dashboard' ? '' : 'none';
}

function showToast(msg) {
  const el = $('toast');
  el.textContent = msg;
  el.style.display = '';
  // Force reflow
  void el.offsetHeight;
  el.classList.add('show');
  if (state.toastTimer) clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => {
    el.classList.remove('show');
    setTimeout(() => {
      if (!el.classList.contains('show')) el.style.display = 'none';
    }, 200);
  }, 2500);
}

// === 挂载目录 ===
let _loadMountsBusy = false;
async function loadMounts() {
  if (_loadMountsBusy) return;
  _loadMountsBusy = true;
  try {
    state.mounts = await API.getMounts();
    renderSidebar();
    // Docker mode: hide browse button and show hint
    if (state.dockerMode) {
      const browseBtn = document.querySelector('.browse-btn');
      const dirPicker = $('dir-picker');
      const dirInput = $('new-dir-path');
      if (browseBtn) browseBtn.style.display = 'none';
      if (dirPicker) dirPicker.style.display = 'none';
      if (dirInput) dirInput.placeholder = 'Docker 模式下请通过 compose.yaml 配置挂载';
    }
  } catch (_e) {
    showToast('加载挂载点失败');
  } finally {
    _loadMountsBusy = false;
  }
}

// === 目录选择 ===

function chooseDirectory() {
  $('dir-picker').click();
}

function onDirPicked(event) {
  const files = event.target.files;
  if (!files || files.length === 0) return;

  let fullPath = null;
  let dirName = '';

  // 方式1：files[0].path（Chrome/Edge 桌面版非标准属性）
  const f = files[0];
  if (f.path) {
    const p = f.path;
    const idx = Math.max(p.lastIndexOf('/'), p.lastIndexOf('\\'));
    if (idx > 0) fullPath = p.substring(0, idx);
  }

  // 方式2：webkitRelativePath（标准属性，所有浏览器支持）
  if (!fullPath && f.webkitRelativePath) {
    dirName = f.webkitRelativePath.split('/')[0];
  }

  if (fullPath) {
    $('new-dir-path').value = fullPath;
  } else {
    const dirName = f.webkitRelativePath ? f.webkitRelativePath.split('/')[0] : '';
    if (dirName) {
      $('new-dir-path').value = '';
      $('new-dir-path').placeholder = `正在定位 "${dirName}"...`;
      API.findMountPath(dirName)
        .then((result) => {
          if (result && result.path) {
            $('new-dir-path').value = result.path;
            showToast(`已定位: ${result.path}`);
          } else {
            $('new-dir-path').placeholder =
              `无法自动定位，请输入完整路径（如 D:\\xxx\\${dirName}）`;
            showToast(`无法自动定位 "${dirName}"，请手动输入完整路径`);
          }
        })
        .catch(() => {
          $('new-dir-path').placeholder = `无法自动定位，请输入完整路径（如 D:\\xxx\\${dirName}）`;
          showToast(`无法自动定位 "${dirName}"，请手动输入完整路径`);
        });
    }
  }

  $('new-dir-path').focus();
  event.target.value = '';
}

async function openDirectory() {
  const dirPath = $('new-dir-path').value.trim();
  if (!dirPath) {
    showToast('请输入目录路径或点击浏览选择');
    return;
  }
  try {
    const resp = await API.addMount(dirPath, '');
    if (resp && resp.id) {
      showToast(`已挂载: ${resp.name || resp.path}`);
      $('new-dir-path').value = '';
      $('new-dir-path').placeholder = '输入目录路径';
      await loadMounts();
    } else {
      const errMsg = resp?.error || '';
      if (errMsg.includes('Not a valid directory')) {
        showToast('目录不存在，请检查路径是否正确');
      } else {
        showToast('挂载失败: ' + errMsg);
      }
    }
  } catch (e) {
    showToast('挂载失败: ' + (e.message || '未知错误'));
  }
}

async function toggleMountPublic(mountId, isPublic) {
  try {
    const resp = await API.updateMount(mountId, { public: isPublic });
    if (resp && resp.id) {
      const idx = state.mounts.findIndex((m) => m.id === mountId);
      if (idx >= 0) state.mounts[idx].public = isPublic;
      renderSidebar();
      showToast(isPublic ? '已设为公开' : '已设为私有');
    }
  } catch (_e) {
    showToast('操作失败');
  }
}

// === 文件树 ===

// 挂载点展开/折叠
async function toggleMount(mountId) {
  const idx = state.expandedMounts.indexOf(mountId);
  if (idx >= 0) {
    state.expandedMounts.splice(idx, 1);
  } else {
    state.expandedMounts.push(mountId);
    await loadTree(mountId, '/');
  }
  renderSidebar();
}

// 子目录展开/折叠（不关闭挂载点）
async function toggleDir(mountId, dirPath) {
  const key = `${mountId}:${dirPath}`;
  const idx = state.expandedMounts.indexOf(key);
  if (idx >= 0) {
    state.expandedMounts.splice(idx, 1);
  } else {
    state.expandedMounts.push(key);
    await loadTree(mountId, dirPath);
  }
  renderSidebar();
}

async function loadTree(mountId, path) {
  if (!state.treeData[mountId]) state.treeData[mountId] = {};
  // Skip if already loaded
  if (state.treeData[mountId][path]) return;
  try {
    const tree = await API.getTree(mountId, path);
    // Store the root entry; renderEntries will use .children
    state.treeData[mountId][path] = tree;
  } catch (e) {
    console.error('Failed to load tree:', e);
  }
}

// 卸载挂载点
async function removeMount(mountId) {
  // Cannot delete builtin mount
  const mount = state.mounts.find((m) => m.id === mountId);
  if (mount && mount.id === 'builtin-storage') {
    showToast('内置目录不能卸载');
    return;
  }
  try {
    const headers = {};
    if (state.isAdmin) headers['X-Admin'] = '1';
    const resp = await fetch(`${_apiBase}/api/mounts/${mountId}`, {
      method: 'DELETE',
      headers,
    });
    if (resp.ok) {
      // Backend successfully deleted
    } else if (resp.status === 401) {
      showToast('请先登录再卸载');
      return;
    }
    // 404 / 401 handled: always clean up frontend state
    state.mounts = state.mounts.filter((m) => m.id !== mountId);
    delete state.treeData[mountId];
    state.expandedMounts = state.expandedMounts.filter(
      (id) => id !== mountId && !id.startsWith(`${mountId}:`),
    );
    // Clean up access log entries for the unmounted directory
    for (const key of Object.keys(state.accessLog)) {
      if (key.startsWith(mountId + ':')) {
        delete state.accessLog[key];
      }
    }
    localStorage.setItem('nasmd_access_log', JSON.stringify(state.accessLog));
    if (state.currentMountId === mountId) {
      state.currentPath = null;
      state.currentMountId = null;
      if (window._vditor) {
        window._vditor.destroy();
        window._vditor = null;
      }
      showPage('welcome');
    }
    renderSidebar();
    loadRecentFiles();
    showToast('已卸载');
  } catch (_e) {
    // Network error: still clean up frontend
    state.mounts = state.mounts.filter((m) => m.id !== mountId);
    delete state.treeData[mountId];
    state.expandedMounts = state.expandedMounts.filter(
      (id) => id !== mountId && !id.startsWith(`${mountId}:`),
    );
    renderSidebar();
    showToast('已卸载（本地）');
  }
}

function renderSidebar() {
  const tree = $('file-tree');
  tree.innerHTML = '';

  // SVG icon templates
  const svgFolder = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--c-steel)" stroke-width="1.5"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>`;
  const svgFile = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--c-steel)" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>`;
  const svgLock = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--c-muted)" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>`;

  // Built-in files shown at root level (not nested under a mount point)
  const builtin = state.mounts.find((m) => m.id === 'builtin-storage');
  const builtinRoot = builtin ? state.treeData[builtin.id]?.['/'] : null;
  const builtinEntries = builtinRoot?.children || null;
  if (builtinEntries) {
    const items = builtinEntries
      .filter((e) => !e.name.startsWith('.') && e.name !== 'mounts.json')
      .sort((a, b) => {
        if (a.isDir && !b.isDir) return -1;
        if (!a.isDir && b.isDir) return 1;
        return a.name.localeCompare(b.name);
      });
    for (const e of items) {
      const fullPath = e.path;
      const isActive = state.currentPath === fullPath;
      const icon = e.isDir ? svgFolder : svgFile;
      const cls = `tree-item builtin-file ${e.isDir ? 'folder' : ''} ${isActive ? 'active' : ''}`;
      tree.innerHTML += `<div class="${cls}" onclick="openFile('${fullPath}','${builtin.id}')">
        <span class="tree-icon">${icon}</span>
        <span title="${e.name}">${e.name}</span>
        <span class="mount-builtin-badge" title="内置只读">${svgLock}</span>
      </div>`;
    }
  }

  // Regular mount points
  const regularMounts = state.mounts.filter((m) => m.id !== 'builtin-storage');
  for (const mount of regularMounts) {
    const isExpanded = state.expandedMounts.includes(mount.id);
    const chevron = `<svg class="tree-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="transform:rotate(${isExpanded ? 90 : 0}deg);transition:transform 0.15s"><polyline points="9 18 15 12 9 6"/></svg>`;

    let html = `<div class="mount-group">`;
    html += `<div class="mount-name-row">`;
    html += `<div class="mount-name" onclick="toggleMount('${mount.id}')">`;
    html += `<span class="mount-icon">${chevron}</span>`;
    html += `<span>${mount.name}</span>`;
    html += `</div>`;
    html += `<span class="mount-path-hint" title="${mount.path}">${svgFolder} ${mount.path}</span>`;
    html += `<button class="mount-remove-btn" onclick="removeMount('${mount.id}')" title="卸载"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>`;
    html += `</div>`;

    if (isExpanded) {
      const treeData = state.treeData[mount.id]?.['/'];
      if (treeData) {
        html += renderEntries(treeData.children || [], mount.id, '/');
      } else {
        html += '<div class="tree-loading">加载中...</div>';
        loadTree(mount.id, '/').then(() => renderSidebar());
      }
    }

    html += `</div>`;
    tree.innerHTML += html;
  }

  if (regularMounts.length === 0 && !builtinEntries) {
    tree.innerHTML = '<div class="tree-loading">暂无挂载目录</div>';
  }
}

function renderEntries(entries, mountId, _parentPath) {
  const items = entries
    .filter((e) => {
      if (e.name.startsWith('.')) return false;
      // Always show if hasMd flag is set (contains .md files in subtree)
      if (e.hasMd) return true;
      // Always show .md files themselves
      if (!e.isDir && e.name.toLowerCase().endsWith('.md')) return true;
      // Hide directories without .md files in their subtree
      return false;
    })
    .sort((a, b) => {
      if (a.isDir && !b.isDir) return -1;
      if (!a.isDir && b.isDir) return 1;
      return a.name.localeCompare(b.name);
    });

  // SVG icon templates
  const svgFolder = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--c-steel)" stroke-width="1.5"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>`;
  const svgFile = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--c-steel)" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>`;

  return items
    .map((e) => {
      const fullPath = e.path;
      const isActive = state.currentPath === fullPath;
      const icon = e.isDir ? svgFolder : svgFile;
      const cls = `tree-item ${e.isDir ? 'folder' : ''} ${isActive ? 'active' : ''}`;

      if (e.isDir) {
        const dirKey = `${mountId}:${fullPath}`;
        const isDirExpanded = state.expandedMounts.includes(dirKey);
        const subEntries = state.treeData[mountId]?.[fullPath];
        const chevron = `<svg class="tree-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="transform:rotate(${isDirExpanded ? 90 : 0}deg);transition:transform 0.15s"><polyline points="9 18 15 12 9 6"/></svg>`;

        let html = `<div>`;
        html += `<div class="${cls}" onclick="toggleDir('${mountId}','${fullPath}')">`;
        html += `<span class="tree-icon">${chevron}</span>`;
        html += `<span class="tree-folder" title="${e.name}">${e.name}</span>`;
        html += `</div>`;

        if (isDirExpanded) {
          if (subEntries) {
            html += `<div class="tree-sub">${renderEntries(subEntries.children || [], mountId, fullPath)}</div>`;
          } else {
            html += '<div class="tree-loading">加载中...</div>';
            loadTree(mountId, fullPath).then(() => renderSidebar());
          }
        }

        html += `</div>`;
        return html;
      }

      return `<div class="${cls}" onclick="openFile('${fullPath}','${mountId}')">
      <span class="tree-icon">${icon}</span>
      <span title="${e.name}">${e.name}</span>
    </div>`;
    })
    .join('');
}

// === 文件操作 ===

// Find which mount a file path belongs to (recursive tree search)
function findMountForPath(path) {
  for (const m of state.mounts) {
    const tree = state.treeData[m.id]?.['/'];
    if (tree && _treeHasPath(tree, path)) return m;
  }
  return null;
}

function _treeHasPath(entry, path) {
  if (entry.path === path) return true;
  if (entry.children) {
    for (const c of entry.children) {
      if (_treeHasPath(c, path)) return true;
    }
  }
  return false;
}

async function openFile(path, preferredMountId, searchKeyword) {
  let mount = null;
  // 1. Try preferred mount id (from sidebar click or restore)
  if (preferredMountId) {
    mount = state.mounts.find((m) => m.id === preferredMountId);
  }
  // 2. Try current mount
  if (!mount && state.currentMountId) {
    mount = state.mounts.find((m) => m.id === state.currentMountId);
  }
  // 3. Search treeData
  if (!mount) {
    mount = findMountForPath(path);
  }
  // 4. Fallback to first mount
  if (!mount && state.mounts.length > 0) {
    mount = state.mounts[0];
  }
  if (!mount) {
    showToast('无法确定文件的挂载点');
    return;
  }

  try {
    const content = await API.getFile(mount.id, path);
    if (content === null) {
      showToast('文件加载失败，请查看浏览器控制台获取详情');
      return;
    }
    state.currentPath = path;
    state.currentMountId = mount.id;
    state.searchResults = [];
    localStorage.setItem('nasmd_last_path', path);
    localStorage.setItem('nasmd_last_mount', mount.id);

    // Record access time for "recent files"
    const accessKey = mount.id + ':' + path;
    state.accessLog[accessKey] = Date.now();
    localStorage.setItem('nasmd_access_log', JSON.stringify(state.accessLog));

    $('breadcrumb').textContent = path + (mount.readonly ? ' (只读)' : '');
    $('editor-modes').style.display = mount.readonly ? 'none' : path.endsWith('.md') ? '' : 'none';
    $('save-group').style.display = mount.readonly ? 'none' : '';
    showPage('editor');

    if (window._vditor) window._vditor.destroy();
    // Check for offline draft
    const draft = loadFromLocalStorage(path);
    const finalContent = draft ? draft.content : content;
    if (draft) {
      showToast('已恢复本地缓存版本');
    }
    initEditor(finalContent, state.editorMode, !!mount.readonly);
    setFileInfo(mount.id, path);
    state.dirty = false;
    startDirtyCheck();
    renderSidebar();
    loadBacklinks(path);
    startSyncPolling();

    // If opened from search, scroll to the keyword
    if (searchKeyword) {
      _scrollToKeyword(searchKeyword);
    }
  } catch (e) {
    showToast('加载文件失败');
    console.error(e);
  }
}

// Scroll to keyword in editor after opening a file from search
function _scrollToKeyword(keyword) {
  if (!keyword || !window._vditor) return;
  // Wait for editor to finish rendering
  setTimeout(() => {
    try {
      // Try Vditor's built-in search (Ctrl+F) and highlight
      const vditorEl = document.getElementById('vditor');
      if (!vditorEl) return;
      // In WYSIWYG mode, search the DOM for the keyword
      const contentEl =
        vditorEl.querySelector('.vditor-wysiwyg') || vditorEl.querySelector('.vditor-sv');
      if (!contentEl) return;
      const walker = document.createTreeWalker(contentEl, NodeFilter.SHOW_TEXT);
      let firstMatch = null;
      while (walker.nextNode()) {
        const node = walker.currentNode;
        const idx = node.textContent.indexOf(keyword);
        if (idx !== -1) {
          firstMatch = node;
          break;
        }
      }
      if (firstMatch && firstMatch.parentElement) {
        firstMatch.parentElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
        // Highlight the match briefly
        firstMatch.parentElement.style.backgroundColor = '#fff3b0';
        setTimeout(() => {
          firstMatch.parentElement.style.backgroundColor = '';
        }, 3000);
      }
    } catch (e) {
      console.warn('Scroll to keyword failed:', e);
    }
  }, 500);
}

function startDirtyCheck() {
  if (window._dirtyTimer) clearInterval(window._dirtyTimer);
  window._dirtyTimer = setInterval(() => {
    if (window._vditor) {
      const isDirty = window._vditor.getValue() !== window._originalContent;
      if (isDirty !== state.dirty) {
        state.dirty = isDirty;
        const btn = $('btn-save');
        if (btn) btn.classList.toggle('dirty', isDirty);
        // Auto-save trigger
        if (isDirty && state.autoSave) scheduleAutoSave();
      }
    }
  }, 500);
}

// === Auto-save ===
state.autoSave = localStorage.getItem('nasmd_autosave') === '1';

function toggleAutoSave(on) {
  state.autoSave = on;
  localStorage.setItem('nasmd_autosave', on ? '1' : '0');
  if (!on && window._autoSaveTimer) {
    clearTimeout(window._autoSaveTimer);
    window._autoSaveTimer = null;
  }
}

function scheduleAutoSave() {
  if (window._autoSaveTimer) clearTimeout(window._autoSaveTimer);
  window._autoSaveTimer = setTimeout(() => {
    if (state.dirty && state.autoSave && state.currentPath) {
      saveFile({ silent: true });
    }
    window._autoSaveTimer = null;
  }, 3000);
}

// Restore auto-save switch state on load
document.addEventListener('DOMContentLoaded', () => {
  const sw = $('autosave-switch');
  if (sw) sw.checked = state.autoSave;
});

function markDirty() {
  state.dirty = true;
  const btn = $('btn-save');
  if (btn) btn.classList.add('dirty');
}

function markClean() {
  state.dirty = false;
  const btn = $('btn-save');
  if (btn) btn.classList.remove('dirty');
}

// === 侧边栏折叠（移动端） ===
function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('open');
}

// === 暗色模式 ===
if (localStorage.getItem('nasmd_dark') === '1') {
  document.documentElement.classList.add('dark');
}

function toggleDarkMode() {
  const isDark = document.documentElement.classList.toggle('dark');
  localStorage.setItem('nasmd_dark', isDark ? '1' : '0');
  // Sync Vditor content theme
  if (window._vditor) {
    window._vditor.setContentTheme(
      isDark ? 'dark' : 'light',
      '/lib/vditor-cdn/dist/css/content-theme',
    );
    window._vditor.setTheme(
      isDark ? 'dark' : 'classic',
      isDark ? 'dark' : 'classic',
      isDark ? 'dracula' : 'github',
    );
  }
}

async function loadBacklinks(page) {
  const panel = $('backlinks-panel');
  const content = $('backlinks-content');
  const title = $('backlinks-title');
  if (!panel || !page.endsWith('.md')) {
    if (panel) panel.style.display = 'none';
    return;
  }
  try {
    const data = await API.getBacklinks(page);
    const bls = data.backlinks || [];
    if (bls.length === 0) {
      panel.style.display = 'none';
      return;
    }
    title.textContent = `反向链接 (${bls.length})`;
    content.innerHTML = bls
      .map(
        (bl) =>
          `<div class="backlink-item" onclick="openFile('${bl.path.replace(/'/g, "\\'")}')">
        <span class="backlink-page">${bl.title || bl.path}</span>
        <span class="backlink-line">第 ${bl.line} 行</span>
      </div>`,
      )
      .join('');
    panel.style.display = '';
    panel.classList.remove('collapsed');
  } catch (e) {
    console.error('Backlinks error:', e);
    panel.style.display = 'none';
  }
}

function toggleBacklinks() {
  const panel = $('backlinks-panel');
  if (panel) panel.classList.toggle('collapsed');
}

async function saveFile({ silent = false } = {}) {
  if (!state.currentPath || !state.currentMountId || !window._vditor) return;
  // Check if current mount is readonly
  const mount = state.mounts.find((m) => m.id === state.currentMountId);
  if (mount && mount.readonly) {
    if (!silent) showToast('此文件不允许修改');
    return;
  }
  const content = window._vditor.getValue();

  // Show saving state on button (only for manual save)
  const btn = $('btn-save');
  if (!silent && btn) {
    btn.classList.add('saving');
    btn.disabled = true;
  }

  if (!navigator.onLine) {
    // Offline: save to localStorage
    saveToLocalStorage(state.currentPath, content);
    markClean();
    if (!silent) {
      showToast('已离线保存，恢复连接后自动同步');
      btn.classList.remove('saving');
      btn.disabled = false;
    }
    return;
  }

  try {
    const resp = await API.putFile(state.currentMountId, state.currentPath, content);
    if (resp && resp.error) {
      throw new Error(resp.error);
    }
    window._originalContent = content;
    markClean();
    clearLocalStorage(state.currentPath);
    if (!silent) showToast('已保存');
    else showToast('自动保存完成');
    // Trigger sync after save
    performSync();
  } catch (e) {
    // Fallback to localStorage on error
    saveToLocalStorage(state.currentPath, content);
    if (!silent) showToast('保存失败，已缓存到本地');
    else showToast('自动保存失败');
    console.error(e);
  } finally {
    if (!silent && btn) {
      btn.classList.remove('saving');
      btn.disabled = false;
    }
  }
}

function confirmNewFile() {
  const name = $('new-file-name').value.trim();
  if (!name) return;
  hideNewFile();
  // 简化：在第一个挂载点根目录创建
  const mount = state.mounts[0];
  if (!mount) {
    showToast('请先打开一个目录');
    return;
  }
  const fileName = name.endsWith('.md') ? name : name + '.md';
  const path = `/${fileName}`;
  API.putFile(mount.id, path, '')
    .then(() => {
      clearTreeCache();
      loadTree(mount.id, '/').then(() => {
        renderSidebar();
        openFile(path, mount.id);
        showToast('已创建');
      });
    })
    .catch(() => showToast('创建失败'));
}

function showNewFile() {
  const modal = $('new-file-modal');
  modal.style.display = '';
  // Force reflow then add active class to trigger animation
  requestAnimationFrame(() => modal.classList.add('active'));
  $('new-file-name').focus();
}

function hideNewFile() {
  const modal = $('new-file-modal');
  modal.classList.remove('active');
  // Wait for transition to finish before hiding
  setTimeout(() => {
    if (!modal.classList.contains('active')) {
      modal.style.display = 'none';
    }
  }, 200);
  $('new-file-name').value = '';
}

// === 导航 ===
function navigateHome() {
  localStorage.removeItem('nasmd_last_path');
  localStorage.removeItem('nasmd_last_mount');
  state.currentPath = null;
  state.currentMountId = null;
  $('breadcrumb').textContent = '';
  $('editor-modes').style.display = 'none';
  $('save-group').style.display = 'none';
  if (window._vditor) {
    window._vditor.destroy();
    window._vditor = null;
  }
  if (window._dirtyTimer) {
    clearInterval(window._dirtyTimer);
    window._dirtyTimer = null;
  }
  if (window._autoSaveTimer) {
    clearTimeout(window._autoSaveTimer);
    window._autoSaveTimer = null;
  }
  showPage('welcome');
  renderSidebar();
}

async function showGraph() {
  $('breadcrumb').textContent = '知识图谱';
  showPage('graph');
  try {
    const data = await API.getGraph();
    renderGraph(data);
  } catch (e) {
    console.error('Graph failed:', e);
    $('graph-container').innerHTML =
      '<p style="padding:20px;color:var(--c-muted)">加载图谱失败</p>';
  }
}

function renderGraph(data) {
  const container = $('graph-container');
  container.innerHTML = '';
  if (!data.nodes || data.nodes.length === 0) {
    container.innerHTML =
      '<p style="padding:20px;color:var(--c-muted)">暂无数据，请先打开目录并创建笔记</p>';
    return;
  }

  const width = container.clientWidth;
  const height = container.clientHeight || 500;

  const svg = d3.select(container).append('svg').attr('width', width).attr('height', height);

  const zoom = d3
    .zoom()
    .scaleExtent([0.3, 4])
    .on('zoom', (event) => g.attr('transform', event.transform));
  svg.call(zoom);

  const g = svg.append('g');

  // Build node id map
  const nodeMap = {};
  data.nodes.forEach((n) => {
    nodeMap[n.id] = n;
  });

  // Build links for d3
  const links = data.edges.map((e) => ({
    source: e.source,
    target: e.target,
  }));

  const simulation = d3
    .forceSimulation(data.nodes)
    .force(
      'link',
      d3
        .forceLink(links)
        .id((d) => d.id)
        .distance(80),
    )
    .force('charge', d3.forceManyBody().strength(-200))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collision', d3.forceCollide().radius(30));

  const link = g.append('g').selectAll('line').data(links).join('line').attr('class', 'graph-link');

  const node = g
    .append('g')
    .selectAll('g')
    .data(data.nodes)
    .join('g')
    .attr('class', 'graph-node')
    .call(d3.drag().on('start', dragstarted).on('drag', dragged).on('end', dragended));

  // Count connections per node for sizing
  const connCount = {};
  links.forEach((l) => {
    const sid = typeof l.source === 'object' ? l.source.id : l.source;
    const tid = typeof l.target === 'object' ? l.target.id : l.target;
    connCount[sid] = (connCount[sid] || 0) + 1;
    connCount[tid] = (connCount[tid] || 0) + 1;
  });

  node
    .append('circle')
    .attr('r', (d) => 6 + (connCount[d.id] || 0) * 2)
    .attr('fill', (d) =>
      (connCount[d.id] || 0) > 0 ? 'var(--c-primary, #5645d4)' : 'var(--c-border, #e5e3df)',
    );

  node
    .append('text')
    .attr('dx', 12)
    .attr('dy', 4)
    .text((d) => (d.title.length > 20 ? d.title.slice(0, 20) + '...' : d.title));

  node.on('click', (event, d) => {
    event.stopPropagation();
    openFile(d.rel_path || d.path, d.mount_id || '');
  });

  simulation.on('tick', () => {
    link
      .attr('x1', (d) => d.source.x)
      .attr('y1', (d) => d.source.y)
      .attr('x2', (d) => d.target.x)
      .attr('y2', (d) => d.target.y);
    node.attr('transform', (d) => `translate(${d.x},${d.y})`);
  });

  function dragstarted(event, d) {
    if (!event.active) simulation.alphaTarget(0.3).restart();
    d.fx = d.x;
    d.fy = d.y;
  }
  function dragged(event, d) {
    d.fx = event.x;
    d.fy = event.y;
  }
  function dragended(event, d) {
    if (!event.active) simulation.alphaTarget(0);
    d.fx = null;
    d.fy = null;
  }
}

async function showDashboard() {
  $('breadcrumb').textContent = '数据看板';
  showPage('dashboard');
  try {
    const stats = await API.getStats();
    $('dash-files').textContent = stats.file_count || 0;
    $('dash-tasks-total').textContent = stats.task_total || 0;
    $('dash-tasks-done').textContent = stats.task_done || 0;
    const rate = stats.task_total ? Math.round((stats.task_done / stats.task_total) * 100) : 0;
    $('dash-task-rate').textContent = rate + '%';
    $('dash-tags').textContent = stats.tag_count || 0;
    $('dash-links').textContent = stats.link_count || 0;

    const recent = stats.recent_pages || [];
    $('dash-recent').innerHTML =
      recent.length === 0
        ? '<p style="color:var(--c-muted)">暂无数据</p>'
        : recent
            .map(
              (p) =>
                `<div class="dash-recent-item" onclick="openFile('${(p.rel_path || p.path).replace(/'/g, "\\'")}', '${p.mount_id || ''}')">
          <span class="dash-recent-title">${p.title || p.path}</span>
          <span class="dash-recent-time">${p.rel_path || p.path}</span>
        </div>`,
            )
            .join('');

    // Load orphan pages
    try {
      const orphans = await API.getOrphans();
      const orphansEl = $('dash-orphans');
      if (orphansEl) {
        orphansEl.innerHTML =
          !orphans || orphans.length === 0
            ? '<p style="color:var(--c-muted)">无孤立页面</p>'
            : orphans
                .map(
                  (p) =>
                    `<div class="dash-recent-item" onclick="openFile('${(p.rel_path || p.path).replace(/'/g, "\\'")}', '${p.mount_id || ''}')">
              <span class="dash-recent-title">${p.title || p.path}</span>
              <span class="dash-recent-time">孤立页面</span>
            </div>`,
                )
                .join('');
      }
    } catch (_err) {}
  } catch (e) {
    console.error('Dashboard failed:', e);
  }
}

// === 同步 ===
function updateSyncIndicator() {
  // sync-indicator element removed from UI
}

function startSyncPolling() {
  stopSyncPolling();
  // Poll every 30 seconds
  state.syncTimer = setInterval(() => performSync(), 30000);
  // Initial sync
  performSync();
}

function stopSyncPolling() {
  if (state.syncTimer) {
    clearInterval(state.syncTimer);
    state.syncTimer = null;
  }
}

async function performSync() {
  if (!state.currentMountId || !navigator.onLine) {
    state.syncStatus = 'offline';
    updateSyncIndicator();
    return;
  }
  state.syncStatus = 'syncing';
  updateSyncIndicator();

  try {
    // Build client file list from tree cache
    const files = {};
    const entries = state.treeData[state.currentMountId + ':/'] || [];
    collectFileMtimes(entries, files);

    const result = await API.sync(state.currentMountId, files);
    if (result.download || result.upload || result.delete) {
      const dl = (result.download || []).length;
      const ul = (result.upload || []).length;
      const del = (result.delete || []).length;

      // If there are server changes, refresh file tree
      if (dl > 0 || del > 0) {
        await refreshTree();
      }

      state.syncStatus = dl > 0 || ul > 0 || del > 0 ? 'synced' : 'synced';
      state.lastSyncTime = Date.now();

      // Check for conflicts
      if (result.conflicts && result.conflicts.length > 0) {
        state.syncStatus = 'conflict';
        showToast(`发现 ${result.conflicts.length} 个文件冲突`);
      }
    } else {
      state.syncStatus = 'synced';
    }
  } catch (e) {
    console.error('Sync failed:', e);
    state.syncStatus = navigator.onLine ? 'synced' : 'offline';
  }
  updateSyncIndicator();
}

function collectFileMtimes(entries, files) {
  if (!entries) return;
  for (const entry of entries) {
    if (entry.type === 'file') {
      files[entry.path] = entry.modTime || 0;
    } else if (entry.type === 'directory' && entry.children) {
      collectFileMtimes(entry.children, files);
    }
  }
}

async function refreshTree() {
  if (!state.currentMountId) return;
  try {
    const tree = await API.getTree(state.currentMountId, '/');
    state.treeData[state.currentMountId + ':/'] = tree.children || [];
    renderFileTree();
  } catch (e) {
    console.error('Refresh tree failed:', e);
  }
}

// === 离线支持 ===
function saveToLocalStorage(path, content) {
  try {
    const key = 'nasmd_draft_' + path;
    localStorage.setItem(key, JSON.stringify({ content, savedAt: Date.now() }));
  } catch (_e) {
    /* quota exceeded */
  }
}

function loadFromLocalStorage(path) {
  try {
    const key = 'nasmd_draft_' + path;
    const data = localStorage.getItem(key);
    if (!data) return null;
    return JSON.parse(data);
  } catch (_e) {
    return null;
  }
}

function clearLocalStorage(path) {
  try {
    localStorage.removeItem('nasmd_draft_' + path);
  } catch (_e) {
    /* ignore */
  }
}

// Online/offline event listeners
window.addEventListener('online', () => {
  state.syncStatus = 'synced';
  updateSyncIndicator();
  performSync();
});
window.addEventListener('offline', () => {
  state.syncStatus = 'offline';
  updateSyncIndicator();
});
async function doSearch() {
  const query = $('search-input').value.trim();
  const resultsEl = $('search-results');
  if (!query) {
    resultsEl.innerHTML = '';
    return;
  }
  try {
    state.searchResults = await API.search(query);
    if (state.searchResults.length === 0) {
      resultsEl.innerHTML = '<div style="padding:8px;color:var(--c-muted)">无结果</div>';
      return;
    }
    resultsEl.innerHTML = state.searchResults
      .map((r, i) => {
        const relPath = r.rel_path || r.path;
        const displayTitle = r.title || r.filename;
        const displayPath = relPath.length > 50 ? '...' + relPath.slice(-47) : relPath;
        const snippet = (r.snippet || '').replace(/<[^>]*>/g, ''); // strip HTML tags from snippet
        return `<div class="search-result-item" data-idx="${i}">
        <span class="result-path">${displayTitle} <small style="color:var(--c-muted)">${displayPath}</small></span>
        <span class="result-snippet">${snippet}</span>
      </div>`;
      })
      .join('');
    // Use event delegation instead of inline onclick to avoid escaping issues
    resultsEl.onclick = (e) => {
      const item = e.target.closest('.search-result-item');
      if (!item) return;
      const idx = parseInt(item.dataset.idx);
      const r = state.searchResults[idx];
      if (!r) return;
      const mountId = r.mount_id || '';
      const relPath = r.rel_path || r.path;
      openFile(relPath, mountId, query);
      resultsEl.innerHTML = '';
      $('search-input').value = '';
    };
  } catch (e) {
    console.error('Search failed:', e);
  }
}

// === 编辑器模式 ===
function setEditorMode(mode) {
  if (state.editorMode === mode) return;
  state.editorMode = mode;

  if (window._reinitEditor) {
    window._reinitEditor(mode);
  }
}

// === 最近文件 ===
async function loadRecentFiles() {
  const allFiles = [];
  const activeMountIds = new Set(state.mounts.map((m) => m.id));
  const seen = new Set();
  for (const mount of state.mounts) {
    try {
      await loadTree(mount.id, '/');
      const root = state.treeData[mount.id]?.['/'];
      if (root) collectFiles(root, mount.id, allFiles);
    } catch {}
  }
  // Filter out files belonging to mounts that no longer exist
  const filtered = allFiles.filter((f) => activeMountIds.has(f.mountId));
  // Deduplicate by (mountId + path)
  const deduped = filtered.filter((f) => {
    const key = f.mountId + ':' + f.path;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  // Sort by access time (most recent first), fall back to modTime
  deduped.sort((a, b) => {
    const aTime = state.accessLog[a.mountId + ':' + a.path] || a.modTime || 0;
    const bTime = state.accessLog[b.mountId + ':' + b.path] || b.modTime || 0;
    return bTime - aTime;
  });
  state.recentFiles = deduped.slice(0, 10);
  renderRecentFiles();
}

function collectFiles(entries, mountId, result) {
  if (!entries) return;
  // entries is a single tree root from tree-recursive; walk its children
  const stack = [...(entries.children || [])];
  while (stack.length > 0) {
    const e = stack.pop();
    if (!e.isDir && e.name.endsWith('.md')) {
      result.push({ name: e.name, path: e.path, modTime: e.modTime, mountId });
    }
    if (e.children) stack.push(...e.children);
  }
}

function renderRecentFiles() {
  const el = $('recent-files');
  if (state.recentFiles.length === 0) {
    el.innerHTML = '';
    return;
  }
  let html = '<h3 class="section-title">最近访问</h3>';
  for (const f of state.recentFiles) {
    const accessTime = state.accessLog[f.mountId + ':' + f.path];
    const displayTime = accessTime ? formatTime(accessTime) : formatTime(f.modTime);
    html += `<div class="recent-item" onclick="openFile('${f.path.replace(/'/g, "\\'")}', '${f.mountId}')">
      <span class="recent-name">${f.name}</span>
      <span class="recent-time">${displayTime}</span>
    </div>`;
  }
  el.innerHTML = html;
}

function formatTime(ms) {
  if (!ms) return '';
  const d = new Date(ms);
  const now = new Date();
  const diff = now - d;
  if (diff < 60000) return '刚刚';
  if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`;
  if (diff < 604800000) return `${Math.floor(diff / 86400000)} 天前`;
  return d.toLocaleDateString('zh-CN');
}

// === 侧边栏点击外部关闭（移动端） ===
document.querySelector('.main').addEventListener('click', () => {
  document.getElementById('sidebar').classList.remove('open');
});

// === 键盘快捷键 ===
document.addEventListener('keydown', (e) => {
  // Ctrl+K: 聚焦搜索框
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault();
    $('search-input').focus();
  }
  // Ctrl+S: 保存
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault();
    saveFile();
  }
  // Ctrl+N: 新建文件
  if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
    e.preventDefault();
    showNewFile();
  }
  // Escape: 关闭模态框/搜索结果
  if (e.key === 'Escape') {
    $('search-results').innerHTML = '';
    hideNewFile();
  }
});
