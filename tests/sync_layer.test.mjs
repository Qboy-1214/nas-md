import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

function makeElement() {
  return {
    children: [],
    innerHTML: '',
    parentNode: null,
    style: {},
    appendChild(child) {
      child.parentNode = this;
      this.children.push(child);
    },
    removeChild(child) {
      this.children = this.children.filter((item) => item !== child);
      child.parentNode = null;
    },
  };
}

function loadSyncLayer({
  version = 2,
  content = 'current-v2',
  baseContent,
  dirty = false,
  fullResult,
  fullPromise,
  fullPromises,
  manualTimers = false,
} = {}) {
  const confirmedContent = baseContent === undefined ? content : baseContent;
  const state = {
    currentMountId: 'mount-0',
    currentPath: '/doc.md',
    baseVersion: version,
    baseContent: confirmedContent,
    fileVersions: { 'mount-0:/doc.md': version },
    pendingRemoteVersion: null,
    dirty,
  };
  const editor = {
    value: content,
    getValue() {
      return this.value;
    },
    setValue(value) {
      this.value = value;
    },
  };
  const apiCalls = [];
  const consoleErrors = [];
  const toasts = [];
  const timers = new Map();
  const windowListeners = new Map();
  let nextTimerId = 1;
  let currentTime = 10000;
  const documentBody = makeElement();
  const context = vm.createContext({
    API: {
      getFile(mountId, path) {
        apiCalls.push([mountId, path]);
        if (fullPromises) return fullPromises.shift();
        if (fullPromise) return fullPromise;
        return Promise.resolve(fullResult || { content: 'full-v3', version: 3, mtime: 0 });
      },
    },
    clearTimeout(timerId) {
      timers.delete(timerId);
    },
    Date: {
      now() {
        return currentTime;
      },
    },
    console: {
      error(...args) {
        consoleErrors.push(args);
      },
      log() {},
      warn() {},
    },
    document: {
      body: documentBody,
      readyState: 'loading',
      addEventListener() {},
      createElement() {
        return makeElement();
      },
      getElementById() {
        return null;
      },
    },
    requestAnimationFrame(callback) {
      callback();
    },
    setInterval() {},
    setTimeout(callback, delay) {
      if (manualTimers) {
        const timerId = nextTimerId++;
        timers.set(timerId, { callback, delay });
        return timerId;
      }
      callback();
      return 1;
    },
    state,
    window: {
      _lastSavedContent: confirmedContent,
      _originalContent: confirmedContent,
      _vditor: editor,
      addEventListener(type, listener) {
        const listeners = windowListeners.get(type) || [];
        listeners.push(listener);
        windowListeners.set(type, listeners);
      },
      showToast(...args) {
        toasts.push(args);
      },
      state,
    },
  });
  vm.runInContext(readFileSync(new URL('../web/sync_layer.js', import.meta.url), 'utf8'), context);
  return {
    advanceTime(milliseconds) {
      currentTime += milliseconds;
    },
    apiCalls,
    consoleErrors,
    context,
    dispatchWindowEvent(type) {
      for (const listener of windowListeners.get(type) || []) listener();
    },
    editor,
    runTimers(delay) {
      const due = Array.from(timers.entries()).filter(([, timer]) => timer.delay === delay);
      for (const [timerId, timer] of due) {
        timers.delete(timerId);
        timer.callback();
      }
    },
    state,
    toasts,
  };
}

async function flushPromises() {
  await Promise.resolve();
  await Promise.resolve();
}

function snapshotClient(app, versionKey = 'mount-0:/doc.md') {
  return {
    baseContent: app.state.baseContent,
    baseVersion: app.state.baseVersion,
    editor: app.editor.value,
    fileVersion: app.state.fileVersions[versionKey],
    lastSavedContent: app.context.window._lastSavedContent,
    originalContent: app.context.window._originalContent,
  };
}

test('late v1 events cannot roll back current v2 state', async () => {
  const external = loadSyncLayer();
  external.context.window.nasmdSync.handleExternalReload({
    type: 'external_reload',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 1,
    content: 'stale-v1',
  });
  assert.equal(external.state.baseVersion, 2);
  assert.equal(external.editor.value, 'current-v2');
  assert.deepEqual(external.apiCalls, []);

  const remote = loadSyncLayer();
  remote.context.window.nasmdSync.handleRemoteEdit({
    type: 'remote_edit',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 1,
    changes: [{ type: 'replace', paraIdx: 0, content: 'stale-v1' }],
  });
  assert.equal(remote.state.baseVersion, 2);
  assert.equal(remote.editor.value, 'current-v2');
  assert.deepEqual(remote.apiCalls, []);
  await flushPromises();
  assert.deepEqual(external.consoleErrors, []);
  assert.deepEqual(remote.consoleErrors, []);
});

test('version gaps fetch and atomically apply full content', async () => {
  const external = loadSyncLayer({ version: 1, content: 'current-v1' });
  external.context.window.nasmdSync.handleExternalReload({
    type: 'external_reload',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 3,
    content: 'event-v3',
  });
  assert.equal(external.editor.value, 'current-v1');
  assert.deepEqual(external.apiCalls, [['mount-0', '/doc.md']]);
  await flushPromises();
  assert.deepEqual(snapshotClient(external), {
    baseContent: 'full-v3',
    baseVersion: 3,
    editor: 'full-v3',
    fileVersion: 3,
    lastSavedContent: 'full-v3',
    originalContent: 'full-v3',
  });
  assert.deepEqual(external.consoleErrors, []);

  const remote = loadSyncLayer({ version: 1, content: 'current-v1' });
  remote.context.window.nasmdSync.handleRemoteEdit({
    type: 'remote_edit',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 3,
    changes: [{ type: 'replace', paraIdx: 0, content: 'incremental-v3' }],
  });
  assert.equal(remote.editor.value, 'current-v1');
  assert.deepEqual(remote.apiCalls, [['mount-0', '/doc.md']]);
  await flushPromises();
  assert.deepEqual(snapshotClient(remote), {
    baseContent: 'full-v3',
    baseVersion: 3,
    editor: 'full-v3',
    fileVersion: 3,
    lastSavedContent: 'full-v3',
    originalContent: 'full-v3',
  });
  assert.deepEqual(remote.consoleErrors, []);
});

test('a full-content fetch invalidates an older debounced incremental batch', async () => {
  const app = loadSyncLayer({
    version: 1,
    content: 'current-v1',
    fullResult: { content: 'full-v4', version: 4, mtime: 0 },
    manualTimers: true,
  });

  app.context.window.nasmdSync.handleRemoteEdit({
    type: 'remote_edit',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 2,
    changes: [{ type: 'replace', paraIdx: 0, content: 'incremental-v2' }],
  });
  app.context.window.nasmdSync.handleExternalReload({
    type: 'external_reload',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 4,
    content: 'event-v4',
  });
  await flushPromises();

  app.runTimers(300);

  assert.deepEqual(snapshotClient(app), {
    baseContent: 'full-v4',
    baseVersion: 4,
    editor: 'full-v4',
    fileVersion: 4,
    lastSavedContent: 'full-v4',
    originalContent: 'full-v4',
  });
  assert.deepEqual(app.consoleErrors, []);
});

test('an acknowledged snapshot discards its already queued incremental batch', async () => {
  const app = loadSyncLayer({ version: 1, content: 'A', manualTimers: true });

  app.context.window.nasmdSync.handleRemoteEdit({
    type: 'remote_edit',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 2,
    changes: [{ type: 'insert', paraIdx: 0, content: 'X' }],
  });

  // A separate server reload acknowledges v2 before its incremental timer fires.
  app.state.baseVersion = 2;
  app.state.baseContent = 'X\n\nA';
  app.state.fileVersions['mount-0:/doc.md'] = 2;
  app.editor.value = 'X\n\nA';
  app.context.window._originalContent = 'X\n\nA';
  app.context.window._lastSavedContent = 'X\n\nA';

  app.runTimers(300);

  assert.deepEqual(snapshotClient(app), {
    baseContent: 'X\n\nA',
    baseVersion: 2,
    editor: 'X\n\nA',
    fileVersion: 2,
    lastSavedContent: 'X\n\nA',
    originalContent: 'X\n\nA',
  });
  assert.deepEqual(app.consoleErrors, []);
});

test('an older gap fetch cannot erase a newer queued incremental version', async () => {
  let resolveOlderFetch;
  let resolveNewerFetch;
  const olderFetch = new Promise((resolve) => {
    resolveOlderFetch = resolve;
  });
  const newerFetch = new Promise((resolve) => {
    resolveNewerFetch = resolve;
  });
  const app = loadSyncLayer({
    version: 1,
    content: 'A-v1',
    fullPromises: [olderFetch, newerFetch],
    manualTimers: true,
  });

  app.context.window.nasmdSync.handleRemoteEdit({
    type: 'remote_edit',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 3,
    changes: [{ type: 'replace', paraIdx: 0, content: 'event-v3' }],
  });
  app.context.window.nasmdSync.handleRemoteEdit({
    type: 'remote_edit',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 4,
    changes: [{ type: 'replace', paraIdx: 0, content: 'event-v4' }],
  });
  assert.deepEqual(app.apiCalls, [
    ['mount-0', '/doc.md'],
    ['mount-0', '/doc.md'],
  ]);

  resolveNewerFetch({ content: 'A-v4', version: 4, mtime: 0 });
  await flushPromises();
  assert.equal(app.state.baseVersion, 4);

  app.context.window.nasmdSync.handleRemoteEdit({
    type: 'remote_edit',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 5,
    changes: [{ type: 'insert', paraIdx: 0, content: 'V5' }],
  });

  resolveOlderFetch({ content: 'stale-v4', version: 4, mtime: 0 });
  await flushPromises();
  app.runTimers(300);

  assert.deepEqual(snapshotClient(app), {
    baseContent: 'V5\n\nA-v4',
    baseVersion: 5,
    editor: 'V5\n\nA-v4',
    fileVersion: 5,
    lastSavedContent: 'V5\n\nA-v4',
    originalContent: 'V5\n\nA-v4',
  });
  assert.deepEqual(app.consoleErrors, []);
});

test('a failed newer gap fetch does not invalidate an older sufficient response', async () => {
  let resolveOlderFetch;
  let rejectNewerFetch;
  const olderFetch = new Promise((resolve) => {
    resolveOlderFetch = resolve;
  });
  const newerFetch = new Promise((_resolve, reject) => {
    rejectNewerFetch = reject;
  });
  const app = loadSyncLayer({
    version: 1,
    content: 'A-v1',
    fullPromises: [olderFetch, newerFetch],
    manualTimers: true,
  });

  app.context.window.nasmdSync.handleRemoteEdit({
    type: 'remote_edit',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 3,
    changes: [{ type: 'replace', paraIdx: 0, content: 'event-v3' }],
  });
  app.context.window.nasmdSync.handleRemoteEdit({
    type: 'remote_edit',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 4,
    changes: [{ type: 'replace', paraIdx: 0, content: 'event-v4' }],
  });

  rejectNewerFetch(new Error('newer fetch failed'));
  await flushPromises();
  resolveOlderFetch({ content: 'A-v4', version: 4, mtime: 0 });
  await flushPromises();
  app.runTimers(1000);

  assert.deepEqual(snapshotClient(app), {
    baseContent: 'A-v4',
    baseVersion: 4,
    editor: 'A-v4',
    fileVersion: 4,
    lastSavedContent: 'A-v4',
    originalContent: 'A-v4',
  });
  assert.deepEqual(app.apiCalls, [
    ['mount-0', '/doc.md'],
    ['mount-0', '/doc.md'],
  ]);
  assert.equal(app.consoleErrors.length, 1);
});

test('consecutive remote versions apply in their own paragraph coordinates', async () => {
  const app = loadSyncLayer({ version: 1, content: 'A\n\nB', manualTimers: true });

  app.context.window.nasmdSync.handleRemoteEdit({
    type: 'remote_edit',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 2,
    changes: [{ type: 'insert', paraIdx: 0, content: 'X' }],
  });
  app.context.window.nasmdSync.handleRemoteEdit({
    type: 'remote_edit',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 3,
    changes: [{ type: 'replace', paraIdx: 1, content: 'A2' }],
  });

  app.runTimers(300);

  assert.deepEqual(snapshotClient(app), {
    baseContent: 'X\n\nA2\n\nB',
    baseVersion: 3,
    editor: 'X\n\nA2\n\nB',
    fileVersion: 3,
    lastSavedContent: 'X\n\nA2\n\nB',
    originalContent: 'X\n\nA2\n\nB',
  });
  assert.deepEqual(app.consoleErrors, []);
});

test('protected changes preserve FIFO order across later remote versions', async () => {
  const app = loadSyncLayer({ version: 1, content: 'A\n\nB', manualTimers: true });
  app.context.window.onEditorInput = () => {};
  app.context.window.nasmdSync.init();
  app.editor.value = 'A';
  app.context.window.onEditorInput();
  app.editor.value = 'A\n\nB';

  app.context.window.nasmdSync.handleRemoteEdit({
    type: 'remote_edit',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 2,
    changes: [{ type: 'insert', paraIdx: 0, content: 'X' }],
  });
  app.runTimers(300);
  assert.equal(app.editor.value, 'A\n\nB');
  assert.equal(app.state.baseVersion, 1);

  app.context.window.nasmdSync.handleRemoteEdit({
    type: 'remote_edit',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 3,
    changes: [{ type: 'replace', paraIdx: 1, content: 'A2' }],
  });

  app.runTimers(300);
  assert.equal(app.editor.value, 'A\n\nB');
  assert.equal(app.state.baseVersion, 1);
  app.advanceTime(2001);
  app.context.window.nasmdSync.applyPendingUpdates();

  assert.deepEqual(snapshotClient(app), {
    baseContent: 'X\n\nA2\n\nB',
    baseVersion: 3,
    editor: 'X\n\nA2\n\nB',
    fileVersion: 3,
    lastSavedContent: 'X\n\nA2\n\nB',
    originalContent: 'X\n\nA2\n\nB',
  });
  assert.deepEqual(app.consoleErrors, []);
});

test('a protected update for another file does not block the current file', async () => {
  const app = loadSyncLayer({ version: 1, content: 'file-a', manualTimers: true });
  app.context.window.onEditorInput = () => {};
  app.context.window.nasmdSync.init();
  app.context.window.onEditorInput();

  app.context.window.nasmdSync.handleRemoteEdit({
    type: 'remote_edit',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 2,
    changes: [{ type: 'replace', paraIdx: 0, content: 'file-a-v2' }],
  });
  app.runTimers(300);
  assert.equal(app.editor.value, 'file-a');

  app.advanceTime(2001);
  app.state.currentPath = '/other.md';
  app.state.baseVersion = 7;
  app.state.baseContent = 'file-b';
  app.state.fileVersions['mount-0:/other.md'] = 7;
  app.editor.value = 'file-b';
  app.context.window._originalContent = 'file-b';
  app.context.window._lastSavedContent = 'file-b';

  app.context.window.nasmdSync.handleRemoteEdit({
    type: 'remote_edit',
    mountId: 'mount-0',
    path: '/other.md',
    newVersion: 8,
    changes: [{ type: 'replace', paraIdx: 0, content: 'file-b-v8' }],
  });
  app.runTimers(300);

  assert.deepEqual(snapshotClient(app, 'mount-0:/other.md'), {
    baseContent: 'file-b-v8',
    baseVersion: 8,
    editor: 'file-b-v8',
    fileVersion: 8,
    lastSavedContent: 'file-b-v8',
    originalContent: 'file-b-v8',
  });
  assert.deepEqual(app.consoleErrors, []);
});

test('a delayed remote batch cannot mutate a newly opened file', async () => {
  const app = loadSyncLayer({ version: 1, content: 'file-a', manualTimers: true });

  app.context.window.nasmdSync.handleRemoteEdit({
    type: 'remote_edit',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 2,
    changes: [{ type: 'replace', paraIdx: 0, content: 'file-a-v2' }],
  });

  app.state.currentPath = '/other.md';
  app.state.baseVersion = 7;
  app.state.baseContent = 'file-b';
  app.state.fileVersions['mount-0:/other.md'] = 7;
  app.editor.value = 'file-b';
  app.context.window._originalContent = 'file-b';
  app.context.window._lastSavedContent = 'file-b';

  app.runTimers(300);

  assert.deepEqual(snapshotClient(app), {
    baseContent: 'file-b',
    baseVersion: 7,
    editor: 'file-b',
    fileVersion: 2,
    lastSavedContent: 'file-b',
    originalContent: 'file-b',
  });
  assert.deepEqual(app.consoleErrors, []);
});

test('a batch dropped after an A to B switch does not suppress A when it is reopened', async () => {
  const app = loadSyncLayer({ version: 1, content: 'file-a-v1', manualTimers: true });

  app.context.window.nasmdSync.handleRemoteEdit({
    type: 'remote_edit',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 2,
    changes: [{ type: 'replace', paraIdx: 0, content: 'file-a-v2' }],
  });

  app.state.currentPath = '/other.md';
  app.state.baseVersion = 7;
  app.state.baseContent = 'file-b-v7';
  app.state.fileVersions['mount-0:/other.md'] = 7;
  app.editor.value = 'file-b-v7';
  app.context.window._originalContent = 'file-b-v7';
  app.context.window._lastSavedContent = 'file-b-v7';
  app.runTimers(300);

  app.state.currentPath = '/doc.md';
  app.state.baseVersion = 1;
  app.state.baseContent = 'file-a-v1';
  app.state.fileVersions['mount-0:/doc.md'] = 1;
  app.editor.value = 'file-a-v1';
  app.context.window._originalContent = 'file-a-v1';
  app.context.window._lastSavedContent = 'file-a-v1';

  app.context.window.nasmdSync.handleRemoteEdit({
    type: 'remote_edit',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 2,
    changes: [{ type: 'replace', paraIdx: 0, content: 'file-a-v2' }],
  });
  app.runTimers(300);

  assert.deepEqual(snapshotClient(app), {
    baseContent: 'file-a-v2',
    baseVersion: 2,
    editor: 'file-a-v2',
    fileVersion: 2,
    lastSavedContent: 'file-a-v2',
    originalContent: 'file-a-v2',
  });
  assert.deepEqual(app.consoleErrors, []);
});

test('dirty clients defer exact remote and external events without changing baseline', async () => {
  const remote = loadSyncLayer({
    version: 1,
    content: 'local-dirty',
    baseContent: 'confirmed-v1',
    dirty: true,
  });
  const remoteBefore = snapshotClient(remote);
  remote.context.window.nasmdSync.handleRemoteEdit({
    type: 'remote_edit',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 2,
    changes: [{ type: 'replace', paraIdx: 0, content: 'remote-v2' }],
  });
  await flushPromises();
  assert.deepEqual(snapshotClient(remote), remoteBefore);
  assert.equal(remote.state.pendingRemoteVersion, 2);
  assert.deepEqual(remote.toasts, [['检测到远端更新，将在保存时自动合并', 'info']]);
  assert.deepEqual(remote.apiCalls, []);
  assert.deepEqual(remote.consoleErrors, []);

  const external = loadSyncLayer({
    version: 1,
    content: 'local-dirty',
    baseContent: 'confirmed-v1',
    dirty: true,
  });
  const externalBefore = snapshotClient(external);
  external.context.window.nasmdSync.handleExternalReload({
    type: 'external_reload',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 2,
    content: 'external-v2',
  });
  await flushPromises();
  assert.deepEqual(snapshotClient(external), externalBefore);
  assert.equal(external.state.pendingRemoteVersion, 2);
  assert.deepEqual(external.toasts, [['检测到远端更新，将在保存时自动合并', 'info']]);
  assert.deepEqual(external.apiCalls, []);
  assert.deepEqual(external.consoleErrors, []);
});

test('becoming clean catches up to an exact remote version deferred while dirty', async () => {
  const app = loadSyncLayer({
    version: 1,
    content: 'local-dirty',
    baseContent: 'confirmed-v1',
    dirty: true,
    fullResult: { content: 'full-v2', version: 2, mtime: 0 },
  });

  app.context.window.nasmdSync.handleRemoteEdit({
    type: 'remote_edit',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 2,
    changes: [{ type: 'replace', paraIdx: 0, content: 'event-v2' }],
  });
  assert.equal(app.state.pendingRemoteVersion, 2);
  assert.deepEqual(app.apiCalls, []);

  app.state.dirty = false;
  app.editor.value = 'confirmed-v1';
  app.context.window.nasmdSync.handleDirtyStateChange(false);
  await flushPromises();

  assert.deepEqual(app.apiCalls, [['mount-0', '/doc.md']]);
  assert.deepEqual(snapshotClient(app), {
    baseContent: 'full-v2',
    baseVersion: 2,
    editor: 'full-v2',
    fileVersion: 2,
    lastSavedContent: 'full-v2',
    originalContent: 'full-v2',
  });
  assert.equal(app.state.pendingRemoteVersion, null);
  assert.deepEqual(app.consoleErrors, []);
});

test('an offline draft blocks pending-version catch-up through reconnect', async () => {
  const neverResolvingFetch = new Promise(() => {});
  const app = loadSyncLayer({
    version: 1,
    content: 'offline-draft',
    baseContent: 'confirmed-v1',
    dirty: true,
    fullPromise: neverResolvingFetch,
  });
  app.context.window.navigator = { onLine: false };
  app.context.window.localStorage = {
    getItem(key) {
      return key === 'nasmd_draft_/doc.md' ? '{"content":"offline-draft"}' : null;
    },
  };
  app.context.window.nasmdSync.init();

  app.context.window.nasmdSync.handleRemoteEdit({
    type: 'remote_edit',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 2,
    changes: [{ type: 'replace', paraIdx: 0, content: 'event-v2' }],
  });
  app.state.dirty = false;
  app.context.window.nasmdSync.handleDirtyStateChange(false);
  app.context.window.navigator.onLine = true;
  app.dispatchWindowEvent('online');

  assert.deepEqual(app.apiCalls, []);
  assert.equal(app.state.pendingRemoteVersion, 2);
  assert.deepEqual(snapshotClient(app), {
    baseContent: 'confirmed-v1',
    baseVersion: 1,
    editor: 'offline-draft',
    fileVersion: 1,
    lastSavedContent: 'confirmed-v1',
    originalContent: 'confirmed-v1',
  });
});

test('a current offline draft blocks queued and in-flight remote application', async () => {
  const queued = loadSyncLayer({ version: 1, content: 'confirmed-v1', manualTimers: true });
  queued.context.window.nasmdSync.handleRemoteEdit({
    type: 'remote_edit',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 2,
    changes: [{ type: 'replace', paraIdx: 0, content: 'remote-v2' }],
  });
  queued.editor.value = 'offline-draft';
  queued.context.window.localStorage = {
    getItem(key) {
      return key === 'nasmd_draft_/doc.md' ? '{"content":"offline-draft"}' : null;
    },
  };
  queued.runTimers(300);

  assert.deepEqual(snapshotClient(queued), {
    baseContent: 'confirmed-v1',
    baseVersion: 1,
    editor: 'offline-draft',
    fileVersion: 1,
    lastSavedContent: 'confirmed-v1',
    originalContent: 'confirmed-v1',
  });
  assert.equal(queued.state.pendingRemoteVersion, 2);

  let resolveFetch;
  const fullPromise = new Promise((resolve) => {
    resolveFetch = resolve;
  });
  const inFlight = loadSyncLayer({ version: 1, content: 'confirmed-v1', fullPromise });
  inFlight.context.window.nasmdSync.handleRemoteEdit({
    type: 'remote_edit',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 3,
    changes: [{ type: 'replace', paraIdx: 0, content: 'event-v3' }],
  });
  inFlight.editor.value = 'offline-draft';
  inFlight.context.window.localStorage = queued.context.window.localStorage;
  resolveFetch({ content: 'full-v3', version: 3, mtime: 0 });
  await flushPromises();

  assert.deepEqual(snapshotClient(inFlight), {
    baseContent: 'confirmed-v1',
    baseVersion: 1,
    editor: 'offline-draft',
    fileVersion: 1,
    lastSavedContent: 'confirmed-v1',
    originalContent: 'confirmed-v1',
  });
  assert.equal(inFlight.state.pendingRemoteVersion, 3);
});

test('connectivity restoration retries a failed clean pending-version catch-up', async () => {
  let rejectInitialFetch;
  let resolveRetryFetch;
  const initialFetch = new Promise((_resolve, reject) => {
    rejectInitialFetch = reject;
  });
  const retryFetch = new Promise((resolve) => {
    resolveRetryFetch = resolve;
  });
  const app = loadSyncLayer({
    version: 1,
    content: 'local-dirty',
    baseContent: 'confirmed-v1',
    dirty: true,
    fullPromises: [initialFetch, retryFetch],
    manualTimers: true,
  });
  app.context.window.nasmdSync.init();

  app.context.window.nasmdSync.handleRemoteEdit({
    type: 'remote_edit',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 2,
    changes: [{ type: 'replace', paraIdx: 0, content: 'event-v2' }],
  });
  app.state.dirty = false;
  app.editor.value = 'confirmed-v1';
  app.context.window.nasmdSync.handleDirtyStateChange(false);
  rejectInitialFetch(new Error('offline'));
  await flushPromises();

  assert.equal(app.state.pendingRemoteVersion, 2);
  assert.deepEqual(app.apiCalls, [['mount-0', '/doc.md']]);

  app.dispatchWindowEvent('online');
  assert.deepEqual(app.apiCalls, [
    ['mount-0', '/doc.md'],
    ['mount-0', '/doc.md'],
  ]);
  resolveRetryFetch({ content: 'full-v2', version: 2, mtime: 0 });
  await flushPromises();

  assert.deepEqual(snapshotClient(app), {
    baseContent: 'full-v2',
    baseVersion: 2,
    editor: 'full-v2',
    fileVersion: 2,
    lastSavedContent: 'full-v2',
    originalContent: 'full-v2',
  });
  assert.equal(app.state.pendingRemoteVersion, null);
  assert.equal(app.consoleErrors.length, 1);
});

test('a failed clean pending-version catch-up retries once without looping', async () => {
  let rejectInitialFetch;
  let rejectRetryFetch;
  const initialFetch = new Promise((_resolve, reject) => {
    rejectInitialFetch = reject;
  });
  const retryFetch = new Promise((_resolve, reject) => {
    rejectRetryFetch = reject;
  });
  const app = loadSyncLayer({
    version: 1,
    content: 'local-dirty',
    baseContent: 'confirmed-v1',
    dirty: true,
    fullPromises: [initialFetch, retryFetch],
    manualTimers: true,
  });

  app.context.window.nasmdSync.handleRemoteEdit({
    type: 'remote_edit',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 2,
    changes: [{ type: 'replace', paraIdx: 0, content: 'event-v2' }],
  });
  app.state.dirty = false;
  app.editor.value = 'confirmed-v1';
  app.context.window.nasmdSync.handleDirtyStateChange(false);
  rejectInitialFetch(new Error('temporary server failure'));
  await flushPromises();

  assert.equal(app.state.pendingRemoteVersion, 2);
  assert.deepEqual(app.apiCalls, [['mount-0', '/doc.md']]);

  app.runTimers(1000);
  assert.deepEqual(app.apiCalls, [
    ['mount-0', '/doc.md'],
    ['mount-0', '/doc.md'],
  ]);
  rejectRetryFetch(new Error('retry also failed'));
  await flushPromises();
  app.runTimers(1000);

  assert.deepEqual(snapshotClient(app), {
    baseContent: 'confirmed-v1',
    baseVersion: 1,
    editor: 'confirmed-v1',
    fileVersion: 1,
    lastSavedContent: 'confirmed-v1',
    originalContent: 'confirmed-v1',
  });
  assert.deepEqual(app.apiCalls, [
    ['mount-0', '/doc.md'],
    ['mount-0', '/doc.md'],
  ]);
  assert.equal(app.state.pendingRemoteVersion, 2);
  assert.equal(app.consoleErrors.length, 2);
});

test('a rejected clean gap fetch retains its high-water and retries once successfully', async () => {
  let rejectGapFetch;
  let resolveRetryFetch;
  const gapFetch = new Promise((_resolve, reject) => {
    rejectGapFetch = reject;
  });
  const retryFetch = new Promise((resolve) => {
    resolveRetryFetch = resolve;
  });
  const app = loadSyncLayer({
    version: 1,
    content: 'confirmed-v1',
    fullPromises: [gapFetch, retryFetch],
    manualTimers: true,
  });

  app.context.window.nasmdSync.handleRemoteEdit({
    type: 'remote_edit',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 3,
    changes: [{ type: 'replace', paraIdx: 0, content: 'event-v3' }],
  });
  rejectGapFetch(new Error('temporary gap failure'));
  await flushPromises();

  assert.equal(app.state.pendingRemoteVersion, 3);
  assert.deepEqual(app.apiCalls, [['mount-0', '/doc.md']]);

  app.runTimers(1000);
  assert.deepEqual(app.apiCalls, [
    ['mount-0', '/doc.md'],
    ['mount-0', '/doc.md'],
  ]);

  resolveRetryFetch({ content: 'full-v3', version: 3, mtime: 0 });
  await flushPromises();
  app.runTimers(1000);

  assert.deepEqual(snapshotClient(app), {
    baseContent: 'full-v3',
    baseVersion: 3,
    editor: 'full-v3',
    fileVersion: 3,
    lastSavedContent: 'full-v3',
    originalContent: 'full-v3',
  });
  assert.equal(app.state.pendingRemoteVersion, null);
  assert.deepEqual(app.apiCalls, [
    ['mount-0', '/doc.md'],
    ['mount-0', '/doc.md'],
  ]);
  assert.equal(app.consoleErrors.length, 1);
});

test('a null clean gap fetch retries once and a failed retry does not loop', async () => {
  let rejectRetryFetch;
  const retryFetch = new Promise((_resolve, reject) => {
    rejectRetryFetch = reject;
  });
  const app = loadSyncLayer({
    version: 1,
    content: 'confirmed-v1',
    fullPromises: [Promise.resolve(null), retryFetch],
    manualTimers: true,
  });

  app.context.window.nasmdSync.handleRemoteEdit({
    type: 'remote_edit',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 3,
    changes: [{ type: 'replace', paraIdx: 0, content: 'event-v3' }],
  });
  await flushPromises();

  assert.equal(app.state.pendingRemoteVersion, 3);
  assert.deepEqual(app.apiCalls, [['mount-0', '/doc.md']]);

  app.runTimers(1000);
  assert.deepEqual(app.apiCalls, [
    ['mount-0', '/doc.md'],
    ['mount-0', '/doc.md'],
  ]);

  rejectRetryFetch(new Error('retry also failed'));
  await flushPromises();
  app.runTimers(1000);

  assert.deepEqual(snapshotClient(app), {
    baseContent: 'confirmed-v1',
    baseVersion: 1,
    editor: 'confirmed-v1',
    fileVersion: 1,
    lastSavedContent: 'confirmed-v1',
    originalContent: 'confirmed-v1',
  });
  assert.equal(app.state.pendingRemoteVersion, 3);
  assert.deepEqual(app.apiCalls, [
    ['mount-0', '/doc.md'],
    ['mount-0', '/doc.md'],
  ]);
  assert.equal(app.consoleErrors.length, 1);
});

test('a stale fulfilled catch-up response retries the pending high-water once', async () => {
  let resolveRetryFetch;
  const retryFetch = new Promise((resolve) => {
    resolveRetryFetch = resolve;
  });
  const app = loadSyncLayer({
    version: 1,
    content: 'local-dirty',
    baseContent: 'confirmed-v1',
    dirty: true,
    fullPromises: [Promise.resolve({ content: 'stale-v2', version: 2, mtime: 0 }), retryFetch],
    manualTimers: true,
  });

  app.context.window.nasmdSync.handleRemoteEdit({
    type: 'remote_edit',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 3,
    changes: [{ type: 'replace', paraIdx: 0, content: 'event-v3' }],
  });
  app.state.dirty = false;
  app.editor.value = 'confirmed-v1';
  app.context.window.nasmdSync.handleDirtyStateChange(false);
  await flushPromises();

  assert.deepEqual(app.apiCalls, [['mount-0', '/doc.md']]);
  assert.equal(app.state.pendingRemoteVersion, 3);
  assert.equal(app.state.baseVersion, 1);

  app.runTimers(1000);
  assert.deepEqual(app.apiCalls, [
    ['mount-0', '/doc.md'],
    ['mount-0', '/doc.md'],
  ]);
  resolveRetryFetch({ content: 'full-v3', version: 3, mtime: 0 });
  await flushPromises();

  assert.deepEqual(snapshotClient(app), {
    baseContent: 'full-v3',
    baseVersion: 3,
    editor: 'full-v3',
    fileVersion: 3,
    lastSavedContent: 'full-v3',
    originalContent: 'full-v3',
  });
  assert.equal(app.state.pendingRemoteVersion, null);
  assert.deepEqual(app.consoleErrors, []);
});

test('a gap fetch failing after the client becomes dirty catches up when clean again', async () => {
  let rejectGapFetch;
  let resolveCatchUpFetch;
  const gapFetch = new Promise((_resolve, reject) => {
    rejectGapFetch = reject;
  });
  const catchUpFetch = new Promise((resolve) => {
    resolveCatchUpFetch = resolve;
  });
  const app = loadSyncLayer({
    version: 1,
    content: 'confirmed-v1',
    fullPromises: [gapFetch, catchUpFetch],
  });

  app.context.window.nasmdSync.handleRemoteEdit({
    type: 'remote_edit',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 3,
    changes: [{ type: 'replace', paraIdx: 0, content: 'event-v3' }],
  });
  app.state.dirty = true;
  app.editor.value = 'local-dirty';
  rejectGapFetch(new Error('temporary failure'));
  await flushPromises();

  assert.equal(app.state.pendingRemoteVersion, 3);
  assert.deepEqual(app.apiCalls, [['mount-0', '/doc.md']]);

  app.state.dirty = false;
  app.editor.value = 'confirmed-v1';
  app.context.window.nasmdSync.handleDirtyStateChange(false);
  assert.deepEqual(app.apiCalls, [
    ['mount-0', '/doc.md'],
    ['mount-0', '/doc.md'],
  ]);

  resolveCatchUpFetch({ content: 'full-v3', version: 3, mtime: 0 });
  await flushPromises();

  assert.deepEqual(snapshotClient(app), {
    baseContent: 'full-v3',
    baseVersion: 3,
    editor: 'full-v3',
    fileVersion: 3,
    lastSavedContent: 'full-v3',
    originalContent: 'full-v3',
  });
  assert.equal(app.state.pendingRemoteVersion, null);
  assert.equal(app.consoleErrors.length, 1);
});

test('dirty version gaps do not fetch or change the confirmed baseline', async () => {
  const app = loadSyncLayer({
    version: 1,
    content: 'local-dirty',
    baseContent: 'confirmed-v1',
    dirty: true,
  });
  const before = snapshotClient(app);

  app.context.window.nasmdSync.handleRemoteEdit({
    type: 'remote_edit',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 3,
    changes: [{ type: 'replace', paraIdx: 0, content: 'remote-v3' }],
  });
  await flushPromises();

  assert.deepEqual(snapshotClient(app), before);
  assert.equal(app.state.pendingRemoteVersion, 3);
  assert.deepEqual(app.apiCalls, []);
  assert.deepEqual(app.consoleErrors, []);
});

test('a fetch resolving after the client becomes dirty leaves all content untouched', async () => {
  let resolveFetch;
  const fullPromise = new Promise((resolve) => {
    resolveFetch = resolve;
  });
  const app = loadSyncLayer({ version: 1, content: 'confirmed-v1', fullPromise });
  app.context.window.nasmdSync.handleExternalReload({
    type: 'external_reload',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 3,
    content: 'event-v3',
  });
  app.state.dirty = true;
  app.editor.value = 'local-dirty';
  const before = snapshotClient(app);

  resolveFetch({ content: 'full-v3', version: 3, mtime: 0 });
  await flushPromises();

  assert.deepEqual(snapshotClient(app), before);
  assert.equal(app.state.pendingRemoteVersion, 3);
  assert.deepEqual(app.consoleErrors, []);
});

test('an older fetch response preserves and catches up to a pending remote high-water', async () => {
  let resolveOlderFetch;
  let resolvePendingFetch;
  const olderFetch = new Promise((resolve) => {
    resolveOlderFetch = resolve;
  });
  const pendingFetch = new Promise((resolve) => {
    resolvePendingFetch = resolve;
  });
  const app = loadSyncLayer({
    version: 7,
    content: 'confirmed-v7',
    fullPromises: [olderFetch, pendingFetch],
  });

  app.context.window.nasmdSync.handleRemoteEdit({
    type: 'remote_edit',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 9,
    changes: [{ type: 'replace', paraIdx: 0, content: 'event-v9' }],
  });
  app.state.dirty = true;
  app.editor.value = 'local-dirty';
  app.context.window.nasmdSync.handleRemoteEdit({
    type: 'remote_edit',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 10,
    changes: [{ type: 'replace', paraIdx: 0, content: 'event-v10' }],
  });
  app.state.dirty = false;

  resolveOlderFetch({ content: 'full-v9', version: 9, mtime: 0 });
  await flushPromises();

  assert.deepEqual(snapshotClient(app), {
    baseContent: 'full-v9',
    baseVersion: 9,
    editor: 'full-v9',
    fileVersion: 9,
    lastSavedContent: 'full-v9',
    originalContent: 'full-v9',
  });
  assert.equal(app.state.pendingRemoteVersion, 10);
  assert.deepEqual(app.apiCalls, [
    ['mount-0', '/doc.md'],
    ['mount-0', '/doc.md'],
  ]);

  resolvePendingFetch({ content: 'full-v10', version: 10, mtime: 0 });
  await flushPromises();

  assert.deepEqual(snapshotClient(app), {
    baseContent: 'full-v10',
    baseVersion: 10,
    editor: 'full-v10',
    fileVersion: 10,
    lastSavedContent: 'full-v10',
    originalContent: 'full-v10',
  });
  assert.equal(app.state.pendingRemoteVersion, null);
  assert.deepEqual(app.consoleErrors, []);
});

test('a clean remote batch applies then adopts the higher pending snapshot', async () => {
  const app = loadSyncLayer({
    version: 1,
    content: 'transient-editor-value',
    baseContent: 'A\n\nB',
    fullResult: { content: 'full-v8', version: 8, mtime: 0 },
    manualTimers: true,
  });
  const appliedValues = [];
  app.editor.setValue = function (value) {
    appliedValues.push(value);
    this.value = value;
  };
  app.state.pendingRemoteVersion = 8;

  app.context.window.nasmdSync.handleRemoteEdit({
    type: 'remote_edit',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 2,
    changes: [{ type: 'insert', paraIdx: 0, content: 'X' }],
  });
  app.runTimers(300);
  await flushPromises();

  assert.deepEqual(appliedValues, ['X\n\nA\n\nB', 'full-v8']);
  assert.deepEqual(snapshotClient(app), {
    baseContent: 'full-v8',
    baseVersion: 8,
    editor: 'full-v8',
    fileVersion: 8,
    lastSavedContent: 'full-v8',
    originalContent: 'full-v8',
  });
  assert.equal(app.state.pendingRemoteVersion, null);
  assert.deepEqual(app.apiCalls, [['mount-0', '/doc.md']]);
});

test('a clean remote batch that becomes dirty before debounce preserves its baseline', async () => {
  const app = loadSyncLayer({ version: 1, content: 'confirmed-v1', manualTimers: true });

  app.context.window.nasmdSync.handleRemoteEdit({
    type: 'remote_edit',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 2,
    changes: [{ type: 'replace', paraIdx: 0, content: 'remote-v2' }],
  });
  app.state.dirty = true;
  app.editor.value = 'local-dirty';
  const before = snapshotClient(app);

  app.runTimers(300);

  assert.deepEqual(snapshotClient(app), before);
  assert.equal(app.state.pendingRemoteVersion, 2);
  assert.deepEqual(app.toasts, [['检测到远端更新，将在保存时自动合并', 'info']]);
});

test('a clean external event without content cannot advance only the version metadata', async () => {
  const app = loadSyncLayer({ version: 1, content: 'confirmed-v1' });
  const before = snapshotClient(app);

  app.context.window.nasmdSync.handleExternalReload({
    type: 'external_reload',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 2,
  });
  await flushPromises();

  assert.deepEqual(snapshotClient(app), before);
  assert.equal(app.state.pendingRemoteVersion, null);
});

test('an empty external reload clears a clean editor and advances its baseline', async () => {
  const app = loadSyncLayer({ version: 1, content: 'current-v1' });
  app.context.window.nasmdSync.handleExternalReload({
    type: 'external_reload',
    mountId: 'mount-0',
    path: '/doc.md',
    newVersion: 2,
    content: '',
  });
  await flushPromises();

  assert.deepEqual(snapshotClient(app), {
    baseContent: '',
    baseVersion: 2,
    editor: '',
    fileVersion: 2,
    lastSavedContent: '',
    originalContent: '',
  });
  assert.deepEqual(app.consoleErrors, []);
});
