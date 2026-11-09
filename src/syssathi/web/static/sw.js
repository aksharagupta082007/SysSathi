// SysSathi Service Worker for offline asset support (Phase E §7.1)
const CACHE_NAME = "syssathi-v1";
const STATIC_ASSETS = [
  "/",
  "/static/manifest.json",
  "/static/icon.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      );
    })
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  // Only handle GET requests; let WebSocket and POST APIs bypass cache
  if (event.request.method !== "GET" || event.request.url.includes("/ws/") || event.request.url.includes("/api/")) {
    return;
  }

  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});

