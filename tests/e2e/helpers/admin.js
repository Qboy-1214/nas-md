import { expect } from '@playwright/test';

const adminOptions = { headers: { 'X-Admin': '1' } };

export async function getWritableAdminMount(page) {
  await page.goto('/admin');
  await page.waitForFunction(() => window.state?.mounts?.length > 0);
  const mount = await page.evaluate(() => {
    const item = window.state.mounts.find((candidate) => !candidate.readonly && !candidate._local);
    return item ? { id: item.id, name: item.name } : null;
  });
  expect(mount, 'configured writable server mount').not.toBeNull();
  return mount;
}

export async function putAdminFile(page, mountId, path, content) {
  const response = await page.request.put(
    `/api/mounts/${mountId}/file?path=${encodeURIComponent(path)}`,
    { ...adminOptions, data: content },
  );
  expect(response.ok(), `PUT ${path}: ${response.status()}`).toBeTruthy();
  return response;
}

export async function deleteAdminFile(page, mountId, path) {
  const response = await page.request.delete(
    `/api/mounts/${mountId}/file?path=${encodeURIComponent(path)}`,
    adminOptions,
  );
  expect(response.ok(), `DELETE ${path}: ${response.status()}`).toBeTruthy();
}
