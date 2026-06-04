/**
 * files.js - 文件浏览和 API 对接
 */

// 动态推导 API base（从当前页面 URL）
const _apiBase = (() => {
  const origin = window.location.origin;
  // 如果当前路径有子目录，取到最后一个 / 之前的部分
  // 例如 http://host:8080/nas-md/ -> http://host:8080/nas-md
  // 例如 http://host:8080/ -> http://host:8080
  const pathname = window.location.pathname;
  if (pathname && pathname !== '/') {
    // 去掉末尾的文件名部分（如果有）
    const base = pathname.replace(/\/[^\/]*$/, '');
    return origin + (base.endsWith('/') ? base.slice(0, -1) : base);
  }
  return origin;
})();

const API = {
  async request(path, options = {}) {
    const headers = { ...options.headers };
    if (options.body && typeof options.body === 'string') {
      headers['Content-Type'] = headers['Content-Type'] || 'text/plain; charset=utf-8';
    }
    // Add X-Admin header when in admin mode
    if (window.state?.isAdmin || window.location.pathname.startsWith('/admin') || window.location.hash === '#admin') {
      headers['X-Admin'] = '1';
    }
    const resp = await fetch(`${_apiBase}${path}`, { ...options, headers });
    return resp;
  },

  // 获取挂载点列表（需要认证，返回所有挂载点）
  async getMounts() {
    const r = await this.request('/api/mounts');
    return r ? r.json() : [];
  },

  // 获取公开挂载点列表（无需认证）
  async getPublicMounts() {
    const r = await this.request('/api/mounts/public');
    return r ? r.json() : [];
  },

  // 添加挂载点（无需认证，游客限 1 个）
  async addMount(dirPath, name) {
    const body = { path: dirPath };
    if (name) body.name = name;
    const r = await this.request('/api/mounts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    return r ? r.json() : null;
  },

  // 修改挂载点（需要认证，支持修改 name / public）
  async updateMount(mountId, data) {
    const r = await this.request(`/api/mounts/${mountId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return r ? r.json() : null;
  },

  async getTree(mountId, path) {
    const r = await this.request(`/api/mounts/${mountId}/tree-recursive?path=${encodeURIComponent(path || '/')}`);
    return r ? r.json() : null;
  },

  // 让后端在常见位置搜索目录名，返回完整路径
  async findMountPath(dirName) {
    const r = await this.request(`/api/find-path?name=${encodeURIComponent(dirName)}`);
    return r ? r.json() : null;
  },

  async getFile(mountId, path) {
    const r = await this.request(`/api/mounts/${mountId}/file?path=${encodeURIComponent(path)}`);
    if (!r || !r.ok) return null;
    return r.text();
  },

  async putFile(mountId, path, content) {
    const r = await this.request(`/api/mounts/${mountId}/file?path=${encodeURIComponent(path)}`, {
      method: 'PUT',
      body: content,
    });
    return r ? r.json() : null;
  },

  async deleteFile(mountId, path) {
    const r = await this.request(`/api/mounts/${mountId}/file?path=${encodeURIComponent(path)}`, {
      method: 'DELETE',
    });
    return r ? r.json() : null;
  },

  async rename(mountId, oldPath, newPath) {
    const r = await this.request(`/api/mounts/${mountId}/rename?oldPath=${encodeURIComponent(oldPath)}&newPath=${encodeURIComponent(newPath)}`, {
      method: 'PUT',
    });
    return r ? r.json() : null;
  },

  async mkdir(mountId, path) {
    const r = await this.request(`/api/mounts/${mountId}/mkdir?path=${encodeURIComponent(path)}`, {
      method: 'PUT',
    });
    return r ? r.json() : null;
  },

  async search(query) {
    const r = await this.request(`/api/search?q=${encodeURIComponent(query)}&limit=20`);
    return r ? r.json() : [];
  },

  async searchPages(query) {
    const r = await this.request(`/api/search?q=${encodeURIComponent(query)}&limit=15`);
    return r ? r.json() : [];
  },

  async getBacklinks(page) {
    const r = await this.request(`/api/backlinks?page=${encodeURIComponent(page)}`);
    return r ? r.json() : { backlinks: [] };
  },

  async getStats() {
    const r = await this.request('/api/stats');
    return r ? r.json() : {};
  },

  async getGraph() {
    const r = await this.request('/api/graph');
    return r ? r.json() : { nodes: [], edges: [] };
  },

  async getOrphans() {
    const r = await this.request('/api/orphans');
    return r ? r.json() : [];
  },

  async sync(mountId, files) {
    const headers = { 'Content-Type': 'application/json' };
    const resp = await fetch(`${_apiBase}/api/sync?mount=${encodeURIComponent(mountId)}`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ files }),
    });
    return resp.json();
  },

  async getSyncStatus(mountId) {
    const r = await this.request(`/api/sync/status?mount=${encodeURIComponent(mountId)}`);
    return r ? r.json() : {};
  },

  async getPlugins() {
    const r = await this.request('/api/plugins');
    return r ? r.json() : { plugins: [] };
  },
};

// 全局变量
let _mounts = [];
let _treeCache = {};  // { "mountId:path": [entries] }

async function loadMounts() {
  _mounts = await API.getMounts();
  return _mounts;
}

async function loadTree(mountId, path) {
  const key = `${mountId}:${path}`;
  const entries = await API.getTree(mountId, path);
  _treeCache[key] = entries;
  return entries;
}

function getTreeCached(mountId, path) {
  const key = `${mountId}:${path}`;
  return _treeCache[key] || [];
}

function clearTreeCache() {
  _treeCache = {};
}

function findMountForPath(filePath) {
  for (const m of _mounts) {
    if (filePath.startsWith(m.path)) return m;
  }
  return _mounts[0] || null;
}

function getRelativePath(mount, filePath) {
  if (filePath.startsWith(mount.path)) {
    return filePath.slice(mount.path.length).replace(/^\//, '');
  }
  return filePath;
}

function getMountPath(mount, relPath) {
  return `${mount.path}/${relPath}`.replace(/\/+/g, '/');
}
