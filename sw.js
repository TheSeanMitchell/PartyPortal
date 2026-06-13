/* Party Portal — service worker
   App-shell caching for offline support + faster repeat loads.
   Strategy: navigations & feed.json = network-first (fresh content),
   static assets = cache-first. */
var CACHE = 'party-portal-v1';
var SHELL = [
  './',
  'index.html',
  'about.html',
  'privacy.html',
  'contact.html',
  'offline.html',
  'favicon.svg',
  'favicon.ico',
  'apple-touch-icon.png',
  'icon-192.png',
  'icon-512.png',
  'manifest.webmanifest'
];

self.addEventListener('install', function(e){
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then(function(c){
    return Promise.all(SHELL.map(function(u){
      return c.add(u).catch(function(){ /* ignore individual failures */ });
    }));
  }));
});

self.addEventListener('activate', function(e){
  e.waitUntil(
    caches.keys().then(function(keys){
      return Promise.all(keys.map(function(k){ if(k!==CACHE) return caches.delete(k); }));
    }).then(function(){ return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function(e){
  var req = e.request;
  if (req.method !== 'GET') return;
  var url = new URL(req.url);

  // Don't touch cross-origin (YouTube embeds, fonts, news links) — let them pass through.
  if (url.origin !== self.location.origin) return;

  // Navigations → network first, fall back to cached index, then offline page.
  if (req.mode === 'navigate') {
    e.respondWith(
      fetch(req).then(function(res){
        var copy = res.clone();
        caches.open(CACHE).then(function(c){ c.put(req, copy); });
        return res;
      }).catch(function(){
        return caches.match(req).then(function(m){ return m || caches.match('index.html') || caches.match('offline.html'); });
      })
    );
    return;
  }

  // feed.json → network first (always want fresh news), fall back to cache.
  if (url.pathname.indexOf('feed.json') >= 0) {
    e.respondWith(
      fetch(req).then(function(res){
        var copy = res.clone();
        caches.open(CACHE).then(function(c){ c.put(req, copy); });
        return res;
      }).catch(function(){ return caches.match(req); })
    );
    return;
  }

  // Everything else (icons, manifest) → cache first, then network.
  e.respondWith(
    caches.match(req).then(function(m){
      return m || fetch(req).then(function(res){
        var copy = res.clone();
        caches.open(CACHE).then(function(c){ c.put(req, copy); });
        return res;
      });
    })
  );
});
