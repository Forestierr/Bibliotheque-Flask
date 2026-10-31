// sw.js
// Service Worker for PWA — livresenclasse.com

const CACHE_NAME = "livres-en-classe-v4";
const OFFLINE_URL = "/offline";

const STATIC_ASSETS = [
  "/offline",
  "/static/css/style.css",
  "/static/javascript/app.js",
  "/static/image/icons/web-app-manifest-192x192.png",
  "/static/image/icons/web-app-manifest-512x512.png",
  "/static/image/icons/apple-touch-icon.png",
  "/static/image/icons/favicon.svg",
  "/manifest.json"
];

// ─── Install : précache TOUT de façon garantie ────────────────────────────────
self.addEventListener("install", (event) => {
  console.log("[Service Worker] Installing v4...");
  // skipWaiting APRÈS le précache pour éviter les races
  event.waitUntil(
    caches.open(CACHE_NAME).then(async (cache) => {
      console.log("[Service Worker] Pre-caching shell...");
      // On cache chaque asset individuellement pour qu'une erreur ne bloque pas tout
      await Promise.allSettled(
        STATIC_ASSETS.map((url) =>
          fetch(url, { cache: "no-store" })
            .then((res) => {
              if (res.ok) return cache.put(url, res);
              console.warn("[SW] Could not cache:", url, res.status);
            })
            .catch((err) => console.warn("[SW] Fetch failed for:", url, err))
        )
      );
      console.log("[Service Worker] Pre-cache complete.");
    }).then(() => self.skipWaiting())
  );
});

// ─── Activate : nettoyage des anciens caches ───────────────────────────────────
self.addEventListener("activate", (event) => {
  console.log("[Service Worker] Activating v4...");
  event.waitUntil(
    caches.keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key !== CACHE_NAME)
            .map((key) => {
              console.log("[SW] Deleting old cache:", key);
              return caches.delete(key);
            })
        )
      )
      .then(() => self.clients.claim())
  );
});

// ─── Fetch : stratégies par type de requête ───────────────────────────────────
self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Ignorer non-GET et hors-scope
  if (request.method !== "GET") return;
  if (!url.protocol.startsWith("http")) return;

  // 1. Navigation HTML → Network-First avec fallback /offline
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => response)
        .catch(() =>
          caches.match(OFFLINE_URL).then((offline) =>
            offline ||
            new Response(
              "<h1>Vous êtes hors ligne</h1><p>Vérifiez votre connexion internet.</p>",
              { headers: { "Content-Type": "text/html; charset=utf-8" } }
            )
          )
        )
    );
    return;
  }

  // 2. Assets statiques → Stale-While-Revalidate
  const isStatic =
    url.pathname.startsWith("/static/") ||
    url.pathname === "/manifest.json" ||
    url.pathname === "/offline" ||
    url.pathname.startsWith("/favicon");

  if (isStatic) {
    event.respondWith(
      caches.open(CACHE_NAME).then((cache) =>
        cache.match(request).then((cached) => {
          const networkFetch = fetch(request)
            .then((res) => {
              if (res.ok) cache.put(request, res.clone());
              return res;
            })
            .catch(() => cached);
          return cached || networkFetch;
        })
      )
    );
    return;
  }

  // 3. Tout le reste → Network-Only (API, Stripe, hCaptcha, CDN)
});

// ─── Periodic Background Sync ─────────────────────────────────────────────────
self.addEventListener("periodicsync", (event) => {
  if (event.tag === "refresh-library") {
    // Le navigateur réveille le SW périodiquement pour rafraîchir le cache
    event.waitUntil(
      caches.open(CACHE_NAME).then(async (cache) => {
        // Rafraîchit les assets statiques en arrière-plan
        await Promise.allSettled(
          STATIC_ASSETS.map((url) =>
            fetch(url, { cache: "no-store" })
              .then((res) => { if (res.ok) return cache.put(url, res); })
              .catch(() => {})
          )
        );
        console.log("[SW] Periodic sync: cache refreshed.");
      })
    );
  }
});

// ─── Background Sync (one-shot) ───────────────────────────────────────────────
self.addEventListener("sync", (event) => {
  if (event.tag === "sync-network") {
    self.registration.showNotification("🌐 Connexion rétablie", {
      body: "Vous pouvez continuer à utiliser l'application normalement.",
      icon: "/static/image/icons/web-app-manifest-192x192.png"
    });
  }
});

// ─── Push Notifications ───────────────────────────────────────────────────────
self.addEventListener("push", (event) => {
  if (!event.data) return;
  const data = event.data.json();
  event.waitUntil(
    self.registration.showNotification(data.title || "Ma bibliothèque", {
      body: data.body || "",
      icon: "/static/image/icons/web-app-manifest-192x192.png",
      badge: "/static/image/icons/favicon-96x96.png",
      data: { url: data.url || "/" }
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = event.notification.data?.url || "/";
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if (client.url === targetUrl && "focus" in client) return client.focus();
      }
      if (clients.openWindow) return clients.openWindow(targetUrl);
    })
  );
});
