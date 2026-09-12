# Mermaid 图表全屏查看 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Mermaid 增强工具栏增加图表独立全屏，原生 Fullscreen API 优先，失败时回退应用内全屏，并保持现有查看与编辑能力。

**Architecture:** 不移动 Mermaid DOM，也不修改 Vditor 源码。全屏时由当前 Mermaid 图表元素和 overlay 工具栏通过运行时属性进入 fixed 布局；原生模式让 `document.documentElement` 进入 Fullscreen，再用 CSS 隐藏应用外围界面；回退模式只添加应用内全屏类。一个 enhancer 级状态记录当前全屏 block，并由 `fullscreenchange`、按钮和 Escape 统一收口。

**Tech Stack:** 原生 JavaScript、CSS、Vditor、Playwright。

---

### Task 1: Add Fullscreen Regression Tests

**Files:**
- Create: `tests/e2e/mermaid-fullscreen.spec.js`
- Test fixture: `tests/e2e/test-mount/mermaid-fullscreen.md`

- [ ] **Step 1: Add a stable Mermaid fixture**

Create a Markdown file containing one flowchart followed by ordinary text. The fixture must not be edited by the test; the test disables auto-save and only changes the in-memory editor value.

```markdown
# Mermaid Fullscreen

```mermaid
flowchart TD
  A --> B
```

After the diagram
```

- [ ] **Step 2: Write the failing browser test for the toolbar and fallback state**

Open the fixture through the existing test mount, wait for one `.mme-overlay-item`, then reject `document.documentElement.requestFullscreen`. Click `[data-action="toggleFullscreen"]` and assert:

```js
expect(await page.locator('.mme-overlay-item').count()).toBe(1);
await page.locator('[data-action="toggleFullscreen"]').click();
await expect(page.locator('html')).toHaveClass(/mme-fullscreen-active/);
await expect(page.locator('body')).toHaveClass(/mme-app-fullscreen/);
await expect(page.locator('.language-mermaid[data-mme-fullscreen="true"]')).toBeVisible();
await page.keyboard.press('Escape');
await expect(page.locator('html')).not.toHaveClass(/mme-fullscreen-active/);
```

The same test must assert the Markdown value is unchanged and the SVG remains present.

- [ ] **Step 3: Run the new test and verify the expected failure**

Run:

```powershell
npx playwright test tests/e2e/mermaid-fullscreen.spec.js --project=chromium
```

Expected before implementation: the test fails because the toolbar has no `toggleFullscreen` button and no fullscreen classes.

- [ ] **Step 4: Add native Fullscreen API preference coverage**

Add a second test that stubs `requestFullscreen` to resolve and exposes a fake `document.fullscreenElement`. Assert that the document receives `mme-fullscreen-active` without `mme-app-fullscreen`, then dispatch `fullscreenchange` with no fullscreen element and assert all fullscreen state is cleared.

- [ ] **Step 5: Commit the test specification**

```powershell
git add tests/e2e/mermaid-fullscreen.spec.js tests/e2e/test-mount/mermaid-fullscreen.md
git commit -m "test: specify Mermaid fullscreen behavior"
```

### Task 2: Add Fullscreen State and Toolbar Action

**Files:**
- Modify: `web/mermaid_enhancer.js:11-154, 251-351`

- [ ] **Step 1: Add one enhancer-level active fullscreen state**

Add `_fullscreenState = null` beside `_blocks`. Store `{ blockId, mode: 'native' | 'app', state }`; only one block may be fullscreen at a time.

- [ ] **Step 2: Add the toolbar button**

In `buildToolbarHTML()`, add an icon-only button before the separator:

```html
<button class="mme-btn" data-action="toggleFullscreen" title="全屏查看">
  <svg class="mme-icon-fullscreen" ...></svg>
  <svg class="mme-icon-exit-fullscreen" ... style="display:none"></svg>
</button>
```

Use the existing inline icon style and keep the button text-free. Add a `toggleFullscreen` branch in `handleAction()`.

- [ ] **Step 3: Track the overlay item from each block**

When `insertOverlayUI()` creates `uiContainer`, assign it to `_blocks[blockId].uiContainer`. This gives fullscreen state updates access to both the chart target and toolbar without querying unrelated blocks.

- [ ] **Step 4: Implement state application and cleanup helpers**

Implement these concrete transitions:

- `updateFullscreenButton(state)` sets the button title to `全屏查看` or `退出全屏` and toggles `.mme-icon-fullscreen`/`.mme-icon-exit-fullscreen` visibility.
- `markFullscreenElements(state, active)` adds or removes `data-mme-fullscreen="true"` on `state.targetEl` and `state.uiContainer`, and adds/removes `mme-fullscreen-active` on the document root; fallback mode additionally toggles `mme-app-fullscreen` on `body`.
- `clearFullscreenState(state)` resets the block mode, removes fullscreen attributes/classes, updates the button, and clears `_fullscreenState` without calling `setValue()`.
- `enterFullscreen(id)` closes the previous active block, calls `document.documentElement.requestFullscreen()` when available, records `native` after a resolved request, and records `app` when the API is missing or rejects.
- `exitFullscreen(id)` calls `document.exitFullscreen()` for native mode, then always runs `clearFullscreenState(state)` in a `finally` path.
- `handleNativeFullscreenChange()` clears the active native state when `document.fullscreenElement` becomes null. Register this listener once during overlay initialization, and register one Escape listener that exits only the active app mode.

`enterFullscreen()` must first close another active block, call `document.documentElement.requestFullscreen()` when available, set `mode: 'native'` on success, and catch rejection to use `mode: 'app'`. Both paths add `mme-fullscreen-active`; only fallback adds `mme-app-fullscreen`. Mark the chart and overlay item with `data-mme-fullscreen="true"`.

`exitFullscreen()` must call `document.exitFullscreen()` for native mode, remove both classes and data attributes, restore the icon/title, and clear `_fullscreenState`. `fullscreenchange` must clear state when the browser exits native fullscreen. A single Escape listener must exit only the active app fallback.


- [ ] **Step 5: Keep overlay positioning stable in fullscreen**

Update `updateOverlayPositions()` so an active fullscreen block receives `top: 0`, `left: 0`, and `width: 100%`; normal blocks keep the existing measured position. If a target block disappears while fullscreen, call `clearFullscreenState()` before removing its overlay.

- [ ] **Step 6: Run syntax and the new test**

Run:

```powershell
node --check web/mermaid_enhancer.js
npx playwright test tests/e2e/mermaid-fullscreen.spec.js --project=chromium
```

Expected: JavaScript syntax passes and the new fullscreen tests pass.

- [ ] **Step 7: Commit the behavior implementation**

```powershell
git add web/mermaid_enhancer.js
git commit -m "feat: add Mermaid fullscreen viewer"
```

### Task 3: Add Fullscreen Layout Styles

**Files:**
- Modify: `web/app.css:2588-2617`

- [ ] **Step 1: Replace the obsolete fullscreen selector**

The current CSS targets `[data-mme-protected].mme-fullscreen`, but the overlay implementation uses `.mme-overlay-item` and does not set `data-mme-protected`. Replace it with selectors based on `html.mme-fullscreen-active` and `data-mme-fullscreen="true"`.

- [ ] **Step 2: Add the native and fallback layout rules**

The active Mermaid chart must be fixed to the viewport, remove the normal 70vh limit, and remain scrollable. The active overlay item must cover the viewport with the toolbar at the top and code area/chart controls usable. Hide only application chrome that would visually compete with the isolated chart: sidebar, resizer, topbar, backlinks panel, and Vditor toolbar.

```css
html.mme-fullscreen-active,
html.mme-fullscreen-active body {
  overflow: hidden !important;
}

html.mme-fullscreen-active .language-mermaid[data-mme-fullscreen='true'],
html.mme-fullscreen-active .mme-overlay-item[data-mme-fullscreen='true'] {
  position: fixed !important;
  inset: 0 !important;
}
```

Add dark-theme compatibility using existing `--c-canvas` and `--c-surface` variables. Do not change normal Mermaid layout rules.

- [ ] **Step 3: Run the browser test and inspect both viewport sizes**

Run the fullscreen test at the default desktop viewport and a 375x667 viewport. Assert no horizontal overflow, the toolbar remains inside the viewport, and the chart SVG has a non-zero bounding box.

- [ ] **Step 4: Commit the styles**

```powershell
git add web/app.css
git commit -m "style: lay out Mermaid fullscreen viewer"
```

### Task 4: Regression and Final Verification

**Files:**
- Test: `tests/e2e/mermaid-fullscreen.spec.js`

- [ ] **Step 1: Verify existing Mermaid controls remain functional**

While fullscreen is active, click code/chart, zoom in, toggle theme, and assert the code area display, SVG transform, and SVG filter change. Exit fullscreen and assert the overlay item returns to normal positioning.

- [ ] **Step 2: Verify Undo/Redo isolation**

Edit text after the Mermaid block, execute Undo and Redo through the editor path, and assert:

```js
expect(document.querySelectorAll('.vditor-ir .vditor-wysiwyg__block')).toHaveLength(0);
expect(document.querySelectorAll('.vditor-ir__preview svg')).toHaveLength(1);
```

The Markdown source must return to its pre-edit value after Undo and include the edit after Redo.

- [ ] **Step 3: Run all relevant checks**

```powershell
node --check web/mermaid_enhancer.js
node --check web/editor.js
npx playwright test tests/e2e/mermaid-fullscreen.spec.js --project=chromium
python -m pytest -q
```

Expected: syntax checks pass, fullscreen regression tests pass, and the Python suite remains green.

- [ ] **Step 4: Review the final diff and status**

```powershell
git diff HEAD~3 --check
git status --short
git log -4 --oneline --decorate
```

The final status must contain no temporary fullscreen fixtures beyond the committed regression fixture and no unintended files.
