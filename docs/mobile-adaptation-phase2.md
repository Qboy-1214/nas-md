# Phase 2: 移动端交互优化 - 详细实施计划

## 目标
在 Phase 1 基础布局之上，优化移动端交互体验：文件树触控、搜索体验、版本历史移动端适配。

---

## 改动文件清单

| 文件 | 改动内容 | 预计工作量 |
|------|---------|-----------|
| `web/app.css` | 搜索结果卡片化、版本历史面板移动端适配、文件树 touch 区域扩大 | ~1h |
| `web/app.js` | 搜索框 sticky 滚动行为、长按菜单 | ~2h |
| `web/files.js` | 文件树 touch 手势（滑动手势展开/折叠）、长按弹出操作菜单 | ~2h |
| `web/version_history.js` | 移动端面板宽度适配、单列 diff 视图 | ~1h |
| `tests/e2e/mobile.spec.js` | 新增 Phase 2 E2E 测试 | ~1h |

---

## 2.1 文件树触控优化

### 2.1.1 文件夹 chevron 区域扩大为 44px touch target

**现状**: 文件树项点击区域依赖文本大小，小屏上难以精确点击。

**改动**:
```css
/* app.css - 文件树 touch target */
.tree-item {
  min-height: 44px;
  padding: 8px 12px;
}

.tree-chevron {
  min-width: 44px;
  min-height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 移动端 */
@media (max-width: 767px) {
  .tree-item {
    min-height: 52px;
    padding: 10px 12px;
  }
  .tree-chevron {
    min-width: 52px;
  }
}
```

**JS 改动** (files.js):
```javascript
// 文件树项点击事件增强
function initFileTreeTouch() {
  const tree = document.getElementById('file-tree');
  if (!tree) return;

  // 长按检测
  let pressTimer = null;
  let longPressTriggered = false;

  tree.addEventListener('touchstart', (e) => {
    const item = e.target.closest('.tree-item');
    if (!item) return;
    
    longPressTriggered = false;
    pressTimer = setTimeout(() => {
      longPressTriggered = true;
      const path = item.dataset.path;
      const mountId = item.dataset.mountId;
      if (path) showFileContextMenu(path, mountId, e.touches[0].clientX, e.touches[0].clientY);
    }, 500);
  }, { passive: true });

  tree.addEventListener('touchend', (e) => {
    clearTimeout(pressTimer);
    if (longPressTriggered) {
      e.preventDefault();
      longPressTriggered = false;
    }
  }, { passive: false });

  tree.addEventListener('touchmove', () => {
    clearTimeout(pressTimer);
  }, { passive: true });
}
```

### 2.1.2 滑动手势展开/折叠文件夹

**方案**: 左右滑动文件夹项触发展开/折叠。

**JS 改动** (files.js):
```javascript
function initFileTreeSwipe() {
  const tree = document.getElementById('file-dir');
  if (!tree) return;

  let startX = 0;
  let startY = 0;
  let currentItem = null;

  tree.addEventListener('touchstart', (e) => {
    const item = e.target.closest('.tree-item');
    if (!item || !item.querySelector('.tree-children')) return;
    
    startX = e.touches[0].clientX;
    startY = e.touches[0].clientY;
    currentItem = item;
  }, { passive: true });

  tree.addEventListener('touchend', (e) => {
    if (!currentItem) return;
    
    const endX = e.changedTouches[0].clientX;
    const endY = e.changedTouches[0].clientY;
    const deltaX = endX - startX;
    const deltaY = Math.abs(endY - startY);

    // 只处理水平滑动，忽略垂直滚动
    if (Math.abs(deltaX) > 50 && deltaY < 30) {
      const children = currentItem.querySelector('.tree-children');
      if (children) {
        const isExpanded = currentItem.classList.contains('expanded');
        if (deltaX > 0) {
          // 右滑展开
          if (!isExpanded) toggleDir(currentItem);
        } else {
          // 左滑折叠
          if (isExpanded) toggleDir(currentItem);
        }
      }
    }
    currentItem = null;
  }, { passive: true });
}
```

### 2.1.3 长按弹出操作菜单

**HTML 改动** (index.html) - 添加 context menu:
```html
<!-- 在 body 末尾添加 -->
<div id="file-context-menu" class="file-context-menu" style="display:none">
  <button onclick="openFileContextAction('rename')">重命名</button>
  <button onclick="openFileContextAction('delete')">删除</button>
  <button onclick="openFileContextAction('share')">分享</button>
  <button onclick="openFileContextAction('download')">下载</button>
</div>
```

**CSS 改动** (app.css):
```css
.file-context-menu {
  position: fixed;
  background: var(--c-bg);
  border: 1px solid var(--c-border);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-lg);
  min-width: 160px;
  z-index: 1000;
  padding: 4px 0;
}

.file-context-menu button {
  display: block;
  width: 100%;
  padding: 10px 16px;
  text-align: left;
  background: none;
  border: none;
  font-size: 14px;
  color: var(--c-text);
  cursor: pointer;
}

.file-context-menu button:hover {
  background: var(--c-bg-hover);
}

/* 移动端全屏菜单 */
@media (max-width: 480px) {
  .file-context-menu {
    position: fixed;
    top: auto;
    bottom: 0;
    left: 0;
    right: 0;
    border-radius: var(--r-lg) var(--r-lg) 0 0;
    min-width: auto;
  }
  
  .file-context-menu::before {
    content: '';
    display: block;
    width: 40px;
    height: 4px;
    background: var(--c-border);
    border-radius: 2px;
    margin: 8px auto;
  }
}
```

**JS 改动** (app.js):
```javascript
function showFileContextMenu(path, mountId, x, y) {
  const menu = document.getElementById('file-context-menu');
  if (!menu) return;
  
  // 存储当前操作上下文
  window._contextMenuTarget = { path, mountId };
  
  // 移动端使用底部弹出
  if (window.innerWidth < 480) {
    menu.style.top = 'auto';
    menu.style.bottom = '0';
    menu.style.left = '0';
    menu.style.right = '0';
  } else {
    menu.style.top = y + 'px';
    menu.style.left = x + 'px';
  }
  
  menu.style.display = 'block';
  
  // 点击外部关闭
  setTimeout(() => {
    document.addEventListener('click', hideFileContextMenu, { once: true });
  }, 0);
}

function hideFileContextMenu() {
  const menu = document.getElementById('file-context-menu');
  if (menu) menu.style.display = 'none';
}

function openFileContextAction(action) {
  const target = window._contextMenuTarget;
  if (!target) return;
  
  switch (action) {
    case 'rename':
      showRenameModal(target.path, target.mountId);
      break;
    case 'delete':
      deleteFile(target.path, target.mountId);
      break;
    case 'share':
      shareFile(target.path, target.mountId);
      break;
    case 'download':
      downloadFile(target.path, target.mountId);
      break;
  }
  hideFileContextMenu();
}
```

---

## 2.2 搜索体验优化

### 2.2.1 搜索结果卡片式布局

**CSS 改动** (app.css):
```css
/* 搜索结果卡片化 */
.search-results {
  max-height: 300px;
  overflow-y: auto;
}

.search-result-item {
  display: block;
  padding: 12px;
  border-bottom: 1px solid var(--c-border);
  cursor: pointer;
  transition: background 0.15s;
}

.search-result-item:hover {
  background: var(--c-bg-hover);
}

.search-result-item .result-path {
  display: block;
  font-size: 13px;
  color: var(--c-text);
  margin-bottom: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.search-result-item .result-snippet {
  display: block;
  font-size: 12px;
  color: var(--c-muted);
  line-height: 1.4;
  max-height: 2.8em;
  overflow: hidden;
}

/* 移动端优化 */
@media (max-width: 767px) {
  .search-results {
    max-height: 50vh;
  }
  
  .search-result-item {
    padding: 14px 12px;
  }
  
  .search-result-item .result-path {
    font-size: 14px;
  }
}
```

### 2.2.2 搜索框 sticky 滚动行为

**JS 改动** (app.js):
```javascript
function initSearchSticky() {
  const searchBox = document.querySelector('.search-box');
  if (!searchBox) return;
  
  let lastScrollY = 0;
  let ticking = false;
  
  function onScroll() {
    lastScrollY = window.scrollY;
    if (!ticking) {
      window.requestAnimationFrame(() => {
        // 滚动超过 100px 时添加阴影
        if (lastScrollY > 100) {
          searchBox.classList.add('search-sticky');
        } else {
          searchBox.classList.remove('search-sticky');
        }
        ticking = false;
      });
      ticking = true;
    }
  }
  
  window.addEventListener('scroll', onScroll, { passive: true });
}
```

**CSS 改动** (app.css):
```css
.search-sticky {
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

/* 移动端搜索框固定顶部 */
@media (max-width: 480px) {
  .search-box {
    position: sticky;
    top: 0;
    z-index: 10;
    background: var(--c-bg-sidebar);
    padding: 8px;
  }
}
```

---

## 2.3 版本历史移动端适配

### 2.3.1 面板宽度自适应

**JS 改动** (version_history.js):
```javascript
function createPanel() {
  // ... 现有代码 ...
  
  _panel = document.createElement('div');
  _panel.id = 'version-history-panel';
  
  // 移动端全宽
  const isMobile = window.innerWidth < 768;
  const panelWidth = isMobile ? '100vw' : '400px';
  const panelRight = isMobile ? '-100vw' : '-420px';
  
  _panel.style.cssText =
    `position:fixed;top:0;right:${panelRight};width:${panelWidth};height:100vh;` +
    'background:var(--c-bg);' +
    'box-shadow:-2px 0 12px rgba(0,0,0,0.15);z-index:10000;' +
    'transition:right 0.3s;' +
    'display:flex;flex-direction:column;font-family:system-ui,sans-serif;';
}
```

### 2.3.2 单列 diff 视图

**JS 改动** (version_history.js):
```javascript
function renderDiff(diff) {
  const isMobile = window.innerWidth < 768;
  
  if (isMobile) {
    // 移动端：单列滚动
    return `<div class="diff-mobile">
      ${diff.map(line => `
        <div class="diff-line ${line.type}">
          ${line.type === 'add' ? '+' : line.type === 'del' ? '-' : ' '}
          ${escapeHtml(line.text)}
        </div>
      `).join('')}
    </div>`;
  } else {
    // 桌面端：对比视图
    return `<div class="diff-desktop">
      <div class="diff-old">${renderSide(diff.oldLines, '-')}</div>
      <div class="diff-new">${renderSide(diff.newLines, '+')}</div>
    </div>`;
  }
}
```

**CSS 改动** (app.css):
```css
/* 移动端 diff 单列 */
.diff-mobile {
  font-family: monospace;
  font-size: 12px;
  line-height: 1.5;
}

.diff-mobile .diff-line {
  padding: 4px 8px;
  border-bottom: 1px solid var(--c-border);
}

.diff-mobile .diff-line.add {
  background: rgba(26, 174, 57, 0.1);
  color: #1aae39;
}

.diff-mobile .diff-line.del {
  background: rgba(224, 49, 49, 0.1);
  color: #e03131;
}

/* 移动端面板关闭按钮 */
#version-history-panel .vh-close-btn {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  border: none;
  background: none;
  color: var(--c-text);
  cursor: pointer;
}
```

---

## 2.4 编辑器模式简化（可选）

### 2.4.1 编辑器模式切换按钮

**HTML 改动** (index.html):
```html
<!-- 将三个模式按钮改为一个轮转按钮 -->
<button class="editor-mode-btn" id="editor-mode-btn" onclick="cycleEditorMode()" title="切换编辑模式 (M)">
  <span id="editor-mode-icon"></span>
  <span id="editor-mode-label">即时</span>
</button>
```

**JS 改动** (editor.js):
```javascript
function cycleEditorMode() {
  const modes = ['ir', 'sv', 'wysiwyg'];
  const labels = { ir: '即时', sv: '分屏', wysiwyg: '所见即所得' };
  const icons = { ir: '📝', sv: '📄', wysiwyg: '✏️' };
  
  const current = window._editorMode || 'ir';
  const idx = modes.indexOf(current);
  const next = modes[(idx + 1) % modes.length];
  
  setEditorMode(next);
  
  // 更新按钮显示
  const label = document.getElementById('editor-mode-label');
  const icon = document.getElementById('editor-mode-icon');
  if (label) label.textContent = labels[next];
  if (icon) icon.textContent = icons[next];
}
```

---

## 测试计划

### E2E 测试 (`tests/e2e/mobile.spec.js`)

```javascript
test.describe('Phase 2: 文件树触控', () => {
  test('长按文件弹出操作菜单', async ({ browser }) => {
    const { page, ctx } = await mobileCtx(browser, 375, 667);
    // 触发长按
    await page.evaluate(() => {
      const item = document.querySelector('.tree-item');
      if (item) {
        const touch = new Touch({ identifier: Date.now(), target: item, screenX: 100, screenY: 100 });
        item.dispatchEvent(new TouchEvent('touchstart', { touches: [touch] }));
        setTimeout(() => {
          item.dispatchEvent(new TouchEvent('touchend', { changedTouches: [touch] }));
        }, 500);
      }
    });
    await expect(page.locator('#file-context-menu')).toBeVisible();
    await ctx.close();
  });

  test('滑动手势展开文件夹', async ({ browser }) => {
    const { page, ctx } = await mobileCtx(browser, 375, 667);
    // 触发右滑
    await page.evaluate(() => {
      const folder = document.querySelector('.tree-item.expanded') || document.querySelector('.tree-item');
      if (folder) {
        folder.dispatchEvent(new TouchEvent('touchstart', {
          touches: [{ identifier: 1, screenX: 50, screenY: 100 }],
        }));
        setTimeout(() => {
          folder.dispatchEvent(new TouchEvent('touchend', {
            changedTouches: [{ identifier: 1, screenX: 100, screenY: 100 }],
          }));
        }, 100);
      }
    });
    await ctx.close();
  });
});

test.describe('Phase 2: 搜索体验', () => {
  test('搜索结果卡片布局', async ({ browser }) => {
    const { page, ctx } = await mobileCtx(browser, 375, 667);
    await page.locator('#search-input').fill('test');
    await page.waitForTimeout(500);
    // 验证搜索结果项存在
    await expect(page.locator('.search-result-item')).toBeAttached();
    await ctx.close();
  });
});

test.describe('Phase 2: 版本历史', () => {
  test('版本历史面板移动端宽度', async ({ browser }) => {
    const { page, ctx } = await mobileCtx(browser, 375, 667);
    // 触发版本历史面板
    await page.evaluate(() => showVersionHistory());
    await page.waitForTimeout(300);
    // 验证面板在移动端全宽
    const panel = page.locator('#version-history-panel');
    if (await panel.count() > 0) {
      const width = await panel.evaluate(el => el.offsetWidth);
      expect(width).toBeGreaterThanOrEqual(375);
    }
    await ctx.close();
  });
});
```

---

## 验收标准

- [ ] 文件树项 touch target ≥ 44px
- [ ] 长按文件弹出操作菜单（重命名/删除/分享/下载）
- [ ] 滑动手势可展开/折叠文件夹
- [ ] 搜索结果卡片式布局，路径可截断
- [ ] 搜索框滚动时 sticky 阴影
- [ ] 版本历史面板在移动端全宽显示
- [ ] diff 视图在移动端单列滚动
- [ ] 所有功能通过 Playwright E2E 测试

---

## 风险与注意事项

1. **touch 事件兼容**: 需要同时处理 touchstart/touchend 和 mouse events
2. **长按冲突**: 长按菜单可能与文本选择冲突，需要 preventDefault
3. **手势方向**: 左右滑动手势可能与页面滚动冲突，需要 deltaY 阈值过滤
4. **上下文菜单位置**: 移动端使用底部 sheet，桌面端使用右键菜单
5. **版本历史性能**: 大量历史记录时移动端滚动性能
