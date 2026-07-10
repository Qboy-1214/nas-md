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
    const base = pathname.replace(/\/[^/]*$/, '');
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
    if (window.state?.isAdmin) {
      headers['X-Admin'] = '1';
    }
    // Add identity headers for collaborative editing
    if (window.nasmdIdentity) {
      const identity = window.nasmdIdentity.get();
      if (identity) {
        headers['X-Client-Id'] = identity.id;
        headers['X-Client-Name'] = identity.name;
        headers['X-Client-Color'] = identity.color;
      }
    }
    const resp = await fetch(`${_apiBase}${path}`, { ...options, headers });
    return resp;
  },

  // 获取挂载点列表
  async getMounts() {
    const r = await this.request('/api/mounts');
    return r ? r.json() : [];
  },

  // 获取公开挂载点列表
  async getPublicMounts() {
    const r = await this.request('/api/mounts/public');
    return r ? r.json() : [];
  },

  // 获取运行时配置
  async getConfig() {
    const r = await this.request('/api/config');
    if (!r || !r.ok) return null;
    return r.json();
  },

  // 添加挂载点
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
    const r = await this.request(
      `/api/mounts/${mountId}/tree-recursive?path=${encodeURIComponent(path || '/')}`,
    );
    return r ? r.json() : null;
  },

  // 让后端在常见位置搜索目录名，返回完整路径
  async findMountPath(dirName) {
    const r = await this.request(`/api/find-path?name=${encodeURIComponent(dirName)}`);
    return r ? r.json() : null;
  },

  async getFile(mountId, path) {
    const r = await this.request(
      `/api/mounts/${mountId}/file?path=${encodeURIComponent(path)}&_t=${Date.now()}`,
      { cache: 'no-store' },
    );
    if (!r) {
      console.error('getFile: request failed, no response');
      return null;
    }
    if (!r.ok) {
      const errText = await r.text().catch(() => '');
      console.error(`getFile: HTTP ${r.status}`, errText);
      return null;
    }
    const content = await r.text();
    const mtime = parseInt(r.headers.get('X-Mod-Time') || '0', 10);
    const version = parseInt(r.headers.get('X-File-Version') || '0', 10);
    return { content, mtime, version };
  },

  async putFile(mountId, path, content, expectedMtime) {
    let url = `/api/mounts/${mountId}/file?path=${encodeURIComponent(path)}`;
    if (expectedMtime) {
      url += `&expected_mtime=${expectedMtime}`;
    }
    console.log('[putFile] sending PUT:', {
      url,
      contentLen: content.length,
      expectedMtime,
    });
    try {
      const r = await this.request(url, {
        method: 'PUT',
        body: content,
      });
      console.log('[putFile] response status:', r ? r.status : 'null');
      return r ? r.json() : null;
    } catch (e) {
      console.error('[putFile] fetch error:', e);
      throw e;
    }
  },

  // 提交段落级changes（版本号驱动的协同编辑）
  // 调用 POST /api/mounts/{id}/changes?path=...
  // 返回 { applied, merged, newVersion, content } 或 null（失败时）
  async submitChanges(mountId, path, baseVersion, changes, authorName, authorColor, clientInfo) {
    const url = `/api/mounts/${mountId}/changes?path=${encodeURIComponent(path)}`;
    const body = JSON.stringify({
      baseVersion,
      changes,
      authorName: authorName || 'Anonymous',
      authorColor: authorColor || '#3498db',
      os: clientInfo ? clientInfo.os : 'Unknown OS',
      browser: clientInfo ? clientInfo.browser : 'Unknown Browser',
    });
    console.log('[submitChanges] sending POST:', {
      url,
      baseVersion,
      changesCount: changes.length,
    });
    try {
      const r = await this.request(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
      });
      if (!r || !r.ok) {
        const errText = r ? await r.text().catch(() => '') : '';
        console.error('[submitChanges] error:', errText);
        return null;
      }
      return r.json();
    } catch (e) {
      console.error('[submitChanges] fetch error:', e);
      throw e;
    }
  },

  async deleteFile(mountId, path) {
    const r = await this.request(`/api/mounts/${mountId}/file?path=${encodeURIComponent(path)}`, {
      method: 'DELETE',
    });
    return r ? r.json() : null;
  },

  // 远程文件代理：读取远程服务器上的文件
  async getRemoteFile(src, path, apiKey) {
    const url = `/api/remote/file?src=${encodeURIComponent(src)}&path=${encodeURIComponent(path)}`;
    try {
      const r = await this.request(url, {
        headers: { 'X-Remote-Key': apiKey || '' },
        cache: 'no-store',
      });
      if (!r || !r.ok) {
        const errText = r ? await r.text().catch(() => '') : '';
        console.error('[getRemoteFile] error:', r ? r.status : 'null', errText);
        return null;
      }
      return r.json();
    } catch (e) {
      console.error('[getRemoteFile] fetch error:', e);
      return null;
    }
  },

  // 远程文件代理：写入文件到远程服务器
  async putRemoteFile(src, path, content, apiKey) {
    const url = `/api/remote/file?src=${encodeURIComponent(src)}&path=${encodeURIComponent(path)}`;
    try {
      const r = await this.request(url, {
        method: 'PUT',
        headers: { 'X-Remote-Key': apiKey || '' },
        body: content,
      });
      if (!r || !r.ok) {
        const errText = r ? await r.text().catch(() => '') : '';
        console.error('[putRemoteFile] error:', r ? r.status : 'null', errText);
        return null;
      }
      return r.json();
    } catch (e) {
      console.error('[putRemoteFile] fetch error:', e);
      return null;
    }
  },

  async rename(mountId, oldPath, newPath) {
    const r = await this.request(
      `/api/mounts/${mountId}/rename?oldPath=${encodeURIComponent(oldPath)}&newPath=${encodeURIComponent(newPath)}`,
      {
        method: 'PUT',
      },
    );
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
    if (window.state?.isAdmin) headers['X-Admin'] = '1';
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
let _treeCache = {}; // { "mountId:path": [entries] }

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
