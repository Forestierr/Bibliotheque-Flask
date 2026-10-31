// sw.js
// Service Worker for PWA — livresenclasse.com

const CACHE_NAME = "livres-en-classe-v3";
const OFFLINE_URL = "/offline";

const STATIC_ASSETS = [
  "/static/css/style.css",
  "/static/javascript/app.js",
  "/static/image/icons/web-app-manifest-192x192.png",
  "/static/image/icons/web-app-manifest-512x512.png",
  "/static/image/icons/apple-touch-icon.png",
  "/static/image/icons/favicon.svg",
  "/manifest.json"
];

// ─── Install : précache assets statiques + page offline ───────────────────────
self.addEventListener("install", (event) => {
  console.log("[Service Worker] Installing v3...");
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log("[Service Worker] Caching static assets...");
      // Cache assets statiques (erreurs non bloquantes)
      const staticPromise = cache.addAll(STATIC_ASSETS).catch((err) => {
        console.warn("[Service Worker] Partial cache failure:", err);
      });
      // Cache la page offline (critique)
      const offlinePromise = fetch(OFFLINE_URL)
        .then((res) => {
          if (res.ok) return cache.put(OFFLINE_URL, res);
        })
        .catch(() => {
          // Si /offline n'est pas encore dispo en dev, on ignore
          console.warn("[Service Worker] Could not cache offline page.");
        });
      return Promise.all([staticPromise, offlinePromise]);
    })
  );
});

// ─── Activate : nettoyage des anciens caches ───────────────────────────────────
self.addEventListener("activate", (event) => {
  console.log("[Service Worker] Activating v3...");
  event.waitUntil(
    caches.keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key !== CACHE_NAME)
            .map((key) => {
              console.log("[Service Worker] Deleting old cache:", key);
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

  // Ignorer les requêtes non-GET et les extensions hors-scope
  if (request.method !== "GET") return;
  if (!url.protocol.startsWith("http")) return;

  // 1. Navigation HTML → Network-First avec fallback page offline
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          // Mise à jour du cache sur succès réseau
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            // Ne pas cacher les pages authentifiées dynamiques
            const contentType = response.headers.get("content-type") || "";
            if (response.ok && contentType.includes("text/html")) {
              // On ne cache pas les pages HTML dynamiques pour respecter les sessions
            }
          });
          return response;
        })
        .catch(() => {
          // Réseau indisponible → page offline
          return caches.match(OFFLINE_URL).then((offline) => {
            return offline || new Response(
              "<h1>Vous êtes hors ligne</h1><p>Vérifiez votre connexion internet.</p>",
              { headers: { "Content-Type": "text/html; charset=utf-8" } }
            );
          });
        })
    );
    return;
  }

  // 2. Assets statiques (CSS, JS, images, fonts) → Stale-While-Revalidate
  const isStatic =
    url.pathname.startsWith("/static/") ||
    url.pathname === "/manifest.json" ||
    url.pathname.startsWith("/favicon");

  if (isStatic) {
    event.respondWith(
      caches.open(CACHE_NAME).then((cache) =>
        cache.match(request).then((cachedResponse) => {
          const fetchPromise = fetch(request)
            .then((networkResponse) => {
              if (networkResponse.ok) {
                cache.put(request, networkResponse.clone());
              }
              return networkResponse;
            })
            .catch(() => cachedResponse);
          // Retourne le cache immédiatement si disponible, sinon attend le réseau
          return cachedResponse || fetchPromise;
        })
      )
    );
    return;
  }

  // 3. Autres requêtes (API, CDN externe) → Network-Only
  // Pas de cache pour Stripe, hCaptcha, etc.
});

// ─── Background Sync ──────────────────────────────────────────────────────────
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
        if (client.url === targetUrl && "focus" in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) return clients.openWindow(targetUrl);
    })
  );
});
