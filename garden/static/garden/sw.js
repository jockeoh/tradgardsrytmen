const CACHE = "tradgardsrytmen-v18-login";
const ASSETS = ["/static/garden/worklist.html", "/static/garden/worklist.css?v=m2-8-login", "/static/garden/offline-core.js?v=m2-8-login", "/static/garden/worklist.js?v=m2-8-login", "/static/garden/offline-session.js?v=m2-8-login", "/static/garden/app.css?v=20260926jobs1", "/static/garden/app.js?v=20261002login1", "/static/garden/images/garden-hero.jpg", "/static/garden/icons/icon.svg", "/static/garden/manifest.webmanifest"];
self.addEventListener("install", event => event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS))));
self.addEventListener("activate", event => event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith("tradgardsrytmen-") && k !== CACHE).map(k => caches.delete(k))))));
self.addEventListener("fetch", event => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  if (url.origin === self.location.origin && event.request.mode === "navigate" && (url.pathname === "/worklist/" || url.pathname === "/")) {
    event.respondWith(fetch(event.request).catch(() => caches.open(CACHE).then(c => c.match("/static/garden/worklist.html"))));
    return;
  }
  if (url.origin !== self.location.origin || !url.pathname.startsWith("/static/")) return;
  event.respondWith(caches.match(event.request).then(cached => cached || fetch(event.request).then(response => {
    if (response.ok) caches.open(CACHE).then(cache => cache.put(event.request, response.clone()));
    return response;
  })));
});
self.addEventListener("push", event => { const data = event.data ? event.data.json() : {}; event.waitUntil(self.registration.showNotification(data.title || "Trädgårdsrytmen", {body:data.body || "Något är dags i trädgården.", icon:"/static/garden/icons/icon-192.png", data:{url:data.url || "/"}})); });
self.addEventListener("notificationclick", event => { event.notification.close(); event.waitUntil(clients.openWindow(event.notification.data.url || "/")); });
