// sw.js
// Service Worker for PWA — livresenclasse.com

const CACHE_NAME = "livres-en-classe-v5";
const OFFLINE_URL = "/offline";

const STATIC_ASSETS = [
  "/offline",
  "/static/css/style.css",
  "/static/javascript/app.js",
  "/static/image/icons/favicon-96x96.png",
  "/static/image/icons/logo-w-512x512.png",
  "/static/image/icons/web-app-manifest-192x192.png",
  "/static/image/icons/web-app-manifest-512x512.png",
  "/static/image/icons/apple-touch-icon.png",
  "/static/image/icons/favicon.svg",
  "/manifest.json",
  "https://cdnjs.cloudflare.com/ajax/libs/bulma/1.0.4/css/bulma.min.css",
  "https://unpkg.com/htmx.org@2.0.4",
  "https://kit.fontawesome.com/222094ca6a.js"
];

// ─── Install : précache TOUT de façon garantie ────────────────────────────────
self.addEventListener("install", (event) => {
  console.log("[Service Worker] Installing v5...");
  event.waitUntil(
    caches.open(CACHE_NAME).then(async (cache) => {
      console.log("[Service Worker] Pre-caching shell & core dependencies...");
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
  console.log("[Service Worker] Activating v5...");
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

  // Ignorer non-GET et hors protocole HTTP(S)
  if (request.method !== "GET") return;
  if (!url.protocol.startsWith("http")) return;

  // 1. Dépendances CDN externes (Bulma, HTMX, FontAwesome) → Cache-First
  const isCDN =
    url.hostname === "cdnjs.cloudflare.com" ||
    url.hostname === "unpkg.com" ||
    url.hostname === "kit.fontawesome.com" ||
    url.hostname === "ka-f.fontawesome.com";

  if (isCDN) {
    event.respondWith(
      caches.open(CACHE_NAME).then((cache) =>
        cache.match(request).then((cached) => {
          if (cached) return cached;
          return fetch(request)
            .then((networkRes) => {
              if (networkRes && networkRes.status === 200) {
                cache.put(request, networkRes.clone());
              }
              return networkRes;
            })
            .catch(() => cached);
        })
      )
    );
    return;
  }

  // 2. Navigation HTML classique → Network-First avec fallback /offline
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

  // 3. Navigation HTMX (HX-Request) → Network-First avec fallback hors-ligne
  if (request.headers.get("HX-Request") === "true") {
    event.respondWith(
      fetch(request).catch(() =>
        caches.match(OFFLINE_URL).then((offline) =>
          offline ||
          new Response(
            "<div class='notification is-warning'>Vous êtes hors ligne. Vérifiez votre connexion.</div>",
            { headers: { "Content-Type": "text/html; charset=utf-8" } }
          )
        )
      )
    );
    return;
  }

  // 4. Assets statiques locaux → Stale-While-Revalidate
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

  // 5. Tout le reste → Network-Only (API, Stripe, hCaptcha)
});

// ─── Periodic Background Sync ─────────────────────────────────────────────────
self.addEventListener("periodicsync", (event) => {
  if (event.tag === "refresh-library") {
    event.waitUntil(
      caches.open(CACHE_NAME).then(async (cache) => {
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
