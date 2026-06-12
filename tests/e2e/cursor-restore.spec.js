import { test, expect } from '@playwright/test';

async function waitForFileInTree(page, fileName, timeout = 15000) {
  await page.waitForFunction(
    (name) => {
      const items = document.querySelectorAll('.tree-item');
      return Array.from(items).some((el) => el.textContent.includes(name));
    },
    fileName,
    { timeout },
  );
}

test.describe('光标和滚动位置恢复', () => {
  test('刷新页面后恢复滚动位置', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForSelector('.mount-name', { hasText: 'test-mount' }, { timeout: 10000 });
    await page.evaluate(() => toggleMount('mount-0'));
    await page.waitForTimeout(500);
    await waitForFileInTree(page, 'test-scroll.md');

    // 打开测试文件
    const testFile = page.locator('.tree-item', { hasText: 'test-scroll.md' });
    await testFile.click();
    await page.waitForFunction(() => {
      const vd = window._vditor;
      return vd && vd.getValue().length > 100;
    }, { timeout: 10000 });

    const editorEl = page.locator('.vditor-ir');

    // 使用 Vditor 的滚动 API
    await page.evaluate(() => {
      const vd = window._vditor;
      if (vd) {
        const el = vd.vditor.ir.element;
        const maxScroll = el.scrollHeight - el.clientHeight;
        if (maxScroll > 0) {
          el.scrollTop = maxScroll;
        }
      }
    });
    await page.waitForTimeout(500);

    const scrollBefore = await page.evaluate(() => {
      const vd = window._vditor;
      return vd ? vd.vditor.ir.element.scrollTop : 0;
    });
    // 在 Vditor IR 模式下，直接设置 scrollTop 可能不生效
    // 改用 vditor 的 scrollTo 方法
    if (scrollBefore === 0) {
      await page.evaluate(() => {
        const vd = window._vditor;
        if (vd && vd.vditor && vd.vditor.ir) {
          const el = vd.vditor.ir.element;
          const lastChild = el.lastElementChild;
          if (lastChild) {
            lastChild.scrollIntoView({ block: 'end' });
          }
        }
      });
      await page.waitForTimeout(500);
    }

    const scrollBefore2 = await page.evaluate(() => {
      const vd = window._vditor;
      return vd ? vd.vditor.ir.element.scrollTop : 0;
    });
    expect(scrollBefore2).toBeGreaterThan(0);

    // 刷新页面
    await page.reload();
    await page.waitForFunction(() => {
      return window._vditor && window._vditor.getValue().length > 100;
    }, { timeout: 15000 });
    await page.waitForTimeout(2000);

    // 刷新后自动打开同一个文件
    const breadcrumb = page.locator('#breadcrumb');
    await expect(breadcrumb).toContainText('test-scroll.md');

    // 检查滚动位置是否恢复（允许一定误差）
    const scrollAfter = await page.evaluate(() => {
      const vd = window._vditor;
      return vd ? vd.vditor.ir.element.scrollTop : 0;
    });
    expect(Math.abs(scrollAfter - scrollBefore)).toBeLessThan(100);
  });

  test('刷新页面后恢复标题位置', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForSelector('.mount-name', { hasText: 'test-mount' }, { timeout: 10000 });
    await page.evaluate(() => toggleMount('mount-0'));
    await page.waitForTimeout(500);
    await waitForFileInTree(page, 'test-scroll.md');

    const testFile = page.locator('.tree-item', { hasText: 'test-scroll.md' });
    await testFile.click();
    await page.waitForFunction(() => {
      const vd = window._vditor;
      return vd && vd.getValue().length > 100;
    }, { timeout: 10000 });

    // 点击大纲中的标题
    const outlineItem = page.locator('#outline-panel .outline-item', { hasText: '第三节' });
    if ((await outlineItem.count()) > 0) {
      await outlineItem.click();
      await page.waitForTimeout(500);
    }

    const editorEl = page.locator('.vditor-ir');
    const scrollBefore = await editorEl.evaluate((el) => el.scrollTop);

    // 刷新页面
    await page.reload();
    await page.waitForFunction(() => {
      return window._vditor && window._vditor.getValue().length > 100;
    }, { timeout: 15000 });
    await page.waitForTimeout(2000);

    const breadcrumb = page.locator('#breadcrumb');
    await expect(breadcrumb).toContainText('test-scroll.md');

    const editorElAfter = page.locator('.vditor-ir');
    const scrollAfter = await editorElAfter.evaluate((el) => el.scrollTop);
    expect(Math.abs(scrollAfter - scrollBefore)).toBeLessThan(100);
  });

  test('切换文件时保存光标位置到 localStorage', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForSelector('.mount-name', { hasText: 'test-mount' }, { timeout: 10000 });
    await page.evaluate(() => toggleMount('mount-0'));
    await page.waitForTimeout(500);
    await waitForFileInTree(page, 'test-scroll.md');

    // 打开测试文件
    const testFile = page.locator('.tree-item', { hasText: 'test-scroll.md' });
    await testFile.click();
    await page.waitForFunction(() => {
      const vd = window._vditor;
      return vd && vd.getValue().length > 100;
    }, { timeout: 10000 });

    // 滚动一下
    const editorEl = page.locator('.vditor-ir');
    await editorEl.evaluate((el) => {
      el.scrollTop = (el.scrollHeight - el.clientHeight) / 2;
    });
    await page.waitForTimeout(500);

    // 点击大纲中的标题，确保 headingText 被记录
    const outlineItem = page.locator('#outline-panel .outline-item', { hasText: '第二节' });
    if ((await outlineItem.count()) > 0) {
      await outlineItem.click();
      await page.waitForTimeout(300);
    }

    // 通过 API 直接打开欢迎文件（模拟文件切换，触发 saveCursorScrollToStorage）
    // 先通过 JS 调用 openFile 来切换
    await page.evaluate(() => {
      // 找到内置挂载点的欢迎文件并打开
      openFile('/欢迎.md', 'builtin-storage');
    });
    await page.waitForTimeout(1500);

    // 检查 localStorage
    const savedPos = await page.evaluate(() => localStorage.getItem('nasmd_cursor_pos'));
    expect(savedPos).not.toBeNull();
    const pos = JSON.parse(savedPos);
    expect(pos).toHaveProperty('scrollPercent');
    expect(pos).toHaveProperty('headingText');
  });

  test('打开新文件时光标位于顶部', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForSelector('.mount-name', { hasText: 'test-mount' }, { timeout: 10000 });
    await page.evaluate(() => toggleMount('mount-0'));
    await page.waitForTimeout(500);
    await waitForFileInTree(page, 'test-scroll.md');

    const testFile = page.locator('.tree-item', { hasText: 'test-scroll.md' });
    await testFile.click();
    await page.waitForFunction(() => {
      const vd = window._vditor;
      return vd && vd.getValue().length > 100;
    }, { timeout: 10000 });

    const editorEl = page.locator('.vditor-ir');
    await editorEl.evaluate((el) => { el.scrollTop = el.scrollHeight; });
    await page.waitForTimeout(500);

    // 通过 API 切换到欢迎文件
    await page.evaluate(() => openFile('/欢迎.md', 'builtin-storage'));
    await page.waitForTimeout(1500);

    // 新文件加载后，滚动位置应该在顶部
    const scrollTop = await editorEl.evaluate((el) => el.scrollTop);
    expect(scrollTop).toBeLessThan(50);
  });
});
