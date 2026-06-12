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
  // Local mounts via File System Access API (browser-side only, no server)
  localMounts: {}, // mountId -> { handle: FileSystemDirectoryHandle, name: string }
  _fileOpInProgress: false, // lock to prevent concurrent file operations
};

// Expose state globally so files.js can access isAdmin
window.state = state;

// === IndexedDB helpers for persisting FileSystemDirectoryHandle ===
const IDB_NAME = 'nasmd-local-mounts';
const IDB_STORE = 'handles';
function idbOpen() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(IDB_NAME, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(IDB_STORE);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}
async function idbPut(key, value) {
  const db = await idbOpen();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(IDB_STORE, 'readwrite');
    tx.objectStore(IDB_STORE).put(value, key);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}
async function idbGet(key) {
  const db = await idbOpen();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(IDB_STORE, 'readonly');
    const req = tx.objectStore(IDB_STORE).get(key);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}
async function idbDelete(key) {
  const db = await idbOpen();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(IDB_STORE, 'readwrite');
    tx.objectStore(IDB_STORE).delete(key);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}
async function idbGetAllKeys() {
  const db = await idbOpen();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(IDB_STORE, 'readonly');
    const req = tx.objectStore(IDB_STORE).getAllKeys();
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

// === DOM 引用 ===
const $ = (id) => document.getElementById(id);

// === 初始化 ===
document.addEventListener('DOMContentLoaded', async () => {
  // Load runtime config (e.g. Docker mode)
  try {
    const cfg = await API.getConfig();
    if (cfg) state.dockerMode = cfg.docker_mode === true;
  } catch (_e) {
    /* ignore */
  }
  await loadMounts();
  // Restore local mounts from IndexedDB
  try {
    const keys = await idbGetAllKeys();
    for (const mountId of keys) {
      const record = await idbGet(mountId);
      if (record && record.handle) {
        // Request permission (may prompt user)
        const perm = await record.handle.queryPermission({ mode: 'readwrite' });
        if (perm === 'granted') {
          state.localMounts[mountId] = { handle: record.handle, name: record.name };
          state.mounts.push({
            id: mountId,
            name: record.name,
            path: '本机: ' + record.name,
            public: false,
            readonly: false,
            host: false,
            owner: 'local',
            _local: true,
          });
          await loadLocalTree(mountId);
        } else {
          // Permission not granted yet, will request on first interaction
          // Store handle temporarily and try requestPermission later
          state.localMounts[mountId] = {
            handle: record.handle,
            name: record.name,
            needsPerm: true,
          };
          state.mounts.push({
            id: mountId,
            name: record.name,
            path: '本机: ' + record.name,
            public: false,
            readonly: false,
            host: false,
            owner: 'local',
            _local: true,
            _needsPerm: true,
          });
        }
      }
    }
    if (keys.length > 0) renderSidebar();
  } catch (_e) {
    /* IndexedDB not available, skip */
  }
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
          $('breadcrumb').textContent = mount.name + lastPath + (mount.readonly ? ' 🔒' : '');
          $('editor-modes').style.display = mount.readonly
            ? 'none'
            : lastPath.endsWith('.md')
              ? ''
              : 'none';
          $('save-group').style.display = mount.readonly ? 'none' : '';
          // Show rename/delete buttons if writable and not root
          const _renameBtn = $('rename-top-btn');
          const _deleteBtn = $('delete-top-btn');
          if (_renameBtn)
            _renameBtn.style.display = !mount.readonly && lastPath !== '/' ? '' : 'none';
          if (_deleteBtn)
            _deleteBtn.style.display = !mount.readonly && lastPath !== '/' ? '' : 'none';
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

  // Start sidebar auto-refresh (pause when tab is hidden)
  startSidebarRefresh();
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      stopSidebarRefresh();
    } else {
      refreshTree();
      startSidebarRefresh();
    }
  });
});

// === UI 更新 ===
function showPage(page) {
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
  } catch (_e) {
    showToast('加载挂载点失败');
  } finally {
    _loadMountsBusy = false;
  }
}

// === 目录选择 ===

function chooseDirectory() {
  if (window.showDirectoryPicker) {
    mountLocalDirectory();
  } else {
    // Fallback: use <input webkitdirectory> (works in non-secure contexts)
    const picker = document.getElementById('dir-picker');
    if (picker) {
      picker.click();
    } else {
      showToast('当前浏览器不支持选择本机目录，请使用 Chrome/Edge 浏览器');
    }
  }
}

async function mountLocalDirectory() {
  try {
    const handle = await window.showDirectoryPicker({ mode: 'readwrite' });
    const name = handle.name;
    const mountId = 'local-' + Date.now();
    state.localMounts[mountId] = { handle, name };
    // Add to mounts list as a virtual mount
    state.mounts.push({
      id: mountId,
      name: name,
      path: '本机: ' + name,
      public: false,
      readonly: false,
      host: false,
      owner: 'local',
      _local: true,
    });
    // Persist handle to IndexedDB
    await idbPut(mountId, { handle, name });
    showToast(`已挂载本机目录: ${name}`);
    await loadLocalTree(mountId);
    renderSidebar();
  } catch (e) {
    if (e.name !== 'AbortError') {
      showToast('挂载本机目录失败: ' + (e.message || '未知错误'));
    }
  }
}

async function loadLocalTree(mountId) {
  const localMount = state.localMounts[mountId];
  if (!localMount) return;
  try {
    const root = await readLocalDir(localMount.handle, '/');
    state.treeData[mountId] = { '/': root };
  } catch (e) {
    console.error('Failed to load local tree:', e);
  }
}

async function readLocalDir(dirHandle, parentPath) {
  const children = [];
  for await (const entry of dirHandle.values()) {
    const entryPath = parentPath === '/' ? '/' + entry.name : parentPath + '/' + entry.name;
    if (entry.kind === 'directory') {
      const subChildren = [];
      let hasMd = false;
      try {
        const subHandle = await dirHandle.getDirectoryHandle(entry.name);
        const subResult = await readLocalDir(subHandle, entryPath);
        subChildren.push(...(subResult.children || []));
        hasMd = subResult.hasMd || false;
      } catch (_e) {
        /* skip unreadable dirs */
      }
      // Only include dirs that contain .md files
      if (hasMd) {
        children.push({
          name: entry.name,
          path: entryPath,
          isDir: true,
          hasMd: true,
          children: subChildren,
        });
      }
    } else if (entry.kind === 'file' && entry.name.toLowerCase().endsWith('.md')) {
      children.push({
        name: entry.name,
        path: entryPath,
        isDir: false,
        hasMd: true,
        size: 0,
        modTime: 0,
      });
    }
  }
  // Sort: dirs first, then files
  children.sort((a, b) => {
    if (a.isDir && !b.isDir) return -1;
    if (!a.isDir && b.isDir) return 1;
    return a.name.localeCompare(b.name);
  });
  const hasMd = children.some((c) => c.hasMd);
  return { name: dirHandle.name, path: parentPath, isDir: true, children, hasMd };
}

async function readLocalFile(mountId, path) {
  const localMount = state.localMounts[mountId];
  if (!localMount) return null;
  try {
    // Fallback mode: read from File object stored in fileMap
    if (localMount.fileMap) {
      const file = localMount.fileMap[path];
      if (!file) return null;
      return await file.text();
    }
    // Primary mode: read via FileSystemDirectoryHandle
    const handle = await getLocalFileHandle(localMount.handle, path);
    if (!handle) return null;
    const file = await handle.getFile();
    return await file.text();
  } catch (e) {
    console.error('readLocalFile error:', e);
    return null;
  }
}

async function getLocalFileHandle(dirHandle, path) {
  // path is like /subdir/file.md or /file.md
  const parts = path.split('/').filter(Boolean);
  let current = dirHandle;
  for (let i = 0; i < parts.length; i++) {
    const part = parts[i];
    if (i === parts.length - 1) {
      // Last part should be a file
      try {
        return await current.getFileHandle(part);
      } catch {
        return null;
      }
    } else {
      // Intermediate parts are directories
      try {
        current = await current.getDirectoryHandle(part);
      } catch {
        return null;
      }
    }
  }
  return null;
}

/**
 * Ensure a local mount handle has readwrite permission.
 * If already granted, returns immediately. Otherwise prompts the user once.
 * Returns true if permission is granted, false otherwise.
 */
async function ensureWritePermission(mountId) {
  const localMount = state.localMounts[mountId];
  if (!localMount || !localMount.handle) return false;
  // Check if already granted (no prompt)
  const current = await localMount.handle.queryPermission({ mode: 'readwrite' });
  if (current === 'granted') return true;
  // Request permission (may show browser prompt)
  const result = await localMount.handle.requestPermission({ mode: 'readwrite' });
  if (result !== 'granted') {
    showToast('需要授予目录写入权限');
    return false;
  }
  return true;
}

async function writeLocalFile(mountId, path, content) {
  const localMount = state.localMounts[mountId];
  if (!localMount) return false;
  try {
    if (!(await ensureWritePermission(mountId))) return false;
    const parts = path.split('/').filter(Boolean);
    let current = localMount.handle;
    // Navigate to parent directory
    for (let i = 0; i < parts.length - 1; i++) {
      current = await current.getDirectoryHandle(parts[i]);
    }
    // Create/write file
    const fileName = parts[parts.length - 1];
    const fileHandle = await current.getFileHandle(fileName, { create: true });
    const writable = await fileHandle.createWritable();
    await writable.write(content);
    await writable.close();
    return true;
  } catch (e) {
    console.error('writeLocalFile error:', e);
    if (e.name === 'NotAllowedError') {
      showToast('权限不足，无法写入文件');
    }
    return false;
  }
}

function onDirPicked(event) {
  const files = event.target.files;
  if (!files || files.length === 0) return;

  // Build a local mount from the file list (fallback when showDirectoryPicker is unavailable)
  const firstFile = files[0];
  const dirName = firstFile.webkitRelativePath
    ? firstFile.webkitRelativePath.split('/')[0]
    : '本机目录';
  const mountId = 'local-' + Date.now();

  // Build tree from flat file list
  const root = { name: dirName, path: '/', isDir: true, children: [], hasMd: false };
  const dirMap = { '/': root };

  for (const file of files) {
    const relPath = file.webkitRelativePath; // e.g. "mydir/sub/file.md"
    if (!relPath) continue;
    const parts = relPath.split('/');
    // Only include .md files
    const fileName = parts[parts.length - 1];
    if (!fileName.toLowerCase().endsWith('.md')) continue;

    // Ensure all parent directories exist in the tree
    let currentPath = '';
    for (let i = 0; i < parts.length - 1; i++) {
      const parentPath = currentPath;
      currentPath = currentPath + '/' + parts[i];
      if (!dirMap[currentPath]) {
        const dirEntry = {
          name: parts[i],
          path: currentPath,
          isDir: true,
          children: [],
          hasMd: false,
        };
        dirMap[currentPath] = dirEntry;
        const parent = dirMap[parentPath] || root;
        parent.children.push(dirEntry);
      }
    }
    // Add file entry
    const filePath = currentPath + '/' + fileName;
    const parentDir = dirMap[currentPath] || root;
    parentDir.children.push({
      name: fileName,
      path: filePath,
      isDir: false,
      hasMd: true,
      size: file.size,
      modTime: file.lastModified,
    });
    // Mark all ancestors as having .md
    let markPath = currentPath;
    while (markPath) {
      if (dirMap[markPath]) dirMap[markPath].hasMd = true;
      const idx = markPath.lastIndexOf('/');
      markPath = idx > 0 ? markPath.substring(0, idx) : '';
    }
    root.hasMd = true;
  }

  // Sort children: dirs first, then files
  function sortChildren(entry) {
    if (!entry.children) return;
    entry.children.sort((a, b) => {
      if (a.isDir && !b.isDir) return -1;
      if (!a.isDir && b.isDir) return 1;
      return a.name.localeCompare(b.name);
    });
    entry.children.forEach(sortChildren);
  }
  sortChildren(root);

  // Store file references for reading later
  const fileMap = {};
  for (const file of files) {
    if (file.webkitRelativePath) {
      const parts = file.webkitRelativePath.split('/');
      const filePath = '/' + parts.slice(1).join('/');
      fileMap[filePath] = file;
    }
  }

  state.localMounts[mountId] = { fileMap, name: dirName };
  state.mounts.push({
    id: mountId,
    name: dirName,
    path: '本机: ' + dirName,
    public: false,
    readonly: true, // webkitdirectory only provides read access
    host: false,
    owner: 'local',
    _local: true,
    _fallback: true, // flag: no write support
  });
  state.treeData[mountId] = { '/': root };

  showToast(`已挂载本机目录: ${dirName}（只读）`);
  renderSidebar();
  event.target.value = '';
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
  const mount = state.mounts.find((m) => m.id === mountId);
  // Handle local mount that needs permission
  if (mount && mount._local && mount._needsPerm) {
    const localMount = state.localMounts[mountId];
    if (localMount && localMount.handle) {
      try {
        const perm = await localMount.handle.requestPermission({ mode: 'readwrite' });
        if (perm === 'granted') {
          delete mount._needsPerm;
          delete localMount.needsPerm;
          await loadLocalTree(mountId);
        } else {
          showToast('需要授予目录访问权限');
          return;
        }
      } catch (_e) {
        showToast('权限请求失败');
        return;
      }
    }
  }
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

async function loadTree(mountId, path, force = false) {
  if (!state.treeData[mountId]) state.treeData[mountId] = {};
  // Skip if already loaded (unless forced)
  if (!force && state.treeData[mountId][path]) return;
  // Local mount: load via File System Access API
  const mount = state.mounts.find((m) => m.id === mountId);
  if (mount && mount._local && state.localMounts[mountId]) {
    // Fallback mode: tree already built by onDirPicked, skip even on force
    if (state.localMounts[mountId].fileMap) return;
    try {
      const localMount = state.localMounts[mountId];
      const dirHandle = await getLocalDirHandle(localMount.handle, path);
      if (!dirHandle) return;
      const result = await readLocalDir(dirHandle, path);
      state.treeData[mountId][path] = result;
    } catch (e) {
      console.error('Failed to load local tree:', e);
    }
    return;
  }
  try {
    const tree = await API.getTree(mountId, path);
    // Store the root entry; renderEntries will use .children
    state.treeData[mountId][path] = tree;
  } catch (e) {
    console.error('Failed to load tree:', e);
  }
}

async function getLocalDirHandle(rootHandle, path) {
  if (path === '/') return rootHandle;
  const parts = path.split('/').filter(Boolean);
  let current = rootHandle;
  for (const part of parts) {
    try {
      current = await current.getDirectoryHandle(part);
    } catch {
      return null;
    }
  }
  return current;
}

// 卸载挂载点
async function removeMount(mountId) {
  // Cannot delete builtin mount
  const mount = state.mounts.find((m) => m.id === mountId);
  if (mount && mount.id === 'builtin-storage') {
    showToast('内置目录不能卸载');
    return;
  }
  // Local mount: remove from frontend state only
  if (mount && mount._local) {
    delete state.localMounts[mountId];
    state.mounts = state.mounts.filter((m) => m.id !== mountId);
    delete state.treeData[mountId];
    state.expandedMounts = state.expandedMounts.filter(
      (id) => id !== mountId && !id.startsWith(`${mountId}:`),
    );
    for (const key of Object.keys(state.accessLog)) {
      if (key.startsWith(mountId + ':')) {
        delete state.accessLog[key];
      }
    }
    localStorage.setItem('nasmd_access_log', JSON.stringify(state.accessLog));
    // Remove from IndexedDB
    await idbDelete(mountId);
    renderSidebar();
    showToast('已卸载本机目录');
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
      navigateHome();
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
      const isActive = state.currentPath === fullPath && state.currentMountId === builtin.id;
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
    const canWrite = !mount.readonly && !mount.id.startsWith('builtin');
    const isHostMount = !!mount.host;

    let html = `<div class="mount-group">`;
    html += `<div class="mount-name-row" ${canWrite ? `data-drop-mount="${mount.id}" data-drop-path="/"` : ''}>`;
    html += `<div class="mount-name" onclick="toggleMount('${mount.id}')">`;
    html += `<span class="mount-icon">${chevron}</span>`;
    html += `<span>${mount.name}</span>`;
    if (mount._needsPerm) {
      html += `<span style="color:var(--c-muted);font-size:var(--f-body-xs);margin-left:4px">（点击授权）</span>`;
    }
    html += `</div>`;
    // Action buttons (right side)
    html += `<span class="mount-actions">`;
    if (canWrite && isExpanded) {
      html += `<button class="mount-create-btn" onclick="createItem('${mount.id}','/','file')" title="新建文件"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/></svg></button>`;
      html += `<button class="mount-create-btn" onclick="createItem('${mount.id}','/','folder')" title="新建文件夹"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/><line x1="12" y1="11" x2="12" y2="17"/><line x1="9" y1="14" x2="15" y2="14"/></svg></button>`;
    }
    if (!isHostMount) {
      html += `<button class="mount-remove-btn" onclick="removeMount('${mount.id}')" title="卸载"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>`;
    }
    html += `</span>`;
    html += `</div>`;

    if (isExpanded) {
      // Root directory as drop target
      const dropAttr = canWrite ? `data-drop-mount="${mount.id}" data-drop-path="/"` : '';
      html += `<div ${dropAttr}>`;
      const treeData = state.treeData[mount.id]?.['/'];
      if (treeData) {
        html += renderEntries(treeData.children || [], mount.id, '/');
      } else {
        html += '<div class="tree-loading">加载中...</div>';
        loadTree(mount.id, '/').then(() => renderSidebar());
      }
      html += `</div>`;
    }

    html += `</div>`;
    tree.innerHTML += html;
  }

  if (regularMounts.length === 0 && !builtinEntries) {
    tree.innerHTML = '<div class="tree-loading">暂无挂载目录</div>';
  }

  // Hint at bottom
  const hint = document.createElement('div');
  hint.className = 'sidebar-hint';
  hint.textContent = '拖拽移动文件';
  tree.appendChild(hint);

  // Setup drag & drop event listeners
  setupDragDrop();
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

  const mount = state.mounts.find((m) => m.id === mountId);
  const canWrite = mount && !mount.readonly;

  return items
    .map((e) => {
      const fullPath = e.path;
      const isActive = state.currentPath === fullPath && state.currentMountId === mountId;
      const icon = e.isDir ? svgFolder : svgFile;
      const cls = `tree-item ${e.isDir ? 'folder' : ''} ${isActive ? 'active' : ''}`;

      if (e.isDir) {
        const dirKey = `${mountId}:${fullPath}`;
        const isDirExpanded = state.expandedMounts.includes(dirKey);
        const subEntries = state.treeData[mountId]?.[fullPath];
        const chevron = `<svg class="tree-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="transform:rotate(${isDirExpanded ? 90 : 0}deg);transition:transform 0.15s"><polyline points="9 18 15 12 9 6"/></svg>`;

        // Directories are drop targets; also draggable if writable
        const dragAttr = canWrite
          ? `draggable="true" data-drag-mount="${mountId}" data-drag-path="${fullPath}" data-drag-isdir="true"`
          : '';
        const dropAttr = canWrite
          ? `data-drop-mount="${mountId}" data-drop-path="${fullPath}"`
          : '';

        let html = `<div>`;
        html += `<div class="${cls} dir-row" ${dragAttr} ${dropAttr}>`;
        html += `<span class="dir-label" onclick="toggleDir('${mountId}','${fullPath}')">`;
        html += `<span class="tree-icon">${chevron}</span>`;
        html += `<span class="tree-folder" title="${e.name}">${e.name}</span>`;
        html += `</span>`;
        if (canWrite && isDirExpanded) {
          html += `<span class="dir-actions">`;
          html += `<button class="mount-create-btn" onclick="event.stopPropagation();createItem('${mountId}','${fullPath}','file')" title="新建文件"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/></svg></button>`;
          html += `<button class="mount-create-btn" onclick="event.stopPropagation();createItem('${mountId}','${fullPath}','folder')" title="新建文件夹"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/><line x1="12" y1="11" x2="12" y2="17"/><line x1="9" y1="14" x2="15" y2="14"/></svg></button>`;
          html += `</span>`;
        }
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

      // MD file: draggable if writable
      const dragAttr = canWrite
        ? `draggable="true" data-drag-mount="${mountId}" data-drag-path="${fullPath}" data-drag-isdir="false"`
        : '';
      return `<div class="${cls}" onclick="openFile('${fullPath}','${mountId}')" ${dragAttr}>
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

// === Duplicate handling ===
async function localEntryExists(dirHandle, name, isDir) {
  try {
    if (isDir) {
      await dirHandle.getDirectoryHandle(name);
    } else {
      await dirHandle.getFileHandle(name);
    }
    return true;
  } catch {
    return false;
  }
}

function suggestRename(name) {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  const ts = `_${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
  const dotIdx = name.lastIndexOf('.');
  if (dotIdx > 0) {
    return name.slice(0, dotIdx) + ts + name.slice(dotIdx);
  }
  return name + ts;
}

/**
 * Show a dialog when a duplicate file/folder name is found.
 * Returns: 'overwrite' | 'rename' | 'cancel'
 */
function showDuplicateDialog(suggestedName) {
  return new Promise((resolve) => {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `
      <div class="modal-box">
        <div class="modal-header">文件名冲突</div>
        <div class="modal-body">
          目标位置已存在同名文件。<br>
          重命名规则：在文件名后添加时间戳后缀，如 <code>${suggestedName}</code>
        </div>
        <div class="modal-footer">
          <button class="modal-btn modal-cancel" id="dup-cancel">取消</button>
          <button class="modal-btn modal-confirm" id="dup-rename">重命名</button>
          <button class="modal-btn modal-confirm" id="dup-overwrite" style="background:var(--c-error)">覆盖</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);
    overlay.querySelector('#dup-cancel').onclick = () => {
      overlay.remove();
      resolve('cancel');
    };
    overlay.querySelector('#dup-rename').onclick = () => {
      overlay.remove();
      resolve('rename');
    };
    overlay.querySelector('#dup-overwrite').onclick = () => {
      overlay.remove();
      resolve('overwrite');
    };
    overlay.onclick = (e) => {
      if (e.target === overlay) {
        overlay.remove();
        resolve('cancel');
      }
    };
  });
}

// === Drag & Drop ===
let _dragData = null; // { mountId, path, isDir }

let _dragDropSetup = false;

function setupDragDrop() {
  const tree = $('file-tree');
  if (!tree) return;

  // Only bind event listeners once
  if (_dragDropSetup) return;
  _dragDropSetup = true;

  // Dragstart: capture source info
  tree.addEventListener('dragstart', (e) => {
    const el = e.target.closest('[data-drag-mount]');
    if (!el) return;
    _dragData = {
      mountId: el.dataset.dragMount,
      path: el.dataset.dragPath,
      isDir: el.dataset.dragIsdir === 'true',
    };
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', _dragData.path);
    el.classList.add('dragging');
  });

  tree.addEventListener('dragend', (e) => {
    const el = e.target.closest('[data-drag-mount]');
    if (el) el.classList.remove('dragging');
    // Remove all drop highlights
    tree.querySelectorAll('.drop-target').forEach((el) => el.classList.remove('drop-target'));
    _dragData = null;
  });

  // Dragover: highlight valid drop targets
  tree.addEventListener('dragover', (e) => {
    const dropEl = e.target.closest('[data-drop-mount]');
    if (!dropEl) return;

    // Internal drag (within sidebar)
    if (_dragData) {
      const destMountId = dropEl.dataset.dropMount;
      const destPath = dropEl.dataset.dropPath;
      if (_dragData.mountId === destMountId) {
        if (_dragData.path === destPath) return;
        if (destPath.startsWith(_dragData.path + '/')) return;
      }
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
    } else if (e.dataTransfer.types.includes('Files')) {
      // External file drag (from OS file manager)
      e.preventDefault();
      e.dataTransfer.dropEffect = 'copy';
    }

    // Clear previous highlights
    tree.querySelectorAll('.drop-target').forEach((el) => el.classList.remove('drop-target'));
    dropEl.classList.add('drop-target');
  });

  tree.addEventListener('dragleave', (e) => {
    const dropEl = e.target.closest('[data-drop-mount]');
    if (dropEl && !dropEl.contains(e.relatedTarget)) {
      dropEl.classList.remove('drop-target');
    }
  });

  // Drop: perform move, copy, or external file import
  tree.addEventListener('drop', async (e) => {
    e.preventDefault();
    if (state._fileOpInProgress) {
      showToast('请等待当前操作完成');
      return;
    }
    const dropEl = e.target.closest('[data-drop-mount]');
    if (!dropEl) return;

    const destMountId = dropEl.dataset.dropMount;
    const destPath = dropEl.dataset.dropPath;

    dropEl.classList.remove('drop-target');

    // Handle external file drop (from OS file manager)
    if (!_dragData && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const files = Array.from(e.dataTransfer.files);
      // Check all files are .md
      const nonMd = files.find((f) => !f.name.toLowerCase().endsWith('.md'));
      if (nonMd) {
        showToast('请放入受支持的文件格式（仅支持 .md 文件）');
        return;
      }
      const destMount = state.mounts.find((m) => m.id === destMountId);
      if (!destMount || destMount.readonly) {
        showToast('该目录不可写');
        return;
      }
      state._fileOpInProgress = true;
      try {
        for (const file of files) {
          const content = await file.text();
          const fileName = file.name;
          if (destMount._local && state.localMounts[destMountId]) {
            // Write to local mount
            if (!(await ensureWritePermission(destMountId))) return;
            const dirHandle = await getLocalDirHandle(
              state.localMounts[destMountId].handle,
              destPath,
            );
            if (!dirHandle) {
              showToast('目录不存在');
              return;
            }
            let destName = fileName;
            if (await localEntryExists(dirHandle, fileName, false)) {
              const suggested = suggestRename(fileName);
              const choice = await showDuplicateDialog(suggested);
              if (choice === 'cancel') return;
              if (choice === 'rename') {
                destName = suggested;
              } else {
                // overwrite: remove existing first
                await dirHandle.removeEntry(fileName);
              }
            }
            const fh = await dirHandle.getFileHandle(destName, { create: true });
            const writable = await fh.createWritable();
            await writable.write(content);
            await writable.close();
            showToast(`已导入: ${destName}`);
          } else {
            // Write to server mount
            let destName = fileName;
            const checkPath = destPath === '/' ? '/' + fileName : destPath + '/' + fileName;
            const existing = await API.getFile(destMountId, checkPath);
            if (existing !== null) {
              const suggested = suggestRename(fileName);
              const choice = await showDuplicateDialog(suggested);
              if (choice === 'cancel') return;
              if (choice === 'rename') {
                destName = suggested;
              }
              // overwrite: just write to same path, will replace content
            }
            const writePath = destPath === '/' ? '/' + destName : destPath + '/' + destName;
            const result = await API.putFile(destMountId, writePath, content);
            if (!result || result.status === 'error') {
              showToast(result?.error || '导入失败');
              return;
            }
            showToast(`已导入: ${destName}`);
          }
        }
        // Refresh tree
        if (destMount._local && state.localMounts[destMountId]) {
          await loadLocalTree(destMountId);
        } else {
          delete state.treeData[destMountId];
          await loadTree(destMountId, '/');
        }
        renderSidebar();
      } catch (err) {
        console.error('External file import failed:', err);
        showToast('导入失败');
      } finally {
        state._fileOpInProgress = false;
      }
      return;
    }

    // Internal drag & drop
    if (!_dragData) return;

    // Save drag data to local vars before any await — dragend may clear _dragData
    const srcMountId = _dragData.mountId;
    const srcPath = _dragData.path;

    // Don't allow dropping on self or into own subtree
    if (srcMountId === destMountId) {
      if (srcPath === destPath) return;
      if (destPath.startsWith(srcPath + '/')) return;
    }

    // Don't allow dropping into the same parent directory (no-op)
    const srcParent = srcPath.substring(0, srcPath.lastIndexOf('/')) || '/';
    if (srcMountId === destMountId && srcParent === destPath) return;

    dropEl.classList.remove('drop-target');

    state._fileOpInProgress = true;
    try {
      const isCrossMount = srcMountId !== destMountId;
      const srcMount = state.mounts.find((m) => m.id === srcMountId);
      const srcIsLocal = srcMount && srcMount._local;
      const destMount = state.mounts.find((m) => m.id === destMountId);
      const destIsLocal = destMount && destMount._local;

      if (isCrossMount) {
        const isCrossMachine = srcIsLocal !== destIsLocal;
        const choice = await showMoveCopyDialog(isCrossMachine);
        if (!choice) return; // cancelled
        if (srcIsLocal && destIsLocal) {
          await crossMountLocal(srcMountId, srcPath, destMountId, destPath, choice);
        } else if (srcIsLocal && !destIsLocal) {
          await localToServer(srcMountId, srcPath, destMountId, destPath, choice);
        } else if (!srcIsLocal && destIsLocal) {
          await serverToLocal(srcMountId, srcPath, destMountId, destPath, choice);
        } else {
          await crossMountServer(srcMountId, srcPath, destMountId, destPath, choice);
        }
      } else {
        // Same mount: always move
        if (srcIsLocal) {
          await moveLocalItem(srcMountId, srcPath, destPath);
        } else {
          await moveServerItem(srcMountId, srcPath, destPath);
        }
      }
    } finally {
      state._fileOpInProgress = false;
    }
  });
}

function showMoveCopyDialog(isCrossMachine = false) {
  return new Promise((resolve) => {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay active';
    const title = isCrossMachine ? '跨机器操作' : '跨挂载点操作';
    const body = isCrossMachine
      ? '源文件与目标目录不在同一台机器上，请选择操作：'
      : '目标目录与源文件不在同一挂载点，请选择操作：';
    overlay.innerHTML = `
      <div class="modal-box">
        <div class="modal-title">${title}</div>
        <div class="modal-body">${body}</div>
        <div class="modal-actions">
          <button class="modal-btn primary" data-action="move">移动（删除原文件）</button>
          <button class="modal-btn" data-action="copy">复制（保留原文件）</button>
          <button class="modal-btn cancel" data-action="cancel">取消</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);
    overlay.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-action]');
      if (!btn) return;
      const action = btn.dataset.action;
      overlay.remove();
      resolve(action === 'cancel' ? null : action);
    });
  });
}

// Move item within same server mount
async function moveServerItem(mountId, srcPath, destDir) {
  try {
    const headers = {};
    if (state.isAdmin) headers['X-Admin'] = '1';
    let params = new URLSearchParams({ src: srcPath, destDir: destDir });
    let resp = await fetch(`${_apiBase}/api/mounts/${mountId}/move?${params}`, {
      method: 'POST',
      headers,
    });
    if (resp.status === 409) {
      const data = await resp.json().catch(() => ({}));
      const choice = await showDuplicateDialog(data.suggested_name || '');
      if (choice === 'cancel') return;
      params = new URLSearchParams({
        src: srcPath,
        destDir: destDir,
        ...(choice === 'overwrite' ? { overwrite: '1' } : { newName: data.suggested_name }),
      });
      resp = await fetch(`${_apiBase}/api/mounts/${mountId}/move?${params}`, {
        method: 'POST',
        headers,
      });
    }
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      showToast(data.error || '移动失败');
      return;
    }
    showToast('已移动');
    delete state.treeData[mountId];
    await loadTree(mountId, '/');
    renderSidebar();
  } catch (e) {
    console.error('Move failed:', e);
    showToast('移动失败');
  }
}

// Move item within same local mount
async function moveLocalItem(mountId, srcPath, destDir) {
  const localMount = state.localMounts[mountId];
  if (!localMount) return;
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      if (!(await ensureWritePermission(mountId))) return;
      const srcParentPath = srcPath.substring(0, srcPath.lastIndexOf('/')) || '/';
      const srcName = srcPath.substring(srcPath.lastIndexOf('/') + 1);
      const srcParentHandle = await getLocalDirHandle(localMount.handle, srcParentPath);
      const destDirHandle = await getLocalDirHandle(localMount.handle, destDir);
      if (!srcParentHandle || !destDirHandle) {
        showToast('目录不存在');
        return;
      }

      // Check if destination already exists
      const isSrcDir = await (async () => {
        try {
          await srcParentHandle.getDirectoryHandle(srcName);
          return true;
        } catch {
          return false;
        }
      })();
      let destName = srcName;
      if (await localEntryExists(destDirHandle, srcName, isSrcDir)) {
        const suggested = suggestRename(srcName);
        const choice = await showDuplicateDialog(suggested);
        if (choice === 'cancel') return;
        if (choice === 'rename') {
          destName = suggested;
        } else {
          // overwrite: remove existing first
          await destDirHandle.removeEntry(srcName, { recursive: isSrcDir });
        }
      }

      if (isSrcDir) {
        // Move directory: copy recursively then remove original
        const srcDirHandle = await srcParentHandle.getDirectoryHandle(srcName);
        await copyLocalDir(srcDirHandle, destDirHandle, destName);
        await srcParentHandle.removeEntry(srcName, { recursive: true });
      } else {
        const srcFileHandle = await srcParentHandle.getFileHandle(srcName);
        const file = await srcFileHandle.getFile();
        const destFileHandle = await destDirHandle.getFileHandle(destName, { create: true });
        const writable = await destFileHandle.createWritable();
        await writable.write(await file.arrayBuffer());
        await writable.close();
        await srcParentHandle.removeEntry(srcName);
      }

      showToast('已移动');
      await loadLocalTree(mountId);
      renderSidebar();
      return; // success
    } catch (e) {
      if (attempt === 0 && e.name === 'InvalidStateError') {
        continue; // retry with fresh handles
      }
      console.error('Local move failed:', e);
      showToast('移动失败');
      return;
    }
  }
}

// Copy a local directory recursively
async function copyLocalDir(srcDirHandle, destParentHandle, dirName) {
  const newDirHandle = await destParentHandle.getDirectoryHandle(dirName, { create: true });
  for await (const entry of srcDirHandle.values()) {
    if (entry.kind === 'file') {
      const file = await entry.getFile();
      const newFileHandle = await newDirHandle.getFileHandle(entry.name, { create: true });
      const writable = await newFileHandle.createWritable();
      await writable.write(await file.arrayBuffer());
      await writable.close();
    } else {
      await copyLocalDir(entry, newDirHandle, entry.name);
    }
  }
}

// Cross-mount move/copy on server
async function crossMountServer(srcMountId, srcPath, destMountId, destDir, action) {
  try {
    const endpoint = action === 'move' ? '/api/cross-mount-move' : '/api/cross-mount-copy';
    const headers = {};
    if (state.isAdmin) headers['X-Admin'] = '1';
    let params = new URLSearchParams({
      srcMount: srcMountId,
      srcPath: srcPath,
      destMount: destMountId,
      destDir: destDir,
    });
    let resp = await fetch(`${_apiBase}${endpoint}?${params}`, {
      method: 'POST',
      headers,
    });
    if (resp.status === 409) {
      const data = await resp.json().catch(() => ({}));
      const choice = await showDuplicateDialog(data.suggested_name || '');
      if (choice === 'cancel') return;
      params = new URLSearchParams({
        srcMount: srcMountId,
        srcPath: srcPath,
        destMount: destMountId,
        destDir: destDir,
        ...(choice === 'overwrite' ? { overwrite: '1' } : { newName: data.suggested_name }),
      });
      resp = await fetch(`${_apiBase}${endpoint}?${params}`, {
        method: 'POST',
        headers,
      });
    }
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      showToast(data.error || '操作失败');
      return;
    }
    const actionText = action === 'move' ? '移动' : '复制';
    showToast(`已${actionText}`);
    // Refresh both mounts
    delete state.treeData[srcMountId];
    delete state.treeData[destMountId];
    await loadTree(srcMountId, '/');
    await loadTree(destMountId, '/');
    renderSidebar();
  } catch (e) {
    console.error('Cross-mount operation failed:', e);
    showToast('操作失败');
  }
}

// Cross-mount move/copy between local mounts
async function crossMountLocal(srcMountId, srcPath, destMountId, destDir, action) {
  const srcLocalMount = state.localMounts[srcMountId];
  const destLocalMount = state.localMounts[destMountId];
  if (!srcLocalMount || !destLocalMount) return;

  // Retry once on InvalidStateError (File System Access API handle cache staleness)
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      // Request write permission on both mounts
      if (!(await ensureWritePermission(srcMountId))) return;
      if (!(await ensureWritePermission(destMountId))) return;
      // Always re-resolve handles from root to avoid stale cache
      const srcParentPath = srcPath.substring(0, srcPath.lastIndexOf('/')) || '/';
      const srcName = srcPath.substring(srcPath.lastIndexOf('/') + 1);
      const srcParentHandle = await getLocalDirHandle(srcLocalMount.handle, srcParentPath);
      const destDirHandle = await getLocalDirHandle(destLocalMount.handle, destDir);
      if (!srcParentHandle || !destDirHandle) {
        showToast('目录不存在');
        return;
      }

      const isDir = await (async () => {
        try {
          await srcParentHandle.getDirectoryHandle(srcName);
          return true;
        } catch {
          return false;
        }
      })();

      if (isDir) {
        const srcDirHandle = await srcParentHandle.getDirectoryHandle(srcName);
        let destName = srcName;
        if (await localEntryExists(destDirHandle, srcName, true)) {
          const suggested = suggestRename(srcName);
          const choice = await showDuplicateDialog(suggested);
          if (choice === 'cancel') return;
          if (choice === 'rename') {
            destName = suggested;
          } else {
            // overwrite: remove existing directory first
            await destDirHandle.removeEntry(srcName, { recursive: true });
          }
        }
        await copyLocalDir(srcDirHandle, destDirHandle, destName);
        if (action === 'move') {
          await srcParentHandle.removeEntry(srcName, { recursive: true });
        }
        showToast(action === 'move' ? '已移动' : '已复制');
      } else {
        let destName = srcName;
        if (await localEntryExists(destDirHandle, srcName, false)) {
          const suggested = suggestRename(srcName);
          const choice = await showDuplicateDialog(suggested);
          if (choice === 'cancel') return;
          if (choice === 'rename') {
            destName = suggested;
          }
          // overwrite: getFileHandle with create:true will replace content
        }
        const srcFileHandle = await srcParentHandle.getFileHandle(srcName);
        const file = await srcFileHandle.getFile();
        const destFileHandle = await destDirHandle.getFileHandle(destName, { create: true });
        const writable = await destFileHandle.createWritable();
        await writable.write(await file.arrayBuffer());
        await writable.close();
        if (action === 'move') {
          await srcParentHandle.removeEntry(srcName);
        }
        showToast(action === 'move' ? '已移动' : '已复制');
      }
      await loadLocalTree(srcMountId);
      await loadLocalTree(destMountId);
      renderSidebar();
      return; // success
    } catch (e) {
      if (attempt === 0 && e.name === 'InvalidStateError') {
        // Stale handle — retry with fresh handles
        continue;
      }
      console.error('Cross-mount local operation failed:', e);
      showToast('操作失败');
      return;
    }
  }
}

// Cross-machine: local → server
async function localToServer(srcMountId, srcPath, destMountId, destDir, action) {
  const srcLocalMount = state.localMounts[srcMountId];
  if (!srcLocalMount) return;

  // Only support single MD file
  if (!srcPath.toLowerCase().endsWith('.md')) {
    showToast('跨机器操作仅支持 MD 文件');
    return;
  }

  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      // Read file content from local
      const content = await readLocalFile(srcMountId, srcPath);
      if (content === null) {
        showToast('读取本机文件失败');
        return;
      }

      const fileName = srcPath.substring(srcPath.lastIndexOf('/') + 1);
      // Check if destination file already exists on server
      let destFileName = fileName;
      const existingContent = await API.getFile(
        destMountId,
        destDir === '/' ? '/' + fileName : destDir + '/' + fileName,
      );
      if (existingContent !== null) {
        const suggested = suggestRename(fileName);
        const choice = await showDuplicateDialog(suggested);
        if (choice === 'cancel') return;
        if (choice === 'rename') {
          destFileName = suggested;
        }
        // overwrite: just write to same path, will replace content
      }
      const destFilePath = destDir === '/' ? '/' + destFileName : destDir + '/' + destFileName;

      // Write to server
      const result = await API.putFile(destMountId, destFilePath, content);
      if (!result || result.status === 'error') {
        showToast(result?.error || '写入服务器文件失败');
        return;
      }

      // If move, delete source
      if (action === 'move') {
        if (!(await ensureWritePermission(srcMountId))) return;
        const srcParentPath = srcPath.substring(0, srcPath.lastIndexOf('/')) || '/';
        const srcParentHandle = await getLocalDirHandle(srcLocalMount.handle, srcParentPath);
        if (srcParentHandle) {
          await srcParentHandle.removeEntry(fileName);
        }
      }

      showToast(action === 'move' ? '已移动到服务器' : '已复制到服务器');
      await loadLocalTree(srcMountId);
      delete state.treeData[destMountId];
      await loadTree(destMountId, '/');
      renderSidebar();
      return; // success
    } catch (e) {
      if (attempt === 0 && e.name === 'InvalidStateError') {
        continue; // retry with fresh handles
      }
      console.error('Local to server operation failed:', e);
      showToast('操作失败');
      return;
    }
  }
}

// Cross-machine: server → local
async function serverToLocal(srcMountId, srcPath, destMountId, destDir, action) {
  const destLocalMount = state.localMounts[destMountId];
  if (!destLocalMount) return;

  // Only support single MD file
  if (!srcPath.toLowerCase().endsWith('.md')) {
    showToast('跨机器操作仅支持 MD 文件');
    return;
  }

  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      // Read file content from server
      const content = await API.getFile(srcMountId, srcPath);
      if (content === null) {
        showToast('读取服务器文件失败');
        return;
      }

      const fileName = srcPath.substring(srcPath.lastIndexOf('/') + 1);

      // Check if destination file already exists locally
      const destDirHandle = await getLocalDirHandle(destLocalMount.handle, destDir);
      let destFileName = fileName;
      if (destDirHandle && (await localEntryExists(destDirHandle, fileName, false))) {
        const suggested = suggestRename(fileName);
        const choice = await showDuplicateDialog(suggested);
        if (choice === 'cancel') return;
        if (choice === 'rename') {
          destFileName = suggested;
        }
        // overwrite: writeLocalFile will replace content
      }

      // Write to local
      const destFilePath = destDir === '/' ? '/' + destFileName : destDir + '/' + destFileName;
      const ok = await writeLocalFile(destMountId, destFilePath, content);
      if (!ok) {
        showToast('写入本机文件失败');
        return;
      }

      // If move, delete source from server
      if (action === 'move') {
        await API.deleteFile(srcMountId, srcPath);
      }

      showToast(action === 'move' ? '已移动到本机' : '已复制到本机');
      delete state.treeData[srcMountId];
      await loadTree(srcMountId, '/');
      await loadLocalTree(destMountId);
      renderSidebar();
      return; // success
    } catch (e) {
      if (attempt === 0 && e.name === 'InvalidStateError') {
        continue; // retry with fresh handles
      }
      console.error('Server to local operation failed:', e);
      showToast('操作失败');
      return;
    }
  }
}

// === Rename (modal dialog) ===
async function deleteCurrentFile() {
  const path = state.currentPath;
  const mountId = state.currentMountId;
  if (!path || !mountId || path === '/') return;
  const name = path.split('/').pop();
  if (!window.confirm(`确定要删除「${name}」吗？此操作不可撤销。`)) return;
  const mount = state.mounts.find((m) => m.id === mountId);
  if (!mount) return;
  try {
    if (mount._local && state.localMounts[mountId]) {
      const localMount = state.localMounts[mountId];
      if (!(await ensureWritePermission(mountId))) return;
      const parentPath = path.substring(0, path.lastIndexOf('/')) || '/';
      const parentHandle = await getLocalDirHandle(localMount.handle, parentPath);
      if (!parentHandle) {
        showToast('目录不存在');
        return;
      }
      await parentHandle.removeEntry(name);
      showToast('已删除');
      await loadLocalTree(mountId);
    } else {
      const result = await API.deleteFile(mountId, path);
      if (!result || result.error) {
        showToast(result?.error || '删除失败');
        return;
      }
      showToast('已删除');
      delete state.treeData[mountId];
      await loadTree(mountId, '/');
      // Remove from recent files
      state.recentFiles = state.recentFiles.filter(
        (f) => !(f.mountId === mountId && f.path === path),
      );
      renderRecentFiles();
    }
    // Navigate away from deleted file
    state.currentPath = null;
    state.currentMountId = null;
    localStorage.removeItem('nasmd_last_path');
    localStorage.removeItem('nasmd_last_mount');
    $('breadcrumb').textContent = '';
    $('rename-top-btn').style.display = 'none';
    $('delete-top-btn').style.display = 'none';
    $('editor-modes').style.display = 'none';
    $('save-group').style.display = 'none';
    if (window._vditor) window._vditor.destroy();
    navigateHome();
    renderSidebar();
  } catch (e) {
    console.error('Delete failed:', e);
    showToast('删除失败');
  }
}

function showRenameModal() {
  const path = state.currentPath;
  const mountId = state.currentMountId;
  if (!path || !mountId || path === '/') return;

  const mount = state.mounts.find((m) => m.id === mountId);
  if (!mount || mount.readonly) return;

  const oldName = path.substring(path.lastIndexOf('/') + 1);
  const isDir = !oldName.includes('.');

  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay active';
  overlay.innerHTML = `
    <div class="modal-box">
      <div class="modal-title">重命名</div>
      <div class="modal-body">
        <input type="text" id="rename-modal-input" class="rename-input" value="${oldName}" />
      </div>
      <div class="modal-actions">
        <button class="modal-cancel" onclick="this.closest('.modal-overlay').remove()">取消</button>
        <button class="modal-confirm" id="rename-modal-confirm">确定</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  const input = document.getElementById('rename-modal-input');
  if (!isDir && oldName.includes('.')) {
    input.setSelectionRange(0, oldName.lastIndexOf('.'));
  } else {
    input.select();
  }
  input.focus();

  const doRename = async () => {
    const newName = input.value.trim();
    overlay.remove();
    if (!newName || newName === oldName) return;
    if (newName.includes('/') || newName.includes('\\')) {
      showToast('名称不能包含 / 或 \\');
      return;
    }

    const newPath = path.substring(0, path.lastIndexOf('/') + 1) + newName;
    const isLocal = mount && mount._local;

    if (isLocal) {
      await renameLocalItem(mountId, path, newPath, newName);
    } else {
      await renameServerItem(mountId, path, newPath);
    }
  };

  document.getElementById('rename-modal-confirm').addEventListener('click', doRename);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      doRename();
    } else if (e.key === 'Escape') {
      overlay.remove();
    }
  });
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) overlay.remove();
  });
}

async function renameServerItem(mountId, oldPath, newPath) {
  try {
    const params = new URLSearchParams({ oldPath: oldPath, newPath: newPath });
    const headers = {};
    if (state.isAdmin) headers['X-Admin'] = '1';
    const resp = await fetch(`${_apiBase}/api/mounts/${mountId}/rename?${params}`, {
      method: 'PUT',
      headers,
    });
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      showToast(data.error || '重命名失败');
      renderSidebar();
      return;
    }
    showToast('已重命名');
    // Update current path and breadcrumb if the renamed file is currently open
    if (state.currentPath === oldPath) {
      state.currentPath = newPath;
      localStorage.setItem('nasmd_last_path', newPath);
      const mount = state.mounts.find((m) => m.id === mountId);
      $('breadcrumb').textContent =
        (mount ? mount.name : '') + newPath + (mount && mount.readonly ? ' (只读)' : '');
    }
    // Update recent files: replace old path with new path
    const ri = state.recentFiles.findIndex((f) => f.mountId === mountId && f.path === oldPath);
    if (ri >= 0) {
      state.recentFiles[ri] = {
        ...state.recentFiles[ri],
        path: newPath,
        name: newPath.split('/').pop(),
      };
    }
    // Update accessLog key
    const oldKey = mountId + ':' + oldPath;
    const newKey = mountId + ':' + newPath;
    if (state.accessLog[oldKey] !== undefined) {
      state.accessLog[newKey] = state.accessLog[oldKey];
      delete state.accessLog[oldKey];
      localStorage.setItem('nasmd_access_log', JSON.stringify(state.accessLog));
    }
    renderRecentFiles();
    delete state.treeData[mountId];
    await loadTree(mountId, '/');
    renderSidebar();
  } catch (e) {
    console.error('Rename failed:', e);
    showToast('重命名失败');
    renderSidebar();
  }
}

async function renameLocalItem(mountId, oldPath, newPath, newName) {
  const localMount = state.localMounts[mountId];
  if (!localMount) return;
  try {
    if (!(await ensureWritePermission(mountId))) return;
    const parentPath = oldPath.substring(0, oldPath.lastIndexOf('/')) || '/';
    const oldName = oldPath.substring(oldPath.lastIndexOf('/') + 1);
    const parentHandle = await getLocalDirHandle(localMount.handle, parentPath);
    if (!parentHandle) {
      showToast('目录不存在');
      renderSidebar();
      return;
    }

    // Check if new name already exists
    // Determine if it's a dir by trying to get it
    let srcIsDir = false;
    try {
      await parentHandle.getDirectoryHandle(oldName);
      srcIsDir = true;
    } catch {
      srcIsDir = false;
    }

    // Check destination doesn't exist
    try {
      if (srcIsDir) {
        await parentHandle.getDirectoryHandle(newName);
      } else {
        await parentHandle.getFileHandle(newName);
      }
      showToast('已存在同名项');
      renderSidebar();
      return;
    } catch {
      // OK, doesn't exist
    }

    // For local FS, we need to copy then delete (no native rename in File System Access API)
    if (srcIsDir) {
      const srcDirHandle = await parentHandle.getDirectoryHandle(oldName);
      await copyLocalDir(srcDirHandle, parentHandle, newName);
      await parentHandle.removeEntry(oldName, { recursive: true });
    } else {
      const srcFileHandle = await parentHandle.getFileHandle(oldName);
      const file = await srcFileHandle.getFile();
      const destFileHandle = await parentHandle.getFileHandle(newName, { create: true });
      const writable = await destFileHandle.createWritable();
      await writable.write(await file.arrayBuffer());
      await writable.close();
      await parentHandle.removeEntry(oldName);
    }

    showToast('已重命名');
    // Update current path and breadcrumb if the renamed file is currently open
    if (state.currentPath === oldPath) {
      state.currentPath = newPath;
      localStorage.setItem('nasmd_last_path', newPath);
      const mount = state.mounts.find((m) => m.id === mountId);
      $('breadcrumb').textContent =
        (mount ? mount.name : '') + newPath + (mount && mount.readonly ? ' (只读)' : '');
    }
    // Update recent files: replace old path with new path
    const ri = state.recentFiles.findIndex((f) => f.mountId === mountId && f.path === oldPath);
    if (ri >= 0) {
      state.recentFiles[ri] = {
        ...state.recentFiles[ri],
        path: newPath,
        name: newPath.split('/').pop(),
      };
    }
    // Update accessLog key
    const oldKey = mountId + ':' + oldPath;
    const newKey = mountId + ':' + newPath;
    if (state.accessLog[oldKey] !== undefined) {
      state.accessLog[newKey] = state.accessLog[oldKey];
      delete state.accessLog[oldKey];
      localStorage.setItem('nasmd_access_log', JSON.stringify(state.accessLog));
    }
    renderRecentFiles();
    await loadLocalTree(mountId);
    renderSidebar();
  } catch (e) {
    console.error('Local rename failed:', e);
    showToast('重命名失败');
    renderSidebar();
  }
}

// === Create file / folder ===
async function createItem(mountId, dirPath, kind) {
  const mount = state.mounts.find((m) => m.id === mountId);
  if (!mount || mount.readonly) {
    showToast('该目录不可写');
    return;
  }
  const title = kind === 'folder' ? '新建文件夹' : '新建文件';
  const placeholder = kind === 'folder' ? '文件夹名称' : '文件名称（无需输入 .md 后缀）';

  // Use modal dialog instead of prompt() which is blocked in iframes
  const name = await new Promise((resolve) => {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay active';
    overlay.innerHTML = `
      <div class="modal-box">
        <div class="modal-title">${title}</div>
        <div class="modal-body">
          <input type="text" id="create-modal-input" class="rename-input" placeholder="${placeholder}" />
        </div>
        <div class="modal-actions">
          <button class="modal-cancel" id="create-modal-cancel">取消</button>
          <button class="modal-confirm" id="create-modal-confirm">确定</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);
    const input = document.getElementById('create-modal-input');
    input.focus();
    const done = (val) => {
      overlay.remove();
      resolve(val);
    };
    document.getElementById('create-modal-cancel').onclick = () => done(null);
    document.getElementById('create-modal-confirm').onclick = () => done(input.value);
    input.onkeydown = (e) => {
      if (e.key === 'Enter') done(input.value);
      if (e.key === 'Escape') done(null);
    };
    overlay.onclick = (e) => {
      if (e.target === overlay) done(null);
    };
  });

  if (!name || !name.trim()) return;
  const trimmedName = name.trim();

  // Local mount: use File System Access API
  if (mount._local && state.localMounts[mountId]) {
    try {
      if (!(await ensureWritePermission(mountId))) return;
      const localHandle = state.localMounts[mountId].handle;
      const dirHandle = await getLocalDirHandle(localHandle, dirPath);
      if (!dirHandle) {
        showToast('目录不存在');
        return;
      }
      if (kind === 'folder') {
        let folderName = trimmedName;
        if (await localEntryExists(dirHandle, folderName, true)) {
          const suggested = suggestRename(folderName);
          const choice = await showDuplicateDialog(suggested);
          if (choice === 'cancel') return;
          if (choice === 'rename') {
            folderName = suggested;
          } else {
            // overwrite: remove existing directory first
            await dirHandle.removeEntry(folderName, { recursive: true });
          }
        }
        const newDir = await dirHandle.getDirectoryHandle(folderName, { create: true });
        // Auto-create tmp.md from template so the folder is visible in sidebar
        let templateContent = '';
        try {
          const resp = await fetch(`${_apiBase}/api/folder-template`);
          if (resp.ok) {
            const data = await resp.json();
            templateContent = data.content || '';
          }
        } catch {}
        const tmpHandle = await newDir.getFileHandle('tmp.md', { create: true });
        const tmpWritable = await tmpHandle.createWritable();
        await tmpWritable.write(templateContent);
        await tmpWritable.close();
        showToast(`已创建文件夹: ${folderName}`);
      } else {
        let fileName = trimmedName.endsWith('.md') ? trimmedName : trimmedName + '.md';
        if (await localEntryExists(dirHandle, fileName, false)) {
          const suggested = suggestRename(fileName);
          const choice = await showDuplicateDialog(suggested);
          if (choice === 'cancel') return;
          if (choice === 'rename') {
            fileName = suggested;
          }
          // overwrite: getFileHandle with create:true will replace content
        }
        const fileHandle = await dirHandle.getFileHandle(fileName, { create: true });
        const writable = await fileHandle.createWritable();
        await writable.write('');
        await writable.close();
        showToast(`已创建: ${fileName}`);
        const filePath = dirPath === '/' ? '/' + fileName : dirPath + '/' + fileName;
        await loadLocalTree(mountId);
        renderSidebar();
        openFile(filePath, mountId);
        return;
      }
      await loadLocalTree(mountId);
      renderSidebar();
    } catch (e) {
      if (e.name === 'NotAllowedError') {
        showToast('权限不足，请重新授权目录访问');
      } else {
        console.error('Local create failed:', e);
        showToast('创建失败: ' + (e.message || e));
      }
    }
    return;
  }

  // Server mount: use API
  try {
    let params = new URLSearchParams({
      path: dirPath,
      name: trimmedName,
      kind: kind,
    });
    const headers = {};
    if (state.isAdmin) headers['X-Admin'] = '1';
    let resp = await fetch(`${_apiBase}/api/mounts/${mountId}/create?${params}`, {
      method: 'POST',
      headers,
    });
    if (resp.status === 409) {
      const data = await resp.json().catch(() => ({}));
      const choice = await showDuplicateDialog(data.suggested_name || '');
      if (choice === 'cancel') return;
      params = new URLSearchParams({
        path: dirPath,
        name: trimmedName,
        kind: kind,
        ...(choice === 'overwrite' ? { overwrite: '1' } : { newName: data.suggested_name }),
      });
      resp = await fetch(`${_apiBase}/api/mounts/${mountId}/create?${params}`, {
        method: 'POST',
        headers,
      });
    }
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      showToast(data.error || '创建失败');
      return;
    }
    const result = await resp.json();
    showToast(`已创建: ${result.name}`);
    // Force refresh the entire mount tree (recursive tree is nested from root)
    delete state.treeData[mountId];
    await loadTree(mountId, '/');
    renderSidebar();
    // Auto-open the new file
    if (kind === 'file' && result.name) {
      const filePath = dirPath === '/' ? '/' + result.name : dirPath + '/' + result.name;
      openFile(filePath, mountId);
    }
  } catch (e) {
    console.error('Create item failed:', e);
    showToast('创建失败');
  }
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
    let content;
    if (mount._local && state.localMounts[mount.id]) {
      // Read from local File System Access API
      content = await readLocalFile(mount.id, path);
    } else {
      content = await API.getFile(mount.id, path);
    }
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
    // Update recent files list and re-render
    const existing = state.recentFiles.findIndex((f) => f.mountId === mount.id && f.path === path);
    const entry = { name: path.split('/').pop(), path, modTime: Date.now(), mountId: mount.id };
    if (existing >= 0) {
      state.recentFiles.splice(existing, 1);
    }
    state.recentFiles.unshift(entry);
    state.recentFiles = state.recentFiles.slice(0, 10);
    renderRecentFiles();

    $('breadcrumb').textContent = mount.name + path + (mount.readonly ? ' (只读)' : '');
    // Show rename/delete buttons if file is writable and not root
    const renameBtn = $('rename-top-btn');
    const deleteBtn = $('delete-top-btn');
    if (renameBtn) {
      renameBtn.style.display = !mount.readonly && path !== '/' ? '' : 'none';
    }
    if (deleteBtn) {
      deleteBtn.style.display = !mount.readonly && path !== '/' ? '' : 'none';
    }
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
state.autoSave = localStorage.getItem('nasmd_autosave') !== '0';

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
  // Sync Vditor theme
  if (window._vditor) {
    window._vditor.setTheme(
      isDark ? 'dark' : 'classic',
      isDark ? 'dark' : 'light',
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
    // Local mount: save via File System Access API
    if (mount && mount._local && state.localMounts[mount.id]) {
      const ok = await writeLocalFile(mount.id, state.currentPath, content);
      if (!ok) throw new Error('写入本机文件失败');
      window._originalContent = content;
      markClean();
      clearLocalStorage(state.currentPath);
      if (!silent) showToast('已保存');
      else showToast('自动保存完成');
    } else {
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
    }
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
  // Open welcome.md from builtin-storage
  const builtin = state.mounts.find((m) => m.id === 'builtin-storage');
  if (builtin) {
    if (!state.treeData[builtin.id]) {
      loadTree(builtin.id, '/').then(() => {
        const root = state.treeData[builtin.id]?.['/'];
        const welcome = (root?.children || []).find((e) => e.name === '欢迎.md');
        if (welcome) openFile(welcome.path, builtin.id);
      });
    } else {
      const root = state.treeData[builtin.id]?.['/'];
      const welcome = (root?.children || []).find((e) => e.name === '欢迎.md');
      if (welcome) openFile(welcome.path, builtin.id);
    }
  }
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
  // Skip sync for local mounts (browser-side directories, no server counterpart)
  if (state.currentMountId.startsWith('local-')) {
    state.syncStatus = 'synced';
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

let _refreshTreeBusy = false;

async function refreshTree() {
  // Prevent concurrent refresh
  if (_refreshTreeBusy) return;
  _refreshTreeBusy = true;
  try {
    // Refresh all expanded mount trees by reloading and comparing
    const expandedMountIds = state.expandedMounts.filter((id) => !id.includes(':'));
    let changed = false;
    for (const mountId of expandedMountIds) {
      // Collect expanded dir paths for this mount
      const expandedDirs = state.expandedMounts
        .filter((k) => k.startsWith(mountId + ':'))
        .map((k) => k.substring(mountId.length + 1));
      expandedDirs.push('/'); // always refresh root
      for (const dirPath of expandedDirs) {
        const oldChildren = state.treeData[mountId]?.[dirPath];
        // Force reload without clearing cache first
        // This prevents the tree from collapsing if the reload fails
        await loadTree(mountId, dirPath, true);
        const newChildren = state.treeData[mountId]?.[dirPath];
        // Quick check if tree changed
        if (oldChildren && newChildren) {
          const oldNames = (oldChildren.children || [])
            .map((e) => e.name)
            .sort()
            .join(',');
          const newNames = (newChildren.children || [])
            .map((e) => e.name)
            .sort()
            .join(',');
          if (oldNames !== newNames) changed = true;
        } else if (!oldChildren !== !newChildren) {
          changed = true;
        }
      }
    }
    if (changed) renderSidebar();
  } finally {
    _refreshTreeBusy = false;
  }
}

// === Sidebar auto-refresh ===
let _sidebarRefreshTimer = null;
const SIDEBAR_REFRESH_INTERVAL = 5000; // 5 seconds

function startSidebarRefresh() {
  if (_sidebarRefreshTimer) return;
  _sidebarRefreshTimer = setInterval(refreshTree, SIDEBAR_REFRESH_INTERVAL);
}

function stopSidebarRefresh() {
  if (_sidebarRefreshTimer) {
    clearInterval(_sidebarRefreshTimer);
    _sidebarRefreshTimer = null;
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
    // Refresh local mount trees before searching to avoid stale results
    for (const mountId of Object.keys(state.localMounts)) {
      try {
        await loadLocalTree(mountId);
      } catch (_e) {
        /* ignore */
      }
    }

    // Search server-side mounts
    const serverResults = await API.search(query);

    // Search client-side local mounts
    const localResults = await searchLocalMounts(query);

    // Merge results (local first, then server)
    state.searchResults = [...localResults, ...serverResults];

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
        const localBadge = r._local ? ' 📁' : '';
        return `<div class="search-result-item" data-idx="${i}">
        <span class="result-path">${displayTitle}${localBadge} <small style="color:var(--c-muted)">${displayPath}</small></span>
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
      if (!mountId) {
        // No mount_id from server — try to find matching mount in treeData
        const found = findMountForPath(relPath);
        if (!found) {
          showToast('无法确定文件的挂载点，请从侧边栏打开');
          return;
        }
        openFile(relPath, found.id, query);
      } else {
        openFile(relPath, mountId, query);
      }
      resultsEl.innerHTML = '';
      $('search-input').value = '';
    };
  } catch (e) {
    console.error('Search failed:', e);
  }
}

/**
 * Search local (client-side) mounts by reading .md files and matching query.
 * Returns results in the same format as the server search API.
 */
async function searchLocalMounts(query) {
  const results = [];
  const lowerQuery = query.toLowerCase();
  const localMountIds = Object.keys(state.localMounts);

  for (const mountId of localMountIds) {
    const mount = state.mounts.find((m) => m.id === mountId);
    if (!mount || mount.readonly) continue;

    const tree = state.treeData[mountId];
    if (!tree || !tree['/']) continue;

    // Collect all .md file paths from the tree
    const mdFiles = [];
    function collectMdFiles(entries) {
      for (const entry of entries) {
        if (entry.isDir) {
          if (entry.children) collectMdFiles(entry.children);
        } else if (entry.name.toLowerCase().endsWith('.md')) {
          mdFiles.push(entry);
        }
      }
    }
    collectMdFiles(tree['/'].children || []);

    // Read and search each file (limit to 50 files for performance)
    const filesToSearch = mdFiles.slice(0, 50);
    for (const entry of filesToSearch) {
      try {
        const content = await readLocalFile(mountId, entry.path);
        if (content === null) continue;
        const lowerContent = content.toLowerCase();

        // Match in filename or content
        const nameMatch = entry.name.toLowerCase().includes(lowerQuery);
        const contentMatch = lowerContent.includes(lowerQuery);

        if (nameMatch || contentMatch) {
          // Extract title from first heading or use filename
          let title = entry.name.replace(/\.md$/i, '');
          const headingMatch = content.match(/^#\s+(.+)$/m);
          if (headingMatch) title = headingMatch[1].trim();

          // Extract snippet around first match
          let snippet = '';
          const matchIdx = lowerContent.indexOf(lowerQuery);
          if (matchIdx >= 0) {
            const start = Math.max(0, matchIdx - 40);
            const end = Math.min(content.length, matchIdx + query.length + 60);
            snippet =
              (start > 0 ? '...' : '') +
              content.slice(start, end).replace(/\n/g, ' ') +
              (end < content.length ? '...' : '');
          }

          results.push({
            path: entry.path,
            rel_path: entry.path,
            filename: entry.name,
            title: title,
            snippet: snippet,
            mount_id: mountId,
            _local: true,
          });
        }
      } catch (_e) {
        // Skip unreadable files
      }
    }
  }
  return results;
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
