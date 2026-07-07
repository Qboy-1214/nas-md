import { test, expect } from '@playwright/test';

test('debug: check mount _local property', async ({ page }) => {
  await page.goto('/admin');
  await page.waitForSelector('.mount-name', { timeout: 10000 });

  const mountInfo = await page.evaluate(() => {
    return state.mounts.map((m) => ({
      id: m.id,
      name: m.name,
      _local: m._local,
      host: m.host,
      owner: m.owner,
      path: m.path,
      hasHandle: !!state.localMounts[m.id],
    }));
  });
  console.log('MOUNTS:', JSON.stringify(mountInfo, null, 2));

  // Check if work_TEST and work_PM are _local
  const workTest = mountInfo.find((m) => m.name === 'work_TEST');
  const workPM = mountInfo.find((m) => m.name === 'work_PM');

  console.log('work_TEST:', JSON.stringify(workTest, null, 2));
  console.log('work_PM:', JSON.stringify(workPM, null, 2));

  expect(true).toBe(true);
});
