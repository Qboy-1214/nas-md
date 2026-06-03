/**
 * app.js - 应用主逻辑（原生 JS，无框架）
 */

// === 状态 ===
const state = {
  token: null,
  sidebarCollapsed: false,
  mounts: [],
  expandedMounts: [],
  treeData: {},
  currentPath: null,
  currentMountId: null,
  editorMode: 'ir',
  dirty: false,
  searchResults: [],
  recentFiles: [],
  showSettings: false,
  toastTimer: null,
};

// === DOM 引用 ===
const $ = id => document.getElementById(id);

// === 初始化 ===
document.addEventListener('DOMContentLoaded', async () => {
  const savedToken = localStorage.getItem('nasmd_token');
  if (savedToken) {
    state.token = savedToken;
  }
  updateAuthUI();
  await loadMounts();
  await loadRecentFiles();
  // Auto-open welcome.md if builtin mount exists
  const builtin = state.mounts.find(m => m.id === 'builtin-storage');
  if (builtin) {
    // Load builtin tree data silently (shown at root level, not as collapsible mount)
    if (!state.treeData[builtin.id]) {
      await loadTree(builtin.id, '/');
    }
    const entries = state.treeData[builtin.id]?.['/'];
    if (entries) {
      const welcome = entries.find(e => e.name === '欢迎.md');
      if (welcome) openFile(welcome.path);
    }
  }
});

// === UI 更新 ===
function updateAuthUI() {
  const loginBtn = $('btn-login');
  const logoutBtn = $('btn-logout');
  const guestHint = $('guest-hint');
  if (state.token) {
    loginBtn.style.display = 'none';
    logoutBtn.style.display = '';
    guestHint.style.display = 'none';
  } else {
    loginBtn.style.display = '';
    logoutBtn.style.display = 'none';
    guestHint.style.display = '';
  }
}

function showPage(page) {
  $('welcome-page').style.display = page === 'welcome' ? '' : 'none';
  $('editor-container').style.display = page === 'editor' ? '' : 'none';
  $('settings-page').style.display = page === 'settings' ? '' : 'none';
}

function showToast(msg) {
  const el = $('toast');
  el.textContent = msg;
  el.style.display = '';
  if (state.toastTimer) clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => el.style.display = 'none', 2500);
}

// === 侧边栏 ===
function toggleSidebar() {
  state.sidebarCollapsed = !state.sidebarCollapsed;
  $('sidebar').classList.toggle('collapsed', state.sidebarCollapsed);
}

// === 登录 ===
function showLogin() {
  const modal = $('login-modal');
  modal.style.display = '';
  modal.classList.add('active');
  $('login-token').value = '';
  $('login-error').style.display = 'none';
  setTimeout(() => $('login-token').focus(), 50);
}

function hideLogin() {
  const modal = $('login-modal');
  modal.style.display = 'none';
  modal.classList.remove('active');
}

async function login() {
  const token = $('login-token').value.trim();
  if (!token) {
    $('login-error').textContent = '请输入 Token';
    $('login-error').style.display = '';
    return;
  }
  try {
    const resp = await fetch(`${_apiBase}/api/mounts`, {
      headers: { 'Authorization': `Bearer ${token}` },
    });
    if (resp.ok) {
      state.token = token;
      localStorage.setItem('nasmd_token', token);
      updateAuthUI();
      hideLogin();
      await loadMounts();
      await loadRecentFiles();
      showToast('登录成功');
    } else if (resp.status === 401) {
      $('login-error').textContent = 'Token 无效';
      $('login-error').style.display = '';
    } else {
      $('login-error').textContent = `验证失败 (${resp.status})`;
      $('login-error').style.display = '';
    }
  } catch (e) {
    $('login-error').textContent = '网络错误';
    $('login-error').style.display = '';
  }
}

function logout() {
  localStorage.removeItem('nasmd_token');
  state.token = null;
  state.currentPath = null;
  state.currentMountId = null;
  state.mounts = [];
  state.treeData = {};
  state.expandedMounts = [];
  state.showSettings = false;
  if (window._vditor) { _vditor.destroy(); window._vditor = null; }
  if (window._dirtyTimer) { clearInterval(window._dirtyTimer); window._dirtyTimer = null; }
  updateAuthUI();
  renderSidebar();
  showPage('welcome');
  showToast('已退出');
  // 退出后重新加载公开挂载点
  loadMounts();
}

// === 挂载目录 ===
async function loadMounts() {
  try {
    if (state.token) {
      state.mounts = await API.getMounts();
    } else {
      state.mounts = await API.getPublicMounts();
    }
    renderSidebar();
  } catch (e) {
    showToast('加载挂载点失败');
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
  // 格式为 "目录名/子目录/文件名"，最前面的部分就是所选目录名
  if (!fullPath && f.webkitRelativePath) {
    dirName = f.webkitRelativePath.split('/')[0];
  }

  if (fullPath) {
    // 拿到完整路径，直接填入
    $('new-dir-path').value = fullPath;
  } else {
    // 浏览器安全限制下无法获取完整路径（Edge/Firefox）
    // 尝试让后端搜索匹配的目录
    const dirName = f.webkitRelativePath ? f.webkitRelativePath.split('/')[0] : '';
    if (dirName) {
      $('new-dir-path').value = '';
      $('new-dir-path').placeholder = `正在定位 "${dirName}"...`;
      $('new-dir-name').value = dirName;
      // 后端搜索目录
      API.findMountPath(dirName).then(result => {
        if (result && result.path) {
          $('new-dir-path').value = result.path;
          showToast(`已定位: ${result.path}`);
        } else {
          $('new-dir-path').placeholder = `无法自动定位，请输入完整路径（如 D:\\xxx\\${dirName}）`;
          showToast(`无法自动定位 "${dirName}"，请手动输入完整路径`);
        }
      }).catch(() => {
        $('new-dir-path').placeholder = `无法自动定位，请输入完整路径（如 D:\\xxx\\${dirName}）`;
        showToast(`无法自动定位 "${dirName}"，请手动输入完整路径`);
      });
    }
  }

  // 自动填入显示名称
  if (dirName && !$('new-dir-name').value.trim()) {
    $('new-dir-name').value = dirName;
  }

  // 聚焦路径输入框
  $('new-dir-path').focus();

  // 重置 input，避免同一目录重复选择不触发 onchange
  event.target.value = '';
}

async function openDirectory() {
  const dirPath = $('new-dir-path').value.trim();
  if (!dirPath) { showToast('请点击输入框选择目录，或手动输入路径'); return; }
  try {
    const resp = await API.addMount(dirPath, $('new-dir-name').value.trim());
    if (resp && resp.id) {
      showToast(`已挂载: ${resp.name || resp.path}`);
      $('new-dir-path').value = '';
      $('new-dir-name').value = '';
      $('new-dir-path').placeholder = '输入目录路径，或点击浏览选择';
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
      const idx = state.mounts.findIndex(m => m.id === mountId);
      if (idx >= 0) state.mounts[idx].public = isPublic;
      renderSidebar();
      showToast(isPublic ? '已设为公开' : '已设为私有');
    }
  } catch (e) {
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
  try {
    const tree = await API.getTree(mountId, path);
    if (!state.treeData[mountId]) state.treeData[mountId] = {};
    // Store the root entry; renderEntries will use .children
    state.treeData[mountId][path] = tree;
  } catch (e) {
    console.error('Failed to load tree:', e);
  }
}

// 卸载挂载点
async function removeMount(mountId) {
  // Cannot delete builtin mount
  const mount = state.mounts.find(m => m.id === mountId);
  if (mount && mount.id === 'builtin-storage') { showToast('内置目录不能卸载'); return; }
  try {
    const token = localStorage.getItem('nasmd_token') || '';
    const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
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
    state.mounts = state.mounts.filter(m => m.id !== mountId);
    delete state.treeData[mountId];
    state.expandedMounts = state.expandedMounts.filter(id => id !== mountId && !id.startsWith(`${mountId}:`));
    if (state.currentMountId === mountId) {
      state.currentPath = null;
      state.currentMountId = null;
      if (window._vditor) { _vditor.destroy(); window._vditor = null; }
      showPage('welcome');
    }
    renderSidebar();
    showToast('已卸载');
  } catch (e) {
    // Network error: still clean up frontend
    state.mounts = state.mounts.filter(m => m.id !== mountId);
    delete state.treeData[mountId];
    state.expandedMounts = state.expandedMounts.filter(id => id !== mountId && !id.startsWith(`${mountId}:`));
    renderSidebar();
    showToast('已卸载（本地）');
  }
}

function renderSidebar() {
  const tree = $('file-tree');
  tree.innerHTML = '';

  // Built-in files shown at root level (not nested under a mount point)
  const builtin = state.mounts.find(m => m.id === 'builtin-storage');
  const builtinEntries = builtin ? state.treeData[builtin.id]?.['/'] : null;
  if (builtinEntries) {
    const items = builtinEntries
      .filter(e => !e.name.startsWith('.'))
      .sort((a, b) => {
        if (a.isDir && !b.isDir) return -1;
        if (!a.isDir && b.isDir) return 1;
        return a.name.localeCompare(b.name);
      });
    for (const e of items) {
      const fullPath = e.path;
      const isActive = state.currentPath === fullPath;
      const icon = e.isDir ? '📁' : (e.name.endsWith('.md') ? '📝' : '📄');
      const cls = `tree-item builtin-file ${e.isDir ? 'folder' : ''} ${isActive ? 'active' : ''}`;
      tree.innerHTML += `<div class="${cls}" onclick="openFile('${fullPath}')">
        <span class="tree-icon">${icon}</span>
        <span>${e.name}</span>
        <span class="mount-builtin-badge" title="内置只读">🔒</span>
      </div>`;
    }
  }

  // Regular mount points
  const regularMounts = state.mounts.filter(m => m.id !== 'builtin-storage');
  for (const mount of regularMounts) {
    const isExpanded = state.expandedMounts.includes(mount.id);

    let html = `<div class="mount-group">`;
    html += `<div class="mount-name-row">`;
    html += `<div class="mount-name" onclick="toggleMount('${mount.id}')">`;
    html += `<span class="mount-icon">${isExpanded ? '▼' : '▶'}</span>`;
    html += `<span>${mount.name}</span>`;
    if (mount.public) html += ` <span class="mount-badge" title="公开目录">🌐</span>`;
    html += `</div>`;
    html += `<button class="mount-remove-btn" onclick="removeMount('${mount.id}')" title="卸载">✕</button>`;
    html += `</div>`;

    if (isExpanded) {
      const tree = state.treeData[mount.id]?.['/'];
      if (tree) {
        html += renderEntries(tree.children || [], mount.id, '/');
      } else {
        html += '<div style="padding:8px 12px;color:var(--col-tx-muted)">加载中...</div>';
        loadTree(mount.id, '/').then(() => renderSidebar());
      }
    }

    html += `</div>`;
    tree.innerHTML += html;
  }

  if (regularMounts.length === 0 && !builtinEntries) {
    tree.innerHTML = '<div style="padding:12px;color:var(--col-tx-muted)">暂无挂载目录</div>';
  }
}

function renderEntries(entries, mountId, parentPath) {
  const items = entries
    .filter(e => {
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

  return items.map(e => {
    const fullPath = e.path;
    const isActive = state.currentPath === fullPath;
    const icon = e.isDir ? '📁' : (e.name.endsWith('.md') ? '📝' : '📄');
    const cls = `tree-item ${e.isDir ? 'folder' : ''} ${isActive ? 'active' : ''}`;

    if (e.isDir) {
      const dirKey = `${mountId}:${fullPath}`;
      const isDirExpanded = state.expandedMounts.includes(dirKey);
      const subEntries = state.treeData[mountId]?.[fullPath];

      let html = `<div>`;
      html += `<div class="${cls}" onclick="toggleDir('${mountId}','${fullPath}')">`;
      html += `<span class="tree-icon">${isDirExpanded ? '▼' : '▶'}</span>`;
      html += `<span class="tree-folder">${e.name}</span>`;
      html += `</div>`;

      if (isDirExpanded) {
        if (subEntries) {
          html += `<div class="tree-sub">${renderEntries(subEntries.children || [], mountId, fullPath)}</div>`;
        } else {
          html += '<div style="padding:8px 12px;color:var(--col-tx-muted)">加载中...</div>';
          loadTree(mountId, fullPath).then(() => renderSidebar());
        }
      }

      html += `</div>`;
      return html;
    }

    return `<div class="${cls}" onclick="openFile('${fullPath}')">
      <span class="tree-icon">${icon}</span>
      <span>${e.name}</span>
    </div>`;
  }).join('');
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

async function openFile(path) {
  let mount = findMountForPath(path);
  if (!mount && state.mounts.length > 0) {
    mount = state.mounts[0];
  }
  if (!mount) { showToast('无法确定文件的挂载点'); return; }

  try {
    const content = await API.getFile(mount.id, path);
    if (content === null) { showToast('文件不存在'); return; }
    state.currentPath = path;
    state.currentMountId = mount.id;
    state.showSettings = false;
    state.searchResults = [];

    $('breadcrumb').textContent = path + (mount.readonly ? ' 🔒' : '');
    $('editor-modes').style.display = mount.readonly ? 'none' : (path.endsWith('.md') ? '' : 'none');
    $('btn-save').style.display = mount.readonly ? 'none' : '';
    showPage('editor');

    if (window._vditor) _vditor.destroy();
    initEditor(content, state.editorMode, !!mount.readonly);
    setFileInfo(mount.id, path);
    state.dirty = false;
    startDirtyCheck();
    renderSidebar();
  } catch (e) {
    showToast('加载文件失败');
    console.error(e);
  }
}

function startDirtyCheck() {
  if (window._dirtyTimer) clearInterval(window._dirtyTimer);
  window._dirtyTimer = setInterval(() => {
    if (window._vditor) {
      state.dirty = (window._vditor.getValue() !== window._originalContent);
    }
  }, 500);
}

async function saveFile() {
  if (!state.currentPath || !state.currentMountId || !window._vditor) return;
  // Check if current mount is readonly
  const mount = state.mounts.find(m => m.id === state.currentMountId);
  if (mount && mount.readonly) { showToast('此文件不允许修改'); return; }
  const content = window._vditor.getValue();
  try {
    await API.putFile(state.currentMountId, state.currentPath, content);
    window._originalContent = content;
    state.dirty = false;
    showToast('已保存');
  } catch (e) {
    showToast('保存失败');
    console.error(e);
  }
}

function confirmNewFile() {
  const name = $('new-file-name').value.trim();
  if (!name) return;
  hideNewFile();
  // 简化：在第一个挂载点根目录创建
  const mount = state.mounts[0];
  if (!mount) { showToast('请先打开一个目录'); return; }
  const fileName = name.endsWith('.md') ? name : name + '.md';
  const path = `/${fileName}`;
  API.putFile(mount.id, path, '').then(() => {
    clearTreeCache();
    loadTree(mount.id, '/').then(() => {
      renderSidebar();
      openFile(path);
      showToast('已创建');
    });
  }).catch(() => showToast('创建失败'));
}

function hideNewFile() {
  const modal = $('new-file-modal');
  modal.style.display = 'none';
  modal.classList.remove('active');
  $('new-file-name').value = '';
}

// === 导航 ===
function navigateHome() {
  state.currentPath = null;
  state.currentMountId = null;
  state.showSettings = false;
  $('breadcrumb').textContent = '';
  $('editor-modes').style.display = 'none';
  $('btn-save').style.display = 'none';
  if (window._vditor) { _vditor.destroy(); window._vditor = null; }
  if (window._dirtyTimer) { clearInterval(window._dirtyTimer); window._dirtyTimer = null; }
  showPage('welcome');
  renderSidebar();
}

function showSettings() {
  state.showSettings = true;
  $('breadcrumb').textContent = '设置';
  $('setting-api').textContent = _apiBase;
  const mountsEl = $('setting-mounts');
  mountsEl.innerHTML = state.mounts.map(m =>
    `<div class="mount-info"><strong>${m.name}</strong>: ${m.path}${m.public ? ' <span class="public-badge">公开</span>' : ''}</div>`
  ).join('');
  showPage('settings');
}

// === 搜索 ===
async function doSearch() {
  const query = $('search-input').value.trim();
  const resultsEl = $('search-results');
  if (!query) { resultsEl.innerHTML = ''; return; }
  try {
    state.searchResults = await API.search(query);
    if (state.searchResults.length === 0) {
      resultsEl.innerHTML = '<div style="padding:8px;color:var(--col-tx-muted)">无结果</div>';
      return;
    }
    resultsEl.innerHTML = state.searchResults.map(r =>
      `<div class="search-result-item" onclick="openFile('${r.path}');$('search-results').innerHTML='';$('search-input').value=''">
        <span class="result-path">${r.path}</span>
        <span class="result-snippet">${r.snippet || ''}</span>
      </div>`
    ).join('');
  } catch (e) {
    console.error('Search failed:', e);
  }
}

// === 编辑器模式 ===
function setEditorMode(mode) {
  state.editorMode = mode;
  const vditor = window._getVditor();
  if (vditor) {
    vditor.setMode(mode);
  }
}

// === 最近文件 ===
async function loadRecentFiles() {
  const allFiles = [];
  for (const mount of state.mounts) {
    try {
      const entries = await API.getTree(mount.id, '/');
      collectFiles(entries, mount.id, allFiles);
    } catch {}
  }
  allFiles.sort((a, b) => b.modTime - a.modTime);
  state.recentFiles = allFiles.slice(0, 10);
  renderRecentFiles();
}

function collectFiles(entries, mountId, result) {
  for (const e of entries) {
    if (!e.isDir && e.name.endsWith('.md')) {
      result.push({ name: e.name, path: e.path, modTime: e.modTime, mountId });
    }
  }
}

function renderRecentFiles() {
  const el = $('recent-files');
  if (state.recentFiles.length === 0) { el.innerHTML = ''; return; }
  let html = '<h3 class="section-title">最近修改</h3>';
  for (const f of state.recentFiles) {
    html += `<div class="recent-item" onclick="openFile('${f.path}')">
      <span class="recent-name">${f.name}</span>
      <span class="recent-time">${formatTime(f.modTime)}</span>
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
