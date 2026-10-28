import { test, expect } from '@playwright/test';

/**
 * 侧边栏宽度拖拽（#sidebar-resizer）回归测试。
 * 历史缺陷：拖动宽度不跟手 / 停顿后卡住（width 过渡动画吃掉增量、4px 热区失手）。
 * 手势序列：按下 → 向右拖 → 按住停顿 800ms → 继续向右拖，宽度必须全程跟随。
 */
async function sidebarWidth(page) {
  return page.$eval('#sidebar', (el) => el.getBoundingClientRect().width);
}

test('拖拽侧边栏宽度：停顿后继续拖动仍跟手', async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 900 });
  await page.goto('/');
  const resizer = page.locator('#sidebar-resizer');
  await expect(resizer).toBeVisible();

  const w0 = await sidebarWidth(page);
  const box = await resizer.boundingBox();
  const y = box.y + box.height / 2;
  const startX = box.x + box.width / 2;

  // 阶段 1：按下并右拖 100px
  await page.mouse.move(startX, y);
  await page.mouse.down();
  await page.mouse.move(startX + 40, y, { steps: 8 });
  await page.mouse.move(startX + 100, y, { steps: 8 });
  const w1 = await sidebarWidth(page);
  expect(w1).toBeGreaterThan(w0 + 80);

  // 阶段 2：按住不动停 800ms（模拟“停下来一会儿”）
  await page.waitForTimeout(800);

  // 阶段 3：继续右拖 80px，宽度必须继续跟随
  await page.mouse.move(startX + 100, y);
  await page.mouse.move(startX + 180, y, { steps: 8 });
  const w2 = await sidebarWidth(page);
  expect(w2).toBeGreaterThan(w1 + 60);

  // 阶段 4：向左拖回，双向都跟手
  await page.mouse.move(startX + 100, y, { steps: 8 });
  const w3 = await sidebarWidth(page);
  expect(w3).toBeLessThan(w2 - 60);

  await page.mouse.up();

  // 松手后宽度已持久化
  const saved = await page.evaluate(() => localStorage.getItem('nasmd_sidebar_width'));
  expect(Number(saved)).toBeGreaterThan(0);
});

test('松手后在 resizer 附近重新按下可以继续拖拽（橡皮筋热区）', async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 900 });
  await page.goto('/');
  const resizer = page.locator('#sidebar-resizer');
  await expect(resizer).toBeVisible();

  const w0 = await sidebarWidth(page);
  let box = await resizer.boundingBox();
  const y = box.y + box.height / 2;

  // 先拖一次让侧边栏变宽（resizer 随之右移）
  let startX = box.x + box.width / 2;
  await page.mouse.move(startX, y);
  await page.mouse.down();
  await page.mouse.move(startX + 120, y, { steps: 10 });
  await page.mouse.up();

  // 重新定位：光标停在 resizer 左侧 8px（已飘出 4px 细条但仍在热区内）
  box = await resizer.boundingBox();
  const grabX = box.x + box.width - 8;
  const w1 = await sidebarWidth(page);

  await page.mouse.move(grabX, y);
  await page.mouse.down();
  await page.mouse.move(grabX + 80, y, { steps: 8 });
  const w2 = await sidebarWidth(page);
  expect(w2).toBeGreaterThan(w1 + 60);
  expect(w2).toBeGreaterThan(w0 + 100);
  await page.mouse.up();
});
