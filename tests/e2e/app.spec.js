import { test, expect } from '@playwright/test';

test.describe('应用加载', () => {
  test('首页正常加载', async ({ page }) => {
    await page.goto('/admin');
    await expect(page).toHaveTitle(/nas-md/);
    await expect(page.locator('#sidebar')).toBeVisible();
    await expect(page.locator('#search-input')).toBeVisible();
  });

  test('顶部栏元素完整', async ({ page }) => {
    await page.goto('/admin');
    // breadcrumb 存在（可能为空文本）
    await expect(page.locator('#breadcrumb')).toBeAttached();
    // 暗色模式切换按钮
    const darkBtn = page.locator('button[title="切换暗色模式"]');
    await expect(darkBtn).toBeVisible();
  });

  test('侧边栏底部导航按钮', async ({ page }) => {
    await page.goto('/admin');
    const footer = page.locator('.sidebar-footer');
    await expect(footer).toBeVisible();
    await expect(footer.getByText('挂载文件夹')).toBeVisible();
  });

  test('默认打开欢迎.md', async ({ page }) => {
    await page.goto('/admin');
    // Editor container should be visible (no welcome page)
    await expect(page.locator('#editor-container')).toBeVisible();
    // Welcome page should not exist
    await expect(page.locator('#welcome-page')).not.toBeAttached();
  });
});

test.describe('暗色模式', () => {
  test('切换暗色模式', async ({ page }) => {
    await page.goto('/admin');
    const darkBtn = page.locator('button[title="切换暗色模式"]');
    await expect(page.locator('html')).not.toHaveClass(/dark/);
    await darkBtn.click();
    await expect(page.locator('html')).toHaveClass(/dark/);
    await darkBtn.click();
    await expect(page.locator('html')).not.toHaveClass(/dark/);
  });

  test('暗色模式持久化到 localStorage', async ({ page }) => {
    await page.goto('/admin');
    const darkBtn = page.locator('button[title="切换暗色模式"]');
    await darkBtn.click();
    const theme = await page.evaluate(() => localStorage.getItem('nasmd_dark'));
    expect(theme).toBe('1');
  });
});

test.describe('侧边栏', () => {
  test('移动端侧边栏折叠和展开', async ({ page }) => {
    await page.goto('/admin');
    await page.setViewportSize({ width: 375, height: 667 });
    await page.waitForTimeout(500);
    const sidebar = page.locator('#sidebar');
    // 移动端侧边栏默认隐藏
    await expect(sidebar).not.toHaveClass(/open/);
    // 通过 JS 直接调用 toggleSidebar
    await page.evaluate(() => toggleSidebar());
    await expect(sidebar).toHaveClass(/open/);
    await page.evaluate(() => toggleSidebar());
    await expect(sidebar).not.toHaveClass(/open/);
  });
});

test.describe('搜索功能', () => {
  test('搜索框输入触发搜索', async ({ page }) => {
    await page.goto('/admin');
    const searchInput = page.locator('#search-input');
    await searchInput.fill('test');
    await page.waitForTimeout(500);
    const resultsEl = page.locator('#search-results');
    await expect(resultsEl).toBeVisible();
  });

  test('搜索框清空后隐藏结果', async ({ page }) => {
    await page.goto('/admin');
    const searchInput = page.locator('#search-input');
    await searchInput.fill('test');
    await page.waitForTimeout(500);
    await searchInput.clear();
    await page.waitForTimeout(300);
    await expect(page.locator('#search-results')).not.toBeVisible();
  });
});

test.describe('Toast 提示', () => {
  test('Toast 显示和自动消失', async ({ page }) => {
    await page.goto('/admin');
    await page.evaluate(() => window.showToast('测试提示'));
    const toast = page.locator('#toast');
    await expect(toast).toBeVisible();
    await expect(toast).toContainText('测试提示');
    await expect(toast).not.toBeVisible({ timeout: 4000 });
  });
});

test.describe('键盘快捷键', () => {
  test('Ctrl+K 聚焦搜索框', async ({ page }) => {
    await page.goto('/admin');
    await page.keyboard.press('Control+k');
    await expect(page.locator('#search-input')).toBeFocused();
  });
});

test.describe('API 健康检查', () => {
  test('health API 返回正常', async ({ request }) => {
    const resp = await request.get('/api/health');
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(data.status).toBe('ok');
  });
});

test.describe('文件操作', () => {
  test('点击侧边栏文件打开编辑器', async ({ page }) => {
    await page.goto('/admin');
    // 等待侧边栏加载
    await page.waitForSelector('#file-tree', { timeout: 5000 });
    // 找到第一个 .md 文件条目并点击
    const firstFile = page.locator('#file-tree .tree-file').first();
    if ((await firstFile.count()) > 0) {
      await firstFile.click();
      // 编辑器区域应该显示内容
      await page.waitForTimeout(500);
      // breadcrumb 应该更新
      const breadcrumb = page.locator('#breadcrumb');
      await expect(breadcrumb).not.toHaveText('');
    }
  });

  test('重命名按钮显示在打开文件后', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForSelector('#file-tree', { timeout: 5000 });
    const firstFile = page.locator('#file-tree .tree-file').first();
    if ((await firstFile.count()) > 0) {
      await firstFile.click();
      await page.waitForTimeout(500);
      // 重命名按钮应该可见
      const renameBtn = page.locator('#rename-top-btn');
      await expect(renameBtn).toBeVisible();
    }
  });

  test('重命名模态框弹出和关闭', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForSelector('#file-tree', { timeout: 5000 });
    const firstFile = page.locator('#file-tree .tree-file').first();
    if ((await firstFile.count()) > 0) {
      await firstFile.click();
      await page.waitForTimeout(500);
      const renameBtn = page.locator('#rename-top-btn');
      await renameBtn.click();
      // 模态框应该出现
      const modal = page.locator('.modal-overlay');
      await expect(modal).toBeVisible();
      // 点击取消关闭
      await modal.locator('.modal-cancel').click();
      await expect(modal).not.toBeVisible();
    }
  });

  test('重命名模态框 Escape 关闭', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForSelector('#file-tree', { timeout: 5000 });
    const firstFile = page.locator('#file-tree .tree-file').first();
    if ((await firstFile.count()) > 0) {
      await firstFile.click();
      await page.waitForTimeout(500);
      await page.locator('#rename-top-btn').click();
      const modal = page.locator('.modal-overlay');
      await expect(modal).toBeVisible();
      await page.keyboard.press('Escape');
      await expect(modal).not.toBeVisible();
    }
  });
});

test.describe('HTML 文件树', () => {
  test('服务端目录树显示大小写不敏感的 HTML 文件和父目录', async ({ page }) => {
    await page.route('**/api/mounts', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify([
          { id: 'html-tree-test', name: 'HTML 测试', path: '/html-test', readonly: true },
        ]),
      }),
    );
    await page.route('**/api/mounts/html-tree-test/tree-recursive?*', (route) => {
      const path = new URL(route.request().url()).searchParams.get('path');
      const entries =
        path === '/'
          ? [
              {
                name: 'index.HTML',
                path: '/index.HTML',
                isDir: false,
                hasMd: false,
                hasHtml: true,
              },
              { name: 'docs', path: '/docs', isDir: true, hasMd: false, hasHtml: true },
              { name: 'notes.txt', path: '/notes.txt', isDir: false, hasMd: false, hasHtml: false },
              {
                name: '.hidden.HTML',
                path: '/.hidden.HTML',
                isDir: false,
                hasMd: false,
                hasHtml: true,
              },
            ]
          : [
              {
                name: 'nested.htm',
                path: '/docs/nested.htm',
                isDir: false,
                hasMd: false,
                hasHtml: true,
              },
              {
                name: 'nested.txt',
                path: '/docs/nested.txt',
                isDir: false,
                hasMd: false,
                hasHtml: false,
              },
            ];
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          name: path === '/' ? 'html-test' : 'docs',
          path,
          isDir: true,
          children: entries,
          hasMd: false,
          hasHtml: true,
          isEmpty: false,
          hasEmptyDir: false,
        }),
      });
    });

    await page.goto('/admin');
    await page.evaluate(() => toggleMount('html-tree-test'));

    const tree = page.locator('#file-tree');
    await expect(tree.locator('.tree-item').filter({ hasText: 'index.HTML' })).toBeVisible();
    await expect(tree.locator('.tree-folder[title="docs"]')).toBeVisible();
    await expect(tree.locator('.tree-item').filter({ hasText: 'notes.txt' })).toHaveCount(0);
    await expect(tree.locator('.tree-item').filter({ hasText: '.hidden.HTML' })).toHaveCount(0);

    await tree.locator('.tree-folder[title="docs"]').click();
    await expect(tree.locator('.tree-item').filter({ hasText: 'nested.htm' })).toBeVisible();
    await expect(tree.locator('.tree-item').filter({ hasText: 'nested.txt' })).toHaveCount(0);
  });

  test('webkitdirectory fallback 收录 HTML 和 HTM 并显示父目录', async ({ page }) => {
    await page.goto('/admin');
    await page.evaluate(() => {
      const makeFile = (name, relativePath) => {
        const file = new File(['test'], name, { type: 'text/html' });
        Object.defineProperty(file, 'webkitRelativePath', { value: relativePath });
        return file;
      };
      onDirPicked({
        target: {
          files: [
            makeFile('index.HTML', 'local-html/index.HTML'),
            makeFile('nested.htm', 'local-html/docs/nested.htm'),
            makeFile('notes.txt', 'local-html/docs/notes.txt'),
            makeFile('.hidden.html', 'local-html/.hidden.html'),
          ],
          value: '',
        },
      });
    });

    const tree = page.locator('#file-tree');
    await tree.locator('.mount-name').filter({ hasText: 'local-html' }).click();
    await expect(tree.locator('.tree-item').filter({ hasText: 'index.HTML' })).toBeVisible();
    await expect(tree.locator('.tree-folder[title="docs"]')).toBeVisible();
    await expect(tree.locator('.tree-item').filter({ hasText: 'notes.txt' })).toHaveCount(0);
    await expect(tree.locator('.tree-item').filter({ hasText: '.hidden.html' })).toHaveCount(0);

    await tree.locator('.tree-folder[title="docs"]').click();
    await expect(tree.locator('.tree-item').filter({ hasText: 'nested.htm' })).toBeVisible();
    await expect(tree.locator('.tree-item').filter({ hasText: 'notes.txt' })).toHaveCount(0);
  });

  test('本机目录保留隐藏的静态资源供预览加载', async ({ page }) => {
    await page.goto('/admin');
    const mountId = await page.evaluate(() => {
      const makeFile = (name, relativePath, content, type) => {
        const file = new File([content], name, { type });
        Object.defineProperty(file, 'webkitRelativePath', { value: relativePath });
        return file;
      };
      onDirPicked({
        target: {
          files: [
            makeFile('index.html', 'local-assets/index.html', '<p>hi</p>', 'text/html'),
            makeFile('site.css', 'local-assets/site.css', 'p { color: red }', 'text/css'),
            makeFile('photo.png', 'local-assets/photo.png', 'image', 'image/png'),
            makeFile('notes.txt', 'local-assets/notes.txt', 'notes', 'text/plain'),
          ],
          value: '',
        },
      });
      return state.mounts.at(-1).id;
    });

    const assets = await page.evaluate((id) => {
      const files = state.localMounts[id].fileMap;
      return {
        css: files['/site.css']?.type,
        image: files['/photo.png']?.type,
        text: files['/notes.txt']?.type,
      };
    }, mountId);
    expect(assets).toEqual({ css: 'text/css', image: 'image/png', text: 'text/plain' });

    const tree = page.locator('#file-tree');
    await expect(tree.locator('.tree-item').filter({ hasText: 'site.css' })).toHaveCount(0);
    await expect(tree.locator('.tree-item').filter({ hasText: 'photo.png' })).toHaveCount(0);
    await expect(tree.locator('.tree-item').filter({ hasText: 'notes.txt' })).toHaveCount(0);
  });
});

test.describe('隔离 HTML 预览', () => {
  async function prepareNavigationFiles(page) {
    await page.route('**/api/mounts/html-navigation-test/preview/**', (route) => {
      const path = new URL(route.request().url()).pathname;
      const content = path.endsWith('/second.html') ? 'Second HTML' : 'First HTML';
      return route.fulfill({
        contentType: 'text/html',
        body: `<!doctype html><p id="preview-content">${content}</p>`,
      });
    });
    await page.goto('/admin');
    await page.waitForFunction(() => typeof openFile === 'function' && typeof API !== 'undefined');
    await page.evaluate(() => {
      const mount = { id: 'html-navigation-test', name: '导航测试', readonly: false };
      state.mounts = [mount];
      state.currentPath = '/welcome.md';
      state.currentMountId = mount.id;
      state.dirty = false;
      window.navigationSseConnections = [];
      window.nasmdSSE.connect = (...args) => window.navigationSseConnections.push(args);
      API.getFile = async (_mountId, path) => ({
        content:
          path === '/first.html'
            ? '<!doctype html><p id="preview-content">First HTML</p>'
            : path === '/second.html'
              ? '<!doctype html><p id="preview-content">Second HTML</p>'
              : '# Markdown file',
        mtime: 1,
        version: 1,
      });
    });
  }

  test('HTML 文件显示预览并隐藏 Vditor 和 Markdown 控件', async ({ page }) => {
    await prepareNavigationFiles(page);
    await page.evaluate(() => {
      localStorage.setItem(
        nasmdDraftStorage.key('html-navigation-test', '/first.html'),
        JSON.stringify({ content: 'Stale HTML draft', mountId: 'html-navigation-test' }),
      );
      window.previewContentSeen = [];
      const show = window.nasmdHtmlPreview.show;
      window.nasmdHtmlPreview.show = (options) => {
        window.previewContentSeen.push(options.content);
        return show(options);
      };
      return openFile('/first.html', 'html-navigation-test');
    });

    await expect(page.locator('#nasmd-html-preview-host')).toBeVisible();
    await expect(page.locator('#nasmd-html-preview')).toBeVisible();
    await expect(page.locator('#vditor')).toBeHidden();
    await expect(page.locator('#editor-modes')).toBeHidden();
    await expect(page.locator('#save-group')).toBeHidden();
    await expect(page.locator('#export-pdf-top-btn')).toBeHidden();
    await expect(page.locator('#history-top-btn')).toBeHidden();
    await expect(page.frameLocator('#nasmd-html-preview').locator('#preview-content')).toHaveText(
      'First HTML',
    );
    const previewContent = await page.evaluate(() => window.previewContentSeen[0]);
    expect(previewContent).toContain('First HTML');
    expect(previewContent).not.toContain('Stale HTML draft');
    expect(await page.evaluate(() => window.navigationSseConnections)).toEqual([]);
  });

  test('从 HTML 切换到 Markdown 会清除预览并恢复编辑器控件', async ({ page }) => {
    await prepareNavigationFiles(page);
    await page.evaluate(() => openFile('/first.html', 'html-navigation-test'));
    await page.evaluate(() => openFile('/notes.md', 'html-navigation-test'));

    await expect(page.locator('#nasmd-html-preview')).toHaveCount(0);
    await expect(page.locator('#nasmd-html-preview-host')).toBeHidden();
    await expect(page.locator('#vditor')).toBeVisible();
    await expect(page.locator('#editor-modes')).toBeVisible();
    await expect(page.locator('#save-group')).toBeVisible();
    await expect(page.locator('#export-pdf-top-btn')).toBeVisible();
    await expect(page.locator('#history-top-btn')).toBeVisible();
    await expect(page.locator('#vditor')).toContainText('Markdown file');
    expect(await page.evaluate(() => window.navigationSseConnections)).toEqual([
      ['html-navigation-test', '/notes.md'],
    ]);
  });

  test('从一个 HTML 文件切换到另一个时销毁旧预览', async ({ page }) => {
    await prepareNavigationFiles(page);
    await page.evaluate(() => openFile('/first.html', 'html-navigation-test'));
    await page.evaluate(() => openFile('/second.html', 'html-navigation-test'));

    await expect(page.locator('#nasmd-html-preview')).toHaveCount(1);
    await expect(page.frameLocator('#nasmd-html-preview').locator('#preview-content')).toHaveText(
      'Second HTML',
    );
  });

  test('从有未保存修改的 Markdown 切换到 HTML 仍会询问保存', async ({ page }) => {
    await prepareNavigationFiles(page);
    await page.evaluate(() => openFile('/notes.md', 'html-navigation-test'));
    await page.waitForFunction(() => !!window._vditor);
    expect(await page.evaluate(() => !!window._vditor)).toBe(true);
    await page.evaluate(() => {
      state.autoSave = false;
      window._vditor.setValue('# Changed markdown');
      onEditorInput();
    });
    await page.waitForFunction(() => state.dirty);
    let confirmMessage;
    page.once('dialog', async (dialog) => {
      confirmMessage = dialog.message();
      await dialog.dismiss();
    });
    await page.evaluate(() => openFile('/first.html', 'html-navigation-test'));

    expect(confirmMessage).toContain('未保存的修改');
    await expect(page.locator('#nasmd-html-preview')).toBeVisible();
  });

  test('预览模块出错时显示宿主错误状态并保留当前文件', async ({ page }) => {
    await prepareNavigationFiles(page);
    await page.evaluate(() => {
      window.nasmdHtmlPreview.show = async () => {
        throw new Error('preview failed');
      };
      return openFile('/first.html', 'html-navigation-test');
    });

    await expect(page.locator('#nasmd-html-preview-host .html-preview-error')).toHaveText(
      'HTML 预览加载失败',
    );
    expect(await page.evaluate(() => state.currentPath)).toBe('/first.html');
    await expect(page.locator('#toast')).toContainText('HTML 预览加载失败');
  });

  test('主 HTML 文件消失时显示可恢复的宿主错误状态', async ({ page }) => {
    await prepareNavigationFiles(page);
    await page.evaluate(() => {
      API.getFile = async () => null;
      return openFile('/missing.html', 'html-navigation-test');
    });

    await expect(page.locator('#nasmd-html-preview-host')).toBeVisible();
    await expect(page.locator('#nasmd-html-preview-host .html-preview-error')).toHaveText(
      'HTML 文件不存在或无法读取',
    );
    await expect(page.locator('#vditor')).toBeHidden();
    await expect(page.locator('#editor-modes')).toBeHidden();
    await expect(page.locator('#save-group')).toBeHidden();
    await expect(page.locator('#export-pdf-top-btn')).toBeHidden();
    await expect(page.locator('#history-top-btn')).toBeHidden();
    await expect(page.locator('#toast')).toContainText('HTML 文件不存在或无法读取');
    expect(await page.evaluate(() => state.currentPath)).toBe('/missing.html');
  });

  test('服务端预览渲染静态页面并隔离父窗口', async ({ page }) => {
    await page.route('**/api/mounts/preview-test/preview/demo/index.html', (route) =>
      route.fulfill({
        contentType: 'text/html',
        body: '<!doctype html><link rel="stylesheet" href="styles/site.css"><p id="result">Loading</p><img id="picture" src="images/pixel.png"><script src="scripts/page.js"></script><script>try { parent.document.body.dataset.previewAccess = "allowed"; } catch { document.body.dataset.parentBlocked = "true"; }</script>',
      }),
    );
    await page.route('**/api/mounts/preview-test/preview/demo/styles/site.css', (route) =>
      route.fulfill({ contentType: 'text/css', body: '#result { color: rgb(255, 0, 0); }' }),
    );
    await page.route('**/api/mounts/preview-test/preview/demo/images/pixel.png', (route) =>
      route.fulfill({
        contentType: 'image/png',
        body: Buffer.from(
          'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j3ZkAAAAASUVORK5CYII=',
          'base64',
        ),
      }),
    );
    await page.route('**/api/mounts/preview-test/preview/demo/scripts/page.js', (route) =>
      route.fulfill({
        contentType: 'text/javascript',
        body: 'document.querySelector("#result").textContent = "Rendered";',
      }),
    );
    await page.goto('/admin');
    await page.addScriptTag({ url: '/html_preview.js' });
    expect(
      await page.evaluate(() => API.previewResourceUrl('preview-test', '/demo/index.html')),
    ).toBe('http://127.0.0.1:8080/api/mounts/preview-test/preview/demo/index.html');
    await page.evaluate(() =>
      window.nasmdHtmlPreview.show({
        mount: { id: 'preview-test', _local: false },
        path: '/demo/index.html',
        content: '',
        container: document.body,
      }),
    );

    const frame = page.locator('#nasmd-html-preview');
    await expect(frame).toBeVisible();
    await expect(frame).toHaveAttribute('sandbox', 'allow-scripts');
    const preview = page.frameLocator('#nasmd-html-preview');
    await expect(preview.locator('#result')).toHaveText('Rendered');
    await expect(preview.locator('body')).toHaveAttribute('data-parent-blocked', 'true');
    await expect(preview.locator('#result')).toHaveCSS('color', 'rgb(255, 0, 0)');
    await expect(preview.locator('#picture')).toHaveJSProperty('naturalWidth', 1);
    expect(await page.locator('body').getAttribute('data-preview-access')).toBeNull();
  });

  test('本机预览解析相对 CSS、图片和脚本并在清除时移除资源', async ({ page }) => {
    await page.goto('/admin');
    await page.addScriptTag({ url: '/html_preview.js' });
    const mountId = await page.evaluate(() => {
      const makeFile = (name, relativePath, content, type) => {
        const file = new File([content], name, { type });
        Object.defineProperty(file, 'webkitRelativePath', { value: relativePath });
        return file;
      };
      onDirPicked({
        target: {
          files: [
            makeFile(
              'index.html',
              'preview-local/index.html',
              '<!doctype html><p id="message">Original</p><img id="picture" src="images/pixel.png"><img id="srcset" srcset="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j3ZkAAAAASUVORK5CYII= 1x, images/pixel.png 2x"><img id="escape" src="../../../outside.png"><link rel="stylesheet" href="styles/site.css"><script src="scripts/page.js"></script>',
              'text/html',
            ),
            makeFile(
              'site.css',
              'preview-local/styles/site.css',
              '@import "theme.css"; #message { color: rgb(255, 0, 0); background-image: url("../images/pixel.png") }',
              'text/css',
            ),
            makeFile(
              'theme.css',
              'preview-local/styles/theme.css',
              '#message { font-weight: bold; }',
              'text/css',
            ),
            makeFile(
              'pixel.png',
              'preview-local/images/pixel.png',
              Uint8Array.from(
                atob(
                  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j3ZkAAAAASUVORK5CYII=',
                ),
                (c) => c.charCodeAt(0),
              ),
              'image/png',
            ),
            makeFile(
              'page.js',
              'preview-local/scripts/page.js',
              'document.querySelector("#message").textContent = "Loaded";',
              'text/javascript',
            ),
          ],
          value: '',
        },
      });
      return state.mounts.at(-1).id;
    });

    await page.evaluate(
      (id) =>
        window.nasmdHtmlPreview.show({
          mount: state.mounts.find((mount) => mount.id === id),
          path: '/index.html',
          content:
            '<!doctype html><p id="message">Original</p><img id="picture" src="images/pixel.png"><img id="srcset" srcset="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j3ZkAAAAASUVORK5CYII= 1x, images/pixel.png 2x"><img id="escape" src="../../../outside.png"><link rel="stylesheet" href="styles/site.css"><script src="scripts/page.js"></script>',
          container: document.body,
        }),
      mountId,
    );
    const frame = page.locator('#nasmd-html-preview');
    await expect(frame).toHaveAttribute('sandbox', 'allow-scripts');
    const preview = page.frameLocator('#nasmd-html-preview');
    await expect(preview.locator('#message')).toHaveText('Loaded');
    await expect(preview.locator('#message')).toHaveCSS('color', 'rgb(255, 0, 0)');
    await expect(preview.locator('#message')).toHaveCSS('font-weight', '700');
    await expect(preview.locator('#message')).toHaveCSS('background-image', /data:image\/png/);
    await expect(preview.locator('#picture')).toHaveJSProperty('naturalWidth', 1);
    await expect(preview.locator('#srcset')).toHaveAttribute(
      'srcset',
      /^data:image\/png;base64,[^ ]+ 1x, data:image\/png;base64,[^ ]+ 2x$/,
    );
    await expect(preview.locator('#escape')).toHaveAttribute('src', 'about:blank');
    const previewDocumentUrl = await frame.getAttribute('src');
    expect(previewDocumentUrl).toMatch(/^data:text\/html;base64,/);

    await page.evaluate(() => window.nasmdHtmlPreview.clear());
    await expect(frame).toHaveCount(0);
    const retainedPreviewContent = await page.evaluate(
      (url) => document.body.innerHTML.includes(url),
      previewDocumentUrl,
    );
    expect(retainedPreviewContent).toBe(false);
  });

  test('本机相对资源缺失或越出挂载点时保留 HTML 页面', async ({ page }) => {
    const resourceWarnings = [];
    page.on('console', (message) => {
      if (message.type() === 'warning') resourceWarnings.push(message.text());
    });
    await page.goto('/admin');
    await page.addScriptTag({ url: '/html_preview.js' });
    const mountId = await page.evaluate(() => {
      const file = new File(
        [
          '<!doctype html><h1 id="ready">Still usable</h1><img id="missing" src="assets/gone.png"><img id="escape" src="../../outside.png"><link rel="stylesheet" href="missing.css">',
        ],
        'index.html',
        { type: 'text/html' },
      );
      Object.defineProperty(file, 'webkitRelativePath', { value: 'missing-assets/index.html' });
      const stylesheet = new File(
        ['@import url("missing-import.css"); @import url("../../outside.css");'],
        'broken.css',
        { type: 'text/css' },
      );
      Object.defineProperty(stylesheet, 'webkitRelativePath', {
        value: 'missing-assets/assets/broken.css',
      });
      onDirPicked({ target: { files: [file, stylesheet], value: '' } });
      return state.mounts.at(-1).id;
    });

    await page.evaluate((id) => {
      const mount = state.mounts.find((item) => item.id === id);
      return window.nasmdHtmlPreview.show({
        mount,
        path: '/index.html',
        content:
          '<!doctype html><h1 id="ready">Still usable</h1><img id="missing" src="assets/gone.png"><img id="escape" src="../../outside.png"><link rel="stylesheet" href="missing.css"><link rel="stylesheet" href="assets/broken.css">',
        container: document.body,
      });
    }, mountId);

    const preview = page.frameLocator('#nasmd-html-preview');
    await expect(preview.locator('#ready')).toHaveText('Still usable');
    await expect(preview.locator('#missing')).toHaveAttribute('src', 'about:blank');
    await expect(preview.locator('#escape')).toHaveAttribute('src', 'about:blank');
    await expect(preview.locator('link[rel="stylesheet"]').first()).toHaveAttribute(
      'href',
      'about:blank',
    );
    expect(resourceWarnings.some((message) => message.includes('assets/gone.png'))).toBe(true);
    expect(resourceWarnings.some((message) => message.includes('../../outside.png'))).toBe(true);
    expect(resourceWarnings.some((message) => message.includes('missing-import.css'))).toBe(true);
    expect(resourceWarnings.some((message) => message.includes('../../outside.css'))).toBe(true);
  });

  test('新预览使未完成的旧预览失效并由清除移除全部预览帧', async ({ page }) => {
    await page.goto('/admin');
    await page.addScriptTag({ url: '/html_preview.js' });
    const mountId = await page.evaluate(() => {
      const html = new File(['<p>placeholder</p>'], 'index.html', { type: 'text/html' });
      Object.defineProperty(html, 'webkitRelativePath', { value: 'race-local/index.html' });
      onDirPicked({ target: { files: [html], value: '' } });
      const mount = state.mounts.at(-1);
      state.localMounts[mount.id].fileMap['/slow.css'] = {
        type: 'text/css',
        text: () =>
          new Promise((resolve) => {
            window.releaseSlowPreviewCss = () => resolve('p { color: red; }');
          }),
      };
      return mount.id;
    });

    await page.evaluate((id) => {
      const mount = state.mounts.find((item) => item.id === id);
      window.oldPreview = window.nasmdHtmlPreview.show({
        mount,
        path: '/index.html',
        content: '<link rel="stylesheet" href="slow.css"><p>stale preview</p>',
        container: document.body,
      });
    }, mountId);
    await page.waitForFunction(() => typeof window.releaseSlowPreviewCss === 'function');

    await page.evaluate((id) => {
      const mount = state.mounts.find((item) => item.id === id);
      return window.nasmdHtmlPreview.show({
        mount,
        path: '/index.html',
        content: '<p>latest preview</p>',
        container: document.body,
      });
    }, mountId);
    await expect(page.locator('#nasmd-html-preview')).toHaveCount(1);
    await expect(page.frameLocator('#nasmd-html-preview').locator('p')).toHaveText(
      'latest preview',
    );

    await page.evaluate(() => window.releaseSlowPreviewCss());
    await page.evaluate(() => window.oldPreview);
    await expect(page.locator('#nasmd-html-preview')).toHaveCount(1);
    await expect(page.frameLocator('#nasmd-html-preview').locator('p')).toHaveText(
      'latest preview',
    );

    await page.evaluate(() => window.nasmdHtmlPreview.clear());
    await expect(page.locator('iframe#nasmd-html-preview')).toHaveCount(0);
  });

  test('优先使用明确的容器或默认预览宿主', async ({ page }) => {
    await page.goto('/admin');
    await page.addScriptTag({ url: '/html_preview.js' });
    await page.evaluate(() => {
      document.getElementById('nasmd-html-preview-host').style.display = '';
      window.nasmdHtmlPreview.show({ mount: { id: 'server-mount' }, path: '/index.html' });
    });
    await expect(page.locator('#nasmd-html-preview-host > #nasmd-html-preview')).toHaveCount(1);

    await page.evaluate(() => {
      window.nasmdHtmlPreview.clear();
      const explicitHost = document.createElement('div');
      explicitHost.id = 'explicit-preview-host';
      document.body.appendChild(explicitHost);
      window.nasmdHtmlPreview.show({
        mount: { id: 'server-mount' },
        path: '/index.html',
        container: explicitHost,
      });
    });
    await expect(page.locator('#explicit-preview-host > #nasmd-html-preview')).toHaveCount(1);
    await expect(page.locator('#nasmd-html-preview-host > #nasmd-html-preview')).toHaveCount(0);
  });
});

test.describe('拖拽功能', () => {
  test('文件条目可拖拽', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForSelector('#file-tree', { timeout: 5000 });
    const draggable = page.locator('#file-tree [draggable="true"]').first();
    if ((await draggable.count()) > 0) {
      // 验证 draggable 属性存在
      const attr = await draggable.getAttribute('draggable');
      expect(attr).toBe('true');
    }
  });

  test('目录作为拖放目标', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForSelector('#file-tree', { timeout: 5000 });
    const dirEntry = page.locator('#file-tree .tree-dir').first();
    if ((await dirEntry.count()) > 0) {
      // 目录条目应该存在
      await expect(dirEntry).toBeVisible();
    }
  });
});

test.describe('挂载点管理', () => {
  test('挂载列表 API 可用', async ({ request }) => {
    const resp = await request.get('/api/mounts');
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(Array.isArray(data)).toBeTruthy();
  });

  test('公开挂载列表 API 可用', async ({ request }) => {
    const resp = await request.get('/api/mounts/public');
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(Array.isArray(data)).toBeTruthy();
  });
});

test.describe('配置和插件 API', () => {
  test('配置 API 返回数据', async ({ request }) => {
    const resp = await request.get('/api/config');
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(typeof data).toBe('object');
  });

  test('插件 API 返回数据', async ({ request }) => {
    const resp = await request.get('/api/plugins');
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(typeof data).toBe('object');
    expect('plugins' in data).toBeTruthy();
  });
});

test.describe('重名冲突弹框', () => {
  test('创建同名文件时弹出冲突弹框', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForSelector('#file-tree', { timeout: 5000 });

    // First create a file
    const createFileBtn = page.locator('.mount-create-btn[title="新建文件"]').first();
    if ((await createFileBtn.count()) === 0) return;
    await createFileBtn.click();

    const createModal = page.locator('.modal-overlay.active');
    await expect(createModal).toBeVisible();
    await createModal.locator('#create-modal-input').fill('dup-test');
    await createModal.locator('#create-modal-confirm').click();
    // Wait for creation to complete
    await page.waitForTimeout(1000);

    // Now try creating the same file again
    await createFileBtn.click();
    const createModal2 = page.locator('.modal-overlay.active');
    await expect(createModal2).toBeVisible();
    await createModal2.locator('#create-modal-input').fill('dup-test');
    await createModal2.locator('#create-modal-confirm').click();

    // The duplicate dialog should appear
    const dupDialog = page.locator('.modal-overlay.active');
    await expect(dupDialog).toBeVisible({ timeout: 5000 });
    await expect(dupDialog).toContainText('文件名冲突');

    // Verify all three buttons are present
    await expect(dupDialog.locator('#dup-cancel')).toBeVisible();
    await expect(dupDialog.locator('#dup-rename')).toBeVisible();
    await expect(dupDialog.locator('#dup-overwrite')).toBeVisible();

    // Click cancel to dismiss
    await dupDialog.locator('#dup-cancel').click();
    await expect(dupDialog).not.toBeVisible();
  });

  test('创建同名文件夹时弹出冲突弹框', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForSelector('#file-tree', { timeout: 5000 });

    // First create a folder
    const createFolderBtn = page.locator('.mount-create-btn[title="新建文件夹"]').first();
    if ((await createFolderBtn.count()) === 0) return;
    await createFolderBtn.click();

    const createModal = page.locator('.modal-overlay.active');
    await expect(createModal).toBeVisible();
    await createModal.locator('#create-modal-input').fill('dup-dir-test');
    await createModal.locator('#create-modal-confirm').click();
    // Wait for creation to complete
    await page.waitForTimeout(1000);

    // Now try creating the same folder again
    await createFolderBtn.click();
    const createModal2 = page.locator('.modal-overlay.active');
    await expect(createModal2).toBeVisible();
    await createModal2.locator('#create-modal-input').fill('dup-dir-test');
    await createModal2.locator('#create-modal-confirm').click();

    // The duplicate dialog should appear
    const dupDialog = page.locator('.modal-overlay.active');
    await expect(dupDialog).toBeVisible({ timeout: 5000 });
    await expect(dupDialog).toContainText('文件名冲突');

    // Click rename to dismiss
    await dupDialog.locator('#dup-rename').click();
    await expect(dupDialog).not.toBeVisible();
  });

  test('重名弹框点击覆盖后成功创建', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForSelector('#file-tree', { timeout: 5000 });

    // First create a file
    const createFileBtn = page.locator('.mount-create-btn[title="新建文件"]').first();
    if ((await createFileBtn.count()) === 0) return;
    await createFileBtn.click();

    const createModal = page.locator('.modal-overlay.active');
    await expect(createModal).toBeVisible();
    await createModal.locator('#create-modal-input').fill('overwrite-test');
    await createModal.locator('#create-modal-confirm').click();
    await page.waitForTimeout(1000);

    // Now try creating the same file again
    await createFileBtn.click();
    const createModal2 = page.locator('.modal-overlay.active');
    await expect(createModal2).toBeVisible();
    await createModal2.locator('#create-modal-input').fill('overwrite-test');
    await createModal2.locator('#create-modal-confirm').click();

    // Duplicate dialog appears
    const dupDialog = page.locator('.modal-overlay.active');
    await expect(dupDialog).toBeVisible({ timeout: 5000 });

    // Click overwrite
    await dupDialog.locator('#dup-overwrite').click();
    await expect(dupDialog).not.toBeVisible();

    // Should show success toast
    await expect(page.locator('#toast')).toBeVisible({ timeout: 3000 });
  });
});
