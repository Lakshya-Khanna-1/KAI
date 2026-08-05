const CACHE_NAME = 'kai-pwa-v12';
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/style.css',
  '/app.js',
  '/manifest.json'
];

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => caches.delete(key))
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET' || event.request.url.includes('/api/') || event.request.url.includes('/notify/')) {
    return;
  }
  // Network first strategy to ensure code updates reflect immediately
  event.respondWith(
    fetch(event.request).catch(() => {
      return caches.match(event.request);
    })
  );
});

self.addEventListener('push', (event) => {
  const data = event.data ? event.data.json() : { title: 'KAI Assistant', body: 'New notification' };
  const options = {
    body: data.body || data.message || '',
    icon: 'data:image/svg+xml,<svg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 100 100\'><rect width=\'100\' height=\'100\' rx=\'25\' fill=\'%236366F1\'/><text x=\'50\' y=\'68\' font-size=\'50\' font-weight=\'bold\' text-anchor=\'middle\' fill=\'white\'>K</text></svg>',
    badge: 'data:image/svg+xml,<svg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 100 100\'><rect width=\'100\' height=\'100\' rx=\'25\' fill=\'%236366F1\'/></svg>',
    data: data
  };
  event.waitUntil(self.registration.showNotification(data.title || 'KAI', options));
});
