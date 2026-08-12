/**
 * offline_queue.js - Offline edit queue using IndexedDB
 *
 * When the network is unavailable, edits are queued in IndexedDB
 * and replayed automatically when the connection is restored.
 */
'use strict';

(function () {
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
   * @param {string} mountId
   * @param {string} path
   * @param {string} content
   * @param {number} version
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
   * Get pending edit count
   */
  async function getPendingCount() {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readonly');
      const req = tx.objectStore(STORE_NAME).count();
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  /**
   * Try to replay all pending edits
   * Returns { success: number, failed: number }
   */
  async function replayPending() {
    const pending = await getPendingEdits();
    let success = 0;
    let failed = 0;

    for (const edit of pending) {
      try {
        // Use the API.saveFileRequest if available, otherwise fall back
        if (window.API && window.API.saveFileRequest) {
          const resp = await window.API.saveFileRequest(edit.mountId, edit.path, edit.content);
          if (resp.ok) {
            await markSynced(edit.id);
            success++;
          } else {
            failed++;
          }
        } else {
          // Fallback: use fetch directly
          const url = `/api/files/${encodeURIComponent(edit.mountId)}${encodeURIComponent(edit.path)}`;
          const resp = await fetch(url, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content: edit.content }),
          });
          if (resp.ok) {
            await markSynced(edit.id);
            success++;
          } else {
            failed++;
          }
        }
      } catch (err) {
        failed++;
      }
    }

    return { success, failed };
  }

  // Expose globally
  window.nasmdOfflineQueue = {
    queueEdit,
    getPendingEdits,
    markSynced,
    clearQueue,
    getPendingCount,
    replayPending,
  };

  // Auto-replay on network restore
  window.addEventListener('online', () => {
    console.log('[offline-queue] Network restored, replaying pending edits...');
    replayPending().then(({ success, failed }) => {
      if (failed > 0) {
        showToast(`已同步 ${success} 个编辑，${failed} 个失败`);
      } else if (success > 0) {
        showToast(`已同步 ${success} 个离线编辑`);
      }
    });
  });

  console.log('[offline-queue] Initialized');
})();
