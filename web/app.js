/**
 * app.js - 应用主逻辑（原生 JS，无框架）
 */

// === 辅助函数 ===
// Vditor's getValue() may normalize content (e.g. add trailing newline).
// Use this for dirty comparison and originalContent sync to avoid false positives.
function _normContent(s) {
  return typeof s === 'string' ? s.replace(/\r\n/g, '\n').replace(/\n+$/, '') : '';
}
function _isContentDirty(cur, orig) {
  return _normContent(cur) !== _normContent(orig);
}
function _parseShareHash() {
  const hash = window.location.hash;
  if (!hash || !hash.startsWith('#file=')) return null;
  const raw = hash.substring(6); // e.g. "mount-1:/docs/readme.md"
  const slashIdx = raw.indexOf('/');
  if (slashIdx < 0) return null;
  return { mountId: raw.substring(0, slashIdx), path: raw.substring(slashIdx) };
}

function _parseRemoteHash() {
  const hash = window.location.hash;
  if (!hash || !hash.startsWith('#remote=')) return null;
  const encoded = hash.substring(8);
  try {
    // base64url decode -> JSON
    const b64 = encoded.replace(/-/g, '+').replace(/_/g, '/');
    const json = window.atob(b64);
    const params = JSON.parse(json);
    if (!params.src || !params.path) return null;
    return { src: params.src, path: params.path, key: params.key || '' };
  } catch (e) {
    console.warn('[remote] Failed to parse remote hash:', e);
    return null;
  }
}

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
  // File modification tracking for conflict detection and external change sync
  // "mountId:path" → { mtime: number, size: number }
  fileMtimes: {},
  // Version-driven collaboration state (replaces mtime optimistic lock for server mounts)
  baseVersion: 0, // version number of the content currently loaded in editor
  baseContent: '', // content snapshot at baseVersion (for diff computation)
  fileVersions: {}, // "mountId:path" -> last known version
  remoteFile: null, // { src, path, key } when in remote proxy mode
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

  // Check URL hash for remote file: #remote=<base64url json>
  const remoteParams = _parseRemoteHash();
  if (remoteParams) {
    await openRemoteFile(remoteParams.src, remoteParams.path, remoteParams.key);
    return;
  }

  // Check URL hash for shared file link: #file=mountId:/path/to/file.md
  const hashFile = _parseShareHash();
  if (hashFile) {
    const { mountId: shareMountId, path: sharePath } = hashFile;
    const mount = state.mounts.find((m) => m.id === shareMountId);
    if (mount && !mount._local) {
      try {
        let content;
        let serverMtime = null;
        const result = await API.getFile(shareMountId, sharePath);
        content = result ? result.content : null;
        if (result && result.mtime) serverMtime = result.mtime;
        if (content !== null) {
          state.currentPath = sharePath;
          state.currentMountId = shareMountId;
          state.searchResults = [];
          $('breadcrumb').textContent = mount.name + sharePath + (mount.readonly ? ' 🔒' : '');
          $('editor-modes').style.display = mount.readonly
            ? 'none'
            : sharePath.endsWith('.md')
              ? ''
              : 'none';
          $('save-group').style.display = mount.readonly ? 'none' : '';
          const _renameBtn = $('rename-top-btn');
          const _deleteBtn = $('delete-top-btn');
          const _downloadBtn = $('download-top-btn');
          const _exportPdfBtn = $('export-pdf-top-btn');
          const _shareBtn = $('share-top-btn');
          const _historyBtn = $('history-top-btn');
          if (_renameBtn)
            _renameBtn.style.display = !mount.readonly && sharePath !== '/' ? '' : 'none';
          if (_deleteBtn)
            _deleteBtn.style.display = !mount.readonly && sharePath !== '/' ? '' : 'none';
          if (_downloadBtn) _downloadBtn.style.display = sharePath.endsWith('.md') ? '' : 'none';
          if (_exportPdfBtn) _exportPdfBtn.style.display = sharePath.endsWith('.md') ? '' : 'none';
          if (_shareBtn) _shareBtn.style.display = sharePath !== '/' ? '' : 'none';
          if (_historyBtn) _historyBtn.style.display = sharePath.endsWith('.md') ? '' : 'none';
          showPage('editor');
          if (window._vditor) window._vditor.destroy();
          initEditor(content, state.editorMode, !!mount.readonly);
          // Connect to SSE for collaborative editing (non-readonly files)
          if (!mount.readonly && window.nasmdSSE) {
            window.nasmdSSE.connect(shareMountId, sharePath);
          }
          // Record mtime for server mount
          if (serverMtime) {
            state.fileMtimes[shareMountId + ':' + sharePath] = {
              mtime: serverMtime,
              size: content.length,
            };
          }
          // Initialize version-driven state
          if (result && result.version !== undefined) {
            state.baseVersion = result.version;
            state.baseContent = content;
            state.fileVersions[shareMountId + ':' + sharePath] = result.version;
          }
          setFileInfo(shareMountId, sharePath);
          state.dirty = false;
          startDirtyCheck();
          renderSidebar();
          startSidebarRefresh();
          startFilePoll();
          localStorage.setItem('nasmd_last_path', sharePath);
          localStorage.setItem('nasmd_last_mount', shareMountId);
          // Clear hash so refresh doesn't re-trigger
          history.replaceState(null, '', window.location.pathname);
          return;
        }
      } catch (_e) {
        console.warn('Failed to open shared file:', _e);
      }
    }
  }

  // Restore last opened file, or fall back to welcome.md
  const lastPath = localStorage.getItem('nasmd_last_path');
  const lastMountId = localStorage.getItem('nasmd_last_mount');
  if (lastPath && lastMountId) {
    const mount = state.mounts.find((m) => m.id === lastMountId);
    if (mount) {
      try {
        let content;
        let serverMtime = null;
        if (mount._local && state.localMounts[mount.id]) {
          content = await readLocalFile(mount.id, lastPath);
        } else {
          const result = await API.getFile(mount.id, lastPath);
          content = result ? result.content : null;
          if (result && result.mtime) serverMtime = result.mtime;
          if (result && result.version !== undefined) {
            state.baseVersion = result.version;
            state.baseContent = content;
            state.fileVersions[mount.id + ':' + lastPath] = result.version;
          }
        }
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
          const _downloadBtn = $('download-top-btn');
          const _exportPdfBtn = $('export-pdf-top-btn');
          const _shareBtn = $('share-top-btn');
          const _historyBtn = $('history-top-btn');
          if (_renameBtn)
            _renameBtn.style.display = !mount.readonly && lastPath !== '/' ? '' : 'none';
          if (_deleteBtn)
            _deleteBtn.style.display = !mount.readonly && lastPath !== '/' ? '' : 'none';
          if (_downloadBtn)
            _downloadBtn.style.display = lastPath !== '/' && lastPath.endsWith('.md') ? '' : 'none';
          if (_exportPdfBtn)
            _exportPdfBtn.style.display =
              lastPath !== '/' && lastPath.endsWith('.md') ? '' : 'none';
          if (_shareBtn) _shareBtn.style.display = !mount._local && lastPath !== '/' ? '' : 'none';
          if (_historyBtn)
            _historyBtn.style.display = lastPath !== '/' && lastPath.endsWith('.md') ? '' : 'none';
          // Show refresh button when a file is open
          const _refreshBtn = $('btn-refresh');
          if (_refreshBtn) _refreshBtn.style.display = lastPath !== '/' ? '' : 'none';
          showPage('editor');
          if (window._vditor) window._vditor.destroy();
          // Restore cursor/scroll position from localStorage
          try {
            const savedPos = JSON.parse(localStorage.getItem('nasmd_cursor_pos') || 'null');
            if (savedPos) {
              window._pendingRestore = savedPos;
            }
          } catch (_) {
            /* ignore */
          }
          initEditor(content, state.editorMode, !!mount.readonly);
          // Connect to SSE for collaborative editing (non-readonly files)
          if (!mount.readonly && window.nasmdSSE) {
            window.nasmdSSE.connect(mount.id, lastPath);
          }
          // Note: window._originalContent is set by Vditor's after() callback
          // Record mtime for all mounts
          if (mount._local) {
            try {
              const handle = await getLocalFileHandle(state.localMounts[mount.id].handle, lastPath);
              if (handle) {
                const file = await handle.getFile();
                state.fileMtimes[mount.id + ':' + lastPath] = {
                  mtime: file.lastModified,
                  size: file.size,
                };
              }
            } catch (_e) {
              /* file may have been deleted */
            }
          } else {
            // Server mount: use mtime from the initial API response
            if (serverMtime) {
              state.fileMtimes[mount.id + ':' + lastPath] = {
                mtime: serverMtime,
                size: content.length,
              };
              console.log(
                '[restore] server mount mtime recorded:',
                serverMtime,
                'size:',
                content.length,
              );
            } else {
              console.log('[restore] server mount: no mtime from API response');
            }
          }
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

          // Start auto-refresh timers (normally set up after the fallback block,
          // but we return early here so must start them before returning)
          window.addEventListener('beforeunload', () => saveCursorScrollToStorage());
          setInterval(() => {
            if (window._vditor && state.currentPath) saveCursorScrollToStorage();
          }, 2000);
          startSidebarRefresh();
          startFilePoll();
          document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
              if (window._vditor && state.currentPath) saveCursorScrollToStorage();
              stopSidebarRefresh();
              stopFilePoll();
            } else {
              refreshTree();
              startSidebarRefresh();
              startFilePoll();
            }
          });
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

  // Save cursor/scroll position before page unload
  window.addEventListener('beforeunload', () => saveCursorScrollToStorage());
  // Also periodically save cursor position so refresh/navigation doesn't lose it
  setInterval(() => {
    if (window._vditor && state.currentPath) saveCursorScrollToStorage();
  }, 2000);

  // Start sidebar auto-refresh (pause when tab is hidden)
  startSidebarRefresh();
  startFilePoll();
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      if (window._vditor && state.currentPath) saveCursorScrollToStorage();
      stopSidebarRefresh();
      stopFilePoll();
    } else {
      refreshTree();
      startSidebarRefresh();
      startFilePoll();
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
  let hasRawEntries = false;
  for await (const entry of dirHandle.values()) {
    hasRawEntries = true;
    const entryPath = parentPath === '/' ? '/' + entry.name : parentPath + '/' + entry.name;
    if (entry.kind === 'directory') {
      const subChildren = [];
      let hasMd = false;
      let isEmpty = true;
      let hasEmptyDir = false;
      try {
        const subHandle = await dirHandle.getDirectoryHandle(entry.name);
        const subResult = await readLocalDir(subHandle, entryPath);
        subChildren.push(...(subResult.children || []));
        hasMd = subResult.hasMd || false;
        isEmpty = subResult.isEmpty || false;
        hasEmptyDir = subResult.hasEmptyDir || false;
      } catch (_e) {
        /* skip unreadable dirs */
      }
      // Include dirs that contain .md files, are empty, or contain empty dirs
      if (hasMd || isEmpty || hasEmptyDir) {
        children.push({
          name: entry.name,
          path: entryPath,
          isDir: true,
          hasMd,
          isEmpty,
          hasEmptyDir,
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
  const isEmpty = !hasRawEntries;
  // Propagate hasEmptyDir: any child is empty or contains empty dirs
  const hasEmptyDir = children.some((c) => c.isDir && (c.isEmpty || c.hasEmptyDir));
  return {
    name: dirHandle.name,
    path: parentPath,
    isDir: true,
    children,
    hasMd,
    isEmpty,
    hasEmptyDir,
  };
}

async function buildTreeFromFileMap(fileMap, parentPath) {
  const entries = [];
  const dirMap = {};

  for (const [filePath, file] of Object.entries(fileMap)) {
    let valid = false;
    try {
      await file.slice(0, 1).arrayBuffer();
      valid = true;
    } catch (_) {
      /* file deleted externally */
    }
    if (!valid) continue;

    const relFromRoot = filePath.startsWith('/') ? filePath.substring(1) : filePath;
    const parts = relFromRoot.split('/');
    let currentPath = '';
    for (let i = 0; i < parts.length - 1; i++) {
      const prev = currentPath;
      currentPath = currentPath ? currentPath + '/' + parts[i] : parts[i];
      if (!dirMap['/' + currentPath]) {
        dirMap['/' + currentPath] = {
          name: parts[i],
          path: '/' + currentPath,
          isDir: true,
          children: [],
          hasMd: false,
        };
        if (prev) {
          dirMap['/' + prev].children.push(dirMap['/' + currentPath]);
        }
      }
    }
    const parentDirPath = currentPath ? '/' + currentPath : '/';
    const fileName = parts[parts.length - 1];
    const entry = {
      name: fileName,
      path: filePath,
      isDir: false,
      hasMd: true,
      size: file.size,
      modTime: file.lastModified,
    };
    if (dirMap[parentDirPath]) {
      dirMap[parentDirPath].children.push(entry);
    } else {
      entries.push(entry);
    }
  }

  function markHasMd(dirEntry) {
    let found = false;
    for (const child of dirEntry.children) {
      if (child.isDir) {
        if (markHasMd(child)) found = true;
      } else if (child.hasMd) {
        found = true;
      }
    }
    dirEntry.hasMd = found;
    return found;
  }
  // Propagate hasEmptyDir: a dir has it if any child dir is empty or has empty dirs
  function markHasEmptyDir(dirEntry) {
    if (!dirEntry.isDir) return false;
    let found = false;
    for (const child of dirEntry.children) {
      if (child.isDir) {
        markHasEmptyDir(child);
        if (child.isEmpty || child.hasEmptyDir) found = true;
      }
    }
    dirEntry.hasEmptyDir = found;
    return found;
  }
  for (const dirEntry of Object.values(dirMap)) {
    dirEntry.children.sort((a, b) => {
      if (a.isDir && !b.isDir) return -1;
      if (!a.isDir && b.isDir) return 1;
      return a.name.localeCompare(b.name);
    });
  }
  const root = dirMap['/'] || {
    name: '/',
    path: '/',
    isDir: true,
    children: [],
    hasMd: false,
  };
  if (root.children.length === 0) root.children = entries;
  markHasMd(root);
  markHasEmptyDir(root);

  if (parentPath === '/') return root;
  return (
    dirMap[parentPath] || {
      name: parentPath.split('/').pop(),
      path: parentPath,
      isDir: true,
      children: [],
      hasMd: false,
    }
  );
}

async function readLocalFile(mountId, path) {
  const localMount = state.localMounts[mountId];
  if (!localMount) {
    console.log('[readLocalFile] no localMount for', mountId);
    return null;
  }
  try {
    if (localMount.fileMap) {
      const file = localMount.fileMap[path];
      if (!file) {
        console.log(
          '[readLocalFile] fileMap miss for',
          path,
          'keys:',
          Object.keys(localMount.fileMap).slice(0, 5),
        );
        return null;
      }
      console.log(
        `[readLocalFile] reading from fileMap, size=${file.size} lastModified=${file.lastModified}`,
      );
      return await file.text();
    }
    const handle = await getLocalFileHandle(localMount.handle, path);
    if (!handle) {
      console.log('[readLocalFile] getLocalFileHandle returned null for', path);
      return null;
    }
    const file = await handle.getFile();
    console.log(
      `[readLocalFile] reading via FSAA, size=${file.size} lastModified=${file.lastModified}`,
    );
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
    const localMount = state.localMounts[mountId];
    // FSAA mode: read live directory handle
    if (localMount.handle) {
      try {
        const dirHandle = await getLocalDirHandle(localMount.handle, path);
        if (!dirHandle) return;
        const result = await readLocalDir(dirHandle, path);
        state.treeData[mountId][path] = result;
      } catch (e) {
        console.error('Failed to load local tree:', e);
      }
      return;
    }
    // Fallback mode (webkitdirectory): rebuild tree from fileMap
    if (localMount.fileMap) {
      const tree = buildTreeFromFileMap(localMount.fileMap, path);
      state.treeData[mountId][path] = tree;
      return;
    }
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

// Render a single mount point as an HTML string (used by renderSidebar).
// Extracted so renderSidebar can group host/server mounts separately from local mounts.
function _renderMountHtml(mount) {
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
  return html;
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

  // Regular mount points — group host/server mounts above, local mounts below
  // under a "本机目录" header with a divider, so locally mounted dirs are unified.
  const regularMounts = state.mounts.filter((m) => m.id !== 'builtin-storage');
  const serverMounts = regularMounts.filter((m) => !m._local);
  const localMounts = regularMounts.filter((m) => m._local);

  for (const mount of serverMounts) {
    tree.innerHTML += _renderMountHtml(mount);
  }

  if (localMounts.length > 0) {
    tree.innerHTML += '<div class="mount-section-divider"></div>';
    tree.innerHTML += '<div class="mount-section-header">本机目录</div>';
    for (const mount of localMounts) {
      tree.innerHTML += _renderMountHtml(mount);
    }
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
      // Always show .md files
      if (!e.isDir && e.name.toLowerCase().endsWith('.md')) return true;
      // Show directories that have .md files, are empty, or contain empty dirs
      if (e.isDir && (e.hasMd || e.isEmpty || e.hasEmptyDir)) return true;
      // Hide non-md files and directories without .md files that aren't empty
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
        if (canWrite) {
          html += `<span class="dir-actions">`;
          html += `<button class="mount-create-btn" onclick="event.stopPropagation();createItem('${mountId}','${fullPath}','file')" title="新建文件"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/></svg></button>`;
          html += `<button class="mount-create-btn" onclick="event.stopPropagation();createItem('${mountId}','${fullPath}','folder')" title="新建文件夹"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/><line x1="12" y1="11" x2="12" y2="17"/><line x1="9" y1="14" x2="15" y2="14"/></svg></button>`;
          html += `<button class="mount-create-btn" onclick="event.stopPropagation();renameFolder('${mountId}','${fullPath}')" title="重命名"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/><path d="M15 5H6"/></svg></button>`;
          html += `<button class="mount-create-btn dir-delete-btn" onclick="event.stopPropagation();deleteFolder('${mountId}','${fullPath}')" title="删除"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg></button>`;
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
    overlay.className = 'modal-overlay active';
    overlay.innerHTML = `
      <div class="modal-box">
        <div class="modal-header">文件名冲突</div>
        <div class="modal-body">
          目标位置已存在同名文件。<br>
          重命名规则：在文件名后添加时间戳后缀，如 <code>${suggestedName}</code>
        </div>
        <div class="modal-actions">
          <button class="modal-btn" id="dup-cancel">取消</button>
          <button class="modal-btn primary" id="dup-rename">重命名</button>
          <button class="modal-btn danger" id="dup-overwrite">覆盖</button>
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
    // Store structured drag info so drop handler can recover if dragend fires first
    e.dataTransfer.setData('application/x-nasmd-drag', JSON.stringify(_dragData));
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

    // Recover _dragData if dragend cleared it before drop fired
    if (!_dragData) {
      try {
        const dragJson = e.dataTransfer.getData('application/x-nasmd-drag');
        if (dragJson) _dragData = JSON.parse(dragJson);
      } catch (_) {
        /* ignore */
      }
    }

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
    const srcIsDir = _dragData.isDir;

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
          await localToServer(srcMountId, srcPath, destMountId, destPath, choice, srcIsDir);
        } else if (!srcIsLocal && destIsLocal) {
          await serverToLocal(srcMountId, srcPath, destMountId, destPath, choice, srcIsDir);
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
      _dragData = null;
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
async function localToServer(srcMountId, srcPath, destMountId, destDir, action, isDir) {
  const srcLocalMount = state.localMounts[srcMountId];
  if (!srcLocalMount) return;

  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      if (isDir) {
        await localDirToServer(srcMountId, srcPath, destMountId, destDir);
      } else {
        await localFileToServer(srcMountId, srcPath, destMountId, destDir);
      }

      // If move, delete source
      if (action === 'move') {
        if (!(await ensureWritePermission(srcMountId))) return;
        const srcParentPath = srcPath.substring(0, srcPath.lastIndexOf('/')) || '/';
        const srcName = srcPath.substring(srcPath.lastIndexOf('/') + 1);
        const srcParentHandle = await getLocalDirHandle(srcLocalMount.handle, srcParentPath);
        if (srcParentHandle) {
          await srcParentHandle.removeEntry(srcName, { recursive: isDir });
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

// Helper: copy a single local file to server (supports binary)
async function localFileToServer(srcMountId, srcPath, destMountId, destDir) {
  const srcLocalMount = state.localMounts[srcMountId];
  const fileName = srcPath.substring(srcPath.lastIndexOf('/') + 1);

  // Get local File object
  const fileHandle = await getLocalFileHandle(srcLocalMount.handle, srcPath);
  if (!fileHandle) throw new Error('无法读取本机文件');
  const file = await fileHandle.getFile();
  const arrayBuffer = await file.arrayBuffer();

  // Determine destination file name (handle duplicates)
  let destFileName = fileName;
  const destFilePath = destDir === '/' ? '/' + destFileName : destDir + '/' + destFileName;
  const existing = await API.getFile(destMountId, destFilePath);
  if (existing !== null) {
    const suggested = suggestRename(fileName);
    const choice = await showDuplicateDialog(suggested);
    if (choice === 'cancel') throw new Error('用户取消');
    if (choice === 'rename') destFileName = suggested;
    // overwrite: just write to same path
  }

  const finalDestPath = destDir === '/' ? '/' + destFileName : destDir + '/' + destFileName;
  const headers = {};
  if (state.isAdmin) headers['X-Admin'] = '1';
  const resp = await fetch(
    `${_apiBase}/api/mounts/${destMountId}/file?path=${encodeURIComponent(finalDestPath)}`,
    { method: 'PUT', headers, body: arrayBuffer },
  );
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.error || '写入服务器文件失败');
  }
}

// Helper: recursively copy a local directory to server
async function localDirToServer(srcMountId, srcPath, destMountId, destDir) {
  const srcLocalMount = state.localMounts[srcMountId];
  const dirName = srcPath.substring(srcPath.lastIndexOf('/') + 1);

  // Handle duplicate directory name at destination
  let destDirName = dirName;
  const destDirPath = destDir === '/' ? '/' + destDirName : destDir + '/' + destDirName;
  // Check if destination dir already exists by trying to list it.
  // Note: getTree returns an error JSON (no isDir field) for non-existent paths,
  // so we check isDir === true to confirm the directory truly exists.
  const existingTree = await API.getTree(destMountId, destDirPath);
  if (existingTree && existingTree.isDir === true) {
    const suggested = suggestRename(dirName);
    const choice = await showDuplicateDialog(suggested);
    if (choice === 'cancel') throw new Error('用户取消');
    if (choice === 'rename') destDirName = suggested;
    // overwrite: reuse existing directory, files will be overwritten
  }

  const finalDestDir = destDir === '/' ? '/' + destDirName : destDir + '/' + destDirName;
  // Create destination directory on server
  await API.mkdir(destMountId, finalDestDir);

  // Get source directory handle
  const srcDirHandle = await getLocalDirHandle(srcLocalMount.handle, srcPath);
  if (!srcDirHandle) throw new Error('源目录不存在');

  // Iterate over entries and recursively copy
  for await (const entry of srcDirHandle.values()) {
    const entryPath = srcPath + '/' + entry.name;
    if (entry.kind === 'file') {
      await localFileToServer(srcMountId, entryPath, destMountId, finalDestDir);
    } else {
      await localDirToServer(srcMountId, entryPath, destMountId, finalDestDir);
    }
  }
}

// Cross-machine: server → local
async function serverToLocal(srcMountId, srcPath, destMountId, destDir, action, isDir) {
  const destLocalMount = state.localMounts[destMountId];
  if (!destLocalMount) return;

  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      if (isDir) {
        await serverDirToLocal(srcMountId, srcPath, destMountId, destDir);
      } else {
        await serverFileToLocal(srcMountId, srcPath, destMountId, destDir);
      }

      // If move, delete source from server (deleteFile supports recursive dir removal)
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
      showToast(e.message || '操作失败');
      return;
    }
  }
}

// Helper: fetch a single server file as ArrayBuffer (supports binary files like images)
async function fetchServerFileBytes(mountId, path) {
  const headers = {};
  if (state.isAdmin) headers['X-Admin'] = '1';
  if (window.nasmdIdentity) {
    const identity = window.nasmdIdentity.get();
    if (identity) {
      headers['X-Client-Id'] = identity.id;
      headers['X-Client-Name'] = identity.name;
      headers['X-Client-Color'] = identity.color;
    }
  }
  const url = `${_apiBase}/api/mounts/${mountId}/file?path=${encodeURIComponent(path)}&_t=${Date.now()}`;
  const resp = await fetch(url, { headers, cache: 'no-store' });
  if (!resp.ok) {
    const errText = await resp.text().catch(() => '');
    throw new Error(errText || `读取服务器文件失败 (HTTP ${resp.status})`);
  }
  return await resp.arrayBuffer();
}

// Helper: write ArrayBuffer to a local file, creating parent directories as needed
async function writeLocalFileBytes(mountId, path, arrayBuffer) {
  const localMount = state.localMounts[mountId];
  if (!localMount) throw new Error('本机挂载不存在');
  if (!(await ensureWritePermission(mountId))) throw new Error('权限不足');
  const parts = path.split('/').filter(Boolean);
  let current = localMount.handle;
  // Navigate/create parent directories
  for (let i = 0; i < parts.length - 1; i++) {
    current = await current.getDirectoryHandle(parts[i], { create: true });
  }
  const fileName = parts[parts.length - 1];
  const fileHandle = await current.getFileHandle(fileName, { create: true });
  const writable = await fileHandle.createWritable();
  await writable.write(arrayBuffer);
  await writable.close();
}

// Helper: ensure a local directory exists (create if needed), returns dir handle
async function ensureLocalDir(mountId, path) {
  const localMount = state.localMounts[mountId];
  if (!localMount) throw new Error('本机挂载不存在');
  if (!path || path === '/') return localMount.handle;
  const parts = path.split('/').filter(Boolean);
  let current = localMount.handle;
  for (const part of parts) {
    current = await current.getDirectoryHandle(part, { create: true });
  }
  return current;
}

// Helper: copy a single server file to local (supports binary)
async function serverFileToLocal(srcMountId, srcPath, destMountId, destDir) {
  const fileName = srcPath.substring(srcPath.lastIndexOf('/') + 1);
  const destLocalMount = state.localMounts[destMountId];

  // Fetch file bytes from server (binary-safe)
  const arrayBuffer = await fetchServerFileBytes(srcMountId, srcPath);

  // Check if destination file already exists locally
  const destDirHandle = await getLocalDirHandle(destLocalMount.handle, destDir);
  if (!destDirHandle) throw new Error('目标目录不存在');

  let destFileName = fileName;
  if (await localEntryExists(destDirHandle, fileName, false)) {
    const suggested = suggestRename(fileName);
    const choice = await showDuplicateDialog(suggested);
    if (choice === 'cancel') throw new Error('用户取消');
    if (choice === 'rename') destFileName = suggested;
    // overwrite: writeLocalFileBytes will replace content
  }

  const destFilePath = destDir === '/' ? '/' + destFileName : destDir + '/' + destFileName;
  await writeLocalFileBytes(destMountId, destFilePath, arrayBuffer);
}

// Helper: recursively copy a server directory to local
async function serverDirToLocal(srcMountId, srcPath, destMountId, destDir) {
  const dirName = srcPath.substring(srcPath.lastIndexOf('/') + 1);
  const destLocalMount = state.localMounts[destMountId];

  // Handle duplicate directory name at destination (local side, reliable check)
  let destDirName = dirName;
  const destParentHandle = await getLocalDirHandle(destLocalMount.handle, destDir);
  if (!destParentHandle) throw new Error('目标目录不存在');
  if (await localEntryExists(destParentHandle, destDirName, true)) {
    const suggested = suggestRename(dirName);
    const choice = await showDuplicateDialog(suggested);
    if (choice === 'cancel') throw new Error('用户取消');
    if (choice === 'rename') destDirName = suggested;
    // overwrite: reuse existing directory, files will be overwritten
  }

  // Get recursive tree from server
  const tree = await API.getTree(srcMountId, srcPath);
  if (!tree || tree.isDir !== true) {
    throw new Error('读取服务器目录失败');
  }

  // Copy tree into destDir with the (possibly renamed) dir name.
  // Override the root node's name so the walker creates the right local dir.
  const rootNode = { ...tree, name: destDirName };
  await _serverTreeToLocal(srcMountId, rootNode, destMountId, destDir);
}

// Recursive walker: copy a server tree node into a local parent directory.
// - For a dir node: ensure the local dir exists, then recurse into children.
// - For a file node: fetch bytes from server and write locally.
async function _serverTreeToLocal(srcMountId, node, destMountId, parentDir) {
  if (node.isDir) {
    const dirPath = parentDir === '/' ? '/' + node.name : parentDir + '/' + node.name;
    await ensureLocalDir(destMountId, dirPath);
    if (node.children) {
      for (const child of node.children) {
        await _serverTreeToLocal(srcMountId, child, destMountId, dirPath);
      }
    }
  } else {
    // File: fetch bytes (binary-safe) and write to local parent dir
    const arrayBuffer = await fetchServerFileBytes(srcMountId, node.path);
    const filePath = parentDir === '/' ? '/' + node.name : parentDir + '/' + node.name;
    await writeLocalFileBytes(destMountId, filePath, arrayBuffer);
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
    $('download-top-btn').style.display = 'none';
    $('export-pdf-top-btn').style.display = 'none';
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

function downloadCurrentFile() {
  const path = state.currentPath;
  const mountId = state.currentMountId;
  if (!path || !mountId || path === '/') return;

  const name = path.substring(path.lastIndexOf('/') + 1);
  const content = window._vditor ? window._vditor.getValue() : '';
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  showToast('已下载 ' + name);
}

function exportCurrentPDF() {
  const path = state.currentPath;
  const mountId = state.currentMountId;
  if (!path || !mountId || path === '/') {
    showToast('请先打开一个文件');
    return;
  }

  if (!window._vditor) {
    showToast('编辑器尚未就绪');
    return;
  }

  const name = path.substring(path.lastIndexOf('/') + 1).replace(/\.md$/i, '');

  // Use browser's native print to produce a real PDF with selectable text,
  // heading-based outline, and proper SVG/mermaid rendering.
  // The @media print CSS rules hide the editor and show only the preview.
  document.title = name;
  window.print();
}

function showVersionHistory() {
  const path = state.currentPath;
  const mountId = state.currentMountId;
  if (!path || !mountId || path === '/') return;

  const fileKey = mountId + ':' + path;
  if (window.nasmdHistory) {
    window.nasmdHistory.show(fileKey);
  }
}

function shareCurrentFile() {
  const path = state.currentPath;
  const mountId = state.currentMountId;
  if (!path || !mountId || path === '/') return;

  const mount = state.mounts.find((m) => m.id === mountId);
  if (!mount || mount._local) return;

  // Build share URL: #file=mountId:/path/to/file.md
  const url = window.location.origin + window.location.pathname + '#file=' + mountId + path;
  navigator.clipboard
    .writeText(url)
    .then(() => showToast('分享链接已复制'))
    .catch(() => {
      // Fallback: select text in a temporary input
      const input = document.createElement('input');
      input.value = url;
      document.body.appendChild(input);
      input.select();
      document.execCommand('copy');
      document.body.removeChild(input);
      showToast('分享链接已复制');
    });
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
        await dirHandle.getDirectoryHandle(folderName, { create: true });
        // TODO: Auto-create tmp.md from template (temporarily disabled)
        // let templateContent = '';
        // try {
        //   const resp = await fetch(`${_apiBase}/api/folder-template`);
        //   if (resp.ok) {
        //     const data = await resp.json();
        //     templateContent = data.content || '';
        //   }
        // } catch {}
        // const tmpHandle = await newDir.getFileHandle('tmp.md', { create: true });
        // const tmpWritable = await tmpHandle.createWritable();
        // await tmpWritable.write(templateContent);
        // await tmpWritable.close();
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

async function renameFolder(mountId, dirPath) {
  const mount = state.mounts.find((m) => m.id === mountId);
  if (!mount || mount.readonly) {
    showToast('该目录不可写');
    return;
  }
  if (dirPath === '/') {
    showToast('不能重命名根目录');
    return;
  }

  const oldName = dirPath.substring(dirPath.lastIndexOf('/') + 1);

  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay active';
  overlay.innerHTML = `
    <div class="modal-box">
      <div class="modal-title">重命名文件夹</div>
      <div class="modal-body">
        <input type="text" id="rename-folder-input" class="rename-input" value="${oldName}" />
      </div>
      <div class="modal-actions">
        <button class="modal-cancel" onclick="this.closest('.modal-overlay').remove()">取消</button>
        <button class="modal-confirm" id="rename-folder-confirm">确定</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  const input = document.getElementById('rename-folder-input');
  input.select();
  input.focus();

  const doRename = async () => {
    const newName = input.value.trim();
    overlay.remove();
    if (!newName || newName === oldName) return;
    if (newName.includes('/') || newName.includes('\\')) {
      showToast('名称不能包含 / 或 \\');
      return;
    }

    const parentPath = dirPath.substring(0, dirPath.lastIndexOf('/')) || '/';
    const newPath = parentPath === '/' ? '/' + newName : parentPath + '/' + newName;

    try {
      if (mount._local && state.localMounts[mountId]) {
        if (!(await ensureWritePermission(mountId))) return;
        const localHandle = state.localMounts[mountId].handle;
        const parentHandle = await getLocalDirHandle(localHandle, parentPath);
        if (!parentHandle) {
          showToast('目录不存在');
          return;
        }
        const dirHandle = await getLocalDirHandle(localHandle, dirPath);
        await dirHandle.move(parentHandle, newName);
        showToast('已重命名');
        await loadLocalTree(mountId);
      } else {
        const result = await API.rename(mountId, dirPath, newPath);
        if (!result || result.error) {
          showToast(result?.error || '重命名失败');
          return;
        }
        showToast('已重命名');
        delete state.treeData[mountId];
        await loadTree(mountId, '/');
      }
      renderSidebar();
    } catch (e) {
      console.error('Rename folder failed:', e);
      showToast('重命名失败');
    }
  };

  document.getElementById('rename-folder-confirm').onclick = doRename;
  input.onkeydown = (e) => {
    if (e.key === 'Enter') doRename();
    if (e.key === 'Escape') overlay.remove();
  };
  overlay.onclick = (e) => {
    if (e.target === overlay) overlay.remove();
  };
}

async function deleteFolder(mountId, dirPath) {
  const mount = state.mounts.find((m) => m.id === mountId);
  if (!mount || mount.readonly) {
    showToast('该目录不可写');
    return;
  }
  if (dirPath === '/') {
    showToast('不能删除根目录');
    return;
  }

  const folderName = dirPath.substring(dirPath.lastIndexOf('/') + 1);

  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay active';
  overlay.innerHTML = `
    <div class="modal-box">
      <div class="modal-title">确认删除</div>
      <div class="modal-body">
        <p>确定要删除文件夹「${folderName}」吗？此操作不可撤销，文件夹内的所有文件也将被删除。</p>
      </div>
      <div class="modal-actions">
        <button class="modal-cancel" onclick="this.closest('.modal-overlay').remove()">取消</button>
        <button class="modal-confirm modal-danger" id="delete-folder-confirm">删除</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  const doDelete = async () => {
    overlay.remove();
    try {
      if (mount._local && state.localMounts[mountId]) {
        if (!(await ensureWritePermission(mountId))) return;
        const localHandle = state.localMounts[mountId].handle;
        const parentPath = dirPath.substring(0, dirPath.lastIndexOf('/')) || '/';
        const parentHandle = await getLocalDirHandle(localHandle, parentPath);
        if (!parentHandle) {
          showToast('目录不存在');
          return;
        }
        await parentHandle.removeEntry(folderName, { recursive: true });
        showToast('已删除');
        await loadLocalTree(mountId);
      } else {
        const result = await API.deleteFile(mountId, dirPath);
        if (!result || result.error) {
          showToast(result?.error || '删除失败');
          return;
        }
        showToast('已删除');
        delete state.treeData[mountId];
        await loadTree(mountId, '/');
      }

      if (state.currentPath?.startsWith(dirPath + '/')) {
        state.currentPath = null;
        state.currentMountId = null;
        localStorage.removeItem('nasmd_last_path');
        localStorage.removeItem('nasmd_last_mount');
        $('breadcrumb').textContent = '';
        const renameBtn = $('rename-top-btn');
        const deleteBtn = $('delete-top-btn');
        const downloadBtn = $('download-top-btn');
        const exportPdfBtn = $('export-pdf-top-btn');
        const shareBtn = $('share-top-btn');
        const historyBtn = $('history-top-btn');
        const editorModes = $('editor-modes');
        const saveGroup = $('save-group');
        if (renameBtn) renameBtn.style.display = 'none';
        if (deleteBtn) deleteBtn.style.display = 'none';
        if (downloadBtn) downloadBtn.style.display = 'none';
        if (exportPdfBtn) exportPdfBtn.style.display = 'none';
        if (shareBtn) shareBtn.style.display = 'none';
        if (historyBtn) historyBtn.style.display = 'none';
        if (editorModes) editorModes.style.display = 'none';
        if (saveGroup) saveGroup.style.display = 'none';
        if (window._vditor) window._vditor.destroy();
        navigateHome();
      }

      renderSidebar();
    } catch (e) {
      console.error('Delete folder failed:', e);
      showToast('删除失败');
    }
  };

  document.getElementById('delete-folder-confirm').onclick = doDelete;
  overlay.onclick = (e) => {
    if (e.target === overlay) overlay.remove();
  };
}

/**
 * Save current editor cursor position and scroll to localStorage.
 * Called before switching files or destroying the editor.
 */
function saveCursorScrollToStorage() {
  if (!window._vditor) {
    console.log('[saveCursor] skip: no _vditor');
    return;
  }
  try {
    const vd = window._vditor.vditor;
    const mode = window._vditor.getCurrentMode();
    // IR/WYSIWYG: .vditor-reset (overflow:auto) is the actual scroll container
    let scrollEl;
    if (mode === 'sv') {
      scrollEl = vd.sv.element;
    } else {
      const base = mode === 'wysiwyg' ? vd.wysiwyg.element : vd.ir.element;
      scrollEl = base ? base.querySelector('.vditor-reset') || base : null;
    }
    const maxScroll = scrollEl ? scrollEl.scrollHeight - scrollEl.clientHeight : 0;
    const scrollPercent = maxScroll > 0 ? scrollEl.scrollTop / maxScroll : 0;
    // Save cursor position details for debugging

    let headingText = null;
    let cursorViewportOffset = 0;
    let svCursorPos = 0;

    if (mode === 'sv') {
      const ta = vd.sv.element;
      svCursorPos = ta.selectionStart;
      const text = ta.value;
      const before = text.substring(0, ta.selectionStart);
      const lines = before.split('\n');
      for (let i = lines.length - 1; i >= 0; i--) {
        const m = lines[i].match(/^#{1,6}\s+(.+)/);
        if (m) {
          headingText = m[1].trim();
          break;
        }
      }
    } else {
      const sel = window.getSelection();
      if (sel.rangeCount > 0) {
        const range = sel.getRangeAt(0);
        const cursorRect = range.getBoundingClientRect();
        const scrollRect = scrollEl.getBoundingClientRect();
        cursorViewportOffset = Math.max(0, cursorRect.top - scrollRect.top);
        const editorEl = scrollEl;
        const cursorNode = range.startContainer;
        const heading = window._findHeadingAboveCursor
          ? window._findHeadingAboveCursor(editorEl, cursorNode)
          : null;
        if (heading) headingText = (heading.innerText || heading.textContent).trim();
      }
    }

    localStorage.setItem(
      'nasmd_cursor_pos',
      JSON.stringify({
        headingText,
        scrollPercent,
        cursorViewportOffset,
        svCursorPos,
      }),
    );
  } catch (_) {
    /* ignore */
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

async function openRemoteFile(src, path, key) {
  console.log('[remote] Opening remote file:', { src, path });
  state.remoteFile = { src, path, key };
  state.currentPath = path;
  state.currentMountId = null;

  let content;
  const result = await API.getRemoteFile(src, path, key);
  if (result && result.status === 'ok') {
    content = result.content || '';
  } else {
    showToast('远程文件加载失败');
    content = '# 加载失败\n\n无法从远程服务器获取文件内容。';
  }

  // UI: hide sidebar and file-management buttons, keep editor + save
  const sidebar = $('sidebar');
  if (sidebar) sidebar.style.display = 'none';
  const renameBtn = $('rename-top-btn');
  if (renameBtn) renameBtn.style.display = 'none';
  const deleteBtn = $('delete-top-btn');
  if (deleteBtn) deleteBtn.style.display = 'none';
  const shareBtn = $('share-top-btn');
  if (shareBtn) shareBtn.style.display = 'none';
  const historyBtn = $('history-top-btn');
  if (historyBtn) historyBtn.style.display = 'none';
  // Keep save, download, dark mode toggle visible
  $('save-group').style.display = '';
  $('editor-modes').style.display = path.endsWith('.md') ? '' : 'none';

  // Breadcrumb shows remote source info
  let remoteName = src;
  try {
    const u = new URL(src);
    remoteName = u.hostname;
  } catch (_e) {
    /* keep raw src */
  }
  $('breadcrumb').textContent = remoteName + ' ' + path;

  showPage('editor');
  if (window._vditor) window._vditor.destroy();
  initEditor(content, state.editorMode, false);
  window._originalContent = content;

  state.dirty = false;
  // Clear hash so refresh doesn't re-trigger
  history.replaceState(null, '', window.location.pathname);

  console.log('[remote] Remote file loaded successfully');
}

async function openFile(path, preferredMountId, searchKeyword) {
  // Save current cursor/scroll position before switching files
  saveCursorScrollToStorage();

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
      // Initialize version-driven state for local mounts too
      state.baseVersion = 0;
      state.baseContent = content || '';
      state.fileVersions[mount.id + ':' + path] = 0;
    } else {
      // Read from server API (returns { content, mtime, version })
      const result = await API.getFile(mount.id, path);
      if (result !== null) {
        content = result.content;
        state.fileMtimes[mount.id + ':' + path] = { mtime: result.mtime, size: content.length };
        // Initialize version-driven state
        state.baseVersion = result.version || 0;
        state.baseContent = content;
        state.fileVersions[mount.id + ':' + path] = result.version || 0;
      }
    }
    // Record mtime for local files
    if (content !== null && mount._local) {
      try {
        const handle = await getLocalFileHandle(state.localMounts[mount.id].handle, path);
        if (handle) {
          const file = await handle.getFile();
          state.fileMtimes[mount.id + ':' + path] = { mtime: file.lastModified, size: file.size };
        }
      } catch (_e) {
        /* file may have been deleted */
      }
    }
    if (content === null) {
      showToast('文件加载失败，请查看浏览器控制台获取详情');
      // Remove from recent files if file doesn't exist
      const idx = state.recentFiles.findIndex((f) => f.mountId === mount.id && f.path === path);
      if (idx >= 0) {
        state.recentFiles.splice(idx, 1);
        renderRecentFiles();
      }
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
    if (entry.name !== '欢迎.md') {
      state.recentFiles.unshift(entry);
      state.recentFiles = state.recentFiles.slice(0, 10);
    }
    renderRecentFiles();

    $('breadcrumb').textContent = mount.name + path + (mount.readonly ? ' (只读)' : '');
    // Show rename/delete buttons if file is writable and not root
    const renameBtn = $('rename-top-btn');
    const deleteBtn = $('delete-top-btn');
    const downloadBtn = $('download-top-btn');
    const exportPdfBtn = $('export-pdf-top-btn');
    const shareBtn = $('share-top-btn');
    if (renameBtn) {
      renameBtn.style.display = !mount.readonly && path !== '/' ? '' : 'none';
    }
    if (deleteBtn) {
      deleteBtn.style.display = !mount.readonly && path !== '/' ? '' : 'none';
    }
    // Download and export PDF: show for any md file (readonly is ok)
    if (downloadBtn) {
      downloadBtn.style.display = path !== '/' && path.endsWith('.md') ? '' : 'none';
    }
    if (exportPdfBtn) {
      exportPdfBtn.style.display = path !== '/' && path.endsWith('.md') ? '' : 'none';
    }
    // Share: show for server mount files only (not local mounts)
    if (shareBtn) {
      shareBtn.style.display = !mount._local && path !== '/' ? '' : 'none';
    }
    // Version history: show for any md file
    const historyBtn = $('history-top-btn');
    if (historyBtn) {
      historyBtn.style.display = path !== '/' && path.endsWith('.md') ? '' : 'none';
    }
    $('editor-modes').style.display = mount.readonly ? 'none' : path.endsWith('.md') ? '' : 'none';
    $('save-group').style.display = mount.readonly ? 'none' : '';
    // Show refresh button when a file is open
    const _refreshBtn2 = $('btn-refresh');
    if (_refreshBtn2) _refreshBtn2.style.display = path !== '/' ? '' : 'none';
    showPage('editor');

    if (window._vditor) window._vditor.destroy();
    // Set mount context BEFORE initEditor so image rewriting (which runs during
    // Vditor's render/after callbacks) knows whether this is a local mount.
    setFileInfo(mount.id, path);
    // Check for offline draft
    const draft = loadFromLocalStorage(path);
    const finalContent = draft ? draft.content : content;
    if (draft) {
      showToast('已恢复本地缓存版本');
    }
    initEditor(finalContent, state.editorMode, !!mount.readonly);
    // Connect to SSE for collaborative editing (non-readonly files)
    if (!mount.readonly && window.nasmdSSE) {
      window.nasmdSSE.connect(mount.id, path);
    }
    // Note: window._originalContent is set by Vditor's after() callback
    // to match Vditor's normalized content (e.g. trailing newline handling)
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
    // Remove from recent files on error
    const idx = state.recentFiles.findIndex((f) => f.mountId === mount.id && f.path === path);
    if (idx >= 0) {
      state.recentFiles.splice(idx, 1);
      renderRecentFiles();
    }
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
  // No longer using 500ms polling; driven by Vditor input event via onEditorInput()
}

function onEditorInput() {
  if (!window._vditor) return;
  const isDirty = _isContentDirty(window._vditor.getValue(), window._originalContent);
  if (isDirty !== state.dirty) {
    state.dirty = isDirty;
    const btn = $('btn-save');
    if (btn) btn.classList.toggle('dirty', isDirty);
  }
  if (isDirty && state.autoSave && state.currentPath) {
    // Debounce auto-save for all mount types to avoid race condition
    // with pollCurrentFile reading stale disk content
    scheduleAutoSave();
  }
}
window.onEditorInput = onEditorInput;
window.saveFile = saveFile;
window.markDirty = markDirty;

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
    // If a save is already in progress, reschedule to avoid concurrent saves
    // with stale expectedMtime (which causes false conflicts)
    if (_saveInProgress) {
      window._autoSaveTimer = null;
      scheduleAutoSave();
      return;
    }
    if (state.dirty && state.autoSave && state.currentPath) {
      saveFile({ silent: true });
    }
    window._autoSaveTimer = null;
  }, 1500);
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

function closeSidebar() {
  document.getElementById('sidebar').classList.remove('open');
}

// 点击 sidebar overlay 关闭（移动端）
document.addEventListener('click', (e) => {
  const sidebar = document.getElementById('sidebar');
  const menuToggle = document.getElementById('menu-toggle');
  if (sidebar.classList.contains('open') &&
      !sidebar.contains(e.target) &&
      menuToggle && !menuToggle.contains(e.target)) {
    closeSidebar();
  }
});

// === 更多菜单 ===
function toggleMoreMenu() {
  const menu = document.getElementById('more-menu');
  if (menu) menu.classList.toggle('open');
}

// 点击外部关闭 more menu
document.addEventListener('click', (e) => {
  const moreWrapper = document.querySelector('.topbar-more-wrapper');
  const moreMenu = document.getElementById('more-menu');
  if (moreMenu && moreMenu.classList.contains('open') &&
      moreWrapper && !moreWrapper.contains(e.target)) {
    moreMenu.classList.remove('open');
  }
});

// === 移动端检测与初始化 ===
function isMobile() {
  return window.innerWidth < 768;
}

function isSmallMobile() {
  return window.innerWidth < 480;
}

function initMobileLayout() {
  const body = document.body;
  if (isMobile()) {
    body.classList.add('mobile');
  } else {
    body.classList.remove('mobile');
  }
}

// 初始化并监听 resize
window.addEventListener('load', initMobileLayout);
window.addEventListener('resize', initMobileLayout);

// === 侧边栏拖拽调整宽度 ===
(function initSidebarResizer() {
  const sidebar = document.getElementById('sidebar');
  const resizer = document.getElementById('sidebar-resizer');
  if (!sidebar || !resizer) return;

  // 恢复上次保存的宽度
  const savedWidth = localStorage.getItem('nasmd_sidebar_width');
  if (savedWidth) {
    sidebar.style.width = savedWidth + 'px';
  }

  let isDragging = false;
  let startX = 0;
  let startWidth = 0;

  resizer.addEventListener('mousedown', (e) => {
    isDragging = true;
    startX = e.clientX;
    startWidth = sidebar.offsetWidth;
    resizer.classList.add('dragging');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    e.preventDefault();
  });

  document.addEventListener('mousemove', (e) => {
    if (!isDragging) return;
    const delta = e.clientX - startX;
    let newWidth = startWidth + delta;
    // 限制最小/最大宽度
    const minWidth = 180;
    const maxWidth = Math.min(window.innerWidth - 300, 600);
    newWidth = Math.max(minWidth, Math.min(maxWidth, newWidth));
    sidebar.style.width = newWidth + 'px';
  });

  document.addEventListener('mouseup', () => {
    if (!isDragging) return;
    isDragging = false;
    resizer.classList.remove('dragging');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    localStorage.setItem('nasmd_sidebar_width', sidebar.offsetWidth);
  });
})();

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

// === Save-in-progress flag to prevent pollCurrentFile race condition ===
let _saveInProgress = false;

async function saveFile({ silent = false } = {}) {
  console.log('[saveFile] called:', {
    silent,
    currentPath: state.currentPath,
    currentMountId: state.currentMountId,
    hasVditor: !!window._vditor,
    autoSave: state.autoSave,
    dirty: state.dirty,
  });
  if (_saveInProgress) {
    console.log('[saveFile] skipped: another save in progress');
    return;
  }
  _saveInProgress = true;
  const btn = $('btn-save');
  let content;

  setTimeout(() => {
    if (_saveInProgress) {
      console.error('[saveFile] timeout detected, resetting _saveInProgress');
      _saveInProgress = false;
    }
  }, 15000);

  try {
    // Remote proxy mode: direct PUT to remote server, skip version/diff logic
    if (state.remoteFile && window._vditor) {
      content = window._vditor.getValue();
      const resp = await API.putRemoteFile(
        state.remoteFile.src,
        state.remoteFile.path,
        content,
        state.remoteFile.key,
      );
      if (resp && resp.status === 'ok') {
        markClean();
        if (!silent) showToast('已保存');
        else showToast('自动保存完成');
      } else {
        if (!silent) showToast('保存失败');
        else showToast('自动保存失败');
      }
      return;
    }

    if (!state.currentPath || !state.currentMountId || !window._vditor) return;
    const mount = state.mounts.find((m) => m.id === state.currentMountId);
    if (mount && mount.readonly) {
      if (!silent) showToast('此文件不允许修改');
      return;
    }
    content = window._vditor.getValue();

    if (!silent && btn) {
      btn.classList.add('saving');
      btn.disabled = true;
    }

    if (!navigator.onLine) {
      saveToLocalStorage(state.currentPath, content);
      markClean();
      if (!silent) {
        showToast('已离线保存，恢复连接后自动同步');
      }
      return;
    }

    try {
      if (mount && mount._local && state.localMounts[mount.id]) {
        // 本地挂载：通过 File System Access API 写入
        const baseContent = state.baseContent || window._originalContent || '';
        const changes = computeParagraphDiff(baseContent, content);

        if (changes.length === 0) {
          console.log('[saveFile] local mount: no changes to save');
          markClean();
          return;
        }

        const ok = await writeLocalFile(mount.id, state.currentPath, content);
        if (!ok) throw new Error('写入本机文件失败');
        window._originalContent = content;
        state.baseContent = content;
        state.baseVersion += 1;
        markClean();
        clearLocalStorage(state.currentPath);

        // Record version history for local mounts via server API
        const identity = window.nasmdIdentity ? window.nasmdIdentity.get() : null;
        try {
          await API.submitChanges(
            state.currentMountId,
            state.currentPath,
            state.baseVersion - 1,
            changes,
            identity ? identity.name : 'LocalUser',
            identity ? identity.color : '#9b59b6',
            identity ? { os: identity.os, browser: identity.browser } : null,
          );
        } catch (e) {
          console.warn('[saveFile] local mount version history recording failed:', e);
        }

        if (!silent) showToast('已保存');
        try {
          const handle = await getLocalFileHandle(
            state.localMounts[mount.id].handle,
            state.currentPath,
          );
          if (handle) {
            const file = await handle.getFile();
            state.fileMtimes[mount.id + ':' + state.currentPath] = {
              mtime: file.lastModified,
              size: file.size,
            };
          }
        } catch (_e) {
          /* ignore */
        }
      } else {
        // 服务器挂载：版本号驱动的段落级合并
        const fileKey = state.currentMountId + ':' + state.currentPath;
        const baseContent = state.baseContent || window._originalContent || '';
        const changes = computeParagraphDiff(baseContent, content);

        if (changes.length === 0) {
          console.log('[saveFile] no changes to submit');
          markClean();
          return;
        }

        const identity = window.nasmdIdentity ? window.nasmdIdentity.get() : null;
        console.log('[saveFile] submitChanges:', {
          fileKey,
          baseVersion: state.baseVersion,
          changesCount: changes.length,
        });

        const resp = await API.submitChanges(
          state.currentMountId,
          state.currentPath,
          state.baseVersion,
          changes,
          identity ? identity.name : 'Anonymous',
          identity ? identity.color : '#3498db',
          identity ? { os: identity.os, browser: identity.browser } : null,
        );

        if (!resp || !resp.applied) {
          console.log('[saveFile] changes not applied', resp);
          if (resp && resp.error) {
            throw new Error(resp.error);
          }
          return;
        }

        // 更新版本号和基线内容
        state.baseVersion = resp.newVersion;
        state.baseContent = resp.content;
        state.fileVersions[fileKey] = resp.newVersion;
        window._originalContent = resp.content;
        markClean();
        clearLocalStorage(state.currentPath);

        if (resp.merged) {
          showToast('已合并保存');
        } else if (!silent) {
          showToast('已保存');
        } else {
          showToast('自动保存完成');
        }

        performSync();
        if (window.nasmdHistory && window.nasmdHistory.isVisible()) {
          window.nasmdHistory.loadHistory();
        }
      }
    } catch (e) {
      saveToLocalStorage(state.currentPath, content);
      if (!silent) showToast('保存失败，已缓存到本地');
      else showToast('自动保存失败');
      console.error(e);
    }
  } finally {
    _saveInProgress = false;
    if (!silent && btn) {
      btn.classList.remove('saving');
      btn.disabled = false;
    }
    if (state.dirty && state.autoSave && state.currentPath) {
      scheduleAutoSave();
    }
  }
}

// 客户端段落级 diff 计算：对比 baseContent 与当前内容，输出 changes 列表。
// 使用 LCS（最长公共子序列）算法，与服务端 paragraph_diff.compute_diff 完全一致。
// 朴素按索引对齐会导致插入段落后所有后续段落被误判为修改，LCS 能正确识别真正的变更位置。
function computeParagraphDiff(oldText, newText) {
  if (oldText === newText) return [];

  // Split into paragraphs, matching server-side split_paragraphs
  const splitParas = (text) => {
    const paras = text.split('\n\n');
    while (paras.length && paras[paras.length - 1].trim() === '') paras.pop();
    return paras;
  };

  const oldParas = splitParas(oldText);
  const newParas = splitParas(newText);

  if (JSON.stringify(oldParas) === JSON.stringify(newParas)) return [];

  const m = oldParas.length;
  const n = newParas.length;

  // LCS DP table
  const dp = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      if (oldParas[i - 1] === newParas[j - 1]) {
        dp[i][j] = dp[i - 1][j - 1] + 1;
      } else {
        dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
      }
    }
  }

  // Backtrack to get opcodes (like Python's SequenceMatcher.get_opcodes)
  const ops = [];
  let i = m,
    j = n;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && oldParas[i - 1] === newParas[j - 1]) {
      ops.push({ tag: 'equal', i1: i - 1, i2: i, j1: j - 1, j2: j });
      i--;
      j--;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      ops.push({ tag: 'insert', i1: i, i2: i, j1: j - 1, j2: j });
      j--;
    } else {
      ops.push({ tag: 'delete', i1: i - 1, i2: i, j1: j, j2: j });
      i--;
    }
  }
  ops.reverse();

  // Merge consecutive same-tag ops into blocks
  const opcodes = [];
  for (const op of ops) {
    const last = opcodes[opcodes.length - 1];
    if (last && last.tag === op.tag && last.i2 === op.i1 && last.j2 === op.j1) {
      last.i2 = op.i2;
      last.j2 = op.j2;
    } else {
      opcodes.push({ tag: op.tag, i1: op.i1, i2: op.i2, j1: op.j1, j2: op.j2 });
    }
  }

  // Convert opcodes to changes (matching server-side compute_diff format)
  const changes = [];
  for (const op of opcodes) {
    if (op.tag === 'replace') {
      const oldLen = op.i2 - op.i1;
      const newLen = op.j2 - op.j1;
      const paired = Math.min(oldLen, newLen);
      for (let k = 0; k < paired; k++) {
        changes.push({ type: 'replace', paraIdx: op.i1 + k, content: newParas[op.j1 + k] });
      }
      if (oldLen > newLen) {
        for (let k = paired; k < oldLen; k++) {
          changes.push({ type: 'delete', paraIdx: op.i1 + k });
        }
      } else if (newLen > oldLen) {
        for (let k = paired; k < newLen; k++) {
          changes.push({ type: 'insert', paraIdx: op.i2, content: newParas[op.j1 + k] });
        }
      }
    } else if (op.tag === 'delete') {
      for (let k = op.i1; k < op.i2; k++) {
        changes.push({ type: 'delete', paraIdx: k });
      }
    } else if (op.tag === 'insert') {
      for (let k = op.j1; k < op.j2; k++) {
        changes.push({ type: 'insert', paraIdx: op.i1, content: newParas[k] });
      }
    }
    // 'equal' produces no changes
  }

  return changes;
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
  if (_refreshTreeBusy) return;
  _refreshTreeBusy = true;
  try {
    const expandedMountIds = state.expandedMounts.filter((id) => !id.includes(':'));
    for (const mountId of expandedMountIds) {
      const expandedDirs = state.expandedMounts
        .filter((k) => k.startsWith(mountId + ':'))
        .map((k) => k.substring(mountId.length + 1));
      expandedDirs.push('/');
      for (const dirPath of expandedDirs) {
        await loadTree(mountId, dirPath, true);
      }
    }
    renderSidebar();
  } finally {
    _refreshTreeBusy = false;
  }
}

// === Sidebar auto-refresh ===
let _sidebarRefreshTimer = null;
const SIDEBAR_REFRESH_INTERVAL = 5000; // 5 seconds

// File content external changes are now delivered via SSE (external_reload event)
// handled in sync_layer.js — no more mtime polling needed.

function startSidebarRefresh() {
  if (_sidebarRefreshTimer) return;
  async function tick() {
    await refreshTree();
    _sidebarRefreshTimer = setTimeout(tick, SIDEBAR_REFRESH_INTERVAL);
  }
  _sidebarRefreshTimer = setTimeout(tick, SIDEBAR_REFRESH_INTERVAL);
}

function stopSidebarRefresh() {
  if (_sidebarRefreshTimer) {
    clearTimeout(_sidebarRefreshTimer);
    _sidebarRefreshTimer = null;
  }
}

// Backward-compat stubs: file content polling has been replaced by SSE
// external_reload events (see sync_layer.js). These no-op functions keep
// existing call sites working without behavior change.
function startFilePoll() {}
function stopFilePoll() {}

// === Refresh from disk ===
// eslint-disable-next-line no-unused-vars
async function refreshFromDisk(silent) {
  if (!state.currentPath || !state.currentMountId || !window._vditor) {
    if (!silent) showToast('没有打开的文件');
    return;
  }

  const mount = state.mounts.find((m) => m.id === state.currentMountId);
  if (!mount) {
    if (!silent) showToast('挂载点不存在');
    return;
  }

  try {
    let content = null;

    if (mount._local && state.localMounts[mount.id]) {
      content = await readLocalFile(mount.id, state.currentPath);
      if (content === null) {
        if (!silent) showToast('文件可能已被删除');
        return;
      }
      state.fileMtimes[mount.id + ':' + state.currentPath] = {
        mtime: Date.now(),
        size: content.length,
      };
    } else {
      // Server mount: read via API
      const result = await API.getFile(mount.id, state.currentPath);
      if (!result) {
        if (!silent) showToast('文件读取失败');
        return;
      }
      content = result.content;
      state.fileMtimes[mount.id + ':' + state.currentPath] = {
        mtime: result.mtime,
        size: content.length,
      };
      state.baseVersion = result.version || 0;
      state.baseContent = content;
      state.fileVersions[mount.id + ':' + state.currentPath] = result.version || 0;
    }

    if (content !== null) {
      window._vditor.setValue(content);
      window._originalContent = content;
      state.baseContent = content;
      if (!silent) showToast('已从磁盘重新加载');
    }
  } catch (e) {
    if (!silent) showToast('重新加载失败: ' + (e.message || '未知错误'));
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
  // Only include files this machine has actually accessed (per-browser accessLog)
  const accessed = deduped.filter((f) => state.accessLog[f.mountId + ':' + f.path]);
  // Sort by access time only (most recent first)
  accessed.sort((a, b) => {
    const aTime = state.accessLog[a.mountId + ':' + a.path] || 0;
    const bTime = state.accessLog[b.mountId + ':' + b.path] || 0;
    return bTime - aTime;
  });
  state.recentFiles = accessed.slice(0, 10);
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
  let html = '<h3 class="section-title">最近访问</h3><div class="recent-list">';
  for (const f of state.recentFiles) {
    if (f.name === '欢迎.md') continue;
    const accessTime = state.accessLog[f.mountId + ':' + f.path];
    const displayTime = accessTime ? formatTime(accessTime) : formatTime(f.modTime);
    html += `<div class="recent-item" onclick="openFile('${f.path.replace(/'/g, "\\'")}', '${f.mountId}')">
      <span class="recent-name">${f.name}</span>
      <span class="recent-time">${displayTime}</span>
    </div>`;
  }
  html += '</div>';
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

// === 移动端: 搜索框交互 + 编辑器键盘处理 ===
(function initMobileSearch() {
  const searchBox = document.querySelector('.search-box');
  if (!searchBox) return;

  // 编辑器焦点时滚动到可见区域
  const editorEl = document.querySelector('.vditor');
  if (editorEl) {
    editorEl.addEventListener('focus', () => {
      setTimeout(() => {
        editorEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 300);
    });

    // iOS 键盘打开时重新定位
    window.addEventListener('resize', () => {
      if (document.activeElement === editorEl || editorEl.classList.contains('vditor--focus')) {
        setTimeout(() => {
          editorEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }, 100);
      }
    });
  }
})();

// === Vditor toolbar 移动端横向滚动 ===
(function initMobileToolbar() {
  const toolbar = document.querySelector('.vditor-toolbar');
  if (!toolbar) return;

  // 检测是否为触摸设备
  const isTouchDevice = 'ontouchstart' in window || navigator.maxTouchPoints > 0;
  if (!isTouchDevice) return;

  // 添加横向滚动指示器
  toolbar.classList.add('vditor-toolbar-mobile');

  // 监听滚动事件，显示/隐藏渐变遮罩
  toolbar.addEventListener('scroll', () => {
    const isScrolled = toolbar.scrollLeft > 5;
    toolbar.classList.toggle('scrolled', isScrolled);
  }, { passive: true });
})();

// === Phase 2: 文件树触控优化 ===
(function initFileTreeTouch() {
  const tree = document.getElementById('file-tree');
  if (!tree) return;

  let pressTimer = null;
  let longPressTriggered = false;

  tree.addEventListener('touchstart', (e) => {
    const item = e.target.closest('.tree-item');
    if (!item) return;
    longPressTriggered = false;
    clearTimeout(pressTimer);
    pressTimer = setTimeout(() => {
      longPressTriggered = true;
      const touch = e.touches[0];
      showFileContextMenu(item, touch.clientX, touch.clientY);
    }, 500);
  }, { passive: true });

  tree.addEventListener('touchend', (e) => {
    clearTimeout(pressTimer);
    if (longPressTriggered) {
      e.preventDefault();
      longPressTriggered = false;
    }
  }, { passive: false });

  tree.addEventListener('touchmove', () => {
    clearTimeout(pressTimer);
  }, { passive: true });

  let swipeStartX = 0, swipeStartY = 0, swipeItem = null;

  tree.addEventListener('touchstart', (e) => {
    const folder = e.target.closest('.tree-item.folder');
    if (!folder || !folder.querySelector('.tree-children')) return;
    swipeStartX = e.touches[0].clientX;
    swipeStartY = e.touches[0].clientY;
    swipeItem = folder;
  }, { passive: true });

  tree.addEventListener('touchend', (e) => {
    if (!swipeItem) return;
    const endX = e.changedTouches[0].clientX;
    const endY = e.changedTouches[0].clientY;
    const deltaX = endX - swipeStartX;
    const deltaY = Math.abs(endY - swipeStartY);
    if (Math.abs(deltaX) > 50 && deltaY < 30) {
      const isExpanded = swipeItem.classList.contains('expanded');
      const mountId = swipeItem.dataset.mountId;
      const fpath = swipeItem.dataset.path;
      if (mountId && fpath) {
        if (deltaX > 0 && !isExpanded) toggleDir(mountId, fpath);
        else if (deltaX < 0 && isExpanded) toggleDir(mountId, fpath);
      }
    }
    swipeItem = null;
  }, { passive: true });
})();

// === 文件操作长按菜单 ===
let _contextMenuTarget = null;

function showFileContextMenu(item, x, y) {
  const menu = document.getElementById('file-context-menu');
  if (!menu) return;
  const mountId = item.dataset.mountId || '';
  const fpath = item.dataset.path || item.querySelector('span[title]')?.getAttribute('title') || '';
  _contextMenuTarget = { mountId, path: fpath };
  if (window.innerWidth < 768) {
    menu.style.top = 'auto'; menu.style.bottom = '0';
    menu.style.left = '0'; menu.style.right = '0';
  } else {
    menu.style.top = y + 'px'; menu.style.left = x + 'px';
  }
  menu.style.display = 'block';
  setTimeout(() => { document.addEventListener('click', hideFileContextMenu, { once: true }); }, 0);
}

function hideFileContextMenu() {
  const menu = document.getElementById('file-context-menu');
  if (menu) menu.style.display = 'none';
  _contextMenuTarget = null;
}

function openFileContextAction(action) {
  const target = _contextMenuTarget;
  if (!target) return;
  hideFileContextMenu();
  switch (action) {
    case 'rename': if (target.path) showRenameModal(target.path, target.mountId); break;
    case 'delete': if (target.path) deleteFile(target.path, target.mountId); break;
    case 'share': if (target.path) shareFile(target.path, target.mountId); break;
    case 'download': if (target.path) downloadFile(target.path, target.mountId); break;
  }
}

// === 搜索框滚动阴影 ===
(function initSearchSticky() {
  const searchBox = document.querySelector('.search-box');
  if (!searchBox) return;
  let ticking = false;
  window.addEventListener('scroll', () => {
    if (!ticking) {
      requestAnimationFrame(() => {
        searchBox.classList.toggle('search-sticky', window.scrollY > 100);
        ticking = false;
      });
      ticking = true;
    }
  }, { passive: true });
})();
