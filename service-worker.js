const CACHE_NAME = 'jarvis-multiprovider-core-v19';
const CORE = [
  './', './index.html', './404.html',
  './static/styles.css?v=19', './static/app.js?v=19', './static/config.js?v=19',
  './static/manifest.webmanifest?v=19', './static/favicon-32.png',
  './static/jarvis-reactor-v18.webp', './static/jarvis-reactor-v18.png'
];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(CORE)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.pathname.includes('/api/')) return;
  event.respondWith(
    fetch(request).then(response => {
      if (response.ok && url.origin === self.location.origin) {
        const copy = response.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(request, copy));
      }
      return response;
    }).catch(() => caches.match(request).then(hit => hit || caches.match('./index.html')))
  );
});
