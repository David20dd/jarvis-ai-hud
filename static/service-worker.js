const CACHE_NAME = 'jarvis-cinematic-ui-static-v29';
const CORE = [
  './', './index.html',
  './styles.css?v=29', './app.js?v=29', './config.js?v=29',
  './manifest.webmanifest?v=29', './favicon-v29.svg?v=29',
  './jarvis-reactor-v29.svg'
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
