/**
 * sw.js - Service Worker for nas-md
 *
 * Strategy:
 * - Static assets (CSS, JS, fonts, images): Cache-First
 * - API requests (/api/*): Network-First with cache fallback
 * - Pages (/, /admin): Stale-While-Revalidate
 */
'use strict';

const CACHE_NAME = 'nasmd-v1';
const DATA_CACHE_NAME = 'nasmd-data-v1';

// Static assets to cache on install
const STATIC_ASSETS = [
  '/',
  '/admin',
  '/admin?homescreen=1',
  '/app.css',
  '/app.js?v=2',
  '/editor.js',
  '/files.js',
  '/identity.js',
  '/sync_layer.js',
  '/sse_client.js',
  '/version_history.js',
  '/mermaid_enhancer.js',
  '/highlight.css',
  '/manifest.json',
  '/icons/icon.svg',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
  '/icons/icon-maskable-192.png',
  '/icons/icon-maskable-512.png',
  '/lib/fonts/inter.css',
  '/lib/fonts/inter-temp/web/InterVariable.woff2',
  '/lib/vditor/index.min.js',
  '/lib/vditor/index.css',
  '/lib/d3/d3.min.js',
  '/lib/htmx.min.js',
  '/lib/alpine.min.js',
];

// === Install: precache all static assets ===
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS);
    }).catch((err) => {
      console.warn('[SW] Install cache failed:', err);
    })
  );
  // Activate immediately
  self.skipWaiting();
});

// === Activate: clean old caches ===
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys
          .filter((k) => k !== CACHE_NAME && k !== DATA_CACHE_NAME)
          .map((k) => caches.delete(k))
      );
    })
  );
  // Take control of all clients immediately
  self.clients.claim();
});

// === Fetch: strategy by request type ===
self.addEventListener('fetch', (event) => {
  const { request } = event;

  // Skip non-GET requests
  if (request.method !== 'GET') return;

  const url = new URL(request.url);

  // API requests: Network-First with cache fallback
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirst(request));
    return;
  }

  // SSE connections: always go to network (don't cache event streams)
  if (url.pathname.startsWith('/api/events')) {
    event.respondWith(fetch(request));
    return;
  }

  // Static assets and pages: Cache-First with network fallback
  event.respondWith(cacheFirst(request));
});

// === Cache-First Strategy ===
async function cacheFirst(request) {
  const cache = await caches.open(CACHE_NAME);

  // Try cache first
  const cached = await cache.match(request);
  if (cached) {
    // Update cache in background (stale-while-revalidate)
    const fetchPromise = fetch(request).then((networkResponse) => {
      if (networkResponse.ok) {
        cache.put(request, networkResponse.clone());
      }
    }).catch(() => {});
    // Don't await — return cached immediately
    fetchPromise.catch(() => {});
    return cached;
  }

  // Not in cache — try network
  try {
    const response = await fetch(request);
    if (response.ok) {
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    // Network unavailable — return a simple offline page
    return new Response(
      '<html><body style="background:#0a1530;color:#fff;text-align:center;padding:40px;font-family:system-ui">' +
      '<h2>nas-md</h2>' +
      '<p>离线模式 — 部分内容可能不可用</p>' +
      '<p style="font-size:12px;color:#888">请检查网络连接后刷新</p>' +
      '</body></html>',
      {
        headers: { 'Content-Type': 'text/html; charset=utf-8' },
      }
    );
  }
}

// === Network-First Strategy (for API) ===
async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      // Cache successful responses
      const cache = await caches.open(DATA_CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    // Network failed — try cache
    const cache = await caches.open(DATA_CACHE_NAME);
    const cached = await cache.match(request);
    if (cached) {
      return cached;
    }
    // Nothing cached — return offline error
    return new Response(
      JSON.stringify({ error: 'offline', message: 'No network connection available' }),
      {
        headers: { 'Content-Type': 'application/json' },
        status: 503,
      }
    );
  }
}

// === Message handler for cache management from app ===
self.addEventListener('message', (event) => {
  const data = event.data;

  if (data.action === 'clearCache') {
    caches.open(CACHE_NAME).then((cache) => cache.delete(request)).then(() => {
      self.postMessage({ success: true });
    });
  }

  if (data.action === 'updateCache') {
    const url = data.url;
    caches.open(CACHE_NAME).then((cache) => {
      return cache.add(url);
    }).then(() => {
      self.postMessage({ success: true });
    }).catch((err) => {
      self.postMessage({ success: false, error: err.message });
    });
  }
});
