# Collaboration Correctness Repairs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate silent collaboration data loss, make offline and stale-version saves converge safely, restore trustworthy E2E coverage, and close the remaining Mermaid and quality-gate defects.

**Architecture:** Treat `baseVersion` and `baseContent` as one acknowledged snapshot. Dirty clients defer remote application; saves send the common ancestor and full submitted content so the server can perform a paragraph-level three-way merge without relying on volatile delta history. Browser-only replay uses the same paragraph coordinate contract, while native Mermaid fullscreen renders a temporary clone inside the active overlay so Vditor content remains untouched.

**Tech Stack:** Python 3, pytest, Ruff, Black, browser JavaScript, Vditor, Playwright, ESLint, Prettier.

---

## File Map

- Create `tests/e2e/helpers/admin.js`: shared admin mount and file-fixture operations with mandatory response assertions.
- Create `tests/fixtures/paragraph_split_cases.json`: one source of truth for Python and browser paragraph-boundary cases.
- Create `tests/e2e/collaboration-correctness.spec.js`: browser coverage for parser parity, dirty remote events, save replay, and offline recovery.
- Modify `nas_md/webserver/file_version_store.py`: canonical request validation and server-side three-way merge.
- Modify `nas_md/webserver/__init__.py`: accept `baseContent`, pass the full merge contract, and broadcast only applied writes.
- Modify `web/files.js`: add `baseContent` to the changes request.
- Modify `web/app.js`: parser parity, browser transform/rebase helpers, atomic save acknowledgement, and durable offline drafts.
- Modify `web/sync_layer.js`: defer all current-file remote events while dirty and update acknowledged state atomically while clean.
- Modify `web/mermaid_enhancer.js` and `web/app.css`: active-overlay native fullscreen and cleanup.
- Modify `tests/test_file_version_store.py`, `tests/test_paragraph_diff.py`, and `tests/test_webserver.py`: server and API regression coverage.
- Modify `tests/e2e/cursor-restore.spec.js`, `tests/e2e/poll-external-change.spec.js`, and `tests/e2e/refresh-from-disk.spec.js`: remove runtime false-green skips.
- Modify `tests/test_webserver_perf.py`: resolve the three Ruff `RUF059` failures.

### Task 1: Make E2E Setup Fail Honestly

**Files:**
- Create: `tests/e2e/helpers/admin.js`
- Modify: `tests/e2e/cursor-restore.spec.js`
- Modify: `tests/e2e/poll-external-change.spec.js`
- Modify: `tests/e2e/refresh-from-disk.spec.js`

- [x] **Step 1: Tighten one fixture to expose the current unauthorized setup**

In `refresh-from-disk.spec.js`, temporarily replace the nullable setup result and skip branch with an assertion:

```javascript
const putResp = await page.request.put(
  `/api/mounts/${mountInfo.id}/file?path=/${testFileName}`,
  { data: initialContent },
);
expect(putResp.ok(), `fixture PUT failed: ${putResp.status()}`).toBeTruthy();
return { mountInfo, testFileName };
```

- [x] **Step 2: Run the focused spec and observe RED**

Run: `npx playwright test tests/e2e/refresh-from-disk.spec.js`

Expected: FAIL during fixture setup because the request has neither an `/admin` Referer nor `X-Admin: 1`.

- [x] **Step 3: Add the shared admin helper**

Create `tests/e2e/helpers/admin.js` with this interface:

```javascript
import { expect } from '@playwright/test';

const adminOptions = { headers: { 'X-Admin': '1' } };

export async function getWritableAdminMount(page) {
  await page.goto('/admin');
  await page.waitForFunction(() => window.state?.mounts?.length > 0);
  const mount = await page.evaluate(() => {
    const item = window.state.mounts.find((candidate) => !candidate.readonly && !candidate._local);
    return item ? { id: item.id, name: item.name } : null;
  });
  expect(mount, 'configured writable server mount').not.toBeNull();
  return mount;
}

export async function putAdminFile(page, mountId, path, content) {
  const response = await page.request.put(
    `/api/mounts/${mountId}/file?path=${encodeURIComponent(path)}`,
    { ...adminOptions, data: content },
  );
  expect(response.ok(), `PUT ${path}: ${response.status()}`).toBeTruthy();
  return response;
}

export async function deleteAdminFile(page, mountId, path) {
  const response = await page.request.delete(
    `/api/mounts/${mountId}/file?path=${encodeURIComponent(path)}`,
    adminOptions,
  );
  expect(response.ok(), `DELETE ${path}: ${response.status()}`).toBeTruthy();
}
```

Import these helpers in all three specs. Replace mount-null, missing-file, missing-button, and failed-auto-restore `test.skip()` branches with `expect` assertions. Use `putAdminFile` and `deleteAdminFile` for every private-mount write and cleanup.

- [x] **Step 4: Run the repaired fixture specs**

Run: `npx playwright test tests/e2e/cursor-restore.spec.js tests/e2e/poll-external-change.spec.js tests/e2e/refresh-from-disk.spec.js`

Expected: all tests PASS with no runtime skips.

- [x] **Step 5: Commit**

```bash
git add tests/e2e/helpers/admin.js tests/e2e/cursor-restore.spec.js tests/e2e/poll-external-change.spec.js tests/e2e/refresh-from-disk.spec.js
git commit -m "test: make admin e2e setup failures visible"
```

### Task 2: Share Paragraph Coordinates and Browser Rebase Primitives

**Files:**
- Create: `tests/fixtures/paragraph_split_cases.json`
- Create: `tests/e2e/collaboration-correctness.spec.js`
- Modify: `tests/test_paragraph_diff.py`
- Modify: `web/app.js`

- [x] **Step 1: Add shared frontmatter fixtures**

Create `tests/fixtures/paragraph_split_cases.json`:

```json
[
  {
    "name": "frontmatter-without-blank-line",
    "text": "---\ntitle: Doc\n---\nBody",
    "paragraphs": ["---\ntitle: Doc\n---", "Body"]
  },
  {
    "name": "frontmatter-dot-close-with-blank-line",
    "text": "---\ntitle: Doc\n...\n\nBody",
    "paragraphs": ["---\ntitle: Doc\n...", "Body"]
  },
  {
    "name": "frontmatter-only",
    "text": "---\ntitle: Doc\n---",
    "paragraphs": ["---\ntitle: Doc\n---"]
  },
  {
    "name": "fence-and-math-blank-lines",
    "text": "```js\na();\n\nb();\n```\n\n$$\na\n\nb\n$$",
    "paragraphs": ["```js\na();\n\nb();\n```", "$$\na\n\nb\n$$"]
  }
]
```

Add a parametrized pytest that loads this file and asserts `split_paragraphs(case["text"]) == case["paragraphs"]`. Add a Playwright test that reads the same JSON with `readFileSync`, opens `/admin`, and evaluates `window.nasmdDiff.splitParagraphs` for every case.

- [x] **Step 2: Run both contracts and observe browser RED**

Run: `python -m pytest tests/test_paragraph_diff.py -q`

Expected: PASS; the backend implementation is the contract source.

Run: `npx playwright test tests/e2e/collaboration-correctness.spec.js -g "paragraph contract"`

Expected: FAIL for `frontmatter-without-blank-line`; the browser currently joins `Body` into the frontmatter paragraph.

- [x] **Step 3: Align the browser splitter with the backend rule**

Replace the boolean-only frontmatter loop in `splitParagraphsWithDelims` with explicit extraction of a valid closing marker and following delimiter:

```javascript
if (lines.length > 0 && lines[0].trim() === '---') {
  let closingIdx = -1;
  for (let idx = 1; idx < Math.min(50, lines.length); idx++) {
    const marker = lines[idx].trim();
    if (marker === '---' || marker === '...') {
      closingIdx = idx;
      break;
    }
    if (marker.startsWith('#') || marker.startsWith('```')) break;
  }
  if (closingIdx > 0) {
    paragraphs.push(lines.slice(0, closingIdx + 1).join('\n'));
    let postIdx = closingIdx + 1;
    let blankCount = 0;
    while (postIdx < lines.length && lines[postIdx].trim() === '') {
      blankCount++;
      postIdx++;
    }
    delimiters.push(blankCount > 0 ? '\n'.repeat(blankCount + 1) : '\n\n');
    lines = lines.slice(postIdx);
  }
}
```

Remove the old `inFrontmatter` state and branch.

- [x] **Step 4: Add RED tests for browser index transformation and rebasing**

In `collaboration-correctness.spec.js`, assert the new public helpers preserve edits across an earlier remote insertion:

```javascript
const result = await page.evaluate(() => {
  const base = 'A\n\nB\n\nC';
  const local = 'A\n\nB\n\nC-local';
  const remote = 'HEADER\n\nA\n\nB\n\nC';
  return window.nasmdDiff.rebaseContent(base, local, remote);
});
expect(result).toBe('HEADER\n\nA\n\nB\n\nC-local');
```

Run: `npx playwright test tests/e2e/collaboration-correctness.spec.js -g "rebase"`

Expected: FAIL because `rebaseContent` is not defined.

- [x] **Step 5: Implement and expose transform/rebase helpers**

Port the backend position-map algorithm into `transformParagraphChanges(incoming, accumulated, baseCount)`. Implement the public composition function exactly as follows:

```javascript
function rebaseContent(baseContent, localContent, remoteContent) {
  const localChanges = computeParagraphDiff(baseContent, localContent);
  const remoteChanges = computeParagraphDiff(baseContent, remoteContent);
  const transformed = transformParagraphChanges(
    localChanges,
    remoteChanges,
    splitParagraphs(baseContent).length,
  );
  return applyChangesLocally(remoteContent, transformed);
}

window.nasmdDiff = {
  splitParagraphs,
  splitParagraphsWithDelims,
  applyChangesLocally,
  computeParagraphDiff,
  transformParagraphChanges,
  rebaseContent,
};
```

The transform must map inserts, deletes, and replacements exactly like `transform_changes`: earlier inserts increase mapped positions, earlier deletes decrease later positions, replacing a remotely deleted paragraph becomes an insert, and deleting an already deleted paragraph is omitted.

- [x] **Step 6: Run the focused contracts**

Run: `python -m pytest tests/test_paragraph_diff.py -q`

Run: `npx playwright test tests/e2e/collaboration-correctness.spec.js -g "paragraph contract|rebase"`

Expected: both commands PASS.

- [x] **Step 7: Commit**

```bash
git add tests/fixtures/paragraph_split_cases.json tests/test_paragraph_diff.py tests/e2e/collaboration-correctness.spec.js web/app.js
git commit -m "fix: align paragraph coordinates across clients"
```

### Task 3: Replace Volatile Stale-Version Merging with Three-Way Merge

**Files:**
- Modify: `tests/test_file_version_store.py`
- Modify: `tests/test_webserver.py`
- Modify: `nas_md/webserver/file_version_store.py`
- Modify: `nas_md/webserver/__init__.py`
- Modify: `web/files.js`

- [x] **Step 1: Add failing restart, validation, and ahead-version tests**

Add tests using the common ancestor explicitly:

```python
def test_restart_stale_client_three_way_merges(tmp_path, test_file):
    key = "mount-0:/test.md"
    base = "A\n\nB\n\nC"
    test_file_path = str(test_file)
    first = FileVersionStore(storage_dir=str(tmp_path / ".version_history"))
    first.init_file(key, test_file_path, base)
    first.apply_changes(
        key,
        test_file_path,
        0,
        [{"type": "replace", "paraIdx": 0, "content": "A-remote"}],
        "remote",
        "Remote",
        "#f00",
        base_content=base,
        client_content="A-remote\n\nB\n\nC",
    )

    restarted = FileVersionStore(storage_dir=str(tmp_path / ".version_history"))
    restarted.init_file(key, test_file_path, "A-remote\n\nB\n\nC")
    result = restarted.apply_changes(
        key,
        test_file_path,
        0,
        [{"type": "replace", "paraIdx": 2, "content": "C-local"}],
        "local",
        "Local",
        "#0f0",
        base_content=base,
        client_content="A\n\nB\n\nC-local",
    )
    assert result["content"] == "A-remote\n\nB\n\nC-local"
```

Also add:

- `test_ahead_version_returns_resync_without_writing`
- `test_missing_stale_base_content_returns_resync_without_writing`
- `test_declared_changes_must_reconstruct_client_content`

Each rejection must assert `applied is False`, `resyncRequired is True`, the current `newVersion/content`, and unchanged disk bytes. Update existing stale-merge tests to pass both `base_content` and `client_content`. Change the existing bogus-change/client-content test to expect resync rather than silent acceptance.

- [x] **Step 2: Run the store tests and observe RED**

Run: `python -m pytest tests/test_file_version_store.py -q`

Expected: FAIL because `apply_changes` has no `base_content` argument and restart merging still trusts missing deltas.

- [x] **Step 3: Implement canonical validation and three-way merge**

Add `base_content: str | None = None` after `client_content` in `FileVersionStore.apply_changes`. Add a private response helper:

```python
def _resync_result(self, fv: _FileVersion) -> dict:
    return {
        "applied": False,
        "merged": False,
        "resyncRequired": True,
        "newVersion": fv.version,
        "content": fv.content,
    }
```

Inside the lock, use this decision sequence:

```python
if base_version < 0 or base_version > fv.version:
    return self._resync_result(fv)

submitted_base = base_content
if submitted_base is None and base_version == fv.version:
    submitted_base = fv.content
if submitted_base is None:
    return self._resync_result(fv)

submitted_content = client_content
if submitted_content is None:
    submitted_content = apply_diff(submitted_base, changes)
elif apply_diff(submitted_base, changes) != submitted_content:
    return self._resync_result(fv)

canonical_changes = compute_diff(submitted_base, submitted_content)
if base_version == fv.version:
    if submitted_base != fv.content:
        return self._resync_result(fv)
    changes_to_apply = canonical_changes
else:
    remote_changes = compute_diff(submitted_base, fv.content)
    changes_to_apply = transform_changes(
        canonical_changes,
        remote_changes,
        len(split_paragraphs(submitted_base)),
    )

new_content = apply_diff(fv.content, changes_to_apply)
```

If `canonical_changes` is empty, return `applied: false` without increasing the version. Keep existing disk write, history record, pruning, and response fields for actual writes.

- [x] **Step 4: Pass `baseContent` through the HTTP and browser API**

In `_handle_submit_changes`, parse `base_content = payload.get("baseContent")` and pass `base_content=base_content` to the store. Extend `API.submitChanges` with a final `baseContent` argument and add it to the JSON payload when defined:

```javascript
if (baseContent !== undefined && baseContent !== null) {
  payload.baseContent = baseContent;
}
```

Add a webserver integration test that POSTs stale `baseVersion`, `baseContent`, `content`, and `changes`, then asserts the response and disk contain both clients' different-paragraph edits.

- [x] **Step 5: Run server and API tests**

Run: `python -m pytest tests/test_file_version_store.py tests/test_webserver.py -q`

Expected: all tests PASS.

- [x] **Step 6: Commit**

```bash
git add nas_md/webserver/file_version_store.py nas_md/webserver/__init__.py web/files.js tests/test_file_version_store.py tests/test_webserver.py
git commit -m "fix: three-way merge stale collaboration saves"
```

### Task 4: Preserve the Acknowledged Baseline While Dirty

**Files:**
- Modify: `tests/e2e/collaboration-correctness.spec.js`
- Modify: `web/sync_layer.js`
- Modify: `web/app.js`

- [x] **Step 1: Add failing dirty-event tests**

Open a fixture file, disable auto-save, set a local editor value, call `markDirty()`, and invoke both exported handlers. Assert the entire acknowledged tuple remains unchanged:

```javascript
const before = await page.evaluate(() => ({
  editor: window._vditor.getValue(),
  baseVersion: state.baseVersion,
  baseContent: state.baseContent,
  originalContent: window._originalContent,
}));

await page.evaluate(() => {
  window.nasmdSync.handleRemoteEdit({
    mountId: state.currentMountId,
    path: state.currentPath,
    newVersion: state.baseVersion + 1,
    authorId: 'remote',
    authorName: 'Remote',
    authorColor: '#f00',
    changes: [{ type: 'replace', paraIdx: 0, content: 'REMOTE' }],
  });
});

await page.waitForTimeout(400);
const after = await page.evaluate(() => ({
  editor: window._vditor.getValue(),
  baseVersion: state.baseVersion,
  baseContent: state.baseContent,
  originalContent: window._originalContent,
  pendingRemoteVersion: state.pendingRemoteVersion,
}));
expect(after.editor).toBe(before.editor);
expect(after.baseVersion).toBe(before.baseVersion);
expect(after.baseContent).toBe(before.baseContent);
expect(after.originalContent).toBe(before.originalContent);
expect(after.pendingRemoteVersion).toBe(before.baseVersion + 1);
```

Repeat with `handleExternalReload`. Add a clean-state test asserting editor, version, base, and original all advance together.

- [x] **Step 2: Run the focused tests and observe RED**

Run: `npx playwright test tests/e2e/collaboration-correctness.spec.js -g "dirty remote|clean remote"`

Expected: dirty tests FAIL because handlers currently advance the version or replace the acknowledged content.

- [x] **Step 3: Add one dirty deferral gate**

Add `state.pendingRemoteVersion = null` to state initialization and reset it on file load. In `sync_layer.js`, centralize the gate:

```javascript
function deferWhileDirty(data) {
  if (!window.state || !state.dirty) return false;
  state.pendingRemoteVersion = Math.max(
    state.pendingRemoteVersion || 0,
    data.newVersion || 0,
  );
  window.showToast('检测到远端更新，将在保存时自动合并', 'info');
  return true;
}
```

For current-file `remote_edit`, call this before version checks or batching. For `external_reload`, call it before updating version metadata. In `fetchFullContent`, test dirty again after the request resolves and defer without changing any baseline field.

- [x] **Step 4: Make clean batching atomic**

Include `newVersion`, `mountId`, and `path` in queued batch items. `applyBatchRemoteChanges` must:

1. abort through the dirty gate if the user edited while the debounce timer was running;
2. apply changes to `state.baseContent`, not arbitrary current editor content;
3. call `setValue` once;
4. update `baseContent`, `baseVersion`, `fileVersions`, and `_originalContent` together;
5. clear `pendingRemoteVersion` only after successful application.

- [x] **Step 5: Run collaboration sync tests**

Run: `npx playwright test tests/e2e/collaboration-correctness.spec.js -g "dirty remote|clean remote"`

Expected: all focused tests PASS.

- [x] **Step 6: Commit**

```bash
git add web/app.js web/sync_layer.js tests/e2e/collaboration-correctness.spec.js
git commit -m "fix: keep collaboration baselines atomic"
```

### Task 5: Reconcile Save Responses and Offline Drafts

**Files:**
- Modify: `tests/e2e/collaboration-correctness.spec.js`
- Modify: `web/app.js`

- [x] **Step 1: Add failing offline recovery coverage**

Use the admin helper to open a server file. Disable auto-save, edit the document, set the browser context offline, and invoke `saveFile({ silent: true })`. Assert `state.dirty` remains true and the draft exists. Restore online and assert the API eventually returns the edited content, the draft disappears, and `state.dirty` becomes false.

Run: `npx playwright test tests/e2e/collaboration-correctness.spec.js -g "offline draft"`

Expected: FAIL because offline save currently calls `markClean()` and reconnect skips the upload.

- [x] **Step 2: Keep offline saves dirty and persist their baseline**

Change the draft record to retain merge context while accepting old records:

```javascript
function saveToLocalStorage(path, content) {
  const data = {
    content,
    mountId: state.currentMountId,
    baseVersion: state.baseVersion,
    baseContent: state.baseContent,
    savedAt: Date.now(),
  };
  localStorage.setItem('nasmd_draft_' + path, JSON.stringify(data));
}
```

Remove `markClean()` from the offline branch. Keep the dirty button state and let the existing `online` listener call `syncOfflineDrafts`, which now sees `state.dirty` and invokes `saveFile({ silent: true })`.

- [x] **Step 3: Add failing stale-save and in-flight-input coverage**

Create a file with three paragraphs. Open it, disable auto-save, edit paragraph three locally, then perform an admin PUT that changes paragraph one. Assert the client baseline remains old. Trigger save and assert disk content contains both edits.

For the in-flight case, delay the `/changes` response with `page.route`, call save, edit another paragraph before releasing the response, and assert the editor contains the server canonical result plus the post-submit edit while `state.dirty` remains true.

Run: `npx playwright test tests/e2e/collaboration-correctness.spec.js -g "stale save|in-flight"`

Expected: FAIL because `baseContent` is not sent, the canonical response is not displayed, and post-submit input is not rebased.

- [x] **Step 4: Send the complete merge contract and handle resync**

Pass `baseContent` as the final `API.submitChanges` argument. Capture `submittedContent`, `submittedBaseContent`, and `submittedBaseVersion` before awaiting.

For `{resyncRequired: true}`, preserve the live editor, rebase it onto `resp.content`, atomically set the returned baseline, set the rebased editor value, persist the draft, and remain dirty:

```javascript
const rebased = window.nasmdDiff.rebaseContent(
  submittedBaseContent,
  window._vditor.getValue(),
  resp.content,
);
state.baseVersion = resp.newVersion;
state.baseContent = resp.content;
window._originalContent = resp.content;
window._vditor.setValue(rebased);
markDirty();
saveToLocalStorage(state.currentPath, rebased);
return;
```

- [x] **Step 5: Rebase input typed during a successful save**

After an applied response, atomically adopt `resp.newVersion/resp.content`. If the live editor still equals `submittedContent`, set it to `resp.content`, mark clean, and clear the draft. Otherwise:

```javascript
const liveContent = window._vditor.getValue();
const rebasedLiveContent = window.nasmdDiff.rebaseContent(
  submittedContent,
  liveContent,
  resp.content,
);
window._vditor.setValue(rebasedLiveContent);
markDirty();
saveToLocalStorage(state.currentPath, rebasedLiveContent);
```

Clear `state.pendingRemoteVersion` when the response baseline is adopted. Keep the next auto-save scheduling in `finally`.

- [x] **Step 6: Run all collaboration browser tests**

Run: `npx playwright test tests/e2e/collaboration-correctness.spec.js`

Expected: parser, rebase, dirty remote, clean remote, stale save, in-flight input, and offline draft tests all PASS.

- [x] **Step 7: Commit**

```bash
git add web/app.js tests/e2e/collaboration-correctness.spec.js
git commit -m "fix: reconcile offline and concurrent saves"
```

### Task 6: Make Native Mermaid Fullscreen Self-Contained

**Files:**
- Modify: `tests/e2e/mermaid-fullscreen.spec.js`
- Modify: `web/mermaid_enhancer.js`
- Modify: `web/app.css`

- [x] **Step 1: Replace the native fullscreen stub with target assertions**

Stub `requestFullscreen` on the active overlay, record its receiver, and expose a fake fullscreen element. Assert the requested element is `.mme-overlay-item` and contains a visible `.mme-fullscreen-chart svg`. Add a second test that removes the source Mermaid element, waits for the tracking loop, and asserts `document.exitFullscreen` was called before overlay state disappears.

Run: `npx playwright test tests/e2e/mermaid-fullscreen.spec.js -g "native fullscreen|source removal"`

Expected: FAIL because the document root is currently requested and source removal clears state without explicitly exiting browser fullscreen.

- [x] **Step 2: Add a temporary native visual instance**

Extend each block state with `fullscreenChartEl: null`. Add these helpers:

```javascript
function createNativeFullscreenChart(state) {
  var sourceSvg = state.targetEl && state.targetEl.querySelector('svg');
  if (!sourceSvg) return null;
  var chart = document.createElement('div');
  chart.className = 'mme-fullscreen-chart';
  chart.appendChild(sourceSvg.cloneNode(true));
  chart._mmeSvg = chart.querySelector('svg');
  state.uiContainer.appendChild(chart);
  state.fullscreenChartEl = chart;
  return chart;
}

function activeChartElement(state) {
  return state.fullscreenChartEl || state.targetEl;
}

function removeNativeFullscreenChart(state) {
  if (state.fullscreenChartEl) state.fullscreenChartEl.remove();
  state.fullscreenChartEl = null;
}
```

Create and bind drag/pan on this chart before calling `state.uiContainer.requestFullscreen()`. If the API rejects, remove the clone before entering application fullscreen. Route zoom, theme, mode, and downloads through `activeChartElement(state)` while native fullscreen is active.

- [x] **Step 3: Make native cleanup asynchronous and ordered**

When the tracking loop finds a missing source in native mode, call `exitFullscreen(blockId)` and remove the block only in its `finally` continuation. `clearFullscreenState` must remove the temporary chart after restoring the pre-fullscreen state. Keep `fullscreenchange` idempotent so an API-generated event cannot clear a newer fullscreen session.

- [x] **Step 4: Style the fullscreen-owned chart**

Add focused CSS:

```css
.mme-overlay-item:fullscreen {
  width: 100vw;
  height: 100vh;
  background: var(--c-canvas, #fff);
}

.mme-fullscreen-chart {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  pointer-events: auto;
}

.mme-fullscreen-chart svg {
  flex: 0 0 auto;
  max-width: none;
}
```

- [x] **Step 5: Run the entire Mermaid spec**

Run: `npx playwright test tests/e2e/mermaid-fullscreen.spec.js`

Expected: all Mermaid fullscreen tests PASS, including fallback, undo/redo, zoom, native target, and source-removal cleanup.

- [x] **Step 6: Commit**

```bash
git add web/mermaid_enhancer.js web/app.css tests/e2e/mermaid-fullscreen.spec.js
git commit -m "fix: scope native Mermaid fullscreen to its overlay"
```

### Task 7: Close Static Analysis and Formatting Failures

**Files:**
- Modify: `tests/test_webserver_perf.py`
- Modify: `web/mermaid_enhancer.js`
- Modify: `web/app.css`
- Modify any JavaScript file changed by Tasks 1-6 only when reported by ESLint or Prettier

- [x] **Step 1: Confirm the narrow quality failures**

Run: `python -m ruff check nas_md tests`

Expected before repair: three `RUF059` failures at `tests/test_webserver_perf.py:151`, `:155`, and `:159`.

Run: `npx eslint web/ --rule "prettier/prettier: off"`

Expected before repair: warnings for `_trackingTimer` and the unused `uiContainer` parameter in `web/mermaid_enhancer.js`.

- [x] **Step 2: Fix semantic warnings without suppression**

Rename the three unused unpacked results from `data` to `_data`. Remove `_trackingTimer` and call `requestAnimationFrame(loop)` without assigning the return value. Remove the unused `uiContainer` parameter from `bindEvents` and its call site.

- [x] **Step 3: Format only the touched frontend files**

Run: `npx prettier --write web/app.js web/files.js web/sync_layer.js web/mermaid_enhancer.js web/app.css tests/e2e/helpers/admin.js tests/e2e/collaboration-correctness.spec.js tests/e2e/cursor-restore.spec.js tests/e2e/poll-external-change.spec.js tests/e2e/refresh-from-disk.spec.js tests/e2e/mermaid-fullscreen.spec.js`

Expected: files are rewritten to the repository's configured LF and style rules; no unrelated frontend file changes.

- [x] **Step 4: Run focused quality gates**

Run: `python -m ruff check nas_md tests`

Run: `python -m black --check nas_md tests`

Run: `npm run lint`

Run: `npm run format:check`

Run: `git diff --check`

Expected: every command exits 0 with no warnings or whitespace errors.

- [x] **Step 5: Commit**

```bash
git add tests/test_webserver_perf.py web/app.js web/files.js web/sync_layer.js web/mermaid_enhancer.js web/app.css tests/e2e/helpers/admin.js tests/e2e/collaboration-correctness.spec.js tests/e2e/cursor-restore.spec.js tests/e2e/poll-external-change.spec.js tests/e2e/refresh-from-disk.spec.js tests/e2e/mermaid-fullscreen.spec.js
git commit -m "chore: restore repository quality gates"
```

Before committing, inspect `git diff --stat` and unstage any file not named in this plan.

### Task 8: Run Full Regression Verification

**Files:**
- No production edits expected

- [x] **Step 1: Run all Python tests**

Run: `python -m pytest -q`

Expected: all tests PASS; the previous baseline was 638 passing tests and the total increases by the new regression tests.

- [x] **Step 2: Run all Python quality gates**

Run: `python -m ruff check nas_md tests`

Run: `python -m black --check nas_md tests`

Expected: both commands exit 0.

- [x] **Step 3: Run all frontend quality gates**

Run: `npm run lint`

Run: `npm run format:check`

Expected: both commands exit 0 with no ESLint warnings and no Prettier violations.

- [x] **Step 4: Run all browser tests**

Run: `npx playwright test`

Expected: all required tests PASS and the cursor, external-change, refresh, collaboration, and Mermaid flows have zero runtime setup skips.

- [x] **Step 5: Audit the final repository state**

Run: `git diff --check`

Run: `git status --short`

Run: `git log --oneline -12`

Expected: no whitespace errors, no unexpected generated files, and the task commits appear in the planned order.

- [x] **Step 6: Stop on any verification regression**

If a command fails, return to the task that owns the failing behavior, add a focused regression test there, and repeat that task's RED-GREEN cycle before rerunning Task 8. Do not create a catch-all verification commit.
