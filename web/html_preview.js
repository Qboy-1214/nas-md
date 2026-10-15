let previewFrame = null;

const MIME_TYPES = {
  '.avif': 'image/avif',
  '.css': 'text/css',
  '.gif': 'image/gif',
  '.htm': 'text/html',
  '.html': 'text/html',
  '.ico': 'image/x-icon',
  '.jpeg': 'image/jpeg',
  '.jpg': 'image/jpeg',
  '.js': 'text/javascript',
  '.json': 'application/json',
  '.mjs': 'text/javascript',
  '.mp3': 'audio/mpeg',
  '.mp4': 'video/mp4',
  '.ogg': 'audio/ogg',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.txt': 'text/plain',
  '.wasm': 'application/wasm',
  '.webp': 'image/webp',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
};

function extension(path) {
  const match = String(path)
    .toLowerCase()
    .match(/\.[a-z0-9]+$/);
  return match ? match[0] : '';
}

function clear() {
  previewFrame?.remove();
  previewFrame = null;
}

function normalizeResourcePath(documentPath, resource) {
  const raw = String(resource).trim();
  if (!raw || raw.startsWith('#') || raw.startsWith('//') || /^(?:[a-z][a-z\d+.-]*:)/i.test(raw)) {
    return { external: true, value: raw };
  }

  const pathPart = raw.split(/[?#]/, 1)[0];
  const suffix = raw.slice(pathPart.length);
  const baseSegments = pathPart.startsWith('/')
    ? []
    : documentPath.split('/').filter(Boolean).slice(0, -1);
  const segments = [...baseSegments];
  for (let segment of pathPart.split('/')) {
    if (!segment) continue;
    try {
      segment = decodeURIComponent(segment);
    } catch {
      // Keep malformed escapes as literal filename characters.
    }
    if (segment.includes('/') || segment.includes('\\')) return { rejected: true };
    if (segment === '.') continue;
    if (segment === '..') {
      if (segments.length === 0) return { rejected: true };
      segments.pop();
    } else {
      segments.push(segment);
    }
  }
  const normalizedPath = '/' + segments.join('/');
  return {
    path: normalizedPath,
    suffix,
  };
}

async function getLocalFile(mountId, path) {
  const localMount = window.state?.localMounts?.[mountId];
  if (!localMount) throw new Error('Local mount is unavailable');
  if (localMount.fileMap) return localMount.fileMap[path] || null;

  if (localMount.handle && typeof getLocalFileHandle === 'function') {
    const handle = await getLocalFileHandle(localMount.handle, path);
    return handle ? handle.getFile() : null;
  }
  return null;
}

async function asBlob(file, path) {
  const type = file.type || MIME_TYPES[extension(path)] || 'application/octet-stream';
  return new Blob([file], { type });
}

async function toDataUrl(blob) {
  // The iframe has an opaque origin by design. Chromium blocks parent-created
  // blob: URLs inside that origin, so inline MIME-correct data URLs instead.
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = '';
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
  }
  return `data:${blob.type || 'application/octet-stream'};base64,${btoa(binary)}`;
}

async function createResourceUrl(mountId, documentPath, resource, cssStack = new Set()) {
  const resolved = normalizeResourcePath(documentPath, resource);
  if (resolved.external) return resolved.value;
  if (resolved.rejected) return 'about:blank';

  const file = await getLocalFile(mountId, resolved.path);
  if (!file) return 'about:blank';
  const ext = extension(resolved.path);

  if (ext === '.css') {
    if (cssStack.has(resolved.path)) return 'about:blank';
    const nextStack = new Set(cssStack).add(resolved.path);
    const cssText = await file.text();
    const rewritten = await rewriteCss(cssText, mountId, resolved.path, nextStack);
    const cssBlob = new Blob([rewritten], { type: 'text/css' });
    return (await toDataUrl(cssBlob)) + (resolved.suffix.match(/#[^#]*$/)?.[0] || '');
  }

  return (
    (await toDataUrl(await asBlob(file, resolved.path))) +
    (resolved.suffix.match(/#[^#]*$/)?.[0] || '')
  );
}

async function rewriteCss(css, mountId, cssPath, cssStack) {
  const importPattern = /@import\s+(?:url\(\s*)?(["']?)([^"')\s;]+)\1\s*\)?([^;]*);/gi;
  let rewritten = '';
  let cursor = 0;
  for (const match of css.matchAll(importPattern)) {
    const index = match.index;
    rewritten += css.slice(cursor, index);
    const resource = match[2];
    const resolved = normalizeResourcePath(cssPath, resource);
    if (resolved.external || resolved.rejected || extension(resolved.path) !== '.css') {
      rewritten += match[0];
    } else if (!cssStack.has(resolved.path)) {
      const imported = await getLocalFile(mountId, resolved.path);
      if (imported) {
        const importedText = await rewriteCss(
          await imported.text(),
          mountId,
          resolved.path,
          new Set(cssStack).add(resolved.path),
        );
        const media = match[3].trim();
        rewritten += media ? `@media ${media} {${importedText}}` : importedText;
      }
    }
    cursor = index + match[0].length;
  }

  rewritten += css.slice(cursor);
  let result = '';
  cursor = 0;
  const urlPattern = /url\(\s*(["']?)([^"')]+)\1\s*\)/gi;
  for (const match of rewritten.matchAll(urlPattern)) {
    const index = match.index;
    result += rewritten.slice(cursor, index);
    const resourceUrl = await createResourceUrl(mountId, cssPath, match[2].trim(), cssStack);
    result += `url(${match[1]}${resourceUrl}${match[1]})`;
    cursor = index + match[0].length;
  }
  return result + rewritten.slice(cursor);
}

async function rewriteSrcset(mountId, documentPath, value) {
  const entries = value.split(',');
  const rewritten = await Promise.all(
    entries.map(async (entry) => {
      const [url, ...descriptor] = entry.trim().split(/\s+/);
      return `${await createResourceUrl(mountId, documentPath, url)}${descriptor.length ? ' ' + descriptor.join(' ') : ''}`;
    }),
  );
  return rewritten.join(', ');
}

async function prepareLocalHtml(mountId, path, content) {
  const parsed = new DOMParser().parseFromString(content, 'text/html');
  parsed.querySelectorAll('base, meta[http-equiv="refresh" i]').forEach((el) => el.remove());

  const resourceAttributes = ['src', 'href', 'poster', 'data', 'xlink:href'];
  for (const element of parsed.querySelectorAll('*')) {
    for (const attribute of resourceAttributes) {
      if (!element.hasAttribute(attribute)) continue;
      const value = element.getAttribute(attribute);
      if (!value) continue;
      element.setAttribute(attribute, await createResourceUrl(mountId, path, value));
    }
    if (element.hasAttribute('srcset')) {
      element.setAttribute(
        'srcset',
        await rewriteSrcset(mountId, path, element.getAttribute('srcset')),
      );
    }
    if (element.hasAttribute('style')) {
      element.setAttribute(
        'style',
        await rewriteCss(element.getAttribute('style'), mountId, path, new Set()),
      );
    }
    if (element.tagName === 'STYLE') {
      element.textContent = await rewriteCss(element.textContent, mountId, path, new Set());
    }
  }
  return '<!doctype html>' + parsed.documentElement.outerHTML;
}

async function show({ mount, path, content }) {
  clear();
  if (!mount || !mount.id) throw new Error('A mount is required to preview HTML');

  const iframe = document.createElement('iframe');
  iframe.id = 'nasmd-html-preview';
  iframe.title = 'HTML preview';
  iframe.setAttribute('sandbox', 'allow-scripts');
  iframe.style.cssText = 'display:block;width:100%;height:100%;border:0';

  if (mount._local || window.state?.localMounts?.[mount.id]) {
    const html = await prepareLocalHtml(mount.id, path, content || '');
    iframe.src = await toDataUrl(new Blob([html], { type: 'text/html' }));
  } else {
    iframe.src = API.previewResourceUrl(mount.id, path);
  }

  previewFrame = iframe;
  document.body.appendChild(iframe);
}

window.nasmdHtmlPreview = { show, clear };
