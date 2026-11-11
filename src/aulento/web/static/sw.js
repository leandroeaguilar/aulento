// Service Worker para Aulento PWA (Local-First)
const CACHE_NAME = 'aulento-v4';
// Todo lo que carga index.html (lo controla tests/test_componentes_estatico.py)
const STATIC_ASSETS = [
  '/',
  '/static/manifest.json',
  '/static/icons/icon.svg',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/vendor/mermaid.min.js',
  '/static/vendor/marked.min.js',
  '/static/vendor/purify.min.js',
  '/static/css/tailwind.css',
  '/static/componentes.css',
  '/static/movil.css',
  '/static/componentes.js',
  '/static/capacidades.js',
  '/static/js/00-base.js',
  '/static/js/comunes.js',
  '/static/js/pantalla-courses.js',
  '/static/js/pantalla-schedule.js',
  '/static/js/pantalla-fsrs.js',
  '/static/js/pantalla-brain.js',
  '/static/js/pantalla-dashboard.js',
  '/static/js/pantalla-exams.js',
  '/static/js/pantalla-notes.js',
  '/static/js/pantalla-roadmap.js',
  '/static/js/pantalla-books.js',
  '/static/js/pantalla-config.js',
  '/static/app.js',
  '/static/mcp-remoto.js'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch((err) => {
        console.warn('Advertencia al precachear recursos estáticos:', err);
      });
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Todo endpoint de API y rutas dinámicas: Network first (siempre fresco)
  if (url.pathname.startsWith('/api/') || event.request.method !== 'GET') {
    return;
  }

  event.respondWith(
    fetch(event.request).catch(() => {
      // Los archivos se piden con ?v=… y se precachean sin él
      return caches.match(event.request, { ignoreSearch: true });
    })
  );
});
