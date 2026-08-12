# Phase 3: PWA 增强 — 详细实施计划

## 目标
将 nas-md 从"可用"提升到"优秀"的移动端体验：离线可用、断网重连自动同步、底部导航栏。

---

## 子任务分解

### 3.1 Web App Manifest（PWA 基础）

**目标**: 让浏览器能把 nas-md 安装到桌面/主屏幕。

**改动文件**: 新增 `web/manifest.json`，修改 `web/index.html`

**manifest.json**:
```json
{
  "name": "nas-md — 个人知识管理",
  "short_name": "nas-md",
  "description": "纯 Python 标准库构建的个人 Markdown 知识管理系统，支持 Telegram Bot + PWA 双入口",
  "start_url": "/admin?homescreen=1",
  "display": "standalone",
  "background_color": "#0a1530",
  "theme_color": "#5645d4",
  "orientation": "any",
  "icons": [
    {
      "src": "/icon-192.png",
      "sizes": "192x192",
      "type": "image/png"
    },
    {
      "src": "/icon-512.png",
      "sizes": "512x512",
      "type": "image/png"
    },
    {
      "src": "/icon-maskable-192.png",
      "sizes": "192x192",
      "type": "image/png",
      "purpose": "maskable"
    },
    {
      "src": "/icon-maskable-512.png",
      "sizes": "512x512",
      "type": "image/png",
      "purpose": "maskable"
    }
  ]
}
```

**index.html 改动**:
```html
<head>
  <!-- 已有 -->
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <!-- 新增 PWA meta -->
  <meta name="theme-color" content="#5645d4" />
  <meta name="apple-mobile-web-app-capable" content="yes" />
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
  <meta name="apple-mobile-web-app-title" content="nas-md" />
  <!-- 新增 manifest -->
  <link rel="manifest" href="manifest.json" />
  <!-- 新增 iOS 图标 -->
  <link rel="apple-touch-icon" href="icon-192.png" />
  <title>nas-md</title>
```

**预估工作量**: ~30 分钟

---

### 3.2 Service Worker 基础版

**目标**: 缓存静态资源，实现离线加载。

**改动文件**: 新增 `web/sw.js`，在 `app.js` 中注册。

**sw.js** (基础版):
```javascript
const CACHE_NAME = 'nas-md-v1';
const STATIC_ASSETS = [
  '/',
  '/admin',
  '/app.css',
  '/app.js?v=2',
  '/editor.js',
  '/files.js',
  '/identity.js',
  '/sync_layer.js',
  '/sse_client.js',
  '/version_history.js',
  '/mermaid_enhancer.js',
  '/highlight.css',
  '/lib/vditor/index.min.js',
  '/lib/vditor/index.css',
  '/lib/d3/d3.min.js',
  '/lib/fonts/inter.css',
  '/lib/fonts/inter-temp/web/InterVariable.woff2',
];

// Install: cache all static assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

// Activate: clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
      );
    })
  );
  self.clients.claim();
});

// Fetch: cache-first, fallback to network
self.addEventListener('fetch', (event) => {
  // Skip non-GET requests
  if (event.request.method !== 'GET') return;

  // API calls: network-first
  if (event.request.url.includes('/api/')) {
    event.respondWith(
      fetch(event.request)
        .then((networkResponse) => {
          // Cache successful responses
          if (networkResponse.ok) {
            const responseClone = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(event.request, responseClone);
            });
          }
          return networkResponse;
        })
        .catch(() => {
          return new Response(JSON.stringify({ error: 'offline' }), {
            headers: { 'Content-Type': 'application/json' },
          });
        })
    );
    return;
  }

  // Static assets: cache-first
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      if (cachedResponse) {
        // Serve from cache, update in background
        const fetchPromise = fetch(event.request).then((networkResponse) => {
          if (networkResponse.ok) {
            const responseClone = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(event.request, responseClone);
            });
          }
          return networkResponse;
        }).catch(() => null);
        // Return cached immediately, update in background
        return cachedResponse;
      }
      return fetch(event.request).then((networkResponse) => {
        if (networkResponse.ok) {
          const responseClone = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseClone);
          });
        }
        return networkResponse;
      });
    })
  );
});
```

**app.js 注册 SW**:
```javascript
// Register service worker
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js')
      .then((reg) => {
        console.log('[SW] Registered:', reg.scope);
        state.swRegistered = true;
      })
      .catch((err) => {
        console.warn('[SW] Registration failed:', err);
      });
  });
}
```

**预估工作量**: ~1.5 小时

---

### 3.3 离线编辑队列

**目标**: 离线时编辑内容保存到 IndexedDB，网络恢复后自动同步。

**改动文件**: 新增 `web/offline_queue.js`

**offline_queue.js**:
```javascript
/**
 * Offline Queue — saves edits when offline, replays when online
 */
(function () {
  'use strict';

  const DB_NAME = 'nasmd-offline-queue';
  const STORE_NAME = 'pending-edits';
  let _db = null;

  async function openDB() {
    if (_db) return _db;
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = (e) => {
        const db = e.target.result;
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          const store = db.createObjectStore(STORE_NAME, { keyPath: 'id', autoIncrement: true });
          store.createIndex('synced', 'synced', { unique: false });
          store.createIndex('createdAt', 'createdAt', { unique: false });
        }
      };
      req.onsuccess = (e) => { _db = e.target.result; resolve(_db); };
      req.onerror = (e) => reject(e.target.error);
    });
  }

  /**
   * Queue an edit operation for later sync
   */
  async function queueEdit(mountId, path, content, version) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readwrite');
      const store = tx.objectStore(STORE_NAME);
      const item = {
        mountId,
        path,
        content,
        version,
        synced: false,
        createdAt: Date.now(),
      };
      const req = store.add(item);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  /**
   * Get all pending (unsynced) edits
   */
  async function getPendingEdits() {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readonly');
      const store = tx.objectStore(STORE_NAME);
      const idx = store.index('synced');
      const req = idx.getAll(false);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  /**
   * Mark an edit as synced and remove it
   */
  async function markSynced(editId) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readwrite');
      const store = tx.objectStore(STORE_NAME);
      const req = store.delete(editId);
      req.onsuccess = () => resolve();
      req.onerror = () => reject(req.error);
    });
  }

  /**
   * Clear all pending edits
   */
  async function clearQueue() {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readwrite');
      const req = tx.objectStore(STORE_NAME).clear();
      req.onsuccess = () => resolve();
      req.onerror = () => reject(req.error);
    });
  }

  /**
   * Try to replay all pending edits
   */
  async function replayPending() {
    const pending = await getPendingEdits();
    const results = [];
    for (const edit of pending) {
      try {
        const resp = await API.saveFile(edit.mountId, edit.path, edit.content);
        if (resp.ok) {
          await markSynced(edit.id);
          results.push({ edit, success: true });
        } else {
          results.push({ edit, success: false, error: resp.statusText });
        }
      } catch (err) {
        results.push({ edit, success: false, error: err.message });
      }
    }
    return results;
  }

  // Expose globally
  window.nasmdOfflineQueue = {
    queueEdit,
    getPendingEdits,
    markSynced,
    clearQueue,
    replayPending,
    get pendingCount() {
      return getPendingEdits().then((e) => e.length);
    },
  };

  // Auto-replay on online
  window.addEventListener('online', () => {
    console.log('[offline-queue] Network restored, replaying pending edits...');
    replayPending().then((results) => {
      const succeeded = results.filter((r) => r.success).length;
      const failed = results.filter((r) => !r.success).length;
      if (failed > 0) {
        showToast(`已同步 ${succeeded} 个编辑，${failed} 个失败`);
      } else if (succeeded > 0) {
        showToast(`已同步 ${succeeded} 个离线编辑`);
      }
    });
  });
})();
```

**集成到 app.js**:
```javascript
// In saveFile function, add offline fallback
async function saveFile({ silent = false } = {}) {
  // ... existing save logic ...
  
  // If save fails due to network, queue for offline
  try {
    const resp = await API.saveFileRequest(mountId, path, content);
    if (!resp.ok) throw new Error('Network error');
    // Success — clear any offline queue entry
    if (window.nasmdOfflineQueue) {
      const pending = await window.nasmdOfflineQueue.getPendingEdits();
      const match = pending.find(e => e.mountId === mountId && e.path === path);
      if (match) await window.nasmdOfflineQueue.markSynced(match.id);
    }
  } catch (err) {
    // Network error — queue for offline sync
    if (window.nasmdOfflineQueue && !navigator.onLine) {
      await window.nasmdOfflineQueue.queueEdit(mountId, path, content, version);
      if (!silent) showToast('已保存到离线队列，网络恢复后自动同步');
    }
    throw err;
  }
}
```

**预估工作量**: ~2 小时

---

### 3.4 网络状态指示器

**目标**: 在 UI 上显示在线/离线状态，让用户知道同步状态。

**改动文件**: `web/app.css`, `web/app.js`, `web/index.html`

**HTML 改动** (index.html topbar):
```html
<!-- 添加在网络状态指示器 -->
<div id="network-status" class="network-status" title="网络状态">
  <span class="network-dot"></span>
  <span class="network-label">在线</span>
</div>
```

**CSS 改动** (app.css):
```css
.network-status {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: var(--r-sm);
  font-size: 11px;
  color: var(--c-text-muted);
  transition: all 0.2s;
}

.network-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--c-success);
  transition: background 0.2s;
}

.network-status.offline .network-dot {
  background: var(--c-danger);
}

.network-status.syncing .network-dot {
  background: var(--c-warning);
  animation: pulse 1s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* Mobile: hide label, show only dot */
@media (max-width: 767px) {
  .network-label {
    display: none;
  }
}
```

**JS 改动** (app.js):
```javascript
// Network status indicator
(function initNetworkStatus() {
  const el = document.getElementById('network-status');
  if (!el) return;

  function updateStatus() {
    const isOnline = navigator.onLine;
    el.classList.toggle('offline', !isOnline);
    el.querySelector('.network-label').textContent = isOnline ? '在线' : '离线';
  }

  updateStatus();
  window.addEventListener('online', updateStatus);
  window.addEventListener('offline', updateStatus);
})();
```

**预估工作量**: ~30 分钟

---

### 3.5 底部 Tab Bar（可选，Phase 3.5）

**目标**: 在移动端提供类似 Notion Mobile 的底部导航栏，替代侧边栏。

**改动文件**: `web/app.css`, `web/index.html`, `web/app.js`

**HTML** (在 body 末尾添加):
```html
<!-- Mobile Bottom Tab Bar -->
<nav id="mobile-tab-bar" class="mobile-tab-bar" style="display:none">
  <button class="tab-btn active" data-tab="files" onclick="switchTab('files')">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
    </svg>
    <span>文件</span>
  </button>
  <button class="tab-btn" data-tab="search" onclick="switchTab('search')">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
    </svg>
    <span>搜索</span>
  </button>
  <button class="tab-btn" data-tab="graph" onclick="switchTab('graph')">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/>
      <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/>
      <line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>
    </svg>
    <span>图谱</span>
  </button>
  <button class="tab-btn" data-tab="stats" onclick="switchTab('stats')">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/>
      <line x1="6" y1="20" x2="6" y2="14"/>
    </svg>
    <span>统计</span>
  </button>
</nav>
```

**CSS**:
```css
/* Mobile Tab Bar */
.mobile-tab-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  height: 56px;
  background: var(--c-bg-sidebar);
  border-top: 1px solid var(--c-border);
  display: none;
  justify-content: space-around;
  align-items: center;
  z-index: 200;
  padding-bottom: env(safe-area-inset-bottom);
}

@media (max-width: 767px) {
  .mobile-tab-bar {
    display: flex;
  }
  
  /* Adjust main content for tab bar */
  .main {
    padding-bottom: 64px;
  }
}

.tab-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  padding: 6px 12px;
  border: none;
  background: none;
  color: var(--c-text-muted);
  font-size: 10px;
  cursor: pointer;
  transition: color 0.15s;
  min-width: 56px;
}

.tab-btn.active {
  color: var(--c-primary);
}

.tab-btn svg {
  width: 20px;
  height: 20px;
}
```

**JS**:
```javascript
function switchTab(tab) {
  document.querySelectorAll('.tab-btn').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.tab === tab);
  });
  
  switch (tab) {
    case 'files':
      // Show sidebar
      document.getElementById('sidebar').classList.add('open');
      break;
    case 'search':
      // Focus search
      document.getElementById('search-input')?.focus();
      break;
    case 'graph':
      // Open graph viewer
      window.open('/graph-viewer.html', '_blank');
      break;
    case 'stats':
      // Navigate to dashboard
      window.location.href = '/admin#stats';
      break;
  }
}

// Show/hide tab bar based on viewport
function updateTabBar() {
  const tabBar = document.getElementById('mobile-tab-bar');
  if (!tabBar) return;
  tabBar.style.display = window.innerWidth < 768 ? 'flex' : 'none';
}
window.addEventListener('resize', updateTabBar);
updateTabBar();
```

**预估工作量**: ~1.5 小时

---

### 3.6 SSE 移动端 Toast 通知（可选，Phase 3.6）

**目标**: 协同编辑时，在移动端显示友好的 toast 通知而非浮窗。

**改动文件**: `web/sync_layer.js`, `web/app.css`

**CSS**:
```css
/* Mobile-friendly collaboration toast */
.collab-toast {
  position: fixed;
  bottom: 72px;  /* Above tab bar */
  left: 50%;
  transform: translateX(-50%) translateY(20px);
  background: var(--c-bg);
  border: 1px solid var(--c-border);
  border-radius: var(--r-lg);
  padding: 10px 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  box-shadow: var(--shadow-lg);
  z-index: 9998;
  opacity: 0;
  transition: all 0.3s ease;
  max-width: 90vw;
}

.collab-toast.show {
  opacity: 1;
  transform: translateX(-50%) translateY(0);
}

.collab-toast .toast-avatar {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: bold;
  color: white;
  flex-shrink: 0;
}

.collab-toast .toast-text {
  font-size: 13px;
  color: var(--c-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
```

**sync_layer.js 改动**:
```javascript
// Replace showCollabNotification with mobile-friendly toast
function showCollabNotification(author, changeType, paraIdx) {
  // Remove old toast
  const old = document.querySelector('.collab-toast');
  if (old) old.remove();

  const toast = document.createElement('div');
  toast.className = 'collab-toast';
  
  const initial = (author.name || '?').charAt(0).toUpperCase();
  const actionText = changeType === 'replace' ? '编辑了' : 
                     changeType === 'insert' ? '新增' : '删除';
  
  toast.innerHTML = `
    <div class="toast-avatar" style="background:${author.color}">${initial}</div>
    <div class="toast-text">${author.name} ${actionText} 第${paraIdx + 1}段</div>
  `;
  
  document.body.appendChild(toast);
  
  // Animate in
  requestAnimationFrame(() => {
    toast.classList.add('show');
  });
  
  // Auto-remove
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}
```

**预估工作量**: ~1 小时

---

## 实施顺序

| 顺序 | 子任务 | 依赖 | 工作量 |
|------|--------|------|--------|
| 1 | 3.1 Web App Manifest | 无 | 30min |
| 2 | 3.2 Service Worker 基础版 | 3.1 | 1.5h |
| 3 | 3.4 网络状态指示器 | 无 | 30min |
| 4 | 3.3 离线编辑队列 | 3.2 | 2h |
| 5 | 3.5 底部 Tab Bar | 3.4 | 1.5h |
| 6 | 3.6 SSE 移动端 Toast | 3.5 | 1h |

**总计**: ~7 小时

---

## 验收标准

- [ ] `manifest.json` 存在且通过 Lighthouse PWA 审计
- [ ] Service Worker 正确缓存静态资源
- [ ] 离线时页面可正常加载（Cache First）
- [ ] API 请求在离线时返回友好错误
- [ ] 网络恢复后自动同步离线编辑
- [ ] 网络状态指示器正确显示在线/离线
- [ ] 移动端底部 Tab Bar 可见且可用
- [ ] 协同编辑 toast 在移动端居中显示

---

## 风险与注意事项

1. **Service Worker Scope**: 必须在网站根目录部署 SW，Docker 部署时需配置
2. **IndexedDB Quota**: 离线队列占用 IndexedDB 空间，需要设置上限
3. **Tab Bar 与 Sidebar 冲突**: 移动端同时有侧边栏和底部 Tab Bar 时，需要处理 z-index 和交互冲突
4. **SSE 移动网络稳定性**: 3G/4G 网络下 SSE 连接容易断开，需要 reconnection 逻辑
5. **Push API 兼容性**: 移动端 Push Notification 在不同浏览器/OS 上兼容性差异大，建议先实现 Web Push 基础架构
