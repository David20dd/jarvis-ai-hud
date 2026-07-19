const CACHE_NAME = 'jarvis-professional-core-static-v22';
const CORE = [
  './', './index.html', './styles.css?v=22', './app.js?v=22', './config.js?v=22',
  './manifest.webmanifest?v=22', './favicon-32.png', './jarvis-reactor-v18.webp', './jarvis-reactor-v18.png'
];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(CORE)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  if (url.pathname.includes('/api/')) return;
  event.respondWith(fetch(event.request).then(response => {
    if (response.ok && url.origin === self.location.origin) caches.open(CACHE_NAME).then(cache => cache.put(event.request, response.clone()));
    return response;
  }).catch(() => caches.match(event.request).then(hit => hit || caches.match('./index.html'))));
});
