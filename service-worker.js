const CACHE_NAME = 'jarvis-advanced-core-v16';
const SHELL = [
  './',
  './index.html',
  './404.html',
  './static/styles.css?v=16',
  './static/app.js?v=16',
  './static/config.js?v=16',
  './static/manifest.webmanifest?v=16',
  './static/favicon-32.png',
  './static/favicon-64.png',
  './static/apple-touch-icon.png',
  './static/icon-192.png',
  './static/icon-512.png',
  './static/jarvis-reactor-v10.webp',
  './static/jarvis-reactor-v10.png'
];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then(response => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put('./index.html', clone));
          return response;
        })
        .catch(() => caches.match('./index.html'))
    );
    return;
  }

  event.respondWith(
    caches.match(request).then(cached => {
      const network = fetch(request)
        .then(response => {
          if (response.ok) caches.open(CACHE_NAME).then(cache => cache.put(request, response.clone()));
          return response;
        })
        .catch(() => cached);
      return cached || network;
    })
  );
});
