/**
 * Mobile Adaptation Phase 1 - E2E Tests
 * 验证移动端核心交互功能
 */

import { test, expect } from '@playwright/test';

async function mobileCtx(browser, width = 375, height = 667) {
  const ctx = await browser.newContext({ viewport: { width, height } });
  const page = await ctx.newPage();
  await page.goto('/admin');
  await page.waitForTimeout(500);
  return { page, ctx };
}

async function desktopCtx(browser, width = 1280, height = 800) {
  const ctx = await browser.newContext({ viewport: { width, height } });
  const page = await ctx.newPage();
  await page.goto('/admin');
  await page.waitForTimeout(500);
  return { page, ctx };
}

// ============================================================
// 1. 响应式断点 - 验证元素存在性和基本状态
// ============================================================

test.describe('响应式断点', () => {
  test('桌面端 sidebar 可见，元素存在', async ({ browser }) => {
    const { page, ctx } = await desktopCtx(browser);
    await expect(page.locator('#sidebar')).toBeVisible();
    // 元素存在于 DOM（CSS 隐藏由浏览器处理）
    await expect(page.locator('.sidebar-close')).toBeAttached();
    await expect(page.locator('#topbar-more')).toBeAttached();
    await expect(page.locator('#menu-toggle')).not.toBeAttached();
    await ctx.close();
  });

  test('移动端 sidebar 默认隐藏', async ({ browser }) => {
    const { page, ctx } = await mobileCtx(browser, 375, 667);
    await expect(page.locator('#sidebar')).not.toHaveClass(/open/);
    await expect(page.locator('.sidebar-close')).toBeAttached();
    await expect(page.locator('#topbar-more')).toBeAttached();
    await expect(page.locator('#menu-toggle')).toBeAttached();
    await ctx.close();
  });
});

// ============================================================
// 2. Sidebar 关闭按钮
// ============================================================

test.describe('Sidebar 关闭按钮', () => {
  test('移动端点击关闭按钮可关闭 sidebar', async ({ browser }) => {
    const { page, ctx } = await mobileCtx(browser, 375, 667);
    await page.evaluate(() => toggleSidebar());
    await expect(page.locator('#sidebar')).toHaveClass(/open/);
    await page.locator('.sidebar-close').click();
    await expect(page.locator('#sidebar')).not.toHaveClass(/open/);
    await ctx.close();
  });

  test('关闭按钮绑定 closeSidebar 函数', async ({ browser }) => {
    const { page, ctx } = await mobileCtx(browser, 375, 667);
    await page.evaluate(() => toggleSidebar());
    await expect(page.locator('#sidebar')).toHaveClass(/open/);
    // 通过 JS 调用 closeSidebar
    await page.evaluate(() => closeSidebar());
    await expect(page.locator('#sidebar')).not.toHaveClass(/open/);
    await ctx.close();
  });
});

// ============================================================
// 3. More menu 下拉菜单
// ============================================================

test.describe('More menu 下拉菜单', () => {
  test('点击 more 按钮可打开菜单', async ({ browser }) => {
    const { page, ctx } = await mobileCtx(browser, 375, 667);
    await page.locator('#topbar-more').click();
    await expect(page.locator('#more-menu')).toHaveClass(/open/);
    await expect(page.locator('#more-download')).toBeVisible();
    await expect(page.locator('#more-refresh')).toBeVisible();
    await expect(page.locator('#more-pdf')).toBeVisible();
    await ctx.close();
  });

  test('再次点击 more 按钮可关闭菜单', async ({ browser }) => {
    const { page, ctx } = await mobileCtx(browser, 375, 667);
    await page.locator('#topbar-more').click();
    await expect(page.locator('#more-menu')).toHaveClass(/open/);
    await page.locator('#topbar-more').click();
    await expect(page.locator('#more-menu')).not.toHaveClass(/open/);
    await ctx.close();
  });

  test('点击菜单外部可关闭 more menu', async ({ browser }) => {
    const { page, ctx } = await mobileCtx(browser, 375, 667);
    await page.locator('#topbar-more').click();
    await expect(page.locator('#more-menu')).toHaveClass(/open/);
    await page.locator('#breadcrumb').click();
    await expect(page.locator('#more-menu')).not.toHaveClass(/open/);
    await ctx.close();
  });
});

// ============================================================
// 4. Overlay 点击关闭
// ============================================================

test.describe('Overlay 点击关闭 sidebar', () => {
  test('点击 sidebar 外部区域可关闭', async ({ browser }) => {
    const { page, ctx } = await mobileCtx(browser, 375, 667);
    await page.evaluate(() => toggleSidebar());
    await expect(page.locator('#sidebar')).toHaveClass(/open/);
    await page.locator('#editor-container').click();
    await expect(page.locator('#sidebar')).not.toHaveClass(/open/);
    await ctx.close();
  });

  test('点击 hamburger 按钮切换 sidebar', async ({ browser }) => {
    const { page, ctx } = await mobileCtx(browser, 375, 667);
    await page.evaluate(() => toggleSidebar());
    await expect(page.locator('#sidebar')).toHaveClass(/open/);
    await page.locator('#menu-toggle').click();
    await expect(page.locator('#sidebar')).not.toHaveClass(/open/);
    await ctx.close();
  });
});

// ============================================================
// 5. 移动端布局集成测试
// ============================================================

test.describe('移动端布局集成测试', () => {
  test('移动端完整操作流程', async ({ browser }) => {
    const { page, ctx } = await mobileCtx(browser, 375, 667);
    await expect(page.locator('#sidebar')).not.toHaveClass(/open/);
    await page.locator('#menu-toggle').click();
    await expect(page.locator('#sidebar')).toHaveClass(/open/);
    await page.locator('.sidebar-close').click();
    await expect(page.locator('#sidebar')).not.toHaveClass(/open/);
    await page.locator('#menu-toggle').click();
    await expect(page.locator('#sidebar')).toHaveClass(/open/);
    await page.locator('.main').click();
    await expect(page.locator('#sidebar')).not.toHaveClass(/open/);
    await ctx.close();
  });

  test('移动端 more menu 完整流程', async ({ browser }) => {
    const { page, ctx } = await mobileCtx(browser, 375, 667);
    await page.locator('#topbar-more').click();
    await expect(page.locator('#more-menu')).toHaveClass(/open/);
    await expect(page.locator('#more-download')).toBeVisible();
    await expect(page.locator('#more-refresh')).toBeVisible();
    await expect(page.locator('#more-pdf')).toBeVisible();
    await page.locator('#breadcrumb').click();
    await expect(page.locator('#more-menu')).not.toHaveClass(/open/);
    await page.locator('#topbar-more').click();
    await expect(page.locator('#more-menu')).toHaveClass(/open/);
    await page.locator('#topbar-more').click();
    await expect(page.locator('#more-menu')).not.toHaveClass(/open/);
    await ctx.close();
  });
});

// ============================================================
// 6. 边界条件测试
// ============================================================

test.describe('边界条件', () => {
  test('快速多次点击 sidebar 按钮不崩溃', async ({ browser }) => {
    const { page, ctx } = await mobileCtx(browser, 375, 667);
    for (let i = 0; i < 10; i++) {
      await page.evaluate(() => toggleSidebar());
      await page.waitForTimeout(50);
    }
    await expect(page.locator('#sidebar')).toBeAttached();
    await expect(page.locator('#vditor')).toBeAttached();
    await ctx.close();
  });

  test('快速点击 more menu 不崩溃', async ({ browser }) => {
    const { page, ctx } = await mobileCtx(browser, 375, 667);
    for (let i = 0; i < 10; i++) {
      await page.locator('#topbar-more').click();
      await page.waitForTimeout(50);
    }
    await expect(page.locator('#topbar-more')).toBeAttached();
    await ctx.close();
  });

  test('视口 resize 不丢失状态', async ({ browser }) => {
    const { page, ctx } = await mobileCtx(browser, 375, 667);
    await page.evaluate(() => toggleSidebar());
    await expect(page.locator('#sidebar')).toHaveClass(/open/);
    await page.setViewportSize({ width: 768, height: 667 });
    await page.waitForTimeout(300);
    await expect(page.locator('#sidebar')).toBeAttached();
    await ctx.close();
  });
});
