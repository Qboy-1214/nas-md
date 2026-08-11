# nas-md 移动端适配 - Phase 1 实施计划

## 目标
修复核心移动端体验问题，使手机浏览器可用。

---

## 改动文件清单

| 文件 | 改动类型 | 预计工作量 |
|------|---------|-----------|
| `web/app.css` | 新增 480px 断点 + sidebar 关闭样式 | ~2h |
| `web/index.html` | sidebar 关闭按钮 + topbar 按钮分组 | ~1h |
| `web/app.js` | overlay 点击关闭 + 移动端检测 + sticky 搜索 | ~2h |
| `web/editor.js` | toolbar 横向滚动 + 键盘处理 | ~2h |

---

## 详细改动

### 1. app.css 新增移动端断点

```css
/* === Mobile: < 480px === */
@media (max-width: 480px) {
  :root {
    --sidebar-w: 240px;
  }

  /* Sidebar close button */
  .sidebar-close {
    display: flex;
  }

  /* Topbar: hide secondary buttons */
  #download-top-btn,
  #btn-refresh,
  #export-pdf-top-btn {
    display: none;
  }

  /* Editor toolbar: horizontal scroll */
  .vditor-toolbar {
    overflow-x: auto;
    white-space: nowrap;
    -webkit-overflow-scrolling: touch;
  }

  /* Editor: full height on mobile */
  .vditor {
    height: calc(100vh - 48px - 44px) !important;
  }

  /* Search: sticky */
  .search-box {
    position: sticky;
    top: 0;
    z-index: 10;
  }

  /* File tree items: larger touch target */
  .tree-item {
    min-height: 44px;
    padding: 8px 12px;
  }

  /* Search results: card layout */
  .search-result-item {
    padding: 12px;
  }

  /* Modal: full screen */
  .modal {
    width: 100vw;
    max-width: 100vw;
    min-height: 100vh;
    border-radius: 0;
  }
}
```

### 2. index.html 改动

#### 2.1 sidebar 添加关闭按钮
```html
<!-- 在 sidebar-header 内添加 -->
<div class="sidebar-header">
  <div class="logo" onclick="navigateHome()">nas-md</div>
  <button class="sidebar-close" onclick="closeSidebar()" title="关闭">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <line x1="18" y1="6" x2="6" y2="18"></line>
      <line x1="6" y1="6" x2="18" y2="18"></line>
    </svg>
  </button>
</div>
```

#### 2.2 topbar 按钮分组
```html
<!-- 将次要按钮放入 dropdown -->
<button class="topbar-more" id="topbar-more" onclick="toggleMoreMenu()">
  <svg>...</svg>
</button>

<div class="more-menu" id="more-menu" style="display:none">
  <button onclick="downloadCurrentFile()">下载</button>
  <button onclick="refreshFromDisk()">刷新</button>
  <button onclick="exportCurrentPDF()">导出 PDF</button>
</div>
```

#### 2.3 编辑器模式简化
```html
<!-- 将三个模式按钮改为一个 -->
<button class="editor-mode-btn" onclick="cycleEditorMode()" title="切换编辑模式">
  <span id="editor-mode-label">即时</span>
</button>
```

### 3. app.js 改动

#### 3.1 overlay 点击关闭 sidebar
```javascript
// 点击 sidebar overlay 关闭
document.addEventListener('click', (e) => {
  const sidebar = document.getElementById('sidebar');
  const menuToggle = document.getElementById('menu-toggle');
  if (sidebar.classList.contains('open') &&
      !sidebar.contains(e.target) &&
      !menuToggle.contains(e.target)) {
    closeSidebar();
  }
});

function closeSidebar() {
  document.getElementById('sidebar').classList.remove('open');
}
```

#### 3.2 移动端检测
```javascript
const isMobile = () => window.innerWidth < 768;
const isSmallMobile = () => window.innerWidth < 480;

// 初始化时根据屏幕尺寸调整
function initMobileLayout() {
  if (isMobile()) {
    document.body.classList.add('mobile');
  } else {
    document.body.classList.remove('mobile');
  }
}

window.addEventListener('resize', initMobileLayout);
initMobileLayout();
```

#### 3.3 sticky 搜索框
```javascript
// 搜索框 sticky 逻辑
const searchBox = document.querySelector('.search-box');
let lastScrollY = 0;

window.addEventListener('scroll', () => {
  const currentScrollY = window.scrollY;
  if (isMobile() && currentScrollY > 50) {
    searchBox.style.transform = 'translateY(0)';
  } else {
    searchBox.style.transform = 'translateY(-100%)';
  }
  lastScrollY = currentScrollY;
});
```

### 4. editor.js 改动

#### 4.1 toolbar 横向滚动
```css
/* 已在 app.css 中添加，这里确保 JS 不覆盖 */
.vditor-toolbar {
  overflow-x: auto !important;
  flex-wrap: nowrap !important;
}

.vditor-toolbar__item {
  flex-shrink: 0;
}
```

#### 4.2 键盘处理
```javascript
// 监听键盘事件，避免编辑器被遮挡
const editor = document.querySelector('.vditor');
let keyboardVisible = false;

editor.addEventListener('focus', () => {
  setTimeout(() => {
    // 键盘打开时滚动到编辑器位置
    editor.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, 300);
});

// 监听键盘高度变化（iOS Safari 特有）
window.addEventListener('resize', () => {
  if (document.activeElement === editor) {
    setTimeout(() => {
      editor.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 100);
  }
});
```

---

## 验证清单

- [ ] 在 Chrome DevTools 中测试 375px、414px、768px 断点
- [ ] 真实手机测试（iPhone SE / iPhone 14 / Android）
- [ ] 测试 sidebar 打开/关闭/点击外部关闭
- [ ] 测试编辑器三种模式在移动端的表现
- [ ] 测试搜索功能在移动端的可用性
- [ ] 测试暗色模式切换按钮在移动端可见
- [ ] 测试保存按钮在移动端可用

---

## 后续 Phase

### Phase 2: 交互优化
- 文件树长按菜单
- 文件树手势展开/折叠
- 搜索卡片式布局
- 版本历史全页面板

### Phase 3: PWA 增强
- Service Worker 缓存策略
- 离线编辑队列
- 网络状态检测
