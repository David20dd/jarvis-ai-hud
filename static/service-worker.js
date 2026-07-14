const CACHE_NAME = 'jarvis-advanced-core-static-v16';
const SHELL = [
  './',
  './index.html',
  './styles.css?v=16',
  './app.js?v=16',
  './config.js?v=16',
  './manifest.webmanifest?v=16',
  './favicon-32.png',
  './favicon-64.png',
  './apple-touch-icon.png',
  './icon-192.png',
  './icon-512.png',
  './jarvis-reactor-v10.webp',
  './jarvis-reactor-v10.png'
];
self.addEventListener('install', event => event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting())));
self.addEventListener('activate', event => event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key)))).then(() => self.clients.claim())));
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  if (event.request.mode === 'navigate') {
    event.respondWith(fetch(event.request).catch(() => caches.match('./index.html')));
    return;
  }
  event.respondWith(caches.match(event.request).then(cached => cached || fetch(event.request).then(response => {
    if (response.ok) caches.open(CACHE_NAME).then(cache => cache.put(event.request, response.clone()));
    return response;
  })));
});
