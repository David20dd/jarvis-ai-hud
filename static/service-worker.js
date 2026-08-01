const CACHE_NAME = 'jarvis-adaptive-workspace-v104-1';
// Replaces jarvis-conversation-ui-v103-1 after a clean activation.
const APP_SHELL = [
  './',
  './index.html',
  './404.html',
  './static/styles.css?v=101.0',
  './static/v76.css?v=101.0',
  './static/v77.css?v=101.0',
  './static/v82.css?v=101.0',
  './static/v93.css?v=101.0',
  './static/v100.css?v=101.0',
  './static/v101.css?v=101.0',
  './static/v101-chat.css?v=101.1',
  './static/v101-pro-chat.css?v=101.2',
  './static/v101-modern-chat.css?v=101.3.4',
  './static/v102.css?v=102.0',
  './static/v103-conversation.css?v=103.0',
  './static/v104-adaptive.css?v=104.0',
  './static/app.js?v=101.0',
  './static/v76.js?v=101.0',
  './static/v100.js?v=101.0',
  './static/v101.js?v=101.0',
  './static/v102.js?v=102.0',
  './static/v104.js?v=104.0',
  './static/config.js?v=101.0',
  './static/manifest.webmanifest?v=101.0',
  './static/favicon-v46.svg',
  './static/jarvis-reactor-v46.svg'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(APP_SHELL))
      .then(() => self.skipWaiting())
  );
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
  if (url.pathname.includes('/api/')) return;

  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then(response => {
          if (response.ok) caches.open(CACHE_NAME).then(cache => cache.put('./index.html', response.clone()));
          return response;
        })
        .catch(() => caches.match('./index.html'))
    );
    return;
  }

  event.respondWith(
    caches.match(request).then(cached => {
      const fresh = fetch(request).then(response => {
        if (response.ok && url.origin === self.location.origin) {
          caches.open(CACHE_NAME).then(cache => cache.put(request, response.clone()));
        }
        return response;
      });
      return cached || fresh;
    })
  );
});
