// Bump CACHE_NAME any time this file changes so old caches get evicted
const CACHE_NAME = 'mm-player-tourney-v3';
const CORE_ASSETS = [
  './',
  './index.html',
  './players.json',
  './insights.json',
  './icon-192.png',
  './icon-512.png',
  './archive/index.json',
  './archive/2026.json',
  './archive/2026_players.json',
  './team_logos.json',
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then(cache =>
      // Use individual put() so a single 404 doesn't fail the entire install
      Promise.all(CORE_ASSETS.map(url =>
        fetch(url).then(r => r.ok ? cache.put(url, r.clone()) : null).catch(() => null)
      ))
    )
  );
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Network-first for data files (so updates land), cache-first for static assets.
// Anything under /archive/ is treated as data so future archived years
// auto-cache after first fetch.
function isDataURL(url) {
  return url.includes('players.json')
      || url.includes('insights.json')
      || url.includes('/archive/')
      || url.includes('team_logos.json');
}

self.addEventListener('fetch', (e) => {
  if (isDataURL(e.request.url)) {
    e.respondWith(
      fetch(e.request)
        .then(res => {
          if (res && res.ok) {
            const clone = res.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(e.request, clone));
          }
          return res;
        })
        .catch(() => caches.match(e.request))
    );
  } else {
    e.respondWith(
      caches.match(e.request).then(cached => cached || fetch(e.request))
    );
  }
});
