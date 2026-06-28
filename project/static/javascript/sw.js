// sw.js
// Service Worker for PWA

const CACHE_NAME = "livres-en-classe-v1";
const STATIC_ASSETS = [
  "/",
  "/static/css/style.css",
  "/static/javascript/app.js",
  "/static/image/favicon-32x32.png",
  "/static/image/favicon-512x512.png",
  "/static/image/screenshots/dashboard_2.webp",
  "/static/image/screenshots/livre_2.webp",
  "/static/image/screenshots/eleve_2.webp"
];

// Install event: Cache static assets
self.addEventListener("install", (event) => {
  console.log("[Service Worker] Installing...");
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log("[Service Worker] Caching static assets...");
      return cache.addAll(STATIC_ASSETS).catch((error) => {
        console.error("[Service Worker] Caching failed to cache:", error);
      });
    })
  );
});

// Activate event: Clean up old caches
self.addEventListener("activate", (event) => {
  console.log("[Service Worker] Activating...");
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    )
  );
});

// Fetch event: Serve from cache or fetch from network
self.addEventListener("fetch", (event) => {
  console.log("[Service Worker] Fetching...", event.request.url);
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      return cachedResponse || fetch(event.request);
    })
  );
});

self.addEventListener("sync", (event) => {
  if (event.tag === "sync-network") {
    self.registration.showNotification("🌐 Connexion rétablie", {
      body: "Vous pouvez continuer à utiliser l'application normalement.",
      icon: "/static/image/favicon-192x192.png"
    });
  }
});
