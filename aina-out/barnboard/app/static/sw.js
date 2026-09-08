/* Barnboard service worker — deliberately minimal.
 * Static assets: cache-first (they're fingerprint-stable enough for a farm app).
 * Navigations/API: network-first — live data must stay live; a tiny offline
 * page appears only when the network is truly gone. No background sync yet.
 */
const CACHE = "barnboard-v1";
const OFFLINE_HTML = `<!doctype html><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Barnboard — offline</title>
<body style="font-family:system-ui;display:grid;place-items:center;min-height:100vh;background:#f8f7f4;color:#1c1917">
<div style="text-align:center"><div style="font-size:48px">🐄</div>
<h2>You're offline</h2><p>Barnboard needs the farm network.<br>Your last-synced pages will load when you're back.</p></div>`;

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.put("/__offline", new Response(OFFLINE_HTML, {headers: {"Content-Type": "text/html"}}))));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(clients.claim());
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;             // never cache mutations
  if (url.pathname.startsWith("/static/")) {
    e.respondWith(
      caches.match(e.request).then((hit) => hit ||
        fetch(e.request).then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(e.request, copy));
          return res;
        })));
    return;
  }
  if (e.request.mode === "navigate") {
    e.respondWith(fetch(e.request).catch(() => caches.match("/__offline")));
  }
});
