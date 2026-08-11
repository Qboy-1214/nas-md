/**
 * Mobile Adaptation Phase 1 - Unit & Integration Tests
 * 
 * 测试文件:
 * - unit-mobile.js: JavaScript 函数单元测试
 * - e2e/mobile.spec.js: Playwright E2E 测试
 */

const fs = require('fs');
const path = require('path');

// Resolve project root from test file location
const ROOT = path.resolve(__dirname, '..', '..');

// ============================================================
// 1. CSS 样式验证（单元测试）
// ============================================================

describe('CSS Responsive Styles', () => {
  const cssContent = fs.readFileSync(
    path.join(ROOT, 'web', 'app.css'),
    'utf-8'
  );

  describe('480px breakpoint', () => {
    test('应包含 480px 断点', () => {
      expect(cssContent).toContain('@media (max-width: 480px)');
    });

    test('sidebar 宽度应为 240px', () => {
      expect(cssContent).toContain('--sidebar-w: 240px');
    });

    test('应隐藏下载/刷新/导出 PDF 按钮', () => {
      expect(cssContent).toContain('#download-top-btn');
      expect(cssContent).toContain('#btn-refresh');
      expect(cssContent).toContain('#export-pdf-top-btn');
      // 确认这些按钮在 480px 断点内被 display: none
      const match = cssContent.match(/@media \(max-width: 480px\)([\s\S]*?)\}/);
      expect(match).toBeTruthy();
      const breakpointContent = match[1];
      expect(breakpointContent).toContain('display: none');
    });
  });

  describe('Sidebar close button', () => {
    test('应定义 .sidebar-close 样式', () => {
      expect(cssContent).toContain('.sidebar-close');
    });

    test('桌面端应隐藏 sidebar-close', () => {
      // 在 @media (max-width: 480px) 之外应有 display: none
      const lines = cssContent.split('\n');
      let foundDesktopRule = false;
      for (let i = 0; i < lines.length; i++) {
        if (lines[i].includes('.sidebar-close') && lines[i].includes('display: none')) {
          foundDesktopRule = true;
          break;
        }
      }
      expect(foundDesktopRule).toBe(true);
    });

    test('480px 断点内应显示 sidebar-close', () => {
      const match = cssContent.match(/@media \(max-width: 480px\)([\s\S]*?)\n\}/);
      expect(match).toBeTruthy();
      const breakpointContent = match[1];
      expect(breakpointContent).toContain('display: flex');
    });
  });

  describe('Vditor toolbar mobile', () => {
    test('应定义 .vditor-toolbar-mobile 样式', () => {
      expect(cssContent).toContain('.vditor-toolbar-mobile');
    });

    test('应定义滚动指示器样式', () => {
      expect(cssContent).toContain('.vditor-toolbar-mobile::after');
      expect(cssContent).toContain('.vditor-toolbar-mobile.scrolled::after');
    });
  });

  describe('More menu styles', () => {
    test('应定义 .more-menu 样式', () => {
      expect(cssContent).toContain('.more-menu');
    });

    test('应定义 .topbar-more-wrapper 样式', () => {
      expect(cssContent).toContain('.topbar-more-wrapper');
    });
  });

  describe('Modal full screen on mobile', () => {
    test('480px 断点内 modal 应为全屏', () => {
      const match = cssContent.match(/@media \(max-width: 480px\)([\s\S]*?)\n\}/);
      expect(match).toBeTruthy();
      const breakpointContent = match[1];
      expect(breakpointContent).toContain('width: 100vw');
      expect(breakpointContent).toContain('min-height: 100vh');
      expect(breakpointContent).toContain('border-radius: 0');
    });
  });

  describe('Editor full height on mobile', () => {
    test('480px 断点内编辑器应为全屏高度', () => {
      const match = cssContent.match(/@media \(max-width: 480px\)([\s\S]*?)\n\}/);
      expect(match).toBeTruthy();
      const breakpointContent = match[1];
      expect(breakpointContent).toContain('height: calc(100vh - 48px - 44px)');
    });
  });

  describe('File tree touch targets', () => {
    test('480px 断点内 tree-item 应有最小 44px 高度', () => {
      const match = cssContent.match(/@media \(max-width: 480px\)([\s\S]*?)\n\}/);
      expect(match).toBeTruthy();
      const breakpointContent = match[1];
      expect(breakpointContent).toContain('min-height: 44px');
    });
  });
});

// ============================================================
// 2. HTML 结构验证
// ============================================================

describe('HTML Structure', () => {
  const htmlContent = fs.readFileSync(
    path.join(ROOT, 'web', 'index.html'),
    'utf-8'
  );

  describe('Sidebar close button', () => {
    test('应包含 .sidebar-close 按钮', () => {
      expect(htmlContent).toContain('class="sidebar-close"');
      expect(htmlContent).toContain('closeSidebar()');
    });

    test('sidebar-close 应在 sidebar-header 内', () => {
      // 检查结构: sidebar-header > logo + sidebar-close
      const sidebarHeaderMatch = htmlContent.match(
        /<div class="sidebar-header">[\s\S]*?<\/div>/
      );
      expect(sidebarHeaderMatch).toBeTruthy();
      const headerContent = sidebarHeaderMatch[0];
      expect(headerContent).toContain('class="logo"');
      expect(headerContent).toContain('class="sidebar-close"');
    });
  });

  describe('More menu', () => {
    test('应包含 #topbar-more 按钮', () => {
      expect(htmlContent).toContain('id="topbar-more"');
      expect(htmlContent).toContain('toggleMoreMenu()');
    });

    test('应包含 #more-menu 下拉菜单', () => {
      expect(htmlContent).toContain('id="more-menu"');
    });

    test('more menu 应包含下载按钮', () => {
      expect(htmlContent).toContain('id="more-download"');
      expect(htmlContent).toContain('downloadCurrentFile()');
    });

    test('more menu 应包含刷新按钮', () => {
      expect(htmlContent).toContain('id="more-refresh"');
      expect(htmlContent).toContain('refreshFromDisk()');
    });

    test('more menu 应包含导出 PDF 按钮', () => {
      expect(htmlContent).toContain('id="more-pdf"');
      expect(htmlContent).toContain('exportCurrentPDF()');
    });

    test('more menu 应在 topbar 区域内', () => {
      // 检查 topbar-more-wrapper 在 header 内
      const topbarMatch = htmlContent.match(/<header class="topbar">[\s\S]*?<\/header>/);
      expect(topbarMatch).toBeTruthy();
      const topbarContent = topbarMatch[0];
      expect(topbarContent).toContain('topbar-more-wrapper');
    });
  });
});

// ============================================================
// 3. JavaScript 逻辑验证
// ============================================================

describe('JavaScript Logic', () => {
  const jsContent = fs.readFileSync(
    path.join(ROOT, 'web', 'app.js'),
    'utf-8'
  );

  describe('closeSidebar function', () => {
    test('应定义 closeSidebar 函数', () => {
      expect(jsContent).toContain('function closeSidebar()');
    });

    test('closeSidebar 应移除 sidebar 的 open 类', () => {
      const match = jsContent.match(/function closeSidebar\(\)[\s\S]*?\n\}/);
      expect(match).toBeTruthy();
      expect(match[0]).toContain("classList.remove('open')");
    });
  });

  describe('toggleMoreMenu function', () => {
    test('应定义 toggleMoreMenu 函数', () => {
      expect(jsContent).toContain('function toggleMoreMenu()');
    });

    test('toggleMoreMenu 应切换 more-menu 的 open 类', () => {
      const match = jsContent.match(/function toggleMoreMenu\(\)[\s\S]*?\n\}/);
      expect(match).toBeTruthy();
      expect(match[0]).toContain("classList.toggle('open')");
    });
  });

  describe('isMobile / isSmallMobile', () => {
    test('应定义 isMobile 函数', () => {
      expect(jsContent).toContain('function isMobile()');
    });

    test('isMobile 应返回宽度 < 768', () => {
      const match = jsContent.match(/function isMobile\(\)[\s\S]*?\n\}/);
      expect(match).toBeTruthy();
      expect(match[0]).toContain('window.innerWidth < 768');
    });

    test('应定义 isSmallMobile 函数', () => {
      expect(jsContent).toContain('function isSmallMobile()');
    });

    test('isSmallMobile 应返回宽度 < 480', () => {
      const match = jsContent.match(/function isSmallMobile\(\)[\s\S]*?\n\}/);
      expect(match).toBeTruthy();
      expect(match[0]).toContain('window.innerWidth < 480');
    });
  });

  describe('initMobileLayout', () => {
    test('应定义 initMobileLayout 函数', () => {
      expect(jsContent).toContain('function initMobileLayout()');
    });

    test('应添加/移除 body 的 mobile 类', () => {
      const match = jsContent.match(/function initMobileLayout\(\)[\s\S]*?\n\}/);
      expect(match).toBeTruthy();
      expect(match[0]).toContain("classList.add('mobile')");
      expect(match[0]).toContain("classList.remove('mobile')");
    });

    test('应控制 topbar-more 按钮的显示', () => {
      const match = jsContent.match(/function initMobileLayout\(\)[\s\S]*?\n\}/);
      expect(match).toBeTruthy();
      expect(match[0]).toContain('topbar-more');
      expect(match[0]).toContain('isSmallMobile()');
    });

    test('应绑定 load 和 resize 事件', () => {
      expect(jsContent).toContain("window.addEventListener('load', initMobileLayout)");
      expect(jsContent).toContain("window.addEventListener('resize', initMobileLayout)");
    });
  });

  describe('Overlay click to close', () => {
    test('应监听 click 事件关闭 sidebar', () => {
      // 检查是否有关闭 sidebar 的逻辑
      expect(jsContent).toContain("sidebar.classList.contains('open')");
      expect(jsContent).toContain('!sidebar.contains(e.target)');
    });
  });

  describe('More menu click outside', () => {
    test('应监听 click 事件关闭 more menu', () => {
      expect(jsContent).toContain('topbar-more-wrapper');
      expect(jsContent).toContain('moreMenu.classList.contains("open")');
      expect(jsContent).toContain('!moreWrapper.contains(e.target)');
    });
  });

  describe('Mobile search & keyboard handling', () => {
    test('应定义 initMobileSearch IIFE', () => {
      expect(jsContent).toContain('initMobileSearch');
    });

    test('编辑器 focus 时应滚动到可见区域', () => {
      expect(jsContent).toContain('editorEl.scrollIntoView');
      expect(jsContent).toContain('block: \'start\'');
    });

    test('应监听 resize 事件处理 iOS 键盘', () => {
      expect(jsContent).toContain("window.addEventListener('resize'");
    });
  });

  describe('Vditor toolbar mobile', () => {
    test('应定义 initMobileToolbar IIFE', () => {
      expect(jsContent).toContain('initMobileToolbar');
    });

    test('应检测触摸设备', () => {
      expect(jsContent).toContain("navigator.maxTouchPoints");
    });

    test('应为 toolbar 添加滚动监听', () => {
      expect(jsContent).toContain("toolbar.addEventListener('scroll'");
    });

    test('应切换 scrolled 类', () => {
      expect(jsContent).toContain("toolbar.classList.toggle('scrolled'");
    });
  });
});

// ============================================================
// 4. 集成测试 - 验证改动完整性
// ============================================================

describe('Integration Tests', () => {
  test('CSS、HTML、JS 三端改动一致', () => {
    const cssContent = fs.readFileSync(
      path.join(ROOT, 'web', 'app.css'),
      'utf-8'
    );
    const htmlContent = fs.readFileSync(
      path.join(ROOT, 'web', 'index.html'),
      'utf-8'
    );
    const jsContent = fs.readFileSync(
      path.join(ROOT, 'web', 'app.js'),
      'utf-8'
    );

    // 1. sidebar-close: HTML 定义 + CSS 样式 + JS 函数
    expect(htmlContent).toContain('class="sidebar-close"');
    expect(cssContent).toContain('.sidebar-close');
    expect(jsContent).toContain('function closeSidebar()');

    // 2. more-menu: HTML 定义 + CSS 样式 + JS 函数
    expect(htmlContent).toContain('id="more-menu"');
    expect(cssContent).toContain('.more-menu');
    expect(jsContent).toContain('function toggleMoreMenu()');

    // 3. topbar-more-wrapper: HTML 定义 + CSS 样式
    expect(htmlContent).toContain('topbar-more-wrapper');
    expect(cssContent).toContain('.topbar-more-wrapper');

    // 4. 移动端检测: JS 函数
    expect(jsContent).toContain('function isMobile()');
    expect(jsContent).toContain('function isSmallMobile()');
    expect(jsContent).toContain('function initMobileLayout()');

    // 5. 响应式断点: CSS
    expect(cssContent).toContain('@media (max-width: 480px)');

    // 6. Vditor toolbar 移动端: CSS + JS
    expect(cssContent).toContain('.vditor-toolbar-mobile');
    expect(jsContent).toContain('initMobileToolbar');
  });

  test('无语法错误 - CSS', () => {
    const cssContent = fs.readFileSync(
      path.join(__dirname, '../../web/app.css'),
      'utf-8'
    );
    // 检查括号匹配
    let braceCount = 0;
    for (const char of cssContent) {
      if (char === '{') braceCount++;
      if (char === '}') braceCount--;
      if (braceCount < 0) {
        throw new Error('CSS 存在未闭合的 }');
      }
    }
    expect(braceCount).toBe(0);
  });

  test('无语法错误 - HTML', () => {
    const htmlContent = fs.readFileSync(
      path.join(__dirname, '../../web/index.html'),
      'utf-8'
    );
    // 检查关键标签闭合
    const openDivs = (htmlContent.match(/<div/g) || []).length;
    const closeDivs = (htmlContent.match(/<\/div>/g) || []).length;
    expect(openDivs).toBe(closeDivs);
  });

  test('sidebar 关闭按钮与 toggleSidebar 共存', () => {
    const jsContent = fs.readFileSync(
      path.join(__dirname, '../../web/app.js'),
      'utf-8'
    );
    // closeSidebar 和 toggleSidebar 不能冲突
    expect(jsContent).toContain('function closeSidebar()');
    expect(jsContent).toContain('function toggleSidebar()');
    // toggleSidebar 使用 classList.toggle
    expect(jsContent).toContain("classList.toggle('open')");
    // closeSidebar 使用 classList.remove
    expect(jsContent).toContain("classList.remove('open')");
  });
});
