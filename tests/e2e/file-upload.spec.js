import { test, expect } from '@playwright/test';
import { getWritableAdminMount, putAdminFile } from './helpers/admin.js';

const PNG_BYTES = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
  'base64',
);

async function openMarkdownFile(page, mountId, path) {
  await putAdminFile(page, mountId, path, '# Upload Test\n\n');
  await page.evaluate(
    async ({ fileMountId, filePath }) => {
      await openFile(filePath, fileMountId);
    },
    { fileMountId: mountId, filePath: path },
  );
  await page.waitForFunction(
    ({ fileMountId, filePath }) =>
      window.state?.currentMountId === fileMountId &&
      window.state?.currentPath === filePath &&
      window._vditor &&
      document.querySelector('#vditor .vditor-toolbar'),
    { fileMountId: mountId, filePath: path },
  );
}

async function deleteAdminFileQuietly(page, mountId, path) {
  await page.request.delete(`/api/mounts/${mountId}/file?path=${encodeURIComponent(path)}`, {
    headers: { 'X-Admin': '1' },
  });
}

test('toolbar image upload stores the file under imgs and inserts a relative link', async ({
  page,
}) => {
  const mount = await getWritableAdminMount(page);
  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const markdownPath = `/image-upload-${suffix}.md`;
  const imageName = `toolbar-${suffix}.png`;
  const imagePath = `/imgs/${imageName}`;

  try {
    await openMarkdownFile(page, mount.id, markdownPath);

    const uploadInput = page.locator('#vditor input[type="file"]').first();
    await expect(uploadInput).toBeAttached();
    await uploadInput.setInputFiles({
      name: imageName,
      mimeType: 'image/png',
      buffer: PNG_BYTES,
    });

    await expect
      .poll(() => page.evaluate(() => window._vditor.getValue()))
      .toContain(`![${imageName}](imgs/${imageName})`);

    const response = await page.request.get(
      `/api/mounts/${mount.id}/file?path=${encodeURIComponent(imagePath)}`,
      { headers: { 'X-Admin': '1' } },
    );
    expect(response.ok()).toBeTruthy();
    expect(Buffer.compare(await response.body(), PNG_BYTES)).toBe(0);

    await page.evaluate((mountId) => {
      if (!state.expandedMounts.includes(mountId)) return toggleMount(mountId);
    }, mount.id);
    const tree = page.locator('#file-tree');
    const imgsFolder = tree.locator('.tree-folder[title="imgs"]').first();
    await expect(imgsFolder).toBeVisible();
    await imgsFolder.click();
    const imageItem = tree.locator('.tree-item.image-file').filter({ hasText: imageName });
    await expect(imageItem).toBeVisible();
    await imageItem.click();
    const preview = page.locator('.image-preview-overlay');
    await expect(preview.locator('img')).toHaveAttribute(
      'src',
      new RegExp(
        `/api/mounts/${mount.id}/preview/imgs/${imageName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`,
      ),
    );
    await preview.getByRole('button', { name: '关闭图片预览' }).click();
  } finally {
    await deleteAdminFileQuietly(page, mount.id, imagePath);
    await deleteAdminFileQuietly(page, mount.id, markdownPath);
  }
});

test('pasted image is uploaded through the same imgs flow', async ({ page }) => {
  const mount = await getWritableAdminMount(page);
  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const markdownPath = `/image-paste-${suffix}.md`;
  const imageName = `pasted-${suffix}.png`;
  const imagePath = `/imgs/${imageName}`;

  try {
    await openMarkdownFile(page, mount.id, markdownPath);

    const dispatched = await page.evaluate(
      ({ name, imageBase64 }) => {
        const bytes = Uint8Array.from(atob(imageBase64), (char) => char.charCodeAt(0));
        const transfer = new DataTransfer();
        transfer.items.add(new File([bytes], name, { type: 'image/png' }));
        const mode = window._vditor.getCurrentMode();
        const editor = window._vditor.vditor[mode].element;
        const event = new Event('paste', { bubbles: true, cancelable: true });
        Object.defineProperty(event, 'clipboardData', { value: transfer });
        editor.dispatchEvent(event);
        return editor.isConnected;
      },
      { name: imageName, imageBase64: PNG_BYTES.toString('base64') },
    );
    expect(dispatched).toBeTruthy();

    await expect
      .poll(() => page.evaluate(() => window._vditor.getValue()))
      .toContain(`![${imageName}](imgs/${imageName})`);

    const response = await page.request.get(
      `/api/mounts/${mount.id}/file?path=${encodeURIComponent(imagePath)}`,
      { headers: { 'X-Admin': '1' } },
    );
    expect(response.ok()).toBeTruthy();
    expect(Buffer.compare(await response.body(), PNG_BYTES)).toBe(0);
  } finally {
    await deleteAdminFileQuietly(page, mount.id, imagePath);
    await deleteAdminFileQuietly(page, mount.id, markdownPath);
  }
});

test('pasted screenshot HTML data URI is uploaded instead of inserted inline', async ({ page }) => {
  const mount = await getWritableAdminMount(page);
  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const markdownPath = `/image-data-uri-paste-${suffix}.md`;
  let uploadedPath = '';

  try {
    await openMarkdownFile(page, mount.id, markdownPath);

    const dispatched = await page.evaluate(
      ({ imageBase64 }) => {
        const transfer = new DataTransfer();
        transfer.setData('text/html', `<img src="data:image/png;base64,${imageBase64}">`);
        const mode = window._vditor.getCurrentMode();
        const editor = window._vditor.vditor[mode].element;
        const event = new Event('paste', { bubbles: true, cancelable: true });
        Object.defineProperty(event, 'clipboardData', { value: transfer });
        editor.dispatchEvent(event);
        return {
          connected: editor.isConnected,
          defaultPrevented: event.defaultPrevented,
        };
      },
      { imageBase64: PNG_BYTES.toString('base64') },
    );
    expect(dispatched.connected).toBeTruthy();
    expect(dispatched.defaultPrevented).toBeTruthy();

    await expect.poll(() => page.evaluate(() => window._vditor.getValue())).toContain('](imgs/');

    const markdown = await page.evaluate(() => window._vditor.getValue());
    expect(markdown).not.toContain('data:image');
    const match = markdown.match(/!\[[^\]]*\]\(imgs\/([^)]+)\)/);
    expect(match).not.toBeNull();
    uploadedPath = `/imgs/${decodeURIComponent(match[1])}`;

    const response = await page.request.get(
      `/api/mounts/${mount.id}/file?path=${encodeURIComponent(uploadedPath)}`,
      { headers: { 'X-Admin': '1' } },
    );
    expect(response.ok()).toBeTruthy();
    expect(Buffer.compare(await response.body(), PNG_BYTES)).toBe(0);
  } finally {
    if (uploadedPath) await deleteAdminFileQuietly(page, mount.id, uploadedPath);
    await deleteAdminFileQuietly(page, mount.id, markdownPath);
  }
});

test('image preview can delete a writable image from the sidebar', async ({ page }) => {
  const mount = await getWritableAdminMount(page);
  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const markdownPath = `/image-delete-${suffix}.md`;
  const imageName = `deletable-${suffix}.png`;
  const imagePath = `/imgs/${imageName}`;

  try {
    await openMarkdownFile(page, mount.id, markdownPath);
    await page.locator('#vditor input[type="file"]').first().setInputFiles({
      name: imageName,
      mimeType: 'image/png',
      buffer: PNG_BYTES,
    });
    await expect
      .poll(() => page.evaluate(() => window._vditor.getValue()))
      .toContain(`![${imageName}](imgs/${imageName})`);

    await page.evaluate((mountId) => {
      if (!state.expandedMounts.includes(mountId)) return toggleMount(mountId);
    }, mount.id);
    const tree = page.locator('#file-tree');
    const imgsFolder = tree.locator('.tree-folder[title="imgs"]').first();
    await imgsFolder.click();
    const imageItem = tree.locator('.tree-item.image-file').filter({ hasText: imageName });
    await imageItem.click();

    const preview = page.locator('.image-preview-overlay');
    await expect(preview).toBeVisible();
    page.once('dialog', async (dialog) => {
      expect(dialog.type()).toBe('confirm');
      await dialog.accept();
    });
    await preview.getByRole('button', { name: '删除图片' }).click();

    await expect(preview).not.toBeAttached();
    await expect(imageItem).toHaveCount(0);
    const response = await page.request.get(
      `/api/mounts/${mount.id}/file?path=${encodeURIComponent(imagePath)}`,
      { headers: { 'X-Admin': '1' } },
    );
    expect(response.status()).toBe(404);
  } finally {
    await deleteAdminFileQuietly(page, mount.id, imagePath);
    await deleteAdminFileQuietly(page, mount.id, markdownPath);
  }
});

test('toolbar image upload inserts the link in wysiwyg and split modes', async ({ page }) => {
  const mount = await getWritableAdminMount(page);
  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const markdownPath = `/image-modes-${suffix}.md`;
  const uploadedPaths = [];

  try {
    await openMarkdownFile(page, mount.id, markdownPath);

    for (const mode of ['wysiwyg', 'sv']) {
      await page.evaluate((nextMode) => setEditorMode(nextMode), mode);
      await page.waitForFunction(
        (nextMode) =>
          window.state?.editorMode === nextMode &&
          window._vditor?.getCurrentMode() === nextMode &&
          document.querySelector('#vditor input[type="file"]'),
        mode,
      );

      const imageName = `${mode}-${suffix}.png`;
      uploadedPaths.push(`/imgs/${imageName}`);
      await page.locator('#vditor input[type="file"]').first().setInputFiles({
        name: imageName,
        mimeType: 'image/png',
        buffer: PNG_BYTES,
      });

      await expect
        .poll(() => page.evaluate(() => window._vditor.getValue()))
        .toContain(`![${imageName}](imgs/${imageName})`);
    }
  } finally {
    for (const imagePath of uploadedPaths) {
      await deleteAdminFileQuietly(page, mount.id, imagePath);
    }
    await deleteAdminFileQuietly(page, mount.id, markdownPath);
  }
});

test('sidebar drop uploads a non-document file without corrupting its bytes', async ({ page }) => {
  const mount = await getWritableAdminMount(page);
  const fileName = `sidebar-drop-${Date.now()}-${Math.random().toString(16).slice(2)}.bin`;
  const filePath = `/${fileName}`;
  const payload = [0, 1, 2, 3, 127, 128, 254, 255];

  try {
    const result = await page.evaluate(
      async ({ mountId, name, bytes }) => {
        const target = document.createElement('div');
        target.dataset.dropMount = mountId;
        target.dataset.dropPath = '/';
        document.getElementById('file-tree').appendChild(target);

        const transfer = new DataTransfer();
        transfer.items.add(
          new File([new Uint8Array(bytes)], name, { type: 'application/octet-stream' }),
        );

        try {
          target.dispatchEvent(
            new DragEvent('drop', {
              bubbles: true,
              cancelable: true,
              dataTransfer: transfer,
            }),
          );
          await new Promise((resolve) => setTimeout(resolve, 10));
          while (window.state._fileOpInProgress) {
            await new Promise((resolve) => setTimeout(resolve, 10));
          }
          await new Promise((resolve) => setTimeout(resolve, 0));
          return document.getElementById('toast').textContent;
        } finally {
          target.remove();
        }
      },
      { mountId: mount.id, name: fileName, bytes: payload },
    );
    expect(result).toBe(`已导入: ${fileName}`);

    const response = await page.request.get(
      `/api/mounts/${mount.id}/file?path=${encodeURIComponent(filePath)}`,
      { headers: { 'X-Admin': '1' } },
    );
    expect(response.ok()).toBeTruthy();
    expect(Array.from(await response.body())).toEqual(payload);
  } finally {
    await deleteAdminFileQuietly(page, mount.id, filePath);
  }
});

test('dragging a folder into the sidebar creates its tree and nested files', async ({ page }) => {
  const mount = await getWritableAdminMount(page);
  const folderName = `folder-drop-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const folderPath = `/${folderName}`;
  const imagePaths = [`${folderPath}/cover.png`, `${folderPath}/nested/detail.png`];

  try {
    const result = await page.evaluate(
      async ({ mountId, rootName, imageBase64 }) => {
        const bytes = Uint8Array.from(atob(imageBase64), (char) => char.charCodeAt(0));
        const makeFileEntry = (name) => ({
          isFile: true,
          isDirectory: false,
          name,
          file(resolve) {
            resolve(new File([bytes], name, { type: 'image/png' }));
          },
        });
        const makeDirectoryEntry = (name, children) => ({
          isFile: false,
          isDirectory: true,
          name,
          createReader() {
            let read = false;
            return {
              readEntries(resolve) {
                if (read) {
                  resolve([]);
                  return;
                }
                read = true;
                resolve(children);
              },
            };
          },
        });

        const folder = makeDirectoryEntry(rootName, [
          makeFileEntry('cover.png'),
          makeDirectoryEntry('nested', [makeFileEntry('detail.png')]),
        ]);
        const transfer = {
          types: ['Files'],
          files: [],
          items: [{ kind: 'file', webkitGetAsEntry: () => folder }],
        };

        const target = document.createElement('div');
        target.dataset.dropMount = mountId;
        target.dataset.dropPath = '/';
        document.getElementById('file-tree').appendChild(target);

        try {
          const event = new Event('drop', { bubbles: true, cancelable: true });
          Object.defineProperty(event, 'dataTransfer', { value: transfer });
          target.dispatchEvent(event);
          await new Promise((resolve) => setTimeout(resolve, 10));
          while (window.state._fileOpInProgress) {
            await new Promise((resolve) => setTimeout(resolve, 10));
          }
          return document.getElementById('toast').textContent;
        } finally {
          target.remove();
        }
      },
      { mountId: mount.id, rootName: folderName, imageBase64: PNG_BYTES.toString('base64') },
    );

    expect(result).toBe('已导入 2 个文件');
    for (const imagePath of imagePaths) {
      const response = await page.request.get(
        `/api/mounts/${mount.id}/file?path=${encodeURIComponent(imagePath)}`,
        { headers: { 'X-Admin': '1' } },
      );
      expect(response.ok()).toBeTruthy();
      expect(Buffer.compare(await response.body(), PNG_BYTES)).toBe(0);
    }
  } finally {
    await deleteAdminFileQuietly(page, mount.id, folderPath);
  }
});
