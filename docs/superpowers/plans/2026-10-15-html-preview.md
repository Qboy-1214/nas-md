# HTML Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add isolated, read-only previews for `.html` and `.htm` files in server and browser-local mounts, including relative CSS, image, and JavaScript resources.

**Architecture:** Extend the existing mount tree metadata so both Markdown and HTML files keep their parent directories visible. Add a mount-scoped raw preview resource route for server files; use a dedicated browser preview module to resolve resources for server and local mounts and render the document inside a sandboxed iframe. Keep `openFile` as the navigation entry point and route Markdown through the current Vditor path unchanged.

**Tech Stack:** Python standard-library HTTP server, vanilla JavaScript, HTML iframe sandbox, pytest, Playwright.

---

## File Map

- `nas_md/webserver/__init__.py` — tree metadata, safe preview-resource route, MIME and visibility enforcement.
- `web/app.js` — supported-file filtering, both local tree builders, open-file dispatch, and editor-only controls.
- `web/files.js` — construct mount-scoped server preview resource URLs.
- `web/html_preview.js` — isolated preview lifecycle, local resource resolution, and object-URL cleanup.
- `web/index.html` — iframe preview element and script inclusion.
- `web/app.css` — preview sizing and loading/error presentation.
- `tests/test_webserver.py` — server tree and preview-resource route coverage.
- `tests/e2e/app.spec.js` — browser behavior for file discovery, preview, isolation, and Markdown switching.

## Task 1: Expose HTML files in server mount trees and serve safe preview resources

**Files:**
- Modify: `nas_md/webserver/__init__.py`
- Test: `tests/test_webserver.py`

- [ ] **Step 1: Add failing tests for recursive HTML discovery and mount-scoped resource reads**

Add a test that creates `guide/index.html`, `guide/style.css`, and `guide/img/pixel.png` under the fixture mount. Request the recursive tree and assert `guide/index.html` is present, the containing directory has `hasHtml: true`, and the CSS and image files are not listed as preview documents. Request the proposed preview resource route for `guide/index.html` and `guide/style.css`; assert status `200`, HTML MIME `text/html`, CSS MIME `text/css`, and exact body bytes. Add a traversal request that attempts `../outside.html` and assert `403` or `404` without returning the outside file.

- [ ] **Step 2: Run the focused server tests and confirm they fail**

Run: `pytest tests/test_webserver.py -k "html_tree or preview_resource" -q`
Expected: FAIL because tree metadata and the preview resource route are not implemented.

- [ ] **Step 3: Add separate HTML subtree metadata without changing `hasMd` meaning**

Extend `DirEntry` with `has_html`, serialize it as `hasHtml`, set it for `.html` and `.htm` files case-insensitively, and propagate it from descendants in `MountManager.build_tree`. Keep `.md` metadata and all existing fields unchanged.

Add a GET route under `/api/mounts/{mount_id}/preview/{relative_path}` before the generic unknown-route branch. Resolve the decoded relative path with the existing mount `_safe_path`, check that the mount is visible to the current session, read bytes, and respond with `_content_type`, content length, and `X-Content-Type-Options: nosniff`. Reject directory targets and traversal. Do not route this through the write/version-history flow.

- [ ] **Step 4: Re-run the focused server tests**

Run: `pytest tests/test_webserver.py -k "html_tree or preview_resource" -q`
Expected: PASS for tree metadata, HTML/CSS MIME, binary response, visibility, missing file, and traversal cases.

- [ ] **Step 5: Commit the backend slice**

```bash
git add nas_md/webserver/__init__.py tests/test_webserver.py
git commit -m "feat: expose safe HTML preview resources"
```

## Task 2: Include HTML files in server and local file trees

**Files:**
- Modify: `web/app.js`
- Test: `tests/e2e/app.spec.js`

- [ ] **Step 1: Add browser tests for HTML extensions and parent directories**

Use `page.route` to provide a recursive tree containing `docs/page.HTML`, `docs/child/page.htm`, and an unrelated `.txt` file. Assert both HTML files render as `.tree-file`, `.txt` stays hidden, and parent directories remain visible. Add coverage for the webkitdirectory fallback by dispatching a `change` event with a `DataTransfer` containing `webkitRelativePath` values ending in `.html` and `.htm`.

- [ ] **Step 2: Run the focused browser test and confirm it fails**

Run: `npx playwright test tests/e2e/app.spec.js -g "HTML 文件显示"`
Expected: FAIL because the current filters accept only `.md`.

- [ ] **Step 3: Centralize displayable-file checks and propagate both subtree flags**

In `web/app.js`, add small helpers equivalent to:

```js
function isHtmlFile(path) {
  return /\.html?$/i.test(path);
}

function isDisplayableFile(path) {
  return path.toLowerCase().endsWith('.md') || isHtmlFile(path);
}
```

Use them in builtin sidebar rendering, `readLocalDir`, `renderEntries`, and `onDirPicked`. Set both `hasMd` and `hasHtml` on file entries and propagate both flags through local directory nodes. Show directories when they contain either supported type, are empty, or contain an empty directory. Keep hidden-file filtering and existing sort order.

- [ ] **Step 4: Re-run the browser tree test**

Run: `npx playwright test tests/e2e/app.spec.js -g "HTML 文件显示"`
Expected: PASS for `.html`, `.htm`, mixed-case extensions, nested parents, and hidden unrelated files.

- [ ] **Step 5: Commit the file-discovery slice**

```bash
git add web/app.js tests/e2e/app.spec.js
git commit -m "feat: show HTML files in mount trees"
```

## Task 3: Build the isolated preview and relative-resource loader

**Files:**
- Create: `web/html_preview.js`
- Modify: `web/files.js`
- Test: `tests/e2e/app.spec.js`

- [ ] **Step 1: Add failing tests for resource loading and sandbox restrictions**

Add an E2E test that opens a preview document containing a heading, a relative stylesheet, a relative image, and a relative script that sets a marker in the iframe document. Assert all resources load and the heading is visible. Assert the iframe has `sandbox="allow-scripts"` without `allow-same-origin`, `allow-top-navigation`, or `allow-popups`; assert a script in the iframe cannot read a sentinel placed on the parent window.

- [ ] **Step 2: Run the focused E2E case and confirm it fails**

Run: `npx playwright test tests/e2e/app.spec.js -g "HTML 预览隔离并加载相对资源"`
Expected: FAIL because no preview module or iframe exists.

- [ ] **Step 3: Implement one preview lifecycle API**

Create `window.nasmdHtmlPreview` with `show({ mount, path, content })` and `clear()` methods. `show` creates/uses the dedicated sandboxed iframe, reports main-document read errors in the host UI, and loads the document. `clear` removes the loaded document and revokes every object URL allocated by the current preview before the next file opens.

For server mounts, add `API.previewResourceUrl(mountId, path)` in `web/files.js` and load the HTML from the mount-scoped raw preview route so normal URL-relative resolution works. For File System Access mounts, resolve relative paths from the selected mount handle, create object URLs with the file MIME types, rewrite static document resource references and CSS `url(...)`/`@import` references to those URLs, and revoke them on clear. Normalize and validate every resolved path before reading; reject paths escaping the mount root. Keep absolute external URLs unchanged.

- [ ] **Step 4: Re-run the focused E2E case**

Run: `npx playwright test tests/e2e/app.spec.js -g "HTML 预览隔离并加载相对资源"`
Expected: PASS for server and local mount resource loading and iframe isolation.

- [ ] **Step 5: Commit the preview module**

```bash
git add web/html_preview.js web/files.js tests/e2e/app.spec.js
git commit -m "feat: render HTML in an isolated preview"
```

## Task 4: Integrate HTML preview with file navigation and app controls

**Files:**
- Modify: `web/app.js`
- Modify: `web/index.html`
- Modify: `web/app.css`
- Test: `tests/e2e/app.spec.js`

- [ ] **Step 1: Add failing navigation and Markdown-regression tests**

Add tests that click an HTML tree entry and assert the preview is visible while `#vditor` and Markdown-only controls are hidden. Then open a Markdown entry and assert Vditor is visible and the preview is empty. Add a test for switching away from HTML to another HTML file and assert old object URLs/document content are cleared. For a modified Markdown file with autosave disabled, assert the existing save-before-switch prompt still runs.

- [ ] **Step 2: Run the focused navigation tests and confirm they fail**

Run: `npx playwright test tests/e2e/app.spec.js -g "HTML 与 Markdown 文件切换"`
Expected: FAIL because `openFile` always initializes Vditor.

- [ ] **Step 3: Add the preview host and branch in `openFile`**

Add an iframe host in `#editor-container` alongside `#vditor`. Include `html_preview.js` after `files.js`. In `openFile`, keep existing file loading, recent-file recording, dirty Markdown handling, and breadcrumbs; branch on the HTML extension after reading. For HTML, destroy Vditor, clear the prior preview, show the iframe, hide editor modes, save controls, PDF export, and history controls, then call `nasmdHtmlPreview.show`. For Markdown, clear and hide the iframe, restore current control visibility, and continue the existing draft/Vditor/SSE flow. Ensure local or server HTML open errors show a clear host-side error state. Style the iframe to fill the editor area and allow its own document to scroll.

- [ ] **Step 4: Re-run the focused navigation tests**

Run: `npx playwright test tests/e2e/app.spec.js -g "HTML 与 Markdown 文件切换"`
Expected: PASS for HTML controls, preview cleanup, and unchanged Markdown navigation/save behavior.

- [ ] **Step 5: Commit navigation integration**

```bash
git add web/app.js web/index.html web/app.css tests/e2e/app.spec.js
git commit -m "feat: integrate HTML preview into file navigation"
```

## Task 5: Verify error handling, compatibility, and user documentation

**Files:**
- Modify: `README.md`
- Test: `tests/test_webserver.py`
- Test: `tests/e2e/app.spec.js`

- [ ] **Step 1: Add failing cases for missing resources and denied access**

Cover a missing server resource, a local resource path that escapes the selected directory, and a file that disappears between tree listing and preview. Assert the preview remains usable, the missing main document gets a clear error state, and no path outside the mount is returned.

- [ ] **Step 2: Run the focused validation commands**

Run: `pytest tests/test_webserver.py -k "preview_resource or html_tree" -q`
Run: `npx playwright test tests/e2e/app.spec.js -g "HTML"`
Expected: PASS for supported extension discovery, same-mount relative assets, error states, iframe isolation, and HTML/Markdown switching.

- [ ] **Step 3: Document HTML preview support**

Add a concise feature bullet in `README.md` stating `.html` and `.htm` files can be previewed in an isolated frame and their same-mount relative assets are supported; do not imply that HTML source editing, Markdown history, or search are supported.

- [ ] **Step 4: Run the relevant regression suites**

Run: `pytest tests/test_webserver.py -q`
Run: `npx playwright test tests/e2e/app.spec.js`
Expected: PASS with existing Markdown behavior unchanged.

- [ ] **Step 5: Commit final documentation and compatibility fixes**

```bash
git add README.md tests/test_webserver.py tests/e2e/app.spec.js web nas_md/webserver/__init__.py
git commit -m "docs: document HTML preview support"
```

## Self-review

- **Spec coverage:** Discovery and subtree visibility are covered in Tasks 1–2; separate preview and Markdown dispatch/control behavior in Task 4; relative resources and sandbox boundaries in Task 3; errors and outside-mount rejection in Tasks 1, 3, and 5; Markdown regression and documentation in Tasks 4–5.
- **Placeholder scan:** No TBD/TODO steps remain. Each code task names exact paths, behaviors, and focused commands.
- **Type/API consistency:** The backend emits `hasHtml`; local nodes use `hasHtml`; the preview module exposes `show({ mount, path, content })` and `clear()`; `openFile` calls those methods using the same property names.

