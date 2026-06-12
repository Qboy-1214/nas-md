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
    // 大纲按钮
    const outlineBtn = page.locator('#btn-outline');
    await expect(outlineBtn).toBeVisible();
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

    // Find the first mount's create-file button
    const createFileBtn = page.locator('.mount-create-btn[title="新建文件"]').first();
    if ((await createFileBtn.count()) === 0) return;

    // Click create file button
    await createFileBtn.click();

    // Wait for the create modal to appear
    const createModal = page.locator('.modal-overlay.active');
    await expect(createModal).toBeVisible();

    // Find the first .md file name in the tree to create a duplicate
    const firstFileName = await page.locator('#file-tree .tree-file .tree-name').first().textContent();
    if (!firstFileName) return;

    // Type the existing file name (without .md extension)
    const nameWithoutExt = firstFileName.replace(/\.md$/i, '');
    const input = createModal.locator('#create-modal-input');
    await input.fill(nameWithoutExt);

    // Click confirm
    await createModal.locator('#create-modal-confirm').click();

    // The duplicate dialog should appear
    const dupDialog = page.locator('.modal-overlay.active');
    await expect(dupDialog).toBeVisible();
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

    // Find the first directory name in the tree
    const firstDirName = await page.locator('#file-tree .tree-dir .tree-name').first().textContent();
    if (!firstDirName) return;

    // Click create folder button
    const createFolderBtn = page.locator('.mount-create-btn[title="新建文件夹"]').first();
    if ((await createFolderBtn.count()) === 0) return;
    await createFolderBtn.click();

    // Wait for the create modal
    const createModal = page.locator('.modal-overlay.active');
    await expect(createModal).toBeVisible();

    // Type the existing directory name
    const input = createModal.locator('#create-modal-input');
    await input.fill(firstDirName);

    // Click confirm
    await createModal.locator('#create-modal-confirm').click();

    // The duplicate dialog should appear
    const dupDialog = page.locator('.modal-overlay.active');
    await expect(dupDialog).toBeVisible();
    await expect(dupDialog).toContainText('文件名冲突');

    // Click rename to dismiss
    await dupDialog.locator('#dup-rename').click();
    await expect(dupDialog).not.toBeVisible();
  });

  test('重名弹框点击覆盖后成功创建', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForSelector('#file-tree', { timeout: 5000 });

    // Find the first .md file name
    const firstFileName = await page.locator('#file-tree .tree-file .tree-name').first().textContent();
    if (!firstFileName) return;

    // Click create file button
    const createFileBtn = page.locator('.mount-create-btn[title="新建文件"]').first();
    if ((await createFileBtn.count()) === 0) return;
    await createFileBtn.click();

    const createModal = page.locator('.modal-overlay.active');
    await expect(createModal).toBeVisible();

    const nameWithoutExt = firstFileName.replace(/\.md$/i, '');
    const input = createModal.locator('#create-modal-input');
    await input.fill(nameWithoutExt);
    await createModal.locator('#create-modal-confirm').click();

    // Duplicate dialog appears
    const dupDialog = page.locator('.modal-overlay.active');
    await expect(dupDialog).toBeVisible();

    // Click overwrite
    await dupDialog.locator('#dup-overwrite').click();
    await expect(dupDialog).not.toBeVisible();

    // Should show success toast
    await expect(page.locator('#toast')).toBeVisible({ timeout: 3000 });
  });
});
