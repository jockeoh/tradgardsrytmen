const CACHE = "tradgardsrytmen-v2";
const ASSETS = ["/", "/static/garden/app.css", "/static/garden/task-detail.css", "/static/garden/work-rounds.css", "/static/garden/app.js", "/static/garden/manifest.webmanifest"];
self.addEventListener("install", event => event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS))));
self.addEventListener("activate", event => event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))));
self.addEventListener("fetch", event => {
  if (event.request.method !== "GET" || new URL(event.request.url).pathname.startsWith("/api/")) return;
  event.respondWith(fetch(event.request).then(response => { const copy = response.clone(); caches.open(CACHE).then(c => c.put(event.request, copy)); return response; }).catch(() => caches.match(event.request).then(r => r || caches.match("/"))));
});
self.addEventListener("push", event => { const data = event.data ? event.data.json() : {}; event.waitUntil(self.registration.showNotification(data.title || "Trädgårdsrytmen", {body:data.body || "Något är dags i trädgården.", icon:"/static/garden/icons/icon-192.png", data:{url:data.url || "/"}})); });
self.addEventListener("notificationclick", event => { event.notification.close(); event.waitUntil(clients.openWindow(event.notification.data.url || "/")); });
