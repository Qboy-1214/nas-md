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
  manualTimers = false,
} = {}) {
  const confirmedContent = baseContent === undefined ? content : baseContent;
  const state = {
    currentMountId: 'mount-0',
    currentPath: '/doc.md',
    baseVersion: version,
    baseContent: confirmedContent,
    fileVersions: { 'mount-0:/doc.md': version },
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
  let nextTimerId = 1;
  let currentTime = 10000;
  const documentBody = makeElement();
  const context = vm.createContext({
    API: {
      getFile(mountId, path) {
        apiCalls.push([mountId, path]);
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
  assert.equal(remote.state.pendingRemoteUpdate, true);
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
  assert.equal(external.state.pendingRemoteUpdate, true);
  assert.deepEqual(external.apiCalls, []);
  assert.deepEqual(external.consoleErrors, []);
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
  assert.equal(app.state.pendingRemoteUpdate, true);
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
  assert.equal(app.state.pendingRemoteUpdate, true);
  assert.deepEqual(app.consoleErrors, []);
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
